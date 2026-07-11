from __future__ import annotations

import json
from pathlib import Path

from eve_q.gate1_failure_campaign import (
    CASE_NAMES,
    CoalitionObservation,
    build_summary,
    classify_coalition,
    generate_records,
    run_campaign,
)

PRODUCER_COMMIT = "a" * 40


def test_coalition_classifier_separates_grounded_conflict_and_herding():
    same = "1" * 64
    different = "2" * 64

    grounded = classify_coalition(
        (
            CoalitionObservation("a", "provider-a", same),
            CoalitionObservation("b", "provider-b", same),
        )
    )
    assert grounded.evidence_state == "GROUNDED"
    assert grounded.disposition == "OBSERVE_ONLY"

    conflict = classify_coalition(
        (
            CoalitionObservation("a", "provider-a", same),
            CoalitionObservation("b", "provider-b", different),
        )
    )
    assert conflict.evidence_state == "CONFLICTING"
    assert conflict.disposition == "HOLD"

    herding = classify_coalition(
        (
            CoalitionObservation("a", "shared-provider", same),
            CoalitionObservation("b", "shared-provider", same),
        )
    )
    assert herding.evidence_state == "HERDING_RISK"
    assert herding.disposition == "HOLD"


def test_seeded_records_are_deterministic_and_exercise_every_case():
    first = generate_records(
        cycles=100,
        seed=424243,
        producer_commit=PRODUCER_COMMIT,
    )
    second = generate_records(
        cycles=100,
        seed=424243,
        producer_commit=PRODUCER_COMMIT,
    )

    assert first == second
    assert {record["case"] for record in first} == set(CASE_NAMES)
    assert all(record["passed"] is True for record in first)


def test_campaign_preserves_authority_boundary_and_locked_gates():
    records = generate_records(
        cycles=90,
        seed=7,
        producer_commit=PRODUCER_COMMIT,
    )

    for record in records:
        assert record["artifact_is_command"] is False
        assert record["authority"] is False
        assert record["human_promotion_required"] is True
        assert record["may_generate_live_proposal"] is False
        assert record["may_execute"] is False
        assert record["may_move_capital"] is False
        assert record["gate_posture"] == {
            "gate_0": "ACTIVE",
            "gate_1": "PILOT_ONLY",
            "gate_2_through_6": "LOCKED",
        }


def test_summary_requires_every_case_and_zero_unauthorized_transitions():
    records = generate_records(
        cycles=99,
        seed=11,
        producer_commit=PRODUCER_COMMIT,
    )
    summary = build_summary(
        records,
        cycles=99,
        seed=11,
        producer_commit=PRODUCER_COMMIT,
    )

    assert summary["ok"] is True
    assert summary["results"]["failures"] == 0
    assert summary["results"]["unauthorized_transitions"] == 0
    assert summary["acceptance"]["conflict_holds"] is True
    assert summary["acceptance"]["herding_risk_holds"] is True
    assert summary["acceptance"]["outage_rollback_proven"] is True
    assert summary["acceptance"]["independent_agreement_observation_only"] is True


def test_run_campaign_writes_inspectable_ledger_and_summary(tmp_path: Path):
    output_dir = tmp_path / "campaign"
    summary = run_campaign(
        output_dir,
        cycles=100,
        seed=424243,
        producer_commit=PRODUCER_COMMIT,
    )

    summary_path = output_dir / "summary.json"
    ledger_path = output_dir / "campaign.jsonl"

    assert summary["ok"] is True
    assert summary_path.is_file()
    assert ledger_path.is_file()

    persisted = json.loads(summary_path.read_text(encoding="utf-8"))
    ledger = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
    ]

    assert persisted == summary
    assert len(ledger) == 100
    assert all(record["record_sha256"] for record in ledger)


def test_source_outage_always_produces_valid_gate0_rollback_evidence():
    records = generate_records(
        cycles=90,
        seed=13,
        producer_commit=PRODUCER_COMMIT,
    )
    outages = [record for record in records if record["case"] == "source_outage"]

    assert outages
    assert all(record["passed"] is True for record in outages)
    assert all(record["disposition"] == "ROLLBACK_TO_GATE_0" for record in outages)
    assert all(record["rollback_artifact_id"] for record in outages)


def test_too_few_cycles_fail_before_campaign_execution():
    try:
        generate_records(
            cycles=len(CASE_NAMES) - 1,
            seed=1,
            producer_commit=PRODUCER_COMMIT,
        )
    except ValueError as exc:
        assert "cycles must be at least" in str(exc)
    else:
        raise AssertionError("campaign accepted too few cycles")
