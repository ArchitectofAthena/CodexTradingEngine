from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from eve_q.qaoa_delta import (
    MarketEdge,
    build_cycle_selection_qubo,
    enumerate_triangular_cycles,
)
from eve_q.qaoa_sampling import build_qaoa_confidence_receipt
from eve_q.rust_repricing import build_repricing_request, run_rust_repricing


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


def test_builds_deterministic_hash_bound_request() -> None:
    edges, candidate, receipt = _fixture()

    first = build_repricing_request(
        receipt,
        candidate,
        edges,
        snapshot_sha256="c" * 64,
        minimum_log_delta=0.01,
    )
    second = build_repricing_request(
        receipt,
        candidate,
        edges,
        snapshot_sha256="c" * 64,
        minimum_log_delta=0.01,
    )

    assert first == second
    assert first.request_id.startswith("delta-reprice:")
    assert first.candidate_id == candidate.candidate_id
    assert first.model_sha256 == receipt.model_sha256
    assert first.authority is False


def test_rejects_candidate_not_selected_by_confidence_receipt() -> None:
    edges, candidate, receipt = _fixture()
    unselected = build_qaoa_confidence_receipt(
        build_cycle_selection_qubo((candidate,)),
        (candidate,),
        {"0": 1.0},
        solver="test-distribution",
        reps=1,
    )

    with pytest.raises(ValueError, match="must be selected"):
        build_repricing_request(
            unselected,
            candidate,
            edges,
            snapshot_sha256="c" * 64,
            minimum_log_delta=0.01,
        )


def test_requires_absolute_explicit_executable() -> None:
    edges, candidate, receipt = _fixture()
    request = build_repricing_request(
        receipt,
        candidate,
        edges,
        snapshot_sha256="c" * 64,
        minimum_log_delta=0.01,
    )

    with pytest.raises(ValueError, match="must be absolute"):
        run_rust_repricing(
            request,
            candidate,
            executable="codex-delta-verifier",
        )


def test_real_rust_subprocess_round_trip_when_binary_is_provided() -> None:
    binary = os.environ.get("CODEX_DELTA_VERIFIER_BIN")
    if not binary:
        pytest.skip("Rust verifier binary not provided")

    edges, candidate, receipt = _fixture()
    request = build_repricing_request(
        receipt,
        candidate,
        edges,
        snapshot_sha256="c" * 64,
        minimum_log_delta=0.01,
    )

    evidence = run_rust_repricing(
        request,
        candidate,
        executable=Path(binary).resolve(),
    )

    assert evidence.status == "verified"
    assert evidence.passes_margin is True
    assert evidence.net_log_delta == pytest.approx(candidate.net_log_delta)
    assert evidence.delta_drift == pytest.approx(0.0)
    assert evidence.authority is False


def test_real_rust_subprocess_rejects_candidate_identity_drift() -> None:
    binary = os.environ.get("CODEX_DELTA_VERIFIER_BIN")
    if not binary:
        pytest.skip("Rust verifier binary not provided")

    edges, candidate, receipt = _fixture()
    request = build_repricing_request(
        receipt,
        candidate,
        edges,
        snapshot_sha256="c" * 64,
        minimum_log_delta=0.01,
    )
    altered = replace(request, candidate_id="triangle:00000000000000000000")

    with pytest.raises(RuntimeError, match="rejected the request"):
        run_rust_repricing(
            altered,
            candidate,
            executable=Path(binary).resolve(),
        )
