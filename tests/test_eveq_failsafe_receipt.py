from decimal import Decimal
import json

from eveq_failsafe_receipt import (
    CycleReceipt,
    FailsafeConfig,
    progressive_trust_increment_from_receipt,
    validate_receipt,
)


def make_valid_receipt():
    return CycleReceipt(
        cycle_id="cycle-001",
        mode="live",
        chain="base",
        selected_route="route-a",
        optimizer_used="classical",
        actual_profit_eth=Decimal("1.0"),
        charity_due_eth=Decimal("0.15"),
        charity_distributed_eth=Decimal("0.15"),
        charity_allocations=[{"name": "test", "amount_eth": "0.15"}],
        ipfs_cid="bafyRealProofCid",
        tx_hashes=["0xabc"],
        liveness_valid=True,
        execution_success=True,
        charity_success=True,
        ipfs_success=True,
    )


def test_valid_receipt_allows_trust_increment():
    cfg = FailsafeConfig(ttl_hours=24.0, max_ttl_hours=48.0, trust_level=0.0)
    result = progressive_trust_increment_from_receipt(cfg, make_valid_receipt())
    assert result.trust_increment_allowed is True
    assert cfg.ttl_hours == 25.0
    assert cfg.trust_level == 0.05


def test_shadow_receipt_does_not_increment_trust():
    cfg = FailsafeConfig(ttl_hours=24.0, max_ttl_hours=48.0, trust_level=0.0)
    receipt = CycleReceipt.shadow(
        cycle_id="shadow-001",
        chain="base",
        selected_route="route-a",
        optimizer_used="classical",
        expected_profit_eth=Decimal("1.0"),
    )
    result = progressive_trust_increment_from_receipt(cfg, receipt)
    assert result.trust_increment_allowed is False
    assert cfg.ttl_hours == 24.0
    assert cfg.trust_level == 0.0


def test_mock_proof_blocks_production_trust():
    receipt = make_valid_receipt()
    receipt.ipfs_cid = "mock:test-proof"
    result = validate_receipt(receipt, production_mode=True)
    assert result.trust_increment_allowed is False
    assert any("non-production proof" in error for error in result.errors)


def test_local_proof_blocks_production_trust():
    receipt = make_valid_receipt()
    receipt.ipfs_cid = "local:test-proof"
    result = validate_receipt(receipt, production_mode=True)
    assert result.trust_increment_allowed is False
    assert any("non-production proof" in error for error in result.errors)


def test_claimed_trust_flag_cannot_bypass_gates():
    receipt = make_valid_receipt()
    receipt.liveness_valid = False
    receipt.trust_increment_allowed = True
    result = validate_receipt(receipt)
    assert result.trust_increment_allowed is False
    assert any("proof gates failed" in error for error in result.errors)


def test_receipt_to_json_serializes_nested_decimals():
    receipt = make_valid_receipt()
    receipt.candidate_routes = [
        {
            "route": "route-a",
            "expected_profit_eth": Decimal("0.25"),
            "legs": [{"gas_eth": Decimal("0.01")}],
        }
    ]
    receipt.charity_allocations = [{"name": "test", "amount_eth": Decimal("0.15")}]

    payload = json.loads(receipt.to_json())

    assert payload["candidate_routes"][0]["expected_profit_eth"] == "0.25"
    assert payload["candidate_routes"][0]["legs"][0]["gas_eth"] == "0.01"
    assert payload["charity_allocations"][0]["amount_eth"] == "0.15"
