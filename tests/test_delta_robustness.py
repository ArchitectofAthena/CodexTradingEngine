from __future__ import annotations

import os
from pathlib import Path

import pytest

from eve_q.delta_robustness import (
    PerturbationScenario,
    _apply_scenario,
    evaluate_candidate_robustness,
    standard_adverse_scenarios,
)
from eve_q.qaoa_delta import (
    MarketEdge,
    build_cycle_selection_qubo,
    enumerate_triangular_cycles,
)
from eve_q.qaoa_sampling import build_qaoa_confidence_receipt


def _fixture():
    edges = (
        MarketEdge("usd-eth", "USD", "ETH", 0.0005, venue="alpha"),
        MarketEdge("eth-btc", "ETH", "BTC", 0.05, venue="beta"),
        MarketEdge("btc-usd", "BTC", "USD", 41_000.0, venue="gamma"),
    )
    candidate = enumerate_triangular_cycles(edges)[0]
    model = build_cycle_selection_qubo((candidate,))
    receipt = build_qaoa_confidence_receipt(
        model,
        (candidate,),
        {"1": 1.0},
        solver="test-distribution",
        reps=1,
    )
    return edges, candidate, receipt


def test_standard_scenarios_are_deterministic_and_non_authoritative() -> None:
    first = standard_adverse_scenarios()
    second = standard_adverse_scenarios()

    assert first == second
    assert len(first) == 7
    assert len({scenario.scenario_id for scenario in first}) == 7
    assert all(scenario.authority is False for scenario in first)


def test_adverse_scenario_reduces_candidate_delta() -> None:
    edges, candidate, _ = _fixture()
    scenario = PerturbationScenario(
        "delta-scenario:adverse-test",
        rate_shift_bps=(-10.0, -10.0, -10.0),
        slippage_shift_bps=(5.0, 5.0, 5.0),
        latency_shift_bps=(2.0, 2.0, 2.0),
        gas_penalty_log_shift=0.002,
    )

    perturbed_edges, perturbed_candidate = _apply_scenario(candidate, edges, scenario)

    assert perturbed_candidate.candidate_id == candidate.candidate_id
    assert perturbed_candidate.net_log_delta < candidate.net_log_delta
    assert all(edge.authority is False for edge in perturbed_edges)
    assert perturbed_candidate.authority is False


def test_rejects_duplicate_scenario_identity_before_execution() -> None:
    edges, candidate, receipt = _fixture()
    duplicate = PerturbationScenario("delta-scenario:duplicate")

    with pytest.raises(ValueError, match="identifiers must be unique"):
        evaluate_candidate_robustness(
            receipt,
            candidate,
            edges,
            (duplicate, duplicate),
            baseline_snapshot_sha256="d" * 64,
            minimum_log_delta=0.01,
            executable="/not/reached",
        )


def test_rejects_authority_escalation() -> None:
    with pytest.raises(ValueError, match="cannot grant authority"):
        PerturbationScenario("delta-scenario:forbidden", authority=True)


def test_real_rust_subprocess_builds_deterministic_robustness_receipt() -> None:
    binary = os.environ.get("CODEX_DELTA_VERIFIER_BIN")
    if not binary:
        pytest.skip("Rust verifier binary not provided")

    edges, candidate, receipt = _fixture()
    scenarios = (
        PerturbationScenario("delta-scenario:baseline"),
        PerturbationScenario(
            "delta-scenario:collapse",
            rate_shift_bps=(-100.0, -100.0, -100.0),
            slippage_shift_bps=(25.0, 25.0, 25.0),
            latency_shift_bps=(10.0, 10.0, 10.0),
            gas_penalty_log_shift=0.02,
        ),
    )
    kwargs = {
        "baseline_snapshot_sha256": "d" * 64,
        "minimum_log_delta": 0.01,
        "executable": Path(binary).resolve(),
    }

    first = evaluate_candidate_robustness(receipt, candidate, edges, scenarios, **kwargs)
    second = evaluate_candidate_robustness(receipt, candidate, edges, scenarios, **kwargs)

    assert first == second
    assert first.scenario_count == 2
    assert first.survival_count == 1
    assert first.survival_rate == pytest.approx(0.5)
    assert first.robustness_class == "conditional"
    assert first.worst_case_log_delta < first.median_log_delta
    assert first.margin_failure_reasons["below_minimum_margin"] == 1
    assert first.results[0].scenario.scenario_id == "delta-scenario:baseline"
    assert first.results[1].scenario.scenario_id == "delta-scenario:collapse"
    assert all(abs(result.delta_drift) < 1e-12 for result in first.results)
    assert first.authority is False
