from __future__ import annotations

import math

import pytest

from eve_q.qaoa_delta import TriangularCycle, build_cycle_selection_qubo
from eve_q.qaoa_sampling import (
    build_qaoa_confidence_receipt,
    decode_probability_distribution,
    decode_qiskit_bitstring,
    qubo_model_sha256,
)


def _cycle(candidate_id: str, score: float, suffix: str) -> TriangularCycle:
    return TriangularCycle(
        candidate_id=candidate_id,
        edge_ids=(f"{suffix}:a", f"{suffix}:b", f"{suffix}:c"),
        asset_path=("USD", "ETH", "BTC", "USD"),
        net_multiplier=math.exp(score),
        net_log_delta=score,
    )


def _fixture():
    cycles = (
        _cycle("triangle:strong", 0.025, "strong"),
        _cycle("triangle:weak", 0.010, "weak"),
    )
    return cycles, build_cycle_selection_qubo(cycles)


def test_decodes_qiskit_big_endian_bitstrings() -> None:
    bits = decode_qiskit_bitstring("01", ("triangle:first", "triangle:second"))

    assert bits == {"triangle:first": 1, "triangle:second": 0}


def test_probability_distribution_is_normalized_and_deterministic() -> None:
    cycles, model = _fixture()

    samples, expected_energy = decode_probability_distribution(
        {"01": 8.0, "10": 2.0},
        model,
        cycles,
    )

    assert samples[0].qiskit_bitstring == "01"
    assert samples[0].selected_candidate_ids == ("triangle:strong",)
    assert samples[0].probability == pytest.approx(0.8)
    assert samples[0].authority is False
    assert expected_energy == pytest.approx(
        0.8 * model.energy({"triangle:strong": 1, "triangle:weak": 0})
        + 0.2 * model.energy({"triangle:strong": 0, "triangle:weak": 1})
    )


def test_confidence_receipt_compares_qaoa_with_classical_truth() -> None:
    cycles, model = _fixture()

    receipt = build_qaoa_confidence_receipt(
        model,
        cycles,
        {"01": 0.75, "10": 0.25},
        solver="fixture-sampler",
        reps=1,
        parameter_order=("beta[0]", "gamma[0]"),
        parameter_values=(0.1, 0.2),
    )

    assert receipt.receipt_id.startswith("qaoa-confidence:")
    assert receipt.model_sha256 == qubo_model_sha256(model)
    assert receipt.best_sample.selected_candidate_ids == ("triangle:strong",)
    assert receipt.classical_selection.selected_candidate_ids == ("triangle:strong",)
    assert receipt.energy_gap_to_classical >= 0.0
    assert receipt.authority is False
    assert receipt.as_dict()["authority"] is False


def test_model_digest_changes_when_coefficients_change() -> None:
    cycles, model = _fixture()
    changed = build_cycle_selection_qubo(cycles, selection_penalty=11.0)

    assert qubo_model_sha256(model) != qubo_model_sha256(changed)


def test_rejects_invalid_probability_surfaces() -> None:
    cycles, model = _fixture()

    with pytest.raises(ValueError, match="invalid bitstring"):
        decode_probability_distribution({"2": 1.0}, model, cycles)

    with pytest.raises(ValueError, match="positive mass"):
        decode_probability_distribution({"00": 0.0}, model, cycles)

    with pytest.raises(ValueError, match="finite and non-negative"):
        decode_probability_distribution({"00": -1.0}, model, cycles)


def test_rejects_cycle_model_mismatch() -> None:
    cycles, model = _fixture()

    with pytest.raises(ValueError, match="cycles must match"):
        decode_probability_distribution({"01": 1.0}, model, cycles[:1])
