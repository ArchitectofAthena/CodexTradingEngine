import json
import subprocess
import sys

from eve_q.immutable_receipts import (
    InMemoryIpfsWriter,
    JsonlReceiptLedger,
    seal_receipt,
)
from eve_q.receipt_ledger_audit import audit_receipt_ledger


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


def test_audit_accepts_valid_receipt_chain(tmp_path):
    ledger_path, trade, charity = build_two_event_ledger(tmp_path)

    audit = audit_receipt_ledger(ledger_path)

    assert audit["valid"] is True
    assert audit["event_count"] == 2
    assert audit["latest_cid"] == charity["cid"]
    assert audit["errors"] == []
    assert audit["execution_authority"] == "none"
    assert audit["artifact_is_command"] is False
    assert audit["may_execute"] is False
    assert audit["may_move_capital"] is False


def test_audit_detects_sequence_gap(tmp_path):
    ledger_path, trade, charity = build_two_event_ledger(tmp_path)
    events = JsonlReceiptLedger(ledger_path).read_events()
    events[1]["sequence"] = 99
    write_events(ledger_path, events)

    audit = audit_receipt_ledger(ledger_path)

    assert audit["valid"] is False
    assert any(error["error"] == "sequence_gap_or_mismatch" for error in audit["errors"])


def test_audit_detects_missing_cid(tmp_path):
    ledger_path, trade, charity = build_two_event_ledger(tmp_path)
    events = JsonlReceiptLedger(ledger_path).read_events()
    events[0]["cid"] = ""
    write_events(ledger_path, events)

    audit = audit_receipt_ledger(ledger_path)

    assert audit["valid"] is False
    assert any(error["error"] == "missing_cid" for error in audit["errors"])


def test_audit_detects_previous_cid_chain_mismatch(tmp_path):
    ledger_path, trade, charity = build_two_event_ledger(tmp_path)
    events = JsonlReceiptLedger(ledger_path).read_events()
    events[1]["previous_cid"] = "wrong-cid"
    write_events(ledger_path, events)

    audit = audit_receipt_ledger(ledger_path)

    assert audit["valid"] is False
    assert any(error["error"] == "previous_cid_chain_mismatch" for error in audit["errors"])


def test_audit_detects_authority_drift(tmp_path):
    ledger_path, trade, charity = build_two_event_ledger(tmp_path)
    events = JsonlReceiptLedger(ledger_path).read_events()
    events[0]["may_move_capital"] = True
    write_events(ledger_path, events)

    audit = audit_receipt_ledger(ledger_path)

    assert audit["valid"] is False
    assert any(error["error"] == "may_move_capital_not_false" for error in audit["errors"])


def test_cli_returns_zero_for_valid_ledger(tmp_path):
    ledger_path, trade, charity = build_two_event_ledger(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.receipt_ledger_audit",
            "--ledger",
            str(ledger_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    audit = json.loads(result.stdout)

    assert audit["valid"] is True
    assert audit["latest_cid"] == charity["cid"]


def test_cli_returns_one_for_invalid_ledger(tmp_path):
    ledger_path, trade, charity = build_two_event_ledger(tmp_path)
    events = JsonlReceiptLedger(ledger_path).read_events()
    events[0]["artifact_is_command"] = True
    write_events(ledger_path, events)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.receipt_ledger_audit",
            "--ledger",
            str(ledger_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    audit = json.loads(result.stdout)

    assert result.returncode == 1
    assert audit["valid"] is False
    assert any(error["error"] == "artifact_is_command_not_false" for error in audit["errors"])
