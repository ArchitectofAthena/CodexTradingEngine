import pytest

from eve_q.immutable_receipts import (
    InMemoryIpfsWriter,
    JsonlReceiptLedger,
    ReceiptSealError,
    build_receipt_envelope,
    canonical_json_bytes,
    envelope_digest,
    mark_action_complete,
    seal_receipt,
)


def trade_receipt():
    return {
        "receipt_type": "TradeReceipt",
        "receipt_version": "0.1.0",
        "environment": "paper",
        "strategy_id": "eve_q.shadow_v0",
        "order_intent_hash": "sha256:intent",
        "risk_report_hash": "sha256:risk",
        "human_approval_hash": "sha256:approval",
        "execution_result_hash": "sha256:execution",
        "profit_loss": "0.00",
        "charity_allocation_rule": "15_percent_positive_profit",
    }


def charity_receipt(source_trade_cid):
    return {
        "receipt_type": "CharityTxReceipt",
        "receipt_version": "0.1.0",
        "environment": "paper",
        "source_trade_receipt_cid": source_trade_cid,
        "charity_policy_id": "charity_geodesic_v0",
        "recipient_id_hash": "sha256:recipient",
        "amount": "0.00",
        "currency": "USD",
        "tx_ref_hash": "sha256:txref",
        "verification_status": "simulated",
    }


def test_canonical_json_bytes_are_deterministic():
    first = canonical_json_bytes({"b": 2, "a": 1})
    second = canonical_json_bytes({"a": 1, "b": 2})

    assert first == second


def test_receipt_envelope_preserves_non_authority_flags():
    envelope = build_receipt_envelope(trade_receipt())

    assert envelope["execution_authority"] == "none"
    assert envelope["artifact_is_command"] is False
    assert envelope["may_execute"] is False
    assert envelope["may_move_capital"] is False
    assert envelope["human_promotion_required"] is True
    assert envelope["local_sha256"] == envelope_digest(envelope)


def test_trade_receipt_seals_to_pinned_verified_cid(tmp_path):
    ipfs = InMemoryIpfsWriter()
    ledger = JsonlReceiptLedger(tmp_path / "receipt_ledger.jsonl")

    result = seal_receipt(
        trade_receipt(),
        previous_cid=None,
        ipfs=ipfs,
        ledger=ledger,
    )

    assert result["status"] == "IPFS_PINNED_VERIFIED"
    assert result["cid"].startswith("mock-ipfs-")
    assert ipfs.is_pinned(result["cid"])

    events = ledger.read_events()
    assert len(events) == 1
    assert events[0]["event_type"] == "receipt_pinned"
    assert events[0]["receipt_type"] == "TradeReceipt"
    assert events[0]["cid"] == result["cid"]


def test_charity_receipt_links_to_trade_receipt_cid(tmp_path):
    ipfs = InMemoryIpfsWriter()
    ledger = JsonlReceiptLedger(tmp_path / "receipt_ledger.jsonl")

    trade = seal_receipt(
        trade_receipt(),
        previous_cid=None,
        ipfs=ipfs,
        ledger=ledger,
    )
    charity = seal_receipt(
        charity_receipt(trade["cid"]),
        previous_cid=trade["cid"],
        ipfs=ipfs,
        ledger=ledger,
    )

    assert charity["envelope"]["previous_cid"] == trade["cid"]
    assert charity["envelope"]["receipt"]["source_trade_receipt_cid"]
    assert charity["cid"] != trade["cid"]

    events = ledger.read_events()
    assert len(events) == 2
    assert events[1]["previous_cid"] == trade["cid"]


def test_forbidden_secret_fields_are_rejected_before_sealing(tmp_path):
    ipfs = InMemoryIpfsWriter()
    ledger = JsonlReceiptLedger(tmp_path / "receipt_ledger.jsonl")
    receipt = trade_receipt()
    receipt["wallet_private_key"] = "do-not-store"

    with pytest.raises(ReceiptSealError):
        seal_receipt(
            receipt,
            previous_cid=None,
            ipfs=ipfs,
            ledger=ledger,
        )

    assert ledger.read_events() == []


def test_nested_forbidden_command_field_is_rejected(tmp_path):
    ipfs = InMemoryIpfsWriter()
    ledger = JsonlReceiptLedger(tmp_path / "receipt_ledger.jsonl")
    receipt = trade_receipt()
    receipt["metadata"] = {
        "command": "do-not-run",
    }

    with pytest.raises(ReceiptSealError):
        seal_receipt(
            receipt,
            previous_cid=None,
            ipfs=ipfs,
            ledger=ledger,
        )

    assert ledger.read_events() == []


def test_corrupt_ipfs_readback_fails_verification(tmp_path):
    class CorruptIpfsWriter(InMemoryIpfsWriter):
        def cat(self, cid):
            return b"corrupt"

    ipfs = CorruptIpfsWriter()
    ledger = JsonlReceiptLedger(tmp_path / "receipt_ledger.jsonl")

    with pytest.raises(ReceiptSealError):
        seal_receipt(
            trade_receipt(),
            previous_cid=None,
            ipfs=ipfs,
            ledger=ledger,
        )

    assert ledger.read_events() == []


def test_trade_cannot_settle_without_receipt_cid():
    with pytest.raises(ReceiptSealError):
        mark_action_complete(
            "trade",
            receipt_cid=None,
            target_status="SETTLED",
        )


def test_charity_tx_cannot_complete_without_receipt_cid():
    with pytest.raises(ReceiptSealError):
        mark_action_complete(
            "charity_tx",
            receipt_cid=None,
            target_status="COMPLETE",
        )


def test_action_can_complete_with_verified_receipt_cid(tmp_path):
    ipfs = InMemoryIpfsWriter()
    ledger = JsonlReceiptLedger(tmp_path / "receipt_ledger.jsonl")

    result = seal_receipt(
        trade_receipt(),
        previous_cid=None,
        ipfs=ipfs,
        ledger=ledger,
    )

    completed = mark_action_complete(
        "trade",
        receipt_cid=result["cid"],
        target_status="SETTLED",
    )

    assert completed["status"] == "SETTLED"
    assert completed["receipt_cid"] == result["cid"]
