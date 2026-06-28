"""Shadow cycle runner for EVE_Q++ receipt pipeline exercises.

The runner simulates one complete observation cycle without moving capital. It
emits a shadow-mode CycleReceipt, validates it, writes a receipt JSON file, and
confirms that shadow cycles can learn/log without expanding trust.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from eveq_failsafe_receipt import (
    CycleReceipt,
    FailsafeConfig,
    ValidationResult,
    progressive_trust_increment_from_receipt,
    q18,
)


@dataclass(frozen=True)
class ShadowCycleRun:
    """Result bundle for a simulated shadow cycle."""

    receipt: CycleReceipt
    validation: ValidationResult
    receipt_path: Path
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
    routes = [score_candidate_route(route) for route in candidate_routes or default_candidate_routes()]
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
    receipt.ipfs_cid = f"mock:{receipt.cycle_id}"
    receipt.local_log_path = None
    receipt.tx_hashes = []
    receipt.liveness_valid = True
    receipt.execution_success = True
    receipt.charity_success = True
    receipt.ipfs_success = True
    receipt.trust_increment_allowed = False
    return receipt.finalize()


def write_receipt(receipt: CycleReceipt, output_dir: Path) -> Path:
    """Write a receipt JSON document and return the resulting path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / f"{receipt.cycle_id}.json"
    receipt.local_log_path = str(receipt_path)
    receipt_path.write_text(receipt.to_json(indent=2), encoding="utf-8")
    return receipt_path


def run_shadow_cycle(
    *,
    output_dir: Path | str = "receipts",
    failsafe: Optional[FailsafeConfig] = None,
    cycle_id: Optional[str] = None,
    candidate_routes: Optional[List[Dict[str, Any]]] = None,
) -> ShadowCycleRun:
    """Run one simulated shadow cycle through the receipt validation gate."""
    failsafe_cfg = failsafe or FailsafeConfig()
    receipt = build_shadow_receipt(cycle_id=cycle_id, candidate_routes=candidate_routes)
    validation = progressive_trust_increment_from_receipt(
        failsafe_cfg,
        receipt,
        production_mode=False,
    )
    receipt_path = write_receipt(receipt, Path(output_dir))
    return ShadowCycleRun(
        receipt=receipt,
        validation=validation,
        receipt_path=receipt_path,
        failsafe=failsafe_cfg,
    )


if __name__ == "__main__":
    run = run_shadow_cycle()
    print(f"Receipt path: {run.receipt_path}")
    print(f"Receipt valid: {run.validation.valid}")
    print(f"Trust increment allowed: {run.validation.trust_increment_allowed}")
