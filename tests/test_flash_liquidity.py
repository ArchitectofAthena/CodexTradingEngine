from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from eve_q.flash_liquidity import (
    FlashAmountBucket,
    FlashLiquidityProvider,
    build_flash_liquidity_qubo,
    build_flash_verification_request,
    enumerate_flash_liquidity_candidates,
    run_rust_flash_verification,
)
from eve_q.qaoa_delta import MarketEdge, enumerate_triangular_cycles, solve_qubo_exact
from eve_q.qaoa_sampling import build_qaoa_confidence_receipt


def _fixture():
    edges = (
        MarketEdge("usd-eth", "USD", "ETH", 0.0005, venue="alpha"),
        MarketEdge("eth-btc", "ETH", "BTC", 0.05, venue="beta"),
        MarketEdge("btc-usd", "BTC", "USD", 41_000.0, venue="gamma"),
    )
    route = enumerate_triangular_cycles(edges)[0]
    providers = (
        FlashLiquidityProvider(
            "flash-provider:cheap",
            fee_bps=9.0,
            capacity_by_asset={"USD": 5_000.0},
        ),
        FlashLiquidityProvider(
            "flash-provider:deep",
            fee_bps=30.0,
            capacity_by_asset={"USD": 20_000.0},
        ),
    )
    buckets = (
        FlashAmountBucket("flash-bucket:usd-1000", "USD", 1_000.0),
        FlashAmountBucket("flash-bucket:usd-10000", "USD", 10_000.0),
    )
    candidates = enumerate_flash_liquidity_candidates((route,), providers, buckets)
    return edges, route, providers, buckets, candidates


def _receipt_for(candidates, selected_candidate_id):
    model = build_flash_liquidity_qubo(candidates)
    qaoa_cycles = tuple(candidate.as_qaoa_cycle() for candidate in candidates)
    assignment = {
        name: int(name == selected_candidate_id)
        for name in model.variable_order
    }
    bitstring = "".join(str(assignment[name]) for name in reversed(model.variable_order))
    receipt = build_qaoa_confidence_receipt(
        model,
        qaoa_cycles,
        {bitstring: 1.0},
        solver="test-flash-distribution",
        reps=1,
    )
    return model, receipt


def test_enumerates_route_provider_bucket_geometry_deterministically() -> None:
    _, route, providers, buckets, first = _fixture()
    second = enumerate_flash_liquidity_candidates((route,), providers, buckets)

    assert first == second
    assert len(first) == 4
    assert len({candidate.candidate_id for candidate in first}) == 4
    assert all(candidate.borrowed_asset == "USD" for candidate in first)
    assert all(candidate.authority is False for candidate in first)
    assert sum(candidate.feasible for candidate in first) == 3


def test_qubo_exactly_selects_a_feasible_low_fee_geometry() -> None:
    _, _, _, _, candidates = _fixture()
    model = build_flash_liquidity_qubo(candidates)
    qaoa_cycles = tuple(candidate.as_qaoa_cycle() for candidate in candidates)

    selection = solve_qubo_exact(model, qaoa_cycles)

    assert len(selection.selected_candidate_ids) == 1
    selected = next(
        candidate
        for candidate in candidates
        if candidate.candidate_id == selection.selected_candidate_ids[0]
    )
    assert selected.feasible is True
    assert selected.provider_id == "flash-provider:cheap"
    assert selected.amount_bucket_id == "flash-bucket:usd-1000"
    assert selected.projected_net_profit > 0.0
    assert selection.authority is False


def test_rejects_authority_and_invalid_provider_costs() -> None:
    with pytest.raises(ValueError, match="cannot grant authority"):
        FlashLiquidityProvider(
            "flash-provider:bad",
            fee_bps=1.0,
            capacity_by_asset={"USD": 1_000.0},
            authority=True,
        )
    with pytest.raises(ValueError, match="fee_bps"):
        FlashLiquidityProvider(
            "flash-provider:bad-fee",
            fee_bps=10_000.0,
            capacity_by_asset={"USD": 1_000.0},
        )


def test_builds_hash_bound_flash_verification_request() -> None:
    edges, _, _, _, candidates = _fixture()
    selected = next(
        candidate
        for candidate in candidates
        if candidate.provider_id == "flash-provider:cheap" and candidate.feasible
    )
    _, receipt = _receipt_for(candidates, selected.candidate_id)

    first = build_flash_verification_request(
        receipt,
        selected,
        edges,
        snapshot_sha256="d" * 64,
        gas_penalty_log=0.0,
        minimum_net_profit=1.0,
    )
    second = build_flash_verification_request(
        receipt,
        selected,
        edges,
        snapshot_sha256="d" * 64,
        gas_penalty_log=0.0,
        minimum_net_profit=1.0,
    )

    assert first == second
    assert first.request_id.startswith("flash-verify:")
    assert first.flash_candidate.candidate_id == selected.candidate_id
    assert first.authority is False


def test_rejects_candidate_not_selected_by_qaoa_receipt() -> None:
    edges, _, _, _, candidates = _fixture()
    selected = candidates[0]
    other = candidates[1]
    _, receipt = _receipt_for(candidates, selected.candidate_id)

    with pytest.raises(ValueError, match="must be selected"):
        build_flash_verification_request(
            receipt,
            other,
            edges,
            snapshot_sha256="d" * 64,
            gas_penalty_log=0.0,
        )


def test_real_rust_flash_verifier_round_trip_when_binary_is_provided() -> None:
    binary = os.environ.get("CODEX_FLASH_LIQUIDITY_VERIFIER_BIN")
    if not binary:
        pytest.skip("Rust flash-liquidity verifier binary not provided")

    edges, _, _, _, candidates = _fixture()
    selected = next(
        candidate
        for candidate in candidates
        if candidate.provider_id == "flash-provider:cheap" and candidate.feasible
    )
    _, receipt = _receipt_for(candidates, selected.candidate_id)
    request = build_flash_verification_request(
        receipt,
        selected,
        edges,
        snapshot_sha256="d" * 64,
        gas_penalty_log=0.0,
        minimum_net_profit=1.0,
    )

    evidence = run_rust_flash_verification(
        request,
        executable=Path(binary).resolve(),
    )

    assert evidence.capacity_ok is True
    assert evidence.borrowed_asset_matches_route is True
    assert evidence.repayment_feasible is True
    assert evidence.net_profit == pytest.approx(selected.projected_net_profit)
    assert evidence.authority is False


def test_real_rust_flash_verifier_rejects_identity_drift() -> None:
    binary = os.environ.get("CODEX_FLASH_LIQUIDITY_VERIFIER_BIN")
    if not binary:
        pytest.skip("Rust flash-liquidity verifier binary not provided")

    edges, _, _, _, candidates = _fixture()
    selected = next(candidate for candidate in candidates if candidate.feasible)
    _, receipt = _receipt_for(candidates, selected.candidate_id)
    request = build_flash_verification_request(
        receipt,
        selected,
        edges,
        snapshot_sha256="d" * 64,
        gas_penalty_log=0.0,
    )
    altered_candidate = replace(
        selected,
        candidate_id="flash-geometry:00000000000000000000",
    )
    altered_request = replace(request, flash_candidate=altered_candidate)

    with pytest.raises(RuntimeError, match="rejected the request"):
        run_rust_flash_verification(
            altered_request,
            executable=Path(binary).resolve(),
        )
