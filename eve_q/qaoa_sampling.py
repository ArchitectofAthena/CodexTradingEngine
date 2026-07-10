"""Deterministic, simulation-only QAOA sampling and confidence receipts.

This module turns an unbound QAOA ansatz into reviewable candidate evidence. It
may simulate local statevectors and compare them with the classical exact
fallback. It cannot access wallets, submit transactions, borrow capital, or
grant execution authority.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from eve_q.qaoa_delta import (
    DeltaSelection,
    QuboModel,
    TriangularCycle,
    build_qiskit_qaoa_ansatz,
    solve_qubo_exact,
)


@dataclass(frozen=True)
class SampledAssignment:
    """One decoded Qiskit bitstring and its model-relative evidence."""

    qiskit_bitstring: str
    assignment: tuple[int, ...]
    probability: float
    energy: float
    selected_candidate_ids: tuple[str, ...]
    total_log_delta: float
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.qiskit_bitstring or any(bit not in "01" for bit in self.qiskit_bitstring):
            raise ValueError("qiskit_bitstring must be a non-empty binary string")
        if any(bit not in (0, 1) for bit in self.assignment):
            raise ValueError("assignment must be binary")
        if not math.isfinite(self.probability) or not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be finite in [0, 1]")
        if not math.isfinite(self.energy):
            raise ValueError("energy must be finite")
        if not math.isfinite(self.total_log_delta):
            raise ValueError("total_log_delta must be finite")
        if self.authority:
            raise ValueError("sampled assignments cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "qiskit_bitstring": self.qiskit_bitstring,
            "assignment": list(self.assignment),
            "probability": self.probability,
            "energy": self.energy,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "total_log_delta": self.total_log_delta,
            "authority": False,
        }


@dataclass(frozen=True)
class QaoaConfidenceReceipt:
    """Review artifact comparing a sampled QAOA result with exact classical truth."""

    receipt_id: str
    model_sha256: str
    solver: str
    reps: int
    parameter_order: tuple[str, ...]
    parameter_values: tuple[float, ...]
    expected_energy: float
    best_sample: SampledAssignment
    classical_selection: DeltaSelection
    energy_gap_to_classical: float
    top_samples: tuple[SampledAssignment, ...]
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.receipt_id.startswith("qaoa-confidence:"):
            raise ValueError("receipt_id must use the qaoa-confidence namespace")
        if len(self.model_sha256) != 64:
            raise ValueError("model_sha256 must be a SHA-256 hex digest")
        if not self.solver.strip():
            raise ValueError("solver is required")
        if self.reps < 1:
            raise ValueError("reps must be at least 1")
        if len(self.parameter_order) != len(self.parameter_values):
            raise ValueError("parameter names and values must have matching lengths")
        if not all(math.isfinite(value) for value in self.parameter_values):
            raise ValueError("parameter values must be finite")
        if not math.isfinite(self.expected_energy):
            raise ValueError("expected_energy must be finite")
        if not math.isfinite(self.energy_gap_to_classical):
            raise ValueError("energy_gap_to_classical must be finite")
        if not self.top_samples:
            raise ValueError("top_samples cannot be empty")
        if self.authority:
            raise ValueError("QAOA confidence receipts cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "receipt_id": self.receipt_id,
            "model_sha256": self.model_sha256,
            "solver": self.solver,
            "reps": self.reps,
            "parameter_order": list(self.parameter_order),
            "parameter_values": list(self.parameter_values),
            "expected_energy": self.expected_energy,
            "best_sample": self.best_sample.as_dict(),
            "classical_selection": {
                "selected_candidate_ids": list(self.classical_selection.selected_candidate_ids),
                "energy": self.classical_selection.energy,
                "total_log_delta": self.classical_selection.total_log_delta,
                "solver": self.classical_selection.solver,
                "authority": False,
            },
            "energy_gap_to_classical": self.energy_gap_to_classical,
            "top_samples": [sample.as_dict() for sample in self.top_samples],
            "authority": False,
        }


def qubo_model_sha256(model: QuboModel) -> str:
    """Return a stable digest over the complete QUBO coefficient surface."""

    payload = {
        "variable_order": list(model.variable_order),
        "linear": [[name, model.linear[name]] for name in model.variable_order],
        "quadratic": [
            [left, right, coefficient]
            for (left, right), coefficient in sorted(model.quadratic.items())
        ],
        "constant": model.constant,
        "authority": False,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def decode_qiskit_bitstring(bitstring: str, variable_order: Sequence[str]) -> dict[str, int]:
    """Decode Qiskit's big-endian display order into qubit-index variable order."""

    if len(bitstring) != len(variable_order):
        raise ValueError("bitstring length must match the QUBO variable count")
    if any(bit not in "01" for bit in bitstring):
        raise ValueError("bitstring must contain only zeroes and ones")
    return {
        name: int(bit)
        for name, bit in zip(variable_order, reversed(bitstring), strict=True)
    }


def decode_probability_distribution(
    probabilities: Mapping[str, float],
    model: QuboModel,
    cycles: Sequence[TriangularCycle],
    *,
    top_k: int = 8,
) -> tuple[tuple[SampledAssignment, ...], float]:
    """Normalize and deterministically decode a Qiskit probability distribution."""

    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if not probabilities:
        raise ValueError("probability distribution cannot be empty")

    cycle_by_id = {cycle.candidate_id: cycle for cycle in cycles}
    if set(cycle_by_id) != set(model.variable_order):
        raise ValueError("cycles must match the QUBO variable set")

    normalized_input: list[tuple[str, float]] = []
    total_probability = 0.0
    for bitstring, probability in probabilities.items():
        if len(bitstring) != len(model.variable_order) or any(bit not in "01" for bit in bitstring):
            raise ValueError("distribution contains an invalid bitstring")
        if not math.isfinite(probability) or probability < 0.0:
            raise ValueError("distribution probabilities must be finite and non-negative")
        normalized_input.append((bitstring, probability))
        total_probability += probability
    if total_probability <= 0.0:
        raise ValueError("probability distribution must have positive mass")

    samples: list[SampledAssignment] = []
    expected_energy = 0.0
    for bitstring, raw_probability in normalized_input:
        probability = raw_probability / total_probability
        bits = decode_qiskit_bitstring(bitstring, model.variable_order)
        energy = model.energy(bits)
        selected = tuple(name for name in model.variable_order if bits[name] == 1)
        total_log_delta = sum(cycle_by_id[name].net_log_delta for name in selected)
        assignment = tuple(bits[name] for name in model.variable_order)
        sample = SampledAssignment(
            qiskit_bitstring=bitstring,
            assignment=assignment,
            probability=probability,
            energy=energy,
            selected_candidate_ids=selected,
            total_log_delta=total_log_delta,
        )
        samples.append(sample)
        expected_energy += probability * energy

    samples.sort(
        key=lambda sample: (
            -sample.probability,
            sample.energy,
            sample.qiskit_bitstring,
        )
    )
    return tuple(samples[:top_k]), expected_energy


def build_qaoa_confidence_receipt(
    model: QuboModel,
    cycles: Sequence[TriangularCycle],
    probabilities: Mapping[str, float],
    *,
    solver: str,
    reps: int,
    parameter_order: Sequence[str] = (),
    parameter_values: Sequence[float] = (),
    top_k: int = 8,
    expected_energy: float | None = None,
    classical_max_variables: int = 24,
) -> QaoaConfidenceReceipt:
    """Build a deterministic evidence receipt from one sampled distribution."""

    top_samples, decoded_expected_energy = decode_probability_distribution(
        probabilities,
        model,
        cycles,
        top_k=top_k,
    )
    if expected_energy is None:
        expected_energy = decoded_expected_energy
    elif not math.isclose(expected_energy, decoded_expected_energy, abs_tol=1e-12):
        raise ValueError("provided expected_energy does not match the decoded distribution")

    classical = solve_qubo_exact(
        model,
        cycles,
        max_variables=classical_max_variables,
    )
    model_digest = qubo_model_sha256(model)
    receipt_seed = {
        "model_sha256": model_digest,
        "solver": solver,
        "reps": reps,
        "parameter_order": list(parameter_order),
        "parameter_values": list(parameter_values),
        "expected_energy": expected_energy,
        "best_sample": top_samples[0].as_dict(),
        "classical_energy": classical.energy,
        "authority": False,
    }
    encoded = json.dumps(receipt_seed, sort_keys=True, separators=(",", ":"), allow_nan=False)
    receipt_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    return QaoaConfidenceReceipt(
        receipt_id=f"qaoa-confidence:{receipt_hash[:24]}",
        model_sha256=model_digest,
        solver=solver,
        reps=reps,
        parameter_order=tuple(parameter_order),
        parameter_values=tuple(parameter_values),
        expected_energy=expected_energy,
        best_sample=top_samples[0],
        classical_selection=classical,
        energy_gap_to_classical=expected_energy - classical.energy,
        top_samples=top_samples,
    )


def optimize_qaoa_statevector(
    model: QuboModel,
    cycles: Sequence[TriangularCycle],
    *,
    reps: int = 1,
    parameter_grid: Sequence[float] | None = None,
    max_evaluations: int = 4096,
    top_k: int = 8,
) -> QaoaConfidenceReceipt:
    """Grid-search a local QAOA statevector and emit a confidence receipt.

    This is a bounded research optimizer. It performs no remote quantum call and
    no execution action. Parameter ties are resolved lexicographically.
    """

    if not model.variable_order:
        raise ValueError("QAOA optimization requires at least one variable")
    if max_evaluations < 1:
        raise ValueError("max_evaluations must be at least 1")
    grid = tuple(parameter_grid or (0.0, math.pi / 4.0, math.pi / 2.0, 3.0 * math.pi / 4.0))
    if not grid or not all(math.isfinite(value) for value in grid):
        raise ValueError("parameter_grid must contain finite values")

    try:
        from qiskit.quantum_info import Statevector
    except ImportError as exc:  # pragma: no cover - optional dependency boundary
        raise RuntimeError("Qiskit is not installed; install the optional quantum extra") from exc

    ansatz, _ = build_qiskit_qaoa_ansatz(model, reps=reps)
    parameters = tuple(ansatz.parameters)
    evaluation_count = len(grid) ** len(parameters)
    if evaluation_count > max_evaluations:
        raise ValueError(
            f"parameter grid requires {evaluation_count} evaluations; limit is {max_evaluations}"
        )

    best_values: tuple[float, ...] | None = None
    best_probabilities: Mapping[str, float] | None = None
    best_expected_energy = math.inf

    for values in itertools.product(grid, repeat=len(parameters)):
        bound = ansatz.assign_parameters(dict(zip(parameters, values, strict=True)), inplace=False)
        probabilities = Statevector.from_instruction(bound).probabilities_dict()
        _, expected_energy = decode_probability_distribution(
            probabilities,
            model,
            cycles,
            top_k=top_k,
        )
        if expected_energy < best_expected_energy - 1e-15 or (
            math.isclose(expected_energy, best_expected_energy, abs_tol=1e-15)
            and (best_values is None or values < best_values)
        ):
            best_values = tuple(float(value) for value in values)
            best_probabilities = probabilities
            best_expected_energy = expected_energy

    assert best_values is not None
    assert best_probabilities is not None
    return build_qaoa_confidence_receipt(
        model,
        cycles,
        best_probabilities,
        solver="qiskit-statevector-grid",
        reps=reps,
        parameter_order=tuple(str(parameter) for parameter in parameters),
        parameter_values=best_values,
        top_k=top_k,
        expected_energy=best_expected_energy,
    )
