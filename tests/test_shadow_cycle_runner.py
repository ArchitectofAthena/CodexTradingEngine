import json
from decimal import Decimal

from eveq_failsafe_receipt import FailsafeConfig
from proof_adapters import MockProofAdapter
from shadow_cycle_runner import (
    build_shadow_receipt,
    run_shadow_cycle,
    score_candidate_route,
)


def test_score_candidate_route_subtracts_costs_and_margin():
    route = {
        "expected_profit_eth": Decimal("0.020000000000000000"),
        "gas_cost_eth": Decimal("0.005000000000000000"),
        "slippage_eth": Decimal("0.001000000000000000"),
        "safety_margin_eth": Decimal("0.002000000000000000"),
    }

    scored = score_candidate_route(route)

    assert scored["score_eth"] == Decimal("0.012000000000000000")


def test_build_shadow_receipt_is_populated_but_not_proven_yet():
    receipt = build_shadow_receipt(cycle_id="shadow-test-cycle")

    assert receipt.mode == "shadow"
    assert receipt.liveness_valid is True
    assert receipt.execution_success is True
    assert receipt.charity_success is True
    assert receipt.ipfs_success is False
    assert receipt.ipfs_cid is None
    assert receipt.trust_increment_allowed is False


def test_run_shadow_cycle_writes_receipt_and_blocks_trust(tmp_path):
    failsafe = FailsafeConfig(ttl_hours=24.0, max_ttl_hours=48.0, trust_level=0.0)

    run = run_shadow_cycle(
        output_dir=tmp_path,
        failsafe=failsafe,
        cycle_id="shadow-test-cycle",
    )

    assert run.validation.valid is True
    assert run.validation.trust_increment_allowed is False
    assert any("shadow mode cannot gain trust" in item for item in run.validation.warnings)
    assert run.failsafe.ttl_hours == 24.0
    assert run.failsafe.trust_level == 0.0
    assert run.failsafe.consecutive_failures == 1
    assert run.receipt_path.exists()
    assert run.receipt.ipfs_cid is not None
    assert run.receipt.ipfs_cid.startswith("local:")

    payload = json.loads(run.receipt_path.read_text(encoding="utf-8"))
    assert payload["cycle_id"] == "shadow-test-cycle"
    assert payload["mode"] == "shadow"
    assert payload["candidate_routes"][0]["score_eth"] == "0.012000000000000000"
    assert payload["charity_allocations"][0]["amount_eth"] == "0.001800000000000000"


def test_run_shadow_cycle_can_use_mock_proof_adapter(tmp_path):
    run = run_shadow_cycle(
        output_dir=tmp_path,
        cycle_id="shadow-test-cycle",
        proof_adapter=MockProofAdapter(),
    )

    assert run.validation.valid is True
    assert run.validation.trust_increment_allowed is False
    assert run.receipt.ipfs_cid == "mock:shadow-test-cycle"
    assert run.receipt_path.exists()
