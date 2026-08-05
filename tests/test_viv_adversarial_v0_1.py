from __future__ import annotations

from copy import deepcopy
import json
import subprocess
import sys

import pytest

from eve_q.simulation_runs import build_simulation_run, validate_simulation_run
from eve_q.viv_adversarial import (
    AdversarialCase,
    ViVAdversarialError,
    expected_receipt_id,
    run_viv_gauntlet,
    validate_viv_receipt,
)


def valid_run() -> dict[str, object]:
    return build_simulation_run(
        strategy_id="eve_q.shadow_v0",
        seed=12345,
        market_snapshot_hash="sha256:market",
        candidate_count=3,
        accepted_count=1,
        rejected_count=2,
        result_summary_hash="sha256:summary",
        risk_flags=[],
        perturbation_id="perturbation-viv",
        created_at="2026-08-05T00:00:00Z",
    )


def test_default_gauntlet_blocks_every_mutation() -> None:
    receipt = run_viv_gauntlet(
        valid_run(),
        validator=validate_simulation_run,
        validator_id="simulation_run",
        seed=7331,
        created_at="2026-08-05T00:00:00Z",
    )

    assert receipt["overall_outcome"] == "pass"
    assert receipt["case_count"] == 9
    assert receipt["blocked_count"] == 9
    assert receipt["escaped_count"] == 0
    assert receipt["repair_required"] is False
    assert {case["status"] for case in receipt["cases"]} == {"blocked"}


def test_gauntlet_is_deterministic_for_same_candidate_and_seed() -> None:
    first = run_viv_gauntlet(
        valid_run(),
        validator=validate_simulation_run,
        validator_id="simulation_run",
        seed=42,
    )
    second = run_viv_gauntlet(
        valid_run(),
        validator=validate_simulation_run,
        validator_id="simulation_run",
        seed=42,
    )

    assert first == second
    assert first["receipt_id"] == expected_receipt_id(first)


def test_gauntlet_does_not_mutate_original_candidate() -> None:
    candidate = valid_run()
    before = deepcopy(candidate)

    receipt = run_viv_gauntlet(
        candidate,
        validator=validate_simulation_run,
        validator_id="simulation_run",
    )

    assert candidate == before
    assert receipt["candidate_unchanged"] is True


def test_permissive_validator_produces_escaped_evidence_not_false_pass() -> None:
    def permissive_validator(candidate: dict[str, object]) -> None:
        del candidate

    receipt = run_viv_gauntlet(
        valid_run(),
        validator=permissive_validator,
        validator_id="permissive-test-double",
    )

    assert receipt["overall_outcome"] == "fail"
    assert receipt["escaped_count"] == receipt["case_count"]
    assert receipt["repair_required"] is True
    assert {case["status"] for case in receipt["cases"]} == {"escaped"}


def test_invalid_baseline_is_rejected_before_mutation() -> None:
    candidate = valid_run()
    candidate["environment"] = "live"

    with pytest.raises(ViVAdversarialError, match="baseline candidate is invalid"):
        run_viv_gauntlet(
            candidate,
            validator=validate_simulation_run,
            validator_id="simulation_run",
        )


def test_duplicate_case_ids_are_rejected() -> None:
    def mutation(candidate: dict[str, object], seed: int) -> None:
        del seed
        candidate["may_execute"] = True

    case = AdversarialCase(
        case_id="duplicate",
        name="Duplicate",
        target_invariant="may_execute remains false",
        severity="critical",
        mutator=mutation,
    )

    with pytest.raises(ViVAdversarialError, match="case IDs must be unique"):
        run_viv_gauntlet(
            valid_run(),
            validator=validate_simulation_run,
            validator_id="simulation_run",
            cases=(case, case),
        )


def test_receipt_cannot_grant_itself_authority() -> None:
    receipt = run_viv_gauntlet(
        valid_run(),
        validator=validate_simulation_run,
        validator_id="simulation_run",
    )
    receipt["may_move_capital"] = True
    receipt["receipt_id"] = expected_receipt_id(receipt)

    with pytest.raises(ViVAdversarialError, match="may_move_capital must be false"):
        validate_viv_receipt(receipt)


def test_receipt_remains_non_authoritative() -> None:
    receipt = run_viv_gauntlet(
        valid_run(),
        validator=validate_simulation_run,
        validator_id="simulation_run",
    )

    assert receipt["self_certifying"] is False
    assert receipt["authority"] is False
    assert receipt["artifact_is_command"] is False
    assert receipt["network_access"] is False
    assert receipt["dynamic_code_loading"] is False
    assert receipt["human_promotion_required"] is True
    assert receipt["may_execute"] is False
    assert receipt["may_deploy"] is False
    assert receipt["may_merge"] is False
    assert receipt["may_sign"] is False
    assert receipt["may_broadcast"] is False
    assert receipt["may_access_wallet"] is False
    assert receipt["may_move_capital"] is False
    assert receipt["may_mutate_canonical_memory"] is False


def test_cli_writes_receipt(tmp_path) -> None:
    candidate_path = tmp_path / "candidate.json"
    receipt_path = tmp_path / "viv-receipt.json"
    candidate_path.write_text(json.dumps(valid_run()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.viv_adversarial",
            "--candidate",
            str(candidate_path),
            "--validator",
            "simulation_run",
            "--seed",
            "7331",
            "--created-at",
            "2026-08-05T00:00:00Z",
            "--receipt-out",
            str(receipt_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    output = json.loads(result.stdout)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert output["ok"] is True
    assert receipt["overall_outcome"] == "pass"
    assert receipt["receipt_id"] == output["receipt"]["receipt_id"]
