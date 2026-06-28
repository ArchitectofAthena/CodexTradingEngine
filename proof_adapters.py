"""Proof adapter layer for EVE_Q++ receipts.

Proof adapters separate *where a receipt is persisted* from *whether that proof
is eligible to expand trust*. Development proofs can support telemetry and audit
logs, but only production-eligible proofs should ever be considered for live
trust expansion.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol

from eveq_failsafe_receipt import CycleReceipt


@dataclass(frozen=True)
class ProofResult:
    """Result returned by a proof adapter."""

    success: bool
    proof_type: str
    cid: Optional[str] = None
    local_path: Optional[str] = None
    production_trust_eligible: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class ProofAdapter(Protocol):
    """Interface shared by all receipt proof adapters."""

    proof_type: str

    def publish(self, receipt: CycleReceipt) -> ProofResult:
        """Publish or persist a receipt and return proof metadata."""


class MockProofAdapter:
    """Development-only proof adapter.

    Mock proofs are useful for pipeline testing, but they are never production
    trust eligible.
    """

    proof_type = "mock"

    def publish(self, receipt: CycleReceipt) -> ProofResult:
        return ProofResult(
            success=True,
            proof_type=self.proof_type,
            cid=f"mock:{receipt.cycle_id}",
            production_trust_eligible=False,
            metadata={"reason": "mock proof is development-only"},
        )


class LocalFileProofAdapter:
    """Persist receipts to local JSON files.

    Local file proofs are durable enough for development logs and review, but
    they are not production trust eligible by default.
    """

    proof_type = "local_file"

    def __init__(self, output_dir: Path | str = "receipts") -> None:
        self.output_dir = Path(output_dir)

    def publish(self, receipt: CycleReceipt) -> ProofResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = self.output_dir / f"{receipt.cycle_id}.json"
        receipt.local_log_path = str(receipt_path)

        payload = receipt.to_json(indent=2)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        cid = f"local:{digest}"

        receipt.ipfs_cid = cid
        receipt.ipfs_success = True
        receipt_path.write_text(receipt.to_json(indent=2), encoding="utf-8")

        return ProofResult(
            success=True,
            proof_type=self.proof_type,
            cid=cid,
            local_path=str(receipt_path),
            production_trust_eligible=False,
            metadata={
                "sha256": digest,
                "reason": "local file proof is development/local-audit only",
            },
        )


class IPFSProofAdapter:
    """Future production proof adapter backed by an injected publisher.

    The adapter does not make network calls by itself. A caller must provide a
    publisher callable that accepts receipt JSON and returns a CID. This keeps
    the proof layer testable and prevents accidental mainnet or infrastructure
    side effects.
    """

    proof_type = "ipfs"

    def __init__(self, publisher: Callable[[str], str]) -> None:
        self.publisher = publisher

    def publish(self, receipt: CycleReceipt) -> ProofResult:
        try:
            cid = self.publisher(receipt.to_json(indent=2))
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ProofResult(
                success=False,
                proof_type=self.proof_type,
                production_trust_eligible=False,
                error=str(exc),
            )

        production_eligible = not cid.startswith(("mock:", "local:", "local-mock:"))
        return ProofResult(
            success=True,
            proof_type=self.proof_type,
            cid=cid,
            production_trust_eligible=production_eligible,
            metadata={"publisher": "injected"},
        )


def apply_proof_to_receipt(receipt: CycleReceipt, proof: ProofResult) -> CycleReceipt:
    """Apply proof metadata back onto a CycleReceipt."""
    receipt.ipfs_success = proof.success
    receipt.ipfs_cid = proof.cid
    receipt.local_log_path = proof.local_path or receipt.local_log_path

    if proof.error:
        receipt.errors.append(f"proof adapter error: {proof.error}")
    if proof.success and not proof.production_trust_eligible:
        receipt.warnings.append(f"{proof.proof_type} proof is not production trust eligible")
    return receipt
