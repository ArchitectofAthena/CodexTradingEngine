from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from eve_q.flash_liquidity import (
    build_flash_liquidity_qubo,
    enumerate_flash_liquidity_candidates,
)
from eve_q.hybrid_benchmark import (
    benchmark_case_from_dict,
    emit_benchmark_artifacts,
    exact_distribution,
    load_benchmark_case,
    run_seeded_benchmark,
)
from eve_q.qaoa_delta import build_cycle_selection_qubo, enumerate_triangular_cycles
from eve_q.qaoa_sampling import build_qaoa_confidence_receipt, qubo_model_sha256
from eve_q.receipt_emitter import validate_emitted_receipt


ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "benchmarks" / "seeded_market_v0_1.json"


def test_seeded_case_is_canonical_and_non_authoritative() -> None:
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    reordered = copy.deepcopy(payload)
    reordered["snapshot"]["edges"].reverse()
    reordered["historical_observations"].reverse()
    for observation in reordered["historical_observations"]:
        observation["edges"].reverse()
    reordered["flash_liquidity"]["providers"].reverse()
    reordered["flash_liquidity"]["buckets"].reverse()

    first = benchmark_case_from_dict(payload)
    second = benchmark_case_from_dict(reordered)

    assert first.as_dict() == second.as_dict()
    assert first.case_sha256 == second.case_sha256
    assert first.snapshot_sha256 == second.snapshot_sha256
    assert first.authority is False
    assert all(edge.authority is False for edge in first.edges)


def test_exact_distributions_compare_against_the_identical_qubos() -> None:
    case = load_benchmark_case(CASE_PATH)
    cycles = enumerate_triangular_cycles(
        case.edges,
        gas_penalty_log=case.gas_penalty_log,
        minimum_log_delta=case.minimum_log_delta,
    )
    route_model = build_cycle_selection_qubo(cycles)
    route_receipt = build_qaoa_confidence_receipt(
        route_model,
        cycles,
        exact_distribution(route_model, cycles),
        solver="test-seeded-exact-replay",
        reps=1,
    )

    assert route_receipt.model_sha256 == qubo_model_sha256(route_model)
    assert route_receipt.energy_gap_to_classical == pytest.approx(0.0, abs=1e-15)
    assert len(route_receipt.best_sample.selected_candidate_ids) == 1

    selected_id = route_receipt.best_sample.selected_candidate_ids[0]
    route = next(cycle for cycle in cycles if cycle.candidate_id == selected_id)
    candidates = enumerate_flash_liquidity_candidates((route,), case.providers, case.buckets)
    flash_model = build_flash_liquidity_qubo(candidates)
    flash_cycles = tuple(candidate.as_qaoa_cycle() for candidate in candidates)
    flash_receipt = build_qaoa_confidence_receipt(
        flash_model,
        flash_cycles,
        exact_distribution(flash_model, flash_cycles),
        solver="test-seeded-exact-replay",
        reps=1,
    )

    assert flash_receipt.model_sha256 == qubo_model_sha256(flash_model)
    assert flash_receipt.energy_gap_to_classical == pytest.approx(0.0, abs=1e-15)
    assert len(flash_receipt.best_sample.selected_candidate_ids) == 1
    assert flash_receipt.authority is False


def test_seeded_case_rejects_authority_escalation() -> None:
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    payload["authority"] = True

    with pytest.raises(ValueError, match="cannot grant authority"):
        benchmark_case_from_dict(payload)


def test_real_rust_benchmark_is_reproducible_and_emits_canonical_envelope(
    tmp_path: Path,
) -> None:
    route_binary = os.environ.get("CODEX_DELTA_VERIFIER_BIN")
    flash_binary = os.environ.get("CODEX_FLASH_LIQUIDITY_VERIFIER_BIN")
    if not route_binary or not flash_binary:
        pytest.skip("Rust verifier binaries not provided")

    case = load_benchmark_case(CASE_PATH)
    kwargs = {
        "route_executable": Path(route_binary).resolve(),
        "flash_executable": Path(flash_binary).resolve(),
    }
    first = run_seeded_benchmark(case, **kwargs)
    second = run_seeded_benchmark(case, **kwargs)

    assert first == second
    assert first.route_model_identity_verified is True
    assert first.flash_model_identity_verified is True
    assert first.route_confidence.energy_gap_to_classical == pytest.approx(0.0, abs=1e-15)
    assert first.flash_confidence.energy_gap_to_classical == pytest.approx(0.0, abs=1e-15)
    assert first.route_verification.passes_margin is True
    assert first.calibration.scenario_set_sha256 == first.robustness.scenario_set_sha256
    assert first.robustness.scenario_count == 4
    assert first.flash_verification.capacity_ok is True
    assert first.flash_verification.borrowed_asset_matches_route is True
    assert first.flash_verification.repayment_feasible is True
    assert first.authority is False

    receipt_path = tmp_path / "artifacts" / "hybrid_benchmark_receipt.json"
    envelope_path = tmp_path / "artifacts" / "hybrid_benchmark_envelope.json"
    envelope = emit_benchmark_artifacts(
        first,
        receipt_path=receipt_path,
        envelope_path=envelope_path,
        source_commit="f" * 40,
        source_pr=54,
        root=tmp_path,
    )

    assert receipt_path.is_file()
    assert envelope_path.is_file()
    assert envelope["artifact_type"] == "simulation_summary"
    assert envelope["mode"] == "artifact_only"
    assert envelope["human_promotion_required"] is True
    assert validate_emitted_receipt(envelope) == []
