import pytest

from eve_q.allocation.charity_router import (
    AllocationDiversityPolicy,
    propose_allocations,
)
from eve_q.allocation.geodesic_policy import GeodesicInput


def signal(
    charity_id,
    *,
    impact=0.8,
    need=0.8,
    urgency=0.8,
    neglect=0.8,
    funding_gap=0.8,
    absorptive_capacity=0.8,
    confidence=0.9,
    reliability=0.9,
    provenance="verified-receipt",
):
    return GeodesicInput(
        charity_id=charity_id,
        impact_score=impact,
        need_score=need,
        urgency_score=urgency,
        neglect_factor=neglect,
        funding_gap_score=funding_gap,
        absorptive_capacity_score=absorptive_capacity,
        confidence_score=confidence,
        telemetry_source_reliability=reliability,
        provenance=provenance,
    )


def test_guarded_weight_caps_dominant_charity_and_reserves_exploration():
    policy = AllocationDiversityPolicy(
        max_single_charity_weight=0.45,
        exploration_budget=0.10,
        concentration_review_threshold=0.40,
    )

    decisions = propose_allocations(
        [
            signal("dominant", impact=1.0, need=1.0, urgency=1.0),
            signal("secondary", impact=0.25, need=0.25, urgency=0.25),
            signal("ancillary", impact=0.20, need=0.20, urgency=0.20),
        ],
        policy=policy,
    )

    guarded_weights = [decision["guarded_recommended_weight"] for decision in decisions]

    assert max(guarded_weights) <= 0.45 + 1e-9
    assert sum(guarded_weights) <= 0.90 + 1e-9
    assert all(
        decision["reserved_exploration_weight"] == pytest.approx(0.10) for decision in decisions
    )

    dominant = next(decision for decision in decisions if decision["charity_id"] == "dominant")
    assert "single_charity_cap_applied" in dominant["human_review_reasons"]
    assert "concentration_review_required" in dominant["human_review_reasons"]
    assert dominant["requires_human_review"] is True


def test_router_preserves_raw_normalized_signal_separate_from_guarded_signal():
    policy = AllocationDiversityPolicy(max_single_charity_weight=0.50)

    decisions = propose_allocations(
        [
            signal("a", impact=1.0, need=1.0, urgency=1.0),
            signal("b", impact=0.5, need=0.5, urgency=0.5),
        ],
        policy=policy,
    )

    assert sum(decision["normalized_recommended_weight"] for decision in decisions) == (
        pytest.approx(1.0)
    )
    assert sum(decision["guarded_recommended_weight"] for decision in decisions) <= (
        1.0 - policy.exploration_budget + 1e-9
    )


def test_zero_weight_inputs_stay_zero_and_held():
    decisions = propose_allocations(
        [
            signal(
                "zero-a",
                impact=0.0,
                need=0.0,
                urgency=0.0,
                neglect=0.0,
                funding_gap=0.0,
                absorptive_capacity=0.0,
            ),
            signal(
                "zero-b",
                impact=0.0,
                need=0.0,
                urgency=0.0,
                neglect=0.0,
                funding_gap=0.0,
                absorptive_capacity=0.0,
            ),
        ]
    )

    assert all(decision["guarded_recommended_weight"] == 0.0 for decision in decisions)
    assert all(decision["normalized_recommended_weight"] == 0.0 for decision in decisions)
    assert all(decision["hold_transfer"] is True for decision in decisions)


def test_portfolio_guard_requires_human_promotion():
    decisions = propose_allocations(
        [
            signal("nets"),
            signal("food"),
            signal("education"),
        ]
    )

    assert all(decision["hold_transfer"] is True for decision in decisions)
    assert all(
        decision["portfolio_guard"]["human_review_required_for_promotion"] is True
        for decision in decisions
    )
    assert all("guarded_recommended_weight" in decision for decision in decisions)
