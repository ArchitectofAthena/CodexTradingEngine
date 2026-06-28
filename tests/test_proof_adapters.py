from decimal import Decimal

from eveq_failsafe_receipt import CycleReceipt
from proof_adapters import (
    IPFSProofAdapter,
    LocalFileProofAdapter,
    MockProofAdapter,
    apply_proof_to_receipt,
)


def make_receipt() -> CycleReceipt:
    receipt = CycleReceipt(
        cycle_id="proof-test-cycle",
        mode="shadow",
        chain="base",
        selected_route="mock-route",
        optimizer_used="test-optimizer",
        actual_profit_eth=Decimal("0.010000000000000000"),
        charity_due_eth=Decimal("0.001500000000000000"),
        charity_distributed_eth=Decimal("0.001500000000000000"),
        charity_allocations=[{"recipient": "test", "amount_eth": "0.0015"}],
        liveness_valid=True,
        execution_success=True,
        charity_success=True,
    )
    return receipt.finalize()


def test_mock_proof_is_never_production_trust_eligible():
    receipt = make_receipt()

    proof = MockProofAdapter().publish(receipt)
    apply_proof_to_receipt(receipt, proof)

    assert proof.success is True
    assert proof.cid == "mock:proof-test-cycle"
    assert proof.production_trust_eligible is False
    assert receipt.ipfs_success is True
    assert receipt.ipfs_cid == "mock:proof-test-cycle"
    assert any("not production trust eligible" in item for item in receipt.warnings)


def test_local_file_proof_writes_receipt_and_is_not_production_trust_eligible(tmp_path):
    receipt = make_receipt()

    proof = LocalFileProofAdapter(tmp_path).publish(receipt)
    apply_proof_to_receipt(receipt, proof)

    assert proof.success is True
    assert proof.cid is not None
    assert proof.cid.startswith("local:")
    assert proof.local_path is not None
    assert proof.production_trust_eligible is False
    assert receipt.ipfs_success is True
    assert receipt.ipfs_cid.startswith("local:")
    assert receipt.local_log_path == proof.local_path


def test_ipfs_proof_adapter_uses_injected_publisher():
    receipt = make_receipt()

    proof = IPFSProofAdapter(lambda payload: "bafyProductionProofCid").publish(receipt)
    apply_proof_to_receipt(receipt, proof)

    assert proof.success is True
    assert proof.cid == "bafyProductionProofCid"
    assert proof.production_trust_eligible is True
    assert receipt.ipfs_cid == "bafyProductionProofCid"


def test_ipfs_proof_adapter_rejects_mock_like_cids_for_production_trust():
    receipt = make_receipt()

    proof = IPFSProofAdapter(lambda payload: "mock:not-real").publish(receipt)

    assert proof.success is True
    assert proof.production_trust_eligible is False
