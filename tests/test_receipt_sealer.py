import json
import subprocess
import sys
from pathlib import Path

import pytest

from eve_q.immutable_receipts import (
    InMemoryIpfsWriter,
    JsonlReceiptLedger,
)
from eve_q.ipfs_adapters import KuboHttpIpfsWriter
from eve_q.receipt_sealer import (
    BACKEND_KUBO,
    BACKEND_MOCK,
    build_ipfs_writer,
    seal_receipt_file,
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


def write_receipt(path: Path, receipt: dict):
    path.write_text(json.dumps(receipt, sort_keys=True) + "\n")


def test_build_ipfs_writer_selects_mock_backend():
    writer = build_ipfs_writer(BACKEND_MOCK)

    assert isinstance(writer, InMemoryIpfsWriter)


def test_build_ipfs_writer_selects_kubo_backend():
    writer = build_ipfs_writer(
        BACKEND_KUBO,
        kubo_api_url="http://127.0.0.1:5001",
    )

    assert isinstance(writer, KuboHttpIpfsWriter)
    assert writer.api_url == "http://127.0.0.1:5001"


def test_build_ipfs_writer_rejects_unknown_backend():
    with pytest.raises(ValueError):
        build_ipfs_writer("unknown")


def test_seal_receipt_file_with_mock_backend_writes_ledger(tmp_path):
    receipt_path = tmp_path / "trade_receipt.json"
    ledger_path = tmp_path / "receipt_ledger.jsonl"
    write_receipt(receipt_path, trade_receipt())

    output = seal_receipt_file(
        receipt_path=receipt_path,
        ledger_path=ledger_path,
        backend=BACKEND_MOCK,
    )

    assert output["backend"] == BACKEND_MOCK
    assert output["result"]["status"] == "IPFS_PINNED_VERIFIED"
    assert output["result"]["cid"].startswith("mock-ipfs-")

    ledger = JsonlReceiptLedger(ledger_path)
    events = ledger.read_events()

    assert len(events) == 1
    assert events[0]["receipt_type"] == "TradeReceipt"


def test_seal_receipt_file_preserves_previous_cid(tmp_path):
    receipt_path = tmp_path / "trade_receipt.json"
    ledger_path = tmp_path / "receipt_ledger.jsonl"
    previous_cid = "bafy-previous"
    write_receipt(receipt_path, trade_receipt())

    output = seal_receipt_file(
        receipt_path=receipt_path,
        ledger_path=ledger_path,
        backend=BACKEND_MOCK,
        previous_cid=previous_cid,
    )

    assert output["result"]["envelope"]["previous_cid"] == previous_cid
    assert output["result"]["ledger_event"]["previous_cid"] == previous_cid


def test_cli_seals_receipt_file_with_mock_backend(tmp_path):
    receipt_path = tmp_path / "trade_receipt.json"
    ledger_path = tmp_path / "receipt_ledger.jsonl"
    write_receipt(receipt_path, trade_receipt())

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.receipt_sealer",
            "--receipt",
            str(receipt_path),
            "--ledger",
            str(ledger_path),
            "--backend",
            BACKEND_MOCK,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    output = json.loads(result.stdout)

    assert output["ok"] is True
    assert output["backend"] == BACKEND_MOCK
    assert output["result"]["status"] == "IPFS_PINNED_VERIFIED"
    assert ledger_path.exists()


def test_cli_rejects_forbidden_secret_without_ledger_event(tmp_path):
    receipt_path = tmp_path / "bad_receipt.json"
    ledger_path = tmp_path / "receipt_ledger.jsonl"
    receipt = trade_receipt()
    receipt["wallet_private_key"] = "do-not-store"
    write_receipt(receipt_path, receipt)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.receipt_sealer",
            "--receipt",
            str(receipt_path),
            "--ledger",
            str(ledger_path),
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
    assert "forbidden receipt fields present" in output["error"]

    if ledger_path.exists():
        assert ledger_path.read_text() == ""
