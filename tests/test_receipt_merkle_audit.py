import json
import subprocess
import sys

from eve_q.immutable_receipts import (
    InMemoryIpfsWriter,
    JsonlReceiptLedger,
    seal_receipt,
)
from eve_q.receipt_merkle_audit import (
    build_receipt_merkle_audit,
    event_leaf_hash,
    merkle_parent,
    merkle_root,
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


def write_events(path, events):
    path.write_text("\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n")


def test_event_leaf_hash_is_deterministic():
    first = event_leaf_hash({"b": 2, "a": 1})
    second = event_leaf_hash({"a": 1, "b": 2})

    assert first == second


def test_merkle_root_empty_is_none():
    assert merkle_root([]) is None


def test_merkle_root_single_leaf_is_leaf():
    leaf = event_leaf_hash({"sequence": 1})

    assert merkle_root([leaf]) == leaf


def test_merkle_parent_is_deterministic():
    left = event_leaf_hash({"sequence": 1})
    right = event_leaf_hash({"sequence": 2})

    assert merkle_parent(left, right) == merkle_parent(left, right)
    assert merkle_parent(left, right) != merkle_parent(right, left)


def test_merkle_audit_accepts_valid_ledger(tmp_path):
    ledger_path, trade, charity = build_two_event_ledger(tmp_path)

    packet = build_receipt_merkle_audit(
        ledger_path,
        period="2026-07-08",
    )

    assert packet["valid"] is True
    assert packet["ledger_valid"] is True
    assert packet["event_count"] == 2
    assert packet["period"] == "2026-07-08"
    assert packet["latest_cid"] == charity["cid"]
    assert packet["merkle_root"]
    assert len(packet["leaves"]) == 2
    assert packet["execution_authority"] == "none"
    assert packet["artifact_is_command"] is False
    assert packet["may_execute"] is False
    assert packet["may_move_capital"] is False


def test_merkle_audit_rejects_empty_ledger(tmp_path):
    ledger_path = tmp_path / "empty.jsonl"

    packet = build_receipt_merkle_audit(ledger_path)

    assert packet["valid"] is False
    assert packet["event_count"] == 0
    assert packet["merkle_root"] is None
    assert any(error["error"] == "empty_ledger" for error in packet["errors"])


def test_merkle_audit_detects_invalid_ledger(tmp_path):
    ledger_path, trade, charity = build_two_event_ledger(tmp_path)
    events = JsonlReceiptLedger(ledger_path).read_events()
    events[1]["previous_cid"] = "wrong-cid"
    write_events(ledger_path, events)

    packet = build_receipt_merkle_audit(ledger_path)

    assert packet["valid"] is False
    assert packet["ledger_valid"] is False
    assert any(error["error"] == "ledger_audit_invalid" for error in packet["errors"])


def test_cli_writes_merkle_audit_packet(tmp_path):
    ledger_path, trade, charity = build_two_event_ledger(tmp_path)
    output_path = tmp_path / "daily_merkle_audit.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.receipt_merkle_audit",
            "--ledger",
            str(ledger_path),
            "--period",
            "2026-07-08",
            "--output",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    packet = json.loads(result.stdout)
    written = json.loads(output_path.read_text())

    assert packet["valid"] is True
    assert written == packet
    assert written["merkle_root"]
    assert written["latest_cid"] == charity["cid"]


def test_cli_returns_one_for_invalid_ledger(tmp_path):
    ledger_path, trade, charity = build_two_event_ledger(tmp_path)
    events = JsonlReceiptLedger(ledger_path).read_events()
    events[0]["may_execute"] = True
    write_events(ledger_path, events)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.receipt_merkle_audit",
            "--ledger",
            str(ledger_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    packet = json.loads(result.stdout)

    assert result.returncode == 1
    assert packet["valid"] is False
    assert packet["ledger_valid"] is False
