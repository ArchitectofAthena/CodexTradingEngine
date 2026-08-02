from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from eve_q.mirror_slurper_offline import (
    ARTIFACT_TYPE,
    CONTRACT_VERSION,
    MirrorSlurperError,
    compute_document_id,
    compute_receipt_id,
    evaluate_recorded_route,
)

FIXTURES = Path(__file__).parent / "fixtures" / "mirror_slurper"


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def with_recomputed_id(document: dict[str, object], id_field: str) -> dict[str, object]:
    document[id_field] = ""
    document[id_field] = compute_document_id(document, id_field)
    return document


def test_recorded_fixture_survives_stress_and_receipt_is_deterministic() -> None:
    snapshot = load_fixture("pool_snapshot_v0_1.json")
    candidate = load_fixture("candidate_v0_1.json")
    policy = load_fixture("stress_policy_v0_1.json")

    first = evaluate_recorded_route(snapshot, candidate, policy)
    second = evaluate_recorded_route(snapshot, candidate, policy)

    assert first == second
    assert first["artifact_type"] == ARTIFACT_TYPE
    assert first["contract_version"] == CONTRACT_VERSION
    assert first["evaluation"]["verdict"] == "CANDIDATE"
    assert float(first["evaluation"]["baseline_net_profit_start_token"]) > 0
    assert float(first["evaluation"]["worst_case_net_profit_start_token"]) >= 25
    assert first["receipt_id"] == compute_receipt_id(first)
    schema = json.loads(
        (
            Path(__file__).parents[1]
            / "schemas"
            / "mirror_slurper_offline_receipt_v0_1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(first)
    assert first["offline_only"] is True
    assert first["recorded_snapshot_only"] is True
    assert first["human_review_required"] is True
    assert first["authority"] is False
    assert first["may_generate_live_proposal"] is False
    assert first["may_execute"] is False
    assert first["may_move_capital"] is False


def test_stronger_adverse_scenario_holds_fragile_edge() -> None:
    snapshot = load_fixture("pool_snapshot_v0_1.json")
    candidate = load_fixture("candidate_v0_1.json")
    policy = load_fixture("stress_policy_v0_1.json")
    policy["scenarios"].append(
        {
            "name": "wind_tunnel",
            "gas_multiplier": "2",
            "reserve_shift_bps": 50,
            "slippage_bps": 20,
            "delay_blocks": 3,
        }
    )
    with_recomputed_id(policy, "policy_id")

    receipt = evaluate_recorded_route(snapshot, candidate, policy)

    assert receipt["evaluation"]["verdict"] == "HOLD"
    assert "stress_floor_not_met" in receipt["evaluation"]["failure_modes"]
    assert "scenario:wind_tunnel:negative_net_profit" in receipt["evaluation"]["failure_modes"]


def test_unprofitable_baseline_is_rejected() -> None:
    snapshot = load_fixture("pool_snapshot_v0_1.json")
    candidate = load_fixture("candidate_v0_1.json")
    policy = load_fixture("stress_policy_v0_1.json")
    snapshot["pools"][2]["reserve1"] = "970000"
    with_recomputed_id(snapshot, "snapshot_id")

    receipt = evaluate_recorded_route(snapshot, candidate, policy)

    assert receipt["evaluation"]["verdict"] == "REJECT"
    assert "baseline_not_profitable" in receipt["evaluation"]["failure_modes"]


def test_unknown_fields_fail_closed() -> None:
    snapshot = load_fixture("pool_snapshot_v0_1.json")
    candidate = load_fixture("candidate_v0_1.json")
    policy = load_fixture("stress_policy_v0_1.json")
    candidate["wallet"] = "0xnot-allowed"
    with_recomputed_id(candidate, "candidate_id")

    with pytest.raises(MirrorSlurperError, match="unknown fields"):
        evaluate_recorded_route(snapshot, candidate, policy)


def test_tampered_content_identifier_is_rejected() -> None:
    snapshot = load_fixture("pool_snapshot_v0_1.json")
    candidate = load_fixture("candidate_v0_1.json")
    policy = load_fixture("stress_policy_v0_1.json")
    snapshot["pools"][0]["reserve0"] = "2000001"

    with pytest.raises(MirrorSlurperError, match="snapshot_id does not match"):
        evaluate_recorded_route(snapshot, candidate, policy)


def test_route_must_return_to_start_token() -> None:
    snapshot = load_fixture("pool_snapshot_v0_1.json")
    candidate = load_fixture("candidate_v0_1.json")
    policy = load_fixture("stress_policy_v0_1.json")
    candidate["route"] = candidate["route"][:-1]
    with_recomputed_id(candidate, "candidate_id")

    with pytest.raises(MirrorSlurperError, match="must return"):
        evaluate_recorded_route(snapshot, candidate, policy)


def test_route_may_not_reuse_pool_in_v0_1() -> None:
    snapshot = load_fixture("pool_snapshot_v0_1.json")
    candidate = load_fixture("candidate_v0_1.json")
    policy = load_fixture("stress_policy_v0_1.json")
    candidate["route"][2]["pool_id"] = candidate["route"][0]["pool_id"]
    with_recomputed_id(candidate, "candidate_id")

    with pytest.raises(MirrorSlurperError, match="may not reuse a pool"):
        evaluate_recorded_route(snapshot, candidate, policy)


def test_policy_authority_cannot_be_promoted() -> None:
    snapshot = load_fixture("pool_snapshot_v0_1.json")
    candidate = load_fixture("candidate_v0_1.json")
    policy = load_fixture("stress_policy_v0_1.json")
    policy["may_execute"] = True
    with_recomputed_id(policy, "policy_id")

    with pytest.raises(MirrorSlurperError, match="policy.may_execute must be false"):
        evaluate_recorded_route(snapshot, candidate, policy)


def test_input_documents_are_not_mutated() -> None:
    snapshot = load_fixture("pool_snapshot_v0_1.json")
    candidate = load_fixture("candidate_v0_1.json")
    policy = load_fixture("stress_policy_v0_1.json")
    before = (deepcopy(snapshot), deepcopy(candidate), deepcopy(policy))

    evaluate_recorded_route(snapshot, candidate, policy)

    assert (snapshot, candidate, policy) == before
