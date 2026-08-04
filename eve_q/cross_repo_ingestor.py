"""Cross-repo receipt ingestion adapter for SpiralBloom OS integration.

The adapter validates bounded receipt files before copying them into a separate
SpiralBloom-facing directory. It does not grant execution or capital authority.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp

SAFE_RECEIPT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DEFAULT_MAX_RECEIPT_BYTES = 1_048_576


def utc_now_iso() -> str:
    """Return an offset-aware UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ReceiptIngestionConfig:
    """Configuration for bounded cross-repository receipt ingestion."""

    source_dir: Path
    target_dir: Path
    validate_merkle_proofs: bool = True
    require_production_eligible: bool = False
    governance_gate_url: str | None = None
    shadow_mode: bool = True
    max_receipt_bytes: int = DEFAULT_MAX_RECEIPT_BYTES

    def __post_init__(self) -> None:
        if not 1 <= self.max_receipt_bytes <= 10_485_760:
            raise ValueError("max_receipt_bytes must be between 1 and 10485760")
        if self.governance_gate_url is not None:
            parsed = urlparse(self.governance_gate_url)
            if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
                raise ValueError(
                    "governance_gate_url must be an explicit loopback HTTP endpoint"
                )
            if parsed.username or parsed.password:
                raise ValueError("governance_gate_url may not contain credentials")


@dataclass
class ReceiptIngestionResult:
    """Result of one receipt ingestion attempt."""

    success: bool
    receipt_id: str
    source_path: str | None = None
    target_path: str | None = None
    validation_errors: list[str] = field(default_factory=list)
    telemetry_event_emitted: bool = False
    governance_gate_queried: bool = False
    governance_gate_approved: bool | None = None
    timestamp: str = field(default_factory=utc_now_iso)


class ReceiptValidator:
    """Validate receipt structure, bounded identifiers, and proof bindings."""

    def __init__(self, config: ReceiptIngestionConfig) -> None:
        self.config = config

    def validate_receipt_json(self, receipt_dict: dict[str, Any]) -> list[str]:
        """Return validation errors for the receipt payload."""

        errors: list[str] = []
        required = [
            "cycle_id",
            "mode",
            "chain",
            "optimizer_used",
            "proof_type",
        ]
        for required_field in required:
            if required_field not in receipt_dict:
                errors.append(f"Missing required field: {required_field}")

        cycle_id = receipt_dict.get("cycle_id")
        if not isinstance(cycle_id, str) or not SAFE_RECEIPT_ID.fullmatch(cycle_id):
            errors.append(
                "cycle_id must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
            )

        valid_modes = {"shadow", "dry_run", "paper", "simulation", "live"}
        if receipt_dict.get("mode") not in valid_modes:
            errors.append(
                f"Invalid mode: {receipt_dict.get('mode')}. Must be one of {valid_modes}"
            )

        if self.config.require_production_eligible and not receipt_dict.get(
            "proof_production_trust_eligible", False
        ):
            errors.append("Proof is not production-eligible (config requires production)")

        try:
            actual_profit = Decimal(str(receipt_dict.get("actual_profit_eth", 0)))
            charity_due = Decimal(str(receipt_dict.get("charity_due_eth", 0)))
            expected_charity = actual_profit * Decimal("0.15")
            if actual_profit > 0 and abs(charity_due - expected_charity) > Decimal(
                "0.0001"
            ):
                errors.append(
                    f"Charity mismatch: expected {expected_charity}, got {charity_due}"
                )
        except (ValueError, TypeError, ArithmeticError) as exc:
            errors.append(f"Invalid profit/charity values: {exc}")

        if receipt_dict.get("execution_success") and not receipt_dict.get(
            "charity_success", False
        ):
            errors.append(
                "Execution succeeded but charity distribution failed (unsafe state)"
            )

        return errors

    def validate_merkle_proof(self, receipt_dict: dict[str, Any]) -> list[str]:
        """Validate the supplied Merkle proof envelope and root binding.

        The repository does not define a canonical path-folding algorithm for this
        legacy envelope, so this validator verifies field shape and the declared
        root binding. It fails closed on partial, misspelled, or bypass-sentinel
        proof data instead of silently skipping the proof path.
        """

        if not self.config.validate_merkle_proofs:
            return []

        errors: list[str] = []
        if "merkle_proo" in receipt_dict:
            errors.append("Unsupported field 'merkle_proo'; use 'merkle_proof'")

        merkle_root = receipt_dict.get("merkle_root")
        merkle_proof = receipt_dict.get("merkle_proof")

        if merkle_root is None and merkle_proof is None:
            return errors

        if merkle_root is None:
            errors.append("Merkle proof supplied without merkle_root")
        elif not isinstance(merkle_root, str) or not merkle_root:
            errors.append("merkle_root must be a non-empty string")
        elif merkle_root == "skip_verification":
            errors.append("Merkle verification bypass sentinel is forbidden")

        if merkle_proof is None:
            errors.append("merkle_root supplied without merkle_proof")
            return errors
        if not isinstance(merkle_proof, dict):
            errors.append("Merkle proof must be a dict")
            return errors

        required_proof_fields = ["leaf_hash", "path", "indices", "root_hash"]
        for proof_field in required_proof_fields:
            if proof_field not in merkle_proof:
                errors.append(f"Merkle proof missing field: {proof_field}")

        leaf_hash = merkle_proof.get("leaf_hash")
        root_hash = merkle_proof.get("root_hash")
        path = merkle_proof.get("path")
        indices = merkle_proof.get("indices")

        if leaf_hash is not None and not isinstance(leaf_hash, str):
            errors.append("Merkle proof leaf_hash must be a string")
        if root_hash is not None and not isinstance(root_hash, str):
            errors.append("Merkle proof root_hash must be a string")
        if path is not None and (
            not isinstance(path, list)
            or not all(isinstance(item, str) for item in path)
        ):
            errors.append("Merkle proof path must be a list of strings")
        if indices is not None and (
            not isinstance(indices, list)
            or not all(index in (0, 1) for index in indices)
        ):
            errors.append("Merkle proof indices must be a list containing only 0 or 1")
        if isinstance(path, list) and isinstance(indices, list) and len(path) != len(
            indices
        ):
            errors.append("Merkle proof path and indices must have equal length")

        if (
            isinstance(merkle_root, str)
            and merkle_root
            and isinstance(root_hash, str)
            and root_hash != merkle_root
        ):
            errors.append(
                f"Merkle root mismatch: proof has {root_hash}, receipt has {merkle_root}"
            )

        return errors


class CrossRepoReceiptIngestor:
    """Ingest validated receipt files into a bounded target directory."""

    def __init__(self, config: ReceiptIngestionConfig) -> None:
        self.config = config
        self.validator = ReceiptValidator(config)
        self.config.target_dir.mkdir(parents=True, exist_ok=True)

    def ingest_receipt_file(self, receipt_path: Path) -> ReceiptIngestionResult:
        """Ingest one regular, bounded JSON receipt file."""

        result = ReceiptIngestionResult(
            success=False,
            receipt_id="unknown",
            source_path=str(receipt_path),
        )

        try:
            if receipt_path.is_symlink() or not receipt_path.is_file():
                result.validation_errors = ["Receipt path must be a regular non-symlink file"]
                return result
            if receipt_path.stat().st_size > self.config.max_receipt_bytes:
                result.validation_errors = [
                    f"Receipt exceeds {self.config.max_receipt_bytes} bytes"
                ]
                return result

            loaded = json.loads(receipt_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                result.validation_errors = ["Receipt JSON root must be an object"]
                return result
            receipt_dict: dict[str, Any] = loaded
            cycle_id = receipt_dict.get("cycle_id")
            if isinstance(cycle_id, str):
                result.receipt_id = cycle_id

            errors = self.validator.validate_receipt_json(receipt_dict)
            errors.extend(self.validator.validate_merkle_proof(receipt_dict))
            if errors:
                result.validation_errors = errors
                return result

            target_path = self.config.target_dir / f"{result.receipt_id}_ingested.json"
            receipt_dict["spiralbloom_ingested_at"] = utc_now_iso()
            receipt_dict["spiralbloom_source_path"] = str(receipt_path)
            target_path.write_text(
                json.dumps(receipt_dict, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            result.target_path = str(target_path)

            if self.config.governance_gate_url and not self.config.shadow_mode:
                result.governance_gate_queried = True
                result.governance_gate_approved = self._query_governance_gate(
                    receipt_dict
                )
                if result.governance_gate_approved is not True:
                    target_path.unlink(missing_ok=True)
                    result.target_path = None
                    result.validation_errors = ["Governance gate did not approve receipt"]
                    return result

            result.telemetry_event_emitted = True
            result.success = True
        except json.JSONDecodeError as exc:
            result.validation_errors = [f"Invalid JSON: {exc}"]
        except (OSError, ValueError, TypeError) as exc:
            result.validation_errors = [f"Receipt ingestion failed: {exc}"]

        return result

    def ingest_batch(self) -> list[ReceiptIngestionResult]:
        """Ingest all top-level JSON files from the configured source directory."""

        if not self.config.source_dir.exists():
            return []
        return [
            self.ingest_receipt_file(receipt_file)
            for receipt_file in sorted(self.config.source_dir.glob("*.json"))
        ]

    def _query_governance_gate(self, receipt_dict: dict[str, Any]) -> bool:
        """Query the configured loopback governance gate."""

        if not self.config.governance_gate_url:
            return True

        governance_request = {
            "request_id": f"gov-{receipt_dict.get('cycle_id')}",
            "timestamp": utc_now_iso(),
            "eve_phase": "receipt_post_execution",
            "proposal": {
                "proposal_id": receipt_dict.get("cycle_id"),
                "action_type": "receipt_validation",
                "mode": receipt_dict.get("mode", "shadow"),
            },
            "evidence": {
                "execution_success": receipt_dict.get("execution_success", False),
                "charity_success": receipt_dict.get("charity_success", False),
                "ipfs_success": receipt_dict.get("ipfs_success", False),
            },
        }

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self._post_governance_request(governance_request)
            )
        finally:
            loop.close()

    async def _post_governance_request(self, request: dict[str, Any]) -> bool:
        """POST a bounded validation request to the loopback governance gate."""

        if not self.config.governance_gate_url:
            return True
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.config.governance_gate_url,
                    json=request,
                    allow_redirects=False,
                ) as response:
                    if response.status != 200:
                        return False
                    data = await response.json()
                    return data.get("approved") is True
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError):
            return False

    def generate_ingestion_report(
        self, results: list[ReceiptIngestionResult]
    ) -> str:
        """Generate a human-readable ingestion report."""

        lines = [
            "# Cross-Repo Receipt Ingestion Report",
            f"Generated: {utc_now_iso()}",
            f"Shadow Mode: {self.config.shadow_mode}",
            "",
            "## Summary",
            f"Total receipts: {len(results)}",
            f"Successful: {sum(1 for result in results if result.success)}",
            f"Failed: {sum(1 for result in results if not result.success)}",
            "",
            "## Details",
        ]

        for result in results:
            lines.append(f"\n### {result.receipt_id}")
            lines.append(f"- Status: {'SUCCESS' if result.success else 'FAILED'}")
            lines.append(f"- Source: {result.source_path}")
            if result.target_path:
                lines.append(f"- Target: {result.target_path}")
            if result.validation_errors:
                lines.append("- Errors:")
                lines.extend(f"  - {error}" for error in result.validation_errors)
            if result.governance_gate_queried:
                lines.append(
                    f"- Governance gate approved: {result.governance_gate_approved}"
                )
            if result.telemetry_event_emitted:
                lines.append("- Telemetry: event emitted")

        return "\n".join(lines)
