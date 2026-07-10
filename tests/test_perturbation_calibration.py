from __future__ import annotations

import pytest

from eve_q.perturbation_calibration import (
    HistoricalEdgeObservation,
    HistoricalMarketObservation,
    PerturbationCalibrationPolicy,
    calibrate_perturbation_scenarios,
)
from eve_q.qaoa_delta import MarketEdge, enumerate_triangular_cycles


def _fixture():
    edges = (
        MarketEdge("usd-eth", "USD", "ETH", 0.0005, venue="alpha"),
        MarketEdge("eth-btc", "ETH", "BTC", 0.05, venue="beta"),
        MarketEdge("btc-usd", "BTC", "USD", 41_000.0, venue="gamma"),
    )
    candidate = enumerate_triangular_cycles(edges)[0]
    baseline_by_id = {edge.edge_id: edge for edge in edges}

    observations = []
    for index, adverse_bps in enumerate((10.0, 20.0, 30.0), start=1):
        observed_edges = tuple(
            HistoricalEdgeObservation(
                edge_id=edge_id,
                quoted_rate=baseline_by_id[edge_id].quoted_rate * (1.0 - adverse_bps / 10_000.0),
                fee_bps=float(index),
                slippage_bps=float(index * 2),
                latency_penalty_bps=float(index * 3),
            )
            for edge_id in reversed(candidate.edge_ids)
        )
        observations.append(
            HistoricalMarketObservation(
                observation_id=f"market-observation:{index}",
                observed_at=f"2026-07-0{index}T00:00:00Z",
                edges=observed_edges,
                gas_penalty_log=index * 0.001,
                source_sha256=f"{index}" * 64,
            )
        )
    return edges, candidate, tuple(observations)


def test_calibration_is_deterministic_and_order_independent() -> None:
    edges, candidate, observations = _fixture()

    first = calibrate_perturbation_scenarios(
        candidate,
        edges,
        observations,
        baseline_snapshot_sha256="a" * 64,
    )
    second = calibrate_perturbation_scenarios(
        candidate,
        tuple(reversed(edges)),
        tuple(reversed(observations)),
        baseline_snapshot_sha256="a" * 64,
    )

    assert first == second
    assert first.observation_count == 3
    assert first.observation_ids == (
        "market-observation:1",
        "market-observation:2",
        "market-observation:3",
    )
    assert len(first.scenarios) == 4
    assert first.scenarios[0].scenario_id == "delta-scenario:calibrated-baseline"
    assert all(scenario.authority is False for scenario in first.scenarios)
    assert first.authority is False


def test_calibration_derives_expected_adverse_quantiles() -> None:
    edges, candidate, observations = _fixture()

    receipt = calibrate_perturbation_scenarios(
        candidate,
        edges,
        observations,
        baseline_snapshot_sha256="b" * 64,
    )

    median = receipt.scenarios[1]
    assert median.scenario_id == "delta-scenario:calibrated-q5000"
    assert median.rate_shift_bps == pytest.approx((-20.0, -20.0, -20.0))
    assert median.fee_shift_bps == pytest.approx((2.0, 2.0, 2.0))
    assert median.slippage_shift_bps == pytest.approx((4.0, 4.0, 4.0))
    assert median.latency_shift_bps == pytest.approx((6.0, 6.0, 6.0))
    assert median.gas_penalty_log_shift == pytest.approx(0.002)

    hard = receipt.scenarios[-1]
    assert hard.scenario_id == "delta-scenario:calibrated-q9500"
    assert hard.rate_shift_bps == pytest.approx((-29.0, -29.0, -29.0))
    assert hard.fee_shift_bps == pytest.approx((2.9, 2.9, 2.9))
    assert hard.slippage_shift_bps == pytest.approx((5.8, 5.8, 5.8))
    assert hard.latency_shift_bps == pytest.approx((8.7, 8.7, 8.7))
    assert hard.gas_penalty_log_shift == pytest.approx(0.0029)


def test_calibration_clips_to_declared_policy_bounds() -> None:
    edges, candidate, observations = _fixture()
    policy = PerturbationCalibrationPolicy(
        quantiles=(0.95,),
        minimum_observations=3,
        max_abs_rate_shift_bps=15.0,
        max_cost_shift_bps=4.0,
        max_gas_shift_log=0.002,
    )

    receipt = calibrate_perturbation_scenarios(
        candidate,
        edges,
        observations,
        baseline_snapshot_sha256="c" * 64,
        policy=policy,
    )

    scenario = receipt.scenarios[1]
    assert scenario.rate_shift_bps == pytest.approx((-15.0, -15.0, -15.0))
    assert scenario.fee_shift_bps == pytest.approx((2.9, 2.9, 2.9))
    assert scenario.slippage_shift_bps == pytest.approx((4.0, 4.0, 4.0))
    assert scenario.latency_shift_bps == pytest.approx((4.0, 4.0, 4.0))
    assert scenario.gas_penalty_log_shift == pytest.approx(0.002)
    assert receipt.clipped_counts["rate_shift_bps"] == 3
    assert receipt.clipped_counts["slippage_shift_bps"] == 3
    assert receipt.clipped_counts["latency_shift_bps"] == 3
    assert receipt.clipped_counts["gas_penalty_log_shift"] == 1


def test_calibration_rejects_route_mismatch_and_authority_escalation() -> None:
    edges, candidate, observations = _fixture()
    mismatched = HistoricalMarketObservation(
        observation_id="market-observation:mismatch",
        observed_at="2026-07-04T00:00:00Z",
        edges=(
            HistoricalEdgeObservation("wrong-a", 1.0),
            HistoricalEdgeObservation("wrong-b", 1.0),
            HistoricalEdgeObservation("wrong-c", 1.0),
        ),
        gas_penalty_log=0.0,
        source_sha256="d" * 64,
    )

    with pytest.raises(ValueError, match="must match the candidate edge set"):
        calibrate_perturbation_scenarios(
            candidate,
            edges,
            observations[:2] + (mismatched,),
            baseline_snapshot_sha256="d" * 64,
        )

    with pytest.raises(ValueError, match="cannot grant authority"):
        HistoricalEdgeObservation("forbidden", 1.0, authority=True)

    with pytest.raises(ValueError, match="cannot grant authority"):
        PerturbationCalibrationPolicy(authority=True)
