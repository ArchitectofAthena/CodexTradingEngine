from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from eveq_failsafe_receipt import CHARITY_RATE, CycleReceipt


CONTRACT_VERSION = "eve_q_cross_repo_v0.1"
PRODUCER_REPOSITORY = "ArchitectofAthena/CodexTradingEngine"
DEFAULT_TTL_SECONDS = 86_400
UNKNOWN_COMMIT = "0" * 40
PROHIBITED_ACTIONS = [
    "wallet_access",
    "signing",
    "order_submission",
    "transaction_construction",
    "transaction_broadcast",
    "capital_movement",
    "self_promotion",
]


class ProposalArtifactError(RuntimeError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    if isinstance(value, bytes):
        data = value
    else:
        data = canonical_json_bytes(value)
    return hashlib.sha256(data).hexdigest()


def parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_proposal_artifact(
    receipt: CycleReceipt,
    *,
    producer_commit: str = UNKNOWN_COMMIT,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    impact_category: str = "unassigned_verified_impact",
) -> dict[str, Any]:
    if len(producer_commit) != 40:
        raise ProposalArtifactError("producer_commit must be a 40-character commit SHA")
    if ttl_seconds < 1 or ttl_seconds > 172_800:
        raise ProposalArtifactError("ttl_seconds must be between 1 and 172800")
    if receipt.mode not in {"shadow", "simulation", "paper", "dry_run"}:
        raise ProposalArtifactError("ProposalArtifact builder only accepts simulation-class receipts")

    issued_at = parse_datetime(receipt.created_at)
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    receipt_document = receipt.to_dict()
    receipt_sha256 = sha256_hex(receipt_document)
    candidate_routes_sha256 = sha256_hex(receipt_document.get("candidate_routes", []))

    proposal_seed = {
        "contract_version": CONTRACT_VERSION,
        "cycle_id": receipt.cycle_id,
        "receipt_sha256": receipt_sha256,
        "producer_commit": producer_commit,
    }
    artifact_id = sha256_hex(proposal_seed)

    passed = bool(receipt.execution_success and not receipt.errors)
    simulation_status = "passed" if passed else "failed"
    charity_enabled = str(receipt.charity_due_eth) != "0E-18" and receipt.charity_due_eth > 0

    return {
        "artifact_type": "ProposalArtifact",
        "contract_version": CONTRACT_VERSION,
        "artifact_id": artifact_id,
        "created_at": iso_z(issued_at),
        "producer": {
            "repository": PRODUCER_REPOSITORY,
            "component": "shadow_cycle_runner.proposal_adapter_v0_1",
            "commit_sha": producer_commit,
        },
        "scope": {
            "domain": "market_research",
            "environment": "shadow",
            "action_class": "propose",
        },
        "ttl": {
            "issued_at": iso_z(issued_at),
            "expires_at": iso_z(expires_at),
            "ttl_seconds": ttl_seconds,
        },
        "proposal_id": f"proposal:{receipt.cycle_id}",
        "bounded_inputs": [
            {
                "source_id": f"candidate-routes:{receipt.cycle_id}",
                "source_kind": "market_snapshot",
                "content_sha256": candidate_routes_sha256,
                "observed_at": iso_z(issued_at),
            }
        ],
        "assumptions": [
            "candidate routes are deterministic mock observations",
            "no live liquidity, wallet, signing, submission, or broadcast surface is present",
            "shadow results cannot establish production trust or execution authority",
        ],
        "simulation_outputs": [
            {
                "run_id": receipt.cycle_id,
                "receipt_sha256": receipt_sha256,
                "status": simulation_status,
            }
        ],
        "risk_envelope": {
            "max_notional_usd": 0.0,
            "max_loss_usd": 0.0,
            "slippage_bps": 0.0,
            "confidence": 0.5 if passed else 0.0,
            "known_failure_modes": [
                "mock routes do not establish executable liquidity",
                "ETH-denominated simulation values are not converted to live USD notional",
                "stale observations must be rejected after TTL expiry",
            ],
        },
        "charity_allocation_candidate": {
            "enabled": charity_enabled,
            "fraction": float(CHARITY_RATE),
            "impact_category": impact_category,
            "verified_impact_required": True,
        },
        "prohibited_actions": list(PROHIBITED_ACTIONS),
        "authority": False,
        "human_promotion_required": True,
        "autonomous_capital_movement": False,
    }


def validate_proposal_semantics(
    artifact: dict[str, Any],
    *,
    now: datetime | None = None,
) -> list[str]:
    findings: list[str] = []
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    try:
        issued_at = parse_datetime(artifact["ttl"]["issued_at"])
        expires_at = parse_datetime(artifact["ttl"]["expires_at"])
        ttl_seconds = int(artifact["ttl"]["ttl_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        return [f"invalid TTL structure: {exc}"]

    if expires_at <= issued_at:
        findings.append("TTL expiry must be later than issue time")
    if int((expires_at - issued_at).total_seconds()) != ttl_seconds:
        findings.append("TTL duration does not match ttl_seconds")
    if expires_at <= current:
        findings.append("proposal TTL is stale")

    prohibited = set(artifact.get("prohibited_actions", []))
    for required in ("capital_movement", "self_promotion"):
        if required not in prohibited:
            findings.append(f"missing prohibited action: {required}")

    if artifact.get("authority") is not False:
        findings.append("proposal authority must be false")
    if artifact.get("human_promotion_required") is not True:
        findings.append("human promotion must be required")
    if artifact.get("autonomous_capital_movement") is not False:
        findings.append("autonomous capital movement must be false")

    bounded_inputs = artifact.get("bounded_inputs")
    if not isinstance(bounded_inputs, list) or not bounded_inputs:
        findings.append("bounded input provenance is required")
    else:
        for index, source in enumerate(bounded_inputs):
            if not source.get("content_sha256"):
                findings.append(f"bounded input {index} is missing content_sha256")

    return findings


def write_proposal_artifact(artifact: dict[str, Any], output_dir: Path | str) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    proposal_id = artifact["proposal_id"].replace(":", "-")
    output_path = path / f"{proposal_id}.json"
    output_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path
