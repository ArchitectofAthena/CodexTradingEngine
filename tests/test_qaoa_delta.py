from __future__ import annotations

import itertools
import math

import pytest

from eve_q.qaoa_delta import (
    MarketEdge,
    QuboModel,
    TriangularCycle,
    build_cycle_selection_qubo,
    enumerate_triangular_cycles,
    qubo_to_ising,
    solve_qubo_exact,
)


def _cycle(candidate_id: str, score: float, suffix: str) -> TriangularCycle:
    return TriangularCycle(
        candidate_id=candidate_id,
        edge_ids=(f"{suffix}:a", f"{suffix}:b", f"{suffix}:c"),
        asset_path=("USD", "ETH", "BTC", "USD"),
        net_multiplier=math.exp(score),
        net_log_delta=score,
    )


def test_enumerates_profitable_triangular_delta() -> None:
    edges = (
        MarketEdge("usd-eth", "USD", "ETH", 0.0005, venue="alpha"),
        MarketEdge("eth-btc", "ETH", "BTC", 0.05, venue="beta"),
        MarketEdge("btc-usd", "BTC", "USD", 41_000.0, venue="gamma"),
    )

    cycles = enumerate_triangular_cycles(edges)

    assert len(cycles) == 1
    assert cycles[0].asset_path[0] == cycles[0].asset_path[-1]
    assert cycles[0].net_multiplier == pytest.approx(1.025)
    assert cycles[0].net_log_delta == pytest.approx(math.log(1.025))
    assert cycles[0].profitable is True
    assert cycles[0].authority is False


def test_cost_assumptions_can_remove_apparent_profit() -> None:
    edges = (
        MarketEdge(
            "usd-eth",
            "USD",
            "ETH",
            0.0005,
            fee_bps=50.0,
            slippage_bps=50.0,
            venue="alpha",
        ),
        MarketEdge(
            "eth-btc",
            "ETH",
            "BTC",
            0.05,
            fee_bps=50.0,
            slippage_bps=50.0,
            venue="beta",
        ),
        MarketEdge(
            "btc-usd",
            "BTC",
            "USD",
            40_100.0,
            fee_bps=50.0,
            slippage_bps=50.0,
            venue="gamma",
        ),
    )

    cycles = enumerate_triangular_cycles(edges)

    assert len(cycles) == 1
    assert cycles[0].profitable is False


def test_cycle_enumeration_is_rotation_deduplicated() -> None:
    edges = (
        MarketEdge("a-b", "A", "B", 2.0, venue="one"),
        MarketEdge("b-c", "B", "C", 2.0, venue="two"),
        MarketEdge("c-a", "C", "A", 0.3, venue="three"),
    )

    assert len(enumerate_triangular_cycles(edges)) == 1


def test_exact_fallback_selects_best_positive_cycle() -> None:
    cycles = (
        _cycle("triangle:strong", 0.025, "strong"),
        _cycle("triangle:weak", 0.010, "weak"),
    )
    model = build_cycle_selection_qubo(cycles)

    solution = solve_qubo_exact(model, cycles)

    assert solution.selected_candidate_ids == ("triangle:strong",)
    assert solution.total_log_delta == pytest.approx(0.025)
    assert solution.solver == "classical-exact-fallback"
    assert solution.authority is False


def test_exact_fallback_selects_nothing_when_all_cycles_are_negative() -> None:
    cycles = (
        _cycle("triangle:loss-a", -0.01, "loss-a"),
        _cycle("triangle:loss-b", -0.02, "loss-b"),
    )
    model = build_cycle_selection_qubo(cycles)

    solution = solve_qubo_exact(model, cycles)

    assert solution.selected_candidate_ids == ()
    assert solution.total_log_delta == 0.0


def test_qubo_and_ising_energies_are_equivalent() -> None:
    cycles = (
        _cycle("triangle:a", 0.03, "a"),
        _cycle("triangle:b", 0.02, "b"),
        _cycle("triangle:c", -0.01, "c"),
    )
    qubo = build_cycle_selection_qubo(cycles, selection_penalty=3.0)
    ising = qubo_to_ising(qubo)

    for bit_tuple in itertools.product((0, 1), repeat=len(qubo.variable_order)):
        bits = dict(zip(qubo.variable_order, bit_tuple, strict=True))
        spins = {name: 1 - 2 * bit for name, bit in bits.items()}
        assert ising.energy(spins) == pytest.approx(qubo.energy(bits))


def test_shared_edges_receive_additional_conflict_penalty() -> None:
    first = _cycle("triangle:first", 0.02, "first")
    second = TriangularCycle(
        candidate_id="triangle:second",
        edge_ids=(first.edge_ids[0], "second:b", "second:c"),
        asset_path=("USD", "SOL", "BTC", "USD"),
        net_multiplier=math.exp(0.019),
        net_log_delta=0.019,
    )

    model = build_cycle_selection_qubo(
        (first, second), selection_penalty=2.0, conflict_penalty=7.0
    )

    assert model.quadratic[("triangle:first", "triangle:second")] == pytest.approx(9.0)


def test_authority_escalation_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot grant authority"):
        MarketEdge(
            "usd-eth",
            "USD",
            "ETH",
            0.0005,
            venue="alpha",
            authority=True,
        )

    with pytest.raises(ValueError, match="cannot grant authority"):
        QuboModel(
            variable_order=("x",),
            linear={"x": -1.0},
            quadratic={},
            authority=True,
        )
