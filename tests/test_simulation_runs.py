import json
import subprocess
import sys

import pytest

from eve_q.immutable_receipts import InMemoryIpfsWriter, JsonlReceiptLedger
from eve_q.receipt_ledger_audit import audit_receipt_ledger
from eve_q.simulation_runs import (
    JsonlSimulationRunLedger,
    SimulationRunError,
    build_simulation_promotion_precheck,
    build_simulation_receipt,
    build_simulation_run,
    require_simulation_receipt_for_probe_plan,
    seal_simulation_run,
    validate_simulation_run,
)


def simulation_run():
    return build_simulation_run(
        strategy_id="eve_q.shadow_v0",
        seed=12345,
        market_snapshot_hash="sha256:market",
        candidate_count=3,
        accepted_count=1,
        rejected_count=2,
        result_summary_hash="sha256:summary",
        risk_flags=[],
        perturbation_id="perturbation-001",
        created_at="2026-07-08T00:00:00Z",
    )


def test_simulation_run_id_is_deterministic():
    first = simulation_run()
    second = simulation_run()

    assert first["simulation_run_id"] == second["simulation_run_id"]
    assert first["simulation_run_id"].startswith("sha256:")


def test_simulation_run_rejects_forbidden_command_field():
    run = simulation_run()
    run["metadata"] = {
        "command": "do-not-run",
    }

    with pytest.raises(SimulationRunError):
        validate_simulation_run(run)


def test_simulation_run_rejects_non_simulation_environment():
    run = simulation_run()
    run["environment"] = "paper"

    with pytest.raises(SimulationRunError):
        validate_simulation_run(run)


def test_simulation_run_rejects_invalid_counts():
    with pytest.raises(SimulationRunError):
        build_simulation_run(
            strategy_id="eve_q.shadow_v0",
            seed=12345,
            market_snapshot_hash="sha256:market",
            candidate_count=2,
            accepted_count=2,
            rejected_count=2,
            result_summary_hash="sha256:summary",
        )


def test_simulation_run_ledger_appends_sequence(tmp_path):
    ledger = JsonlSimulationRunLedger(tmp_path / "simulation_runs.jsonl")

    first = ledger.append_run(simulation_run())
    second = ledger.append_run(
        build_simulation_run(
            strategy_id="eve_q.shadow_v0",
            seed=12346,
            market_snapshot_hash="sha256:market-2",
            candidate_count=1,
            accepted_count=0,
            rejected_count=1,
            result_summary_hash="sha256:summary-2",
        )
    )

    events = ledger.read_events()

    assert first["sequence"] == 1
    assert second["sequence"] == 2
    assert len(events) == 2
    assert events[0]["event_type"] == "simulation_run_recorded"
    assert events[0]["execution_authority"] == "none"
    assert events[0]["may_execute"] is False
    assert events[0]["may_move_capital"] is False


def test_build_simulation_receipt_preserves_non_authority_flags():
    receipt = build_simulation_receipt(simulation_run())

    assert receipt["receipt_type"] == "SimulationRunReceipt"
    assert receipt["environment"] == "simulation"
    assert receipt["execution_authority"] == "none"
    assert receipt["artifact_is_command"] is False
    assert receipt["may_execute"] is False
    assert receipt["may_move_capital"] is False
    assert receipt["human_promotion_required"] is True


def test_seal_simulation_run_to_receipt_ledger(tmp_path):
    ipfs = InMemoryIpfsWriter()
    receipt_ledger = JsonlReceiptLedger(tmp_path / "receipt_ledger.jsonl")

    result = seal_simulation_run(
        simulation_run(),
        previous_cid=None,
        ipfs=ipfs,
        receipt_ledger=receipt_ledger,
    )

    assert result["status"] == "IPFS_PINNED_VERIFIED"
    assert result["cid"].startswith("mock-ipfs-")
    assert ipfs.is_pinned(result["cid"])

    events = receipt_ledger.read_events()
    assert len(events) == 1
    assert events[0]["receipt_type"] == "SimulationRunReceipt"
    assert events[0]["cid"] == result["cid"]


def test_receipt_ledger_audit_includes_simulation_receipt_membership(tmp_path):
    ipfs = InMemoryIpfsWriter()
    receipt_ledger_path = tmp_path / "receipt_ledger.jsonl"
    receipt_ledger = JsonlReceiptLedger(receipt_ledger_path)

    result = seal_simulation_run(
        simulation_run(),
        previous_cid=None,
        ipfs=ipfs,
        receipt_ledger=receipt_ledger,
    )
    audit = audit_receipt_ledger(receipt_ledger_path)

    assert audit["valid"] is True
    assert result["cid"] in audit["receipt_cids"]
    assert audit["receipt_events"][0]["receipt_type"] == "SimulationRunReceipt"


def test_probe_plan_requires_simulation_receipt_cid():
    with pytest.raises(SimulationRunError):
        require_simulation_receipt_for_probe_plan(None)


def test_build_simulation_promotion_precheck_accepts_audited_receipt(tmp_path):
    ipfs = InMemoryIpfsWriter()
    receipt_ledger_path = tmp_path / "receipt_ledger.jsonl"
    receipt_ledger = JsonlReceiptLedger(receipt_ledger_path)

    result = seal_simulation_run(
        simulation_run(),
        previous_cid=None,
        ipfs=ipfs,
        receipt_ledger=receipt_ledger,
    )
    audit = audit_receipt_ledger(receipt_ledger_path)

    precheck = build_simulation_promotion_precheck(
        source_simulation_receipt_cid=result["cid"],
        ledger_audit=audit,
        merkle_anchor_cid="mock-anchor",
    )

    assert precheck["probe_plan_eligible"] is True
    assert precheck["may_sign"] is False
    assert precheck["may_broadcast"] is False
    assert precheck["may_move_capital"] is False
    assert precheck["source_simulation_receipt_cid"] == result["cid"]


def test_promotion_precheck_rejects_receipt_absent_from_audit(tmp_path):
    ipfs = InMemoryIpfsWriter()
    receipt_ledger_path = tmp_path / "receipt_ledger.jsonl"
    receipt_ledger = JsonlReceiptLedger(receipt_ledger_path)

    seal_simulation_run(
        simulation_run(),
        previous_cid=None,
        ipfs=ipfs,
        receipt_ledger=receipt_ledger,
    )
    audit = audit_receipt_ledger(receipt_ledger_path)

    with pytest.raises(SimulationRunError):
        build_simulation_promotion_precheck(
            source_simulation_receipt_cid="wrong-cid",
            ledger_audit=audit,
        )


def test_cli_writes_simulation_run_ledger(tmp_path):
    ledger_path = tmp_path / "simulation_runs.jsonl"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.simulation_runs",
            "--strategy-id",
            "eve_q.shadow_v0",
            "--seed",
            "12345",
            "--market-snapshot-hash",
            "sha256:market",
            "--candidate-count",
            "2",
            "--accepted-count",
            "1",
            "--rejected-count",
            "1",
            "--result-summary-hash",
            "sha256:summary",
            "--risk-flag",
            "none",
            "--perturbation-id",
            "perturbation-cli",
            "--created-at",
            "2026-07-08T00:00:00Z",
            "--simulation-ledger",
            str(ledger_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    output = json.loads(result.stdout)
    events = JsonlSimulationRunLedger(ledger_path).read_events()

    assert output["ok"] is True
    assert output["simulation_run"]["environment"] == "simulation"
    assert output["ledger_event"]["sequence"] == 1
    assert events[0]["simulation_run_id"] == output["simulation_run"]["simulation_run_id"]
