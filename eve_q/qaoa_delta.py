"""Simulation-only QAOA price-delta triangulation primitives.

The module owns the deterministic graph, cycle, QUBO, Ising, and classical
fallback contracts. Qiskit is an optional adapter. Nothing in this module can
sign transactions, move capital, submit RPC calls, or grant authority.
"""

from __future__ import annotations

import hashlib
import itertools
import math
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

_BPS = 10_000.0


def _require_nonempty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} is required")


def _require_no_authority(authority: bool, object_name: str) -> None:
    if authority:
        raise ValueError(f"{object_name} cannot grant authority")


@dataclass(frozen=True)
class MarketEdge:
    """One directed price observation after venue-specific cost assumptions."""

    edge_id: str
    source_asset: str
    target_asset: str
    quoted_rate: float
    fee_bps: float = 0.0
    slippage_bps: float = 0.0
    latency_penalty_bps: float = 0.0
    venue: str = "unknown"
    authority: bool = False

    def __post_init__(self) -> None:
        _require_nonempty(self.edge_id, "edge_id")
        _require_nonempty(self.source_asset, "source_asset")
        _require_nonempty(self.target_asset, "target_asset")
        _require_nonempty(self.venue, "venue")
        if self.source_asset == self.target_asset:
            raise ValueError("market edges must connect distinct assets")
        if not math.isfinite(self.quoted_rate) or self.quoted_rate <= 0.0:
            raise ValueError("quoted_rate must be finite and positive")
        for field_name, value in (
            ("fee_bps", self.fee_bps),
            ("slippage_bps", self.slippage_bps),
            ("latency_penalty_bps", self.latency_penalty_bps),
        ):
            if not math.isfinite(value) or not 0.0 <= value < _BPS:
                raise ValueError(f"{field_name} must be finite in [0, 10000)")
        _require_no_authority(self.authority, "market edges")

    @property
    def effective_rate(self) -> float:
        return (
            self.quoted_rate
            * (1.0 - self.fee_bps / _BPS)
            * (1.0 - self.slippage_bps / _BPS)
            * (1.0 - self.latency_penalty_bps / _BPS)
        )


@dataclass(frozen=True)
class TriangularCycle:
    """A deterministic three-edge closed route proposed for optimization."""

    candidate_id: str
    edge_ids: tuple[str, str, str]
    asset_path: tuple[str, str, str, str]
    net_multiplier: float
    net_log_delta: float
    gas_penalty_log: float = 0.0
    authority: bool = False

    def __post_init__(self) -> None:
        _require_nonempty(self.candidate_id, "candidate_id")
        if len(set(self.edge_ids)) != 3:
            raise ValueError("triangular cycles require three distinct edges")
        if len(self.asset_path) != 4 or self.asset_path[0] != self.asset_path[-1]:
            raise ValueError("asset_path must contain a closed three-edge route")
        if len(set(self.asset_path[:-1])) != 3:
            raise ValueError("triangular cycles require three distinct assets")
        if not math.isfinite(self.net_multiplier) or self.net_multiplier <= 0.0:
            raise ValueError("net_multiplier must be finite and positive")
        if not math.isfinite(self.net_log_delta):
            raise ValueError("net_log_delta must be finite")
        if not math.isfinite(self.gas_penalty_log) or self.gas_penalty_log < 0.0:
            raise ValueError("gas_penalty_log must be finite and non-negative")
        _require_no_authority(self.authority, "cycle candidates")

    @property
    def profitable(self) -> bool:
        return self.net_log_delta > 0.0


@dataclass(frozen=True)
class QuboModel:
    """Minimization-form QUBO over triangular-cycle selection variables."""

    variable_order: tuple[str, ...]
    linear: Mapping[str, float]
    quadratic: Mapping[tuple[str, str], float]
    constant: float = 0.0
    authority: bool = False

    def __post_init__(self) -> None:
        if len(set(self.variable_order)) != len(self.variable_order):
            raise ValueError("variable_order must be unique")
        known = set(self.variable_order)
        if set(self.linear) != known:
            raise ValueError("linear coefficients must cover every variable exactly once")
        for (left, right), value in self.quadratic.items():
            if left not in known or right not in known or left == right:
                raise ValueError("quadratic terms require two distinct known variables")
            if (right, left) in self.quadratic:
                raise ValueError("quadratic terms must use one canonical orientation")
            if not math.isfinite(value):
                raise ValueError("quadratic coefficients must be finite")
        if not all(math.isfinite(value) for value in self.linear.values()):
            raise ValueError("linear coefficients must be finite")
        if not math.isfinite(self.constant):
            raise ValueError("constant must be finite")
        _require_no_authority(self.authority, "QUBO models")

    def energy(self, bits: Mapping[str, int]) -> float:
        if set(bits) != set(self.variable_order):
            raise ValueError("bits must cover every QUBO variable exactly once")
        if any(value not in (0, 1) for value in bits.values()):
            raise ValueError("QUBO assignments must be binary")
        total = self.constant
        total += sum(self.linear[name] * bits[name] for name in self.variable_order)
        total += sum(
            coefficient * bits[left] * bits[right]
            for (left, right), coefficient in self.quadratic.items()
        )
        return total


@dataclass(frozen=True)
class IsingModel:
    """Equivalent Ising energy: offset + sum(h_i z_i) + sum(J_ij z_i z_j)."""

    variable_order: tuple[str, ...]
    z_linear: Mapping[str, float]
    zz_quadratic: Mapping[tuple[str, str], float]
    offset: float
    authority: bool = False

    def __post_init__(self) -> None:
        _require_no_authority(self.authority, "Ising models")

    def energy(self, spins: Mapping[str, int]) -> float:
        if set(spins) != set(self.variable_order):
            raise ValueError("spins must cover every Ising variable exactly once")
        if any(value not in (-1, 1) for value in spins.values()):
            raise ValueError("Ising assignments must use -1 or +1")
        return (
            self.offset
            + sum(self.z_linear[name] * spins[name] for name in self.variable_order)
            + sum(
                coefficient * spins[left] * spins[right]
                for (left, right), coefficient in self.zz_quadratic.items()
            )
        )


@dataclass(frozen=True)
class DeltaSelection:
    selected_candidate_ids: tuple[str, ...]
    energy: float
    total_log_delta: float
    solver: str
    authority: bool = False

    def __post_init__(self) -> None:
        _require_nonempty(self.solver, "solver")
        _require_no_authority(self.authority, "delta selections")


def _canonical_rotation(edge_ids: tuple[str, str, str]) -> tuple[str, str, str]:
    rotations = (
        edge_ids,
        (edge_ids[1], edge_ids[2], edge_ids[0]),
        (edge_ids[2], edge_ids[0], edge_ids[1]),
    )
    return min(rotations)


def enumerate_triangular_cycles(
    edges: Iterable[MarketEdge],
    *,
    gas_penalty_log: float = 0.0,
    minimum_log_delta: float = -math.inf,
) -> tuple[TriangularCycle, ...]:
    """Enumerate unique directed three-asset cycles from a market snapshot."""

    if not math.isfinite(gas_penalty_log) or gas_penalty_log < 0.0:
        raise ValueError("gas_penalty_log must be finite and non-negative")
    if math.isnan(minimum_log_delta):
        raise ValueError("minimum_log_delta cannot be NaN")

    edge_list = tuple(edges)
    edge_ids = [edge.edge_id for edge in edge_list]
    if len(set(edge_ids)) != len(edge_ids):
        raise ValueError("edge_id values must be unique")

    by_source: dict[str, list[MarketEdge]] = {}
    for edge in edge_list:
        by_source.setdefault(edge.source_asset, []).append(edge)
    for outgoing in by_source.values():
        outgoing.sort(key=lambda edge: edge.edge_id)

    cycles: list[TriangularCycle] = []
    seen: set[tuple[str, str, str]] = set()

    for first in sorted(edge_list, key=lambda edge: edge.edge_id):
        for second in by_source.get(first.target_asset, []):
            if second.target_asset in {first.source_asset, first.target_asset}:
                continue
            for third in by_source.get(second.target_asset, []):
                if third.target_asset != first.source_asset:
                    continue
                ordered_ids = (first.edge_id, second.edge_id, third.edge_id)
                canonical_ids = _canonical_rotation(ordered_ids)
                if canonical_ids in seen:
                    continue
                seen.add(canonical_ids)

                multiplier = first.effective_rate * second.effective_rate * third.effective_rate
                log_delta = math.log(multiplier) - gas_penalty_log
                if log_delta < minimum_log_delta:
                    continue
                digest = hashlib.sha256("|".join(canonical_ids).encode("utf-8")).hexdigest()
                cycles.append(
                    TriangularCycle(
                        candidate_id=f"triangle:{digest[:20]}",
                        edge_ids=ordered_ids,
                        asset_path=(
                            first.source_asset,
                            first.target_asset,
                            second.target_asset,
                            third.target_asset,
                        ),
                        net_multiplier=multiplier,
                        net_log_delta=log_delta,
                        gas_penalty_log=gas_penalty_log,
                    )
                )

    return tuple(sorted(cycles, key=lambda cycle: cycle.candidate_id))


def build_cycle_selection_qubo(
    cycles: Sequence[TriangularCycle],
    *,
    selection_penalty: float = 10.0,
    conflict_penalty: float = 10.0,
) -> QuboModel:
    """Build an at-most-one cycle-selection QUBO.

    A positive log delta produces a negative minimization coefficient. Pairwise
    penalties prevent multiple simultaneous selections and add extra weight for
    routes that share an edge.
    """

    if not math.isfinite(selection_penalty) or selection_penalty <= 0.0:
        raise ValueError("selection_penalty must be finite and positive")
    if not math.isfinite(conflict_penalty) or conflict_penalty < 0.0:
        raise ValueError("conflict_penalty must be finite and non-negative")

    ordered = tuple(sorted(cycles, key=lambda cycle: cycle.candidate_id))
    ids = tuple(cycle.candidate_id for cycle in ordered)
    if len(set(ids)) != len(ids):
        raise ValueError("candidate_id values must be unique")

    linear = {cycle.candidate_id: -cycle.net_log_delta for cycle in ordered}
    quadratic: dict[tuple[str, str], float] = {}
    for left_index, left in enumerate(ordered):
        left_edges = set(left.edge_ids)
        for right in ordered[left_index + 1 :]:
            penalty = selection_penalty
            if left_edges.intersection(right.edge_ids):
                penalty += conflict_penalty
            quadratic[(left.candidate_id, right.candidate_id)] = penalty

    return QuboModel(
        variable_order=ids,
        linear=linear,
        quadratic=quadratic,
    )


def qubo_to_ising(model: QuboModel) -> IsingModel:
    """Convert x=(1-z)/2 QUBO coefficients into an equivalent Ising model."""

    z_linear = {name: -model.linear[name] / 2.0 for name in model.variable_order}
    zz_quadratic: dict[tuple[str, str], float] = {}
    offset = model.constant + sum(model.linear.values()) / 2.0

    for (left, right), coefficient in model.quadratic.items():
        offset += coefficient / 4.0
        z_linear[left] -= coefficient / 4.0
        z_linear[right] -= coefficient / 4.0
        zz_quadratic[(left, right)] = coefficient / 4.0

    return IsingModel(
        variable_order=model.variable_order,
        z_linear=z_linear,
        zz_quadratic=zz_quadratic,
        offset=offset,
    )


def solve_qubo_exact(
    model: QuboModel,
    cycles: Sequence[TriangularCycle],
    *,
    max_variables: int = 24,
) -> DeltaSelection:
    """Deterministic exact fallback and independent QAOA benchmark."""

    if len(model.variable_order) > max_variables:
        raise ValueError(
            f"exact fallback limited to {max_variables} variables; got {len(model.variable_order)}"
        )
    cycle_by_id = {cycle.candidate_id: cycle for cycle in cycles}
    if set(cycle_by_id) != set(model.variable_order):
        raise ValueError("cycles must match the QUBO variable set")

    best_bits: tuple[int, ...] | None = None
    best_energy = math.inf
    for bit_tuple in itertools.product((0, 1), repeat=len(model.variable_order)):
        assignment = dict(zip(model.variable_order, bit_tuple, strict=True))
        energy = model.energy(assignment)
        if energy < best_energy - 1e-15 or (
            math.isclose(energy, best_energy, abs_tol=1e-15)
            and (best_bits is None or bit_tuple < best_bits)
        ):
            best_energy = energy
            best_bits = bit_tuple

    assert best_bits is not None
    selected = tuple(
        name for name, bit in zip(model.variable_order, best_bits, strict=True) if bit == 1
    )
    return DeltaSelection(
        selected_candidate_ids=selected,
        energy=best_energy,
        total_log_delta=sum(cycle_by_id[name].net_log_delta for name in selected),
        solver="classical-exact-fallback",
    )


def build_qiskit_qaoa_ansatz(model: QuboModel, *, reps: int = 1):
    """Build a Qiskit QAOAAnsatz and return `(ansatz, offset)`.

    Qiskit remains an optional dependency. The returned circuit is unbound and
    performs no remote execution. Importing this function without the optional
    package raises a clear runtime error.
    """

    if reps < 1:
        raise ValueError("reps must be at least 1")
    try:
        from qiskit.circuit.library import QAOAAnsatz
        from qiskit.quantum_info import SparsePauliOp
    except ImportError as exc:  # pragma: no cover - optional dependency boundary
        raise RuntimeError("Qiskit is not installed; install the optional quantum extra") from exc

    ising = qubo_to_ising(model)
    index = {name: position for position, name in enumerate(model.variable_order)}
    sparse_terms: list[tuple[str, list[int], float]] = []
    for name, coefficient in ising.z_linear.items():
        if coefficient:
            sparse_terms.append(("Z", [index[name]], coefficient))
    for (left, right), coefficient in ising.zz_quadratic.items():
        if coefficient:
            sparse_terms.append(("ZZ", [index[left], index[right]], coefficient))
    if sparse_terms:
        operator = SparsePauliOp.from_sparse_list(sparse_terms, num_qubits=len(index))
    else:
        operator = SparsePauliOp.from_list([("I" * len(index), 0.0)])
    return QAOAAnsatz(cost_operator=operator, reps=reps, flatten=True), ising.offset
