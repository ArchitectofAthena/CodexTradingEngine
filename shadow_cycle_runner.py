"""Shadow cycle runner for EVE_Q++ receipt pipeline exercises.

The runner simulates one complete observation cycle without moving capital. It
emits a shadow-mode CycleReceipt, routes proof through an adapter, validates the
receipt, writes a receipt JSON file, and emits a non-authoritative
ProposalArtifact for the cross-repository membrane.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from eve_q.proposal_artifact import (
    UNKNOWN_COMMIT,
    build_proposal_artifact,
    validate_proposal_semantics,
    write_proposal_artifact,
)
from eveq_failsafe_receipt import (
    CycleReceipt,
    FailsafeConfig,
    ValidationResult,
    progressive_trust_increment_from_receipt,
    q18,
)
from proof_adapters import LocalFileProofAdapter, ProofAdapter, apply_proof_to_receipt


@dataclass(frozen=True)
class ShadowCycleRun:
    """Result bundle for a simulated shadow cycle."""

    receipt: CycleReceipt
    validation: ValidationResult
    receipt_path: Path
    proposal_artifact: Dict[str, Any]
    proposal_path: Path
    failsafe: FailsafeConfig


def score_candidate_route(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Score a candidate route using profit minus gas, slippage, and margin."""
    expected_profit = Decimal(str(candidate.get("expected_profit_eth", "0")))
    gas_cost = Decimal(str(candidate.get("gas_cost_eth", "0")))
    slippage = Decimal(str(candidate.get("slippage_eth", "0")))
    safety_margin = Decimal(str(candidate.get("safety_margin_eth", "0")))
    score = q18(expected_profit - gas_cost - slippage - safety_margin)
    scored = dict(candidate)
    scored["score_eth"] = score
    return scored


def default_candidate_routes() -> List[Dict[str, Any]]:
    """Return deterministic mock candidate routes for shadow-mode testing."""
    return [
        {
            "route": "mock-base-weth-usdc-weth",
            "chain": "base",
            "expected_profit_eth": Decimal("0.020000000000000000"),
            "gas_cost_eth": Decimal("0.005000000000000000"),
            "slippage_eth": Decimal("0.001000000000000000"),
            "safety_margin_eth": Decimal("0.002000000000000000"),
        },
        {
            "route": "mock-base-weth-dai-weth",
            "chain": "base",
            "expected_profit_eth": Decimal("0.012000000000000000"),
            "gas_cost_eth": Decimal("0.004500000000000000"),
            "slippage_eth": Decimal("0.001500000000000000"),
            "safety_margin_eth": Decimal("0.002000000000000000"),
        },
    ]


def build_shadow_receipt(
    *,
    cycle_id: Optional[str] = None,
    candidate_routes: Optional[List[Dict[str, Any]]] = None,
) -> CycleReceipt:
    """Build a fully populated shadow CycleReceipt from mock route data."""
    source_routes = candidate_routes or default_candidate_routes()
    routes = [score_candidate_route(route) for route in source_routes]
    selected = max(routes, key=lambda route: route["score_eth"])
    actual_profit = q18(selected["score_eth"])

    receipt = CycleReceipt.shadow(
        cycle_id=cycle_id or f"shadow-{uuid4().hex}",
        chain=str(selected["chain"]),
        selected_route=str(selected["route"]),
        optimizer_used="shadow-score-v0",
        candidate_routes=routes,
        expected_profit_eth=selected["expected_profit_eth"],
        gas_cost_eth=selected["gas_cost_eth"],
        slippage_eth=selected["slippage_eth"],
        safety_margin_eth=selected["safety_margin_eth"],
    )

    receipt.actual_profit_eth = actual_profit
    receipt.charity_due_eth = receipt.compute_charity_due()
    receipt.charity_distributed_eth = receipt.charity_due_eth
    receipt.charity_allocations = [
        {
            "recipient": "mock-charity-ledger",
            "amount_eth": receipt.charity_due_eth,
            "proof_type": "shadow-local-only",
        }
    ]
    receipt.tx_hashes = []
    receipt.liveness_valid = True
    receipt.execution_success = True
    receipt.charity_success = True
    receipt.ipfs_success = False
    receipt.ipfs_cid = None
    receipt.trust_increment_allowed = False
    return receipt.finalize()


def write_receipt(receipt: CycleReceipt, output_dir: Path) -> Path:
    """Write a receipt JSON document using the local proof adapter."""
    proof = LocalFileProofAdapter(output_dir).publish(receipt)
    apply_proof_to_receipt(receipt, proof)
    if proof.local_path is None:
        raise RuntimeError("local proof adapter did not return a receipt path")
    receipt_path = Path(proof.local_path)
    receipt_path.write_text(receipt.to_json(indent=2), encoding="utf-8")
    return receipt_path


def persist_receipt_snapshot(receipt: CycleReceipt, output_dir: Path | str) -> Path:
    """Persist a receipt snapshot without changing its proof metadata."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    receipt_path = path / f"{receipt.cycle_id}.json"
    receipt.local_log_path = str(receipt_path)
    receipt_path.write_text(receipt.to_json(indent=2), encoding="utf-8")
    return receipt_path


def run_shadow_cycle(
    *,
    output_dir: Path | str = "receipts",
    failsafe: Optional[FailsafeConfig] = None,
    cycle_id: Optional[str] = None,
    candidate_routes: Optional[List[Dict[str, Any]]] = None,
    proof_adapter: Optional[ProofAdapter] = None,
    producer_commit: str = UNKNOWN_COMMIT,
    impact_category: str = "unassigned_verified_impact",
) -> ShadowCycleRun:
    """Run one simulated shadow cycle through receipt and proposal gates."""
    failsafe_cfg = failsafe or FailsafeConfig()
    receipt = build_shadow_receipt(
        cycle_id=cycle_id,
        candidate_routes=candidate_routes,
    )
    adapter = proof_adapter or LocalFileProofAdapter(output_dir)
    proof = adapter.publish(receipt)
    apply_proof_to_receipt(receipt, proof)
    validation = progressive_trust_increment_from_receipt(
        failsafe_cfg,
        receipt,
        production_mode=False,
    )

    if proof.local_path is not None:
        receipt_path = Path(proof.local_path)
        receipt_path.write_text(receipt.to_json(indent=2), encoding="utf-8")
    else:
        receipt_path = persist_receipt_snapshot(receipt, output_dir)

    proposal_artifact = build_proposal_artifact(
        receipt,
        producer_commit=producer_commit,
        impact_category=impact_category,
    )
    semantic_findings = validate_proposal_semantics(proposal_artifact)
    if semantic_findings:
        joined = "; ".join(semantic_findings)
        raise RuntimeError(f"ProposalArtifact semantic validation failed: {joined}")

    proposal_path = write_proposal_artifact(
        proposal_artifact,
        Path(output_dir) / "proposal_artifacts",
    )

    return ShadowCycleRun(
        receipt=receipt,
        validation=validation,
        receipt_path=receipt_path,
        proposal_artifact=proposal_artifact,
        proposal_path=proposal_path,
        failsafe=failsafe_cfg,
    )


if __name__ == "__main__":
    run = run_shadow_cycle()
    print(f"Receipt path: {run.receipt_path}")
    print(f"Proposal path: {run.proposal_path}")
    print(f"Receipt valid: {run.validation.valid}")
    print(f"Trust increment allowed: {run.validation.trust_increment_allowed}")
    print(f"Proposal authority: {run.proposal_artifact['authority']}")
