import json
import subprocess
import sys

import pytest

from eve_q.immutable_receipts import (
    InMemoryIpfsWriter,
    JsonlReceiptLedger,
    ReceiptSealError,
    seal_receipt,
)
from eve_q.receipt_merkle_anchor import (
    ANCHOR_RECEIPT_TYPE,
    build_merkle_anchor_receipt,
    merkle_packet_digest,
    seal_merkle_anchor,
)
from eve_q.receipt_merkle_audit import build_receipt_merkle_audit
from eve_q.receipt_sealer import BACKEND_MOCK


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


def build_two_event_ledger(tmp_path):
    ipfs = InMemoryIpfsWriter()
    ledger_path = tmp_path / "receipt_ledger.jsonl"
    ledger = JsonlReceiptLedger(ledger_path)

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

    return ledger_path, trade, charity


def test_merkle_packet_digest_is_deterministic():
    first = merkle_packet_digest({"b": 2, "a": 1})
    second = merkle_packet_digest({"a": 1, "b": 2})

    assert first == second


def test_build_anchor_receipt_from_valid_merkle_packet(tmp_path):
    ledger_path, trade, charity = build_two_event_ledger(tmp_path)
    packet = build_receipt_merkle_audit(
        ledger_path,
        period="2026-07-08",
    )

    receipt = build_merkle_anchor_receipt(packet)

    assert receipt["receipt_type"] == ANCHOR_RECEIPT_TYPE
    assert receipt["period"] == "2026-07-08"
    assert receipt["event_count"] == 2
    assert receipt["latest_cid"] == charity["cid"]
    assert receipt["merkle_root"] == packet["merkle_root"]
    assert receipt["merkle_packet_sha256"] == merkle_packet_digest(packet)
    assert receipt["execution_authority"] == "none"
    assert receipt["artifact_is_command"] is False
    assert receipt["may_execute"] is False
    assert receipt["may_move_capital"] is False


def test_build_anchor_receipt_rejects_invalid_merkle_packet(tmp_path):
    ledger_path = tmp_path / "empty.jsonl"
    packet = build_receipt_merkle_audit(ledger_path)

    with pytest.raises(ReceiptSealError):
        build_merkle_anchor_receipt(packet)


def test_seal_merkle_anchor_uses_separate_anchor_ledger(tmp_path):
    source_ledger_path, trade, charity = build_two_event_ledger(tmp_path)
    anchor_ledger_path = tmp_path / "anchor_ledger.jsonl"

    output = seal_merkle_anchor(
        source_ledger_path=source_ledger_path,
        anchor_ledger_path=anchor_ledger_path,
        backend=BACKEND_MOCK,
        period="2026-07-08",
    )

    source_events = JsonlReceiptLedger(source_ledger_path).read_events()
    anchor_events = JsonlReceiptLedger(anchor_ledger_path).read_events()

    assert len(source_events) == 2
    assert len(anchor_events) == 1
    assert output["result"]["status"] == "IPFS_PINNED_VERIFIED"
    assert output["anchor_receipt"]["merkle_root"]
    assert anchor_events[0]["receipt_type"] == ANCHOR_RECEIPT_TYPE


def test_seal_merkle_anchor_preserves_previous_anchor_cid(tmp_path):
    source_ledger_path, trade, charity = build_two_event_ledger(tmp_path)
    anchor_ledger_path = tmp_path / "anchor_ledger.jsonl"

    output = seal_merkle_anchor(
        source_ledger_path=source_ledger_path,
        anchor_ledger_path=anchor_ledger_path,
        backend=BACKEND_MOCK,
        period="2026-07-08",
        previous_anchor_cid="bafy-anchor-previous",
    )

    assert output["result"]["envelope"]["previous_cid"] == ("bafy-anchor-previous")
    assert output["result"]["ledger_event"]["previous_cid"] == ("bafy-anchor-previous")


def test_cli_seals_merkle_anchor_receipt(tmp_path):
    source_ledger_path, trade, charity = build_two_event_ledger(tmp_path)
    anchor_ledger_path = tmp_path / "anchor_ledger.jsonl"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.receipt_merkle_anchor",
            "--ledger",
            str(source_ledger_path),
            "--anchor-ledger",
            str(anchor_ledger_path),
            "--backend",
            BACKEND_MOCK,
            "--period",
            "2026-07-08",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    output = json.loads(result.stdout)
    anchor_events = JsonlReceiptLedger(anchor_ledger_path).read_events()

    assert output["ok"] is True
    assert output["result"]["status"] == "IPFS_PINNED_VERIFIED"
    assert output["anchor_receipt"]["receipt_type"] == ANCHOR_RECEIPT_TYPE
    assert len(anchor_events) == 1


def test_cli_rejects_empty_source_ledger_without_anchor_event(tmp_path):
    source_ledger_path = tmp_path / "empty.jsonl"
    anchor_ledger_path = tmp_path / "anchor_ledger.jsonl"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.receipt_merkle_anchor",
            "--ledger",
            str(source_ledger_path),
            "--anchor-ledger",
            str(anchor_ledger_path),
            "--backend",
            BACKEND_MOCK,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    output = json.loads(result.stdout)

    assert result.returncode == 1
    assert output["ok"] is False
    assert "cannot anchor invalid Merkle audit packet" in output["error"]
    assert not anchor_ledger_path.exists()
