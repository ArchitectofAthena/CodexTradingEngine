from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from eve_q.gate1a1_evidence_convergence import (
    BOUNDARY,
    SECTION_KEYS,
    EvidenceConvergenceError,
    build_receipt,
    require_schema,
    write_receipt,
)

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_SCHEMA = json.loads(
    (ROOT / "schemas" / "gate1a1_evidence_bundle_v0_1.schema.json").read_text(encoding="utf-8")
)
RECEIPT_SCHEMA = json.loads(
    (ROOT / "schemas" / "gate1a1_decision_receipt_v0_1.schema.json").read_text(encoding="utf-8")
)
SEED = json.loads(
    (ROOT / "benchmarks" / "gate1a1_evidence_bundle_seed_v0_1.json").read_text(encoding="utf-8")
)
GENERATED_AT = "2026-08-06T16:00:00Z"


def bundle() -> dict:
    return copy.deepcopy(SEED)


def validate_and_build(value: dict) -> dict:
    require_schema(value, BUNDLE_SCHEMA, "evidence bundle")
    receipt = build_receipt(value, generated_at=GENERATED_AT)
    require_schema(receipt, RECEIPT_SCHEMA, "decision receipt")
    return receipt


def test_seed_converges_to_qaoa_research_only() -> None:
    receipt = validate_and_build(bundle())

    assert receipt["decision"] == "QAOA_RESEARCH_ONLY"
    assert receipt["hold_reasons"] == []
    assert receipt["qaoa_status"] == "RESEARCH_ONLY"
    assert tuple(receipt["compact_report"]) == SECTION_KEYS
    assert receipt["compact_report"]["EXECUTION_LOCKS"] == "LOCKED"
    assert receipt["compact_report"]["NEXT_DECISION"] == "QAOA_RESEARCH_ONLY"
    assert receipt["boundary"] == BOUNDARY
    assert receipt["boundary"]["gate1b_activated"] is False


def test_positive_qaoa_evidence_only_opens_human_review() -> None:
    value = bundle()
    value["benchmark"]["qaoa_value_demonstrated"] = True

    receipt = validate_and_build(value)

    assert receipt["decision"] == "READY_FOR_GATE1B_REVIEW"
    assert receipt["qaoa_status"] == "CANDIDATE_FOR_FURTHER_TESTING"
    assert receipt["boundary"]["automatic_gate_promotion"] is False
    assert receipt["boundary"]["gate1b_activated"] is False
    assert receipt["boundary"]["human_promotion_required"] is True


Mutation = Callable[[dict], None]


def source_conflict(value: dict) -> None:
    value["source_quorum"]["decision"] = "HOLD_CONFLICT"
    value["source_quorum"]["material_disagreement"] = True


def source_concentration(value: dict) -> None:
    value["source_quorum"]["independent_source_count"] = 1
    value["source_quorum"]["decision"] = "HOLD_CONCENTRATION"
    value["source_quorum"]["shared_provenance_concentration"] = True


def missing_pair(value: dict) -> None:
    value["benchmark"]["exact_pair_present"] = False


def changed_qubo(value: dict) -> None:
    value["benchmark"]["same_qubo_hash"] = False


def unexplained_binary(value: dict) -> None:
    value["rust_verifier"]["binary_hash_verified"] = False


def escaped_viv(value: dict) -> None:
    value["viv"]["critical_escaped"] = 1


def incomplete_economics(value: dict) -> None:
    value["economics"]["complete"] = False


def incomplete_charity_contract(value: dict) -> None:
    value["charity"]["contract_complete"] = False


def failed_rollback(value: dict) -> None:
    value["rollback"]["rollback_replay_passed"] = False


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        (source_conflict, "HOLD_CONFLICT"),
        (source_concentration, "HOLD_CONCENTRATION"),
        (missing_pair, "HOLD_MISSING_EXACT_PAIR"),
        (changed_qubo, "HOLD_QUBO_HASH_MISMATCH"),
        (unexplained_binary, "HOLD_UNVERIFIED_BINARY"),
        (escaped_viv, "HOLD_VIV_CRITICAL_ESCAPE"),
        (incomplete_economics, "HOLD_INCOMPLETE_ECONOMICS"),
        (incomplete_charity_contract, "HOLD_CHARITY_TARGET_CONTRACT"),
        (failed_rollback, "HOLD_ROLLBACK"),
    ],
)
def test_critical_evidence_failures_force_hold(
    mutation: Mutation,
    expected_reason: str,
) -> None:
    value = bundle()
    mutation(value)

    receipt = validate_and_build(value)

    assert receipt["decision"] == "HOLD"
    assert expected_reason in receipt["hold_reasons"]
    assert receipt["compact_report"]["NEXT_DECISION"] == "HOLD"
    assert receipt["boundary"]["may_execute"] is False
    assert receipt["boundary"]["may_move_capital"] is False


def test_receipt_hash_is_stable_across_timestamp_changes() -> None:
    value = bundle()

    first = build_receipt(value, generated_at="2026-08-06T16:00:00Z")
    second = build_receipt(copy.deepcopy(value), generated_at="2026-08-06T17:00:00Z")

    assert first["evidence_sha256"] == second["evidence_sha256"]
    assert first["receipt_sha256"] == second["receipt_sha256"]


def test_authority_drift_is_rejected_before_decision() -> None:
    value = bundle()
    value["boundary"]["may_execute"] = True

    with pytest.raises(EvidenceConvergenceError, match="evidence bundle schema"):
        require_schema(value, BUNDLE_SCHEMA, "evidence bundle")


def test_write_receipt_emits_json_and_compact_text(tmp_path: Path) -> None:
    receipt = validate_and_build(bundle())
    output = tmp_path / "decision.json"

    json_path, summary_path = write_receipt(
        receipt,
        output=output,
        receipt_schema=RECEIPT_SCHEMA,
    )

    persisted = json.loads(json_path.read_text(encoding="utf-8"))
    summary = summary_path.read_text(encoding="utf-8")
    assert persisted == receipt
    assert "SOURCE_QUORUM: ACCEPT_OBSERVATION_ONLY" in summary
    assert "NEXT_DECISION: QAOA_RESEARCH_ONLY" in summary
    assert "GATE_1B_ACTIVATED: false" in summary
    assert "CAPITAL: LOCKED" in summary
