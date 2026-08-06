from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from eve_q.gate1a1_viv_gauntlet import (
    GATE1A1_CASES,
    Gate1A1ViVError,
    run_gate1a1_gauntlet,
    validate_gate1a1_evidence_bundle,
)
from eve_q.viv_adversarial import AdversarialCase, run_viv_gauntlet, validate_viv_receipt

FIXTURE = Path(__file__).parent / "fixtures" / "gate1a1_viv_evidence_bundle_v0_1.json"


def load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_baseline_bundle_is_valid() -> None:
    validate_gate1a1_evidence_bundle(load_fixture())


def test_all_eighteen_required_mutations_are_blocked() -> None:
    candidate = load_fixture()
    original = copy.deepcopy(candidate)

    receipt = run_gate1a1_gauntlet(candidate, seed=145)

    assert receipt["case_count"] == 18
    assert receipt["blocked_count"] == 18
    assert receipt["escaped_count"] == 0
    assert receipt["overall_outcome"] == "pass"
    assert receipt["repair_required"] is False
    assert receipt["candidate_unchanged"] is True
    assert receipt["self_certifying"] is False
    assert receipt["authority"] is False
    assert receipt["may_execute"] is False
    assert receipt["may_move_capital"] is False
    assert candidate == original
    validate_viv_receipt(receipt)


def test_required_case_ids_are_unique_and_stable() -> None:
    case_ids = [case.case_id for case in GATE1A1_CASES]

    assert len(case_ids) == 18
    assert len(case_ids) == len(set(case_ids))
    assert case_ids[0] == "viv.gate1a1.omit_gas.v0.1"
    assert case_ids[-1] == "viv.gate1a1.charity_to_authority.v0.1"


def test_critical_escape_forces_failure_and_repair_loop() -> None:
    candidate = load_fixture()
    escaping_case = AdversarialCase(
        case_id="viv.gate1a1.intentional_escape_test.v0.1",
        name="Intentional escape test",
        target_invariant="test harness must record an escape",
        severity="critical",
        mutator=lambda payload, seed: payload.update({"test_escape": seed}),
    )

    receipt = run_viv_gauntlet(
        candidate,
        validator=lambda payload: None,
        validator_id="intentional_permissive_validator",
        cases=(escaping_case,),
        seed=145,
    )

    assert receipt["overall_outcome"] == "fail"
    assert receipt["escaped_count"] == 1
    assert receipt["repair_required"] is True
    assert receipt["authority"] is False
    assert receipt["self_certifying"] is False


def test_candidate_with_gate_authority_is_rejected_before_mutation() -> None:
    candidate = load_fixture()
    candidate["gate"]["gate1b_activated"] = True

    with pytest.raises(Exception, match="baseline candidate is invalid"):
        run_gate1a1_gauntlet(candidate)


def test_source_concentration_is_rejected() -> None:
    candidate = load_fixture()
    candidate["sources"][1]["provenance_group"] = candidate["sources"][0]["provenance_group"]

    with pytest.raises(Gate1A1ViVError, match="independently operated"):
        validate_gate1a1_evidence_bundle(candidate)


def test_charity_claim_without_evidence_is_rejected() -> None:
    candidate = load_fixture()
    candidate["charity"]["impact_claim"] = "PROVEN_CAUSAL_IMPACT"

    with pytest.raises(Gate1A1ViVError, match="impact"):
        validate_gate1a1_evidence_bundle(candidate)
