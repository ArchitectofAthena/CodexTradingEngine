import json
import subprocess
import sys

import pytest

from eve_q.capital_action_gate import (
    ACTION_CHARITY_TX,
    ACTION_TRADE,
    CapitalActionGateError,
    build_completion_certificate,
)
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


def build_trade_ledger(tmp_path):
    ipfs = InMemoryIpfsWriter()
    ledger_path = tmp_path / "trade_ledger.jsonl"
    ledger = JsonlReceiptLedger(ledger_path)

    trade = seal_receipt(
        trade_receipt(),
        previous_cid=None,
        ipfs=ipfs,
        ledger=ledger,
    )

    return ledger_path, trade


def build_trade_charity_ledger(tmp_path):
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


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n")


def test_trade_completion_certificate_accepts_valid_audit(tmp_path):
    ledger_path, trade = build_trade_ledger(tmp_path)
    audit = audit_receipt_ledger(ledger_path)

    certificate = build_completion_certificate(
        action_kind=ACTION_TRADE,
        target_status="SETTLED",
        receipt_cid=trade["cid"],
        ledger_audit=audit,
    )

    assert certificate["completion_status"] == "ACCOUNTED"
    assert certificate["receipt_cid"] == trade["cid"]
    assert certificate["ledger_latest_cid"] == trade["cid"]
    assert certificate["execution_authority"] == "none"
    assert certificate["artifact_is_command"] is False
    assert certificate["may_execute"] is False
    assert certificate["may_move_capital"] is False


def test_charity_completion_requires_source_receipt_cid(tmp_path):
    ledger_path, trade, charity = build_trade_charity_ledger(tmp_path)
    audit = audit_receipt_ledger(ledger_path)

    with pytest.raises(CapitalActionGateError):
        build_completion_certificate(
            action_kind=ACTION_CHARITY_TX,
            target_status="COMPLETE",
            receipt_cid=charity["cid"],
            ledger_audit=audit,
        )


def test_charity_completion_accepts_source_receipt_cid(tmp_path):
    ledger_path, trade, charity = build_trade_charity_ledger(tmp_path)
    audit = audit_receipt_ledger(ledger_path)

    certificate = build_completion_certificate(
        action_kind=ACTION_CHARITY_TX,
        target_status="COMPLETE",
        receipt_cid=charity["cid"],
        ledger_audit=audit,
        source_receipt_cid=trade["cid"],
    )

    assert certificate["completion_status"] == "ACCOUNTED"
    assert certificate["receipt_cid"] == charity["cid"]
    assert certificate["source_receipt_cid"] == trade["cid"]


def test_rejects_missing_receipt_cid(tmp_path):
    ledger_path, trade = build_trade_ledger(tmp_path)
    audit = audit_receipt_ledger(ledger_path)

    with pytest.raises(CapitalActionGateError):
        build_completion_certificate(
            action_kind=ACTION_TRADE,
            target_status="SETTLED",
            receipt_cid=None,
            ledger_audit=audit,
        )


def test_rejects_invalid_ledger_audit(tmp_path):
    ledger_path, trade = build_trade_ledger(tmp_path)
    audit = audit_receipt_ledger(ledger_path)
    audit["valid"] = False

    with pytest.raises(CapitalActionGateError):
        build_completion_certificate(
            action_kind=ACTION_TRADE,
            target_status="SETTLED",
            receipt_cid=trade["cid"],
            ledger_audit=audit,
        )


def test_rejects_latest_cid_mismatch(tmp_path):
    ledger_path, trade = build_trade_ledger(tmp_path)
    audit = audit_receipt_ledger(ledger_path)

    with pytest.raises(CapitalActionGateError):
        build_completion_certificate(
            action_kind=ACTION_TRADE,
            target_status="SETTLED",
            receipt_cid="wrong-cid",
            ledger_audit=audit,
        )


def test_requires_merkle_anchor_when_policy_requires_it(tmp_path):
    ledger_path, trade = build_trade_ledger(tmp_path)
    audit = audit_receipt_ledger(ledger_path)

    with pytest.raises(CapitalActionGateError):
        build_completion_certificate(
            action_kind=ACTION_TRADE,
            target_status="SETTLED",
            receipt_cid=trade["cid"],
            ledger_audit=audit,
            require_merkle_anchor=True,
        )


def test_accepts_merkle_anchor_when_required(tmp_path):
    ledger_path, trade = build_trade_ledger(tmp_path)
    audit = audit_receipt_ledger(ledger_path)

    certificate = build_completion_certificate(
        action_kind=ACTION_TRADE,
        target_status="SETTLED",
        receipt_cid=trade["cid"],
        ledger_audit=audit,
        merkle_anchor_cid="bafy-anchor",
        require_merkle_anchor=True,
    )

    assert certificate["merkle_anchor_required"] is True
    assert certificate["merkle_anchor_cid"] == "bafy-anchor"


def test_rejects_authority_drift_in_audit_packet(tmp_path):
    ledger_path, trade = build_trade_ledger(tmp_path)
    audit = audit_receipt_ledger(ledger_path)
    audit["may_move_capital"] = True

    with pytest.raises(CapitalActionGateError):
        build_completion_certificate(
            action_kind=ACTION_TRADE,
            target_status="SETTLED",
            receipt_cid=trade["cid"],
            ledger_audit=audit,
        )


def test_cli_writes_completion_certificate(tmp_path):
    ledger_path, trade = build_trade_ledger(tmp_path)
    audit = audit_receipt_ledger(ledger_path)
    audit_path = tmp_path / "ledger_audit.json"
    output_path = tmp_path / "completion_certificate.json"

    write_json(audit_path, audit)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.capital_action_gate",
            "--action-kind",
            ACTION_TRADE,
            "--target-status",
            "SETTLED",
            "--receipt-cid",
            trade["cid"],
            "--ledger-audit",
            str(audit_path),
            "--output",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    output = json.loads(result.stdout)
    written = json.loads(output_path.read_text())

    assert output["ok"] is True
    assert written == output["certificate"]
    assert written["completion_status"] == "ACCOUNTED"
    assert written["receipt_cid"] == trade["cid"]


def test_cli_rejects_charity_without_source_receipt(tmp_path):
    ledger_path, trade, charity = build_trade_charity_ledger(tmp_path)
    audit = audit_receipt_ledger(ledger_path)
    audit_path = tmp_path / "ledger_audit.json"
    write_json(audit_path, audit)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.capital_action_gate",
            "--action-kind",
            ACTION_CHARITY_TX,
            "--target-status",
            "COMPLETE",
            "--receipt-cid",
            charity["cid"],
            "--ledger-audit",
            str(audit_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    output = json.loads(result.stdout)

    assert result.returncode == 1
    assert output["ok"] is False
    assert "source trade receipt CID" in output["error"]
