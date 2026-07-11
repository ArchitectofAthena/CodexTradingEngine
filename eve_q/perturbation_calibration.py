"""Deterministic, source-bound calibration of adverse market perturbations.

The module converts historical route-aligned observations into bounded
``PerturbationScenario`` objects. It performs no market discovery, networking,
trading, scheduling, borrowing, signing, or capital movement. Calibration
receipts are research evidence and always retain ``authority: false``.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from eve_q.delta_robustness import PerturbationScenario
from eve_q.qaoa_delta import MarketEdge, TriangularCycle

_BPS = 10_000.0


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")


def _stable_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _linear_quantile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("quantile values cannot be empty")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


@dataclass(frozen=True)
class HistoricalEdgeObservation:
    edge_id: str
    quoted_rate: float
    fee_bps: float = 0.0
    slippage_bps: float = 0.0
    latency_penalty_bps: float = 0.0
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.edge_id.strip():
            raise ValueError("edge_id is required")
        if not math.isfinite(self.quoted_rate) or self.quoted_rate <= 0.0:
            raise ValueError("quoted_rate must be finite and positive")
        for field_name, value in (
            ("fee_bps", self.fee_bps),
            ("slippage_bps", self.slippage_bps),
            ("latency_penalty_bps", self.latency_penalty_bps),
        ):
            if not math.isfinite(value) or not 0.0 <= value < _BPS:
                raise ValueError(f"{field_name} must be finite in [0, 10000)")
        if self.authority:
            raise ValueError("historical edge observations cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "edge_id": self.edge_id,
            "quoted_rate": self.quoted_rate,
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "latency_penalty_bps": self.latency_penalty_bps,
            "authority": False,
        }


@dataclass(frozen=True)
class HistoricalMarketObservation:
    observation_id: str
    observed_at: str
    edges: tuple[HistoricalEdgeObservation, HistoricalEdgeObservation, HistoricalEdgeObservation]
    gas_penalty_log: float
    source_sha256: str
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.observation_id.startswith("market-observation:"):
            raise ValueError("observation_id must use the market-observation namespace")
        if not self.observed_at.strip():
            raise ValueError("observed_at is required")
        if len(self.edges) != 3:
            raise ValueError("historical observations must contain exactly three edges")
        edge_ids = [edge.edge_id for edge in self.edges]
        if len(set(edge_ids)) != 3:
            raise ValueError("historical observation edge identifiers must be unique")
        if not math.isfinite(self.gas_penalty_log) or self.gas_penalty_log < 0.0:
            raise ValueError("gas_penalty_log must be finite and non-negative")
        _require_sha256(self.source_sha256, "source_sha256")
        if self.authority:
            raise ValueError("historical market observations cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "observed_at": self.observed_at,
            "edges": [edge.as_dict() for edge in sorted(self.edges, key=lambda item: item.edge_id)],
            "gas_penalty_log": self.gas_penalty_log,
            "source_sha256": self.source_sha256,
            "authority": False,
        }


@dataclass(frozen=True)
class PerturbationCalibrationPolicy:
    quantiles: tuple[float, ...] = (0.50, 0.80, 0.95)
    minimum_observations: int = 3
    maximum_observations: int = 4096
    max_abs_rate_shift_bps: float = 5_000.0
    max_cost_shift_bps: float = 5_000.0
    max_gas_shift_log: float = 5.0
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.quantiles:
            raise ValueError("at least one calibration quantile is required")
        if tuple(sorted(set(self.quantiles))) != self.quantiles:
            raise ValueError("quantiles must be unique and strictly increasing")
        if any(not math.isfinite(value) or not 0.0 < value <= 1.0 for value in self.quantiles):
            raise ValueError("quantiles must be finite in (0, 1]")
        if self.minimum_observations < 1:
            raise ValueError("minimum_observations must be positive")
        if self.maximum_observations < self.minimum_observations:
            raise ValueError("maximum_observations must not be below minimum_observations")
        for field_name, value in (
            ("max_abs_rate_shift_bps", self.max_abs_rate_shift_bps),
            ("max_cost_shift_bps", self.max_cost_shift_bps),
            ("max_gas_shift_log", self.max_gas_shift_log),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{field_name} must be finite and positive")
        if self.max_abs_rate_shift_bps > 5_000.0:
            raise ValueError("max_abs_rate_shift_bps cannot exceed the scenario contract")
        if self.max_cost_shift_bps > 5_000.0:
            raise ValueError("max_cost_shift_bps cannot exceed the scenario contract")
        if self.authority:
            raise ValueError("calibration policies cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "quantiles": list(self.quantiles),
            "minimum_observations": self.minimum_observations,
            "maximum_observations": self.maximum_observations,
            "max_abs_rate_shift_bps": self.max_abs_rate_shift_bps,
            "max_cost_shift_bps": self.max_cost_shift_bps,
            "max_gas_shift_log": self.max_gas_shift_log,
            "authority": False,
        }


@dataclass(frozen=True)
class PerturbationCalibrationReceipt:
    receipt_id: str
    baseline_snapshot_sha256: str
    candidate_id: str
    dataset_sha256: str
    policy_sha256: str
    scenario_set_sha256: str
    observation_count: int
    observation_ids: tuple[str, ...]
    policy: PerturbationCalibrationPolicy
    scenarios: tuple[PerturbationScenario, ...]
    clipped_counts: Mapping[str, int]
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.receipt_id.startswith("perturbation-calibration:"):
            raise ValueError("receipt_id must use the perturbation-calibration namespace")
        _require_sha256(self.baseline_snapshot_sha256, "baseline_snapshot_sha256")
        _require_sha256(self.dataset_sha256, "dataset_sha256")
        _require_sha256(self.policy_sha256, "policy_sha256")
        _require_sha256(self.scenario_set_sha256, "scenario_set_sha256")
        if not self.candidate_id.startswith("triangle:"):
            raise ValueError("candidate_id must use the triangle namespace")
        if self.observation_count != len(self.observation_ids):
            raise ValueError("observation_count must match observation_ids")
        if tuple(sorted(set(self.observation_ids))) != self.observation_ids:
            raise ValueError("observation_ids must be unique and sorted")
        if len(self.scenarios) != len(self.policy.quantiles) + 1:
            raise ValueError("scenarios must contain a baseline plus one scenario per quantile")
        if self.scenarios[0].scenario_id != "delta-scenario:calibrated-baseline":
            raise ValueError("the calibrated baseline scenario must be first")
        if any(value < 0 for value in self.clipped_counts.values()):
            raise ValueError("clipped counts cannot be negative")
        if self.authority:
            raise ValueError("calibration receipts cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "perturbation-calibration-receipt-v0.1",
            "receipt_id": self.receipt_id,
            "baseline_snapshot_sha256": self.baseline_snapshot_sha256,
            "candidate_id": self.candidate_id,
            "dataset_sha256": self.dataset_sha256,
            "policy_sha256": self.policy_sha256,
            "scenario_set_sha256": self.scenario_set_sha256,
            "observation_count": self.observation_count,
            "observation_ids": list(self.observation_ids),
            "policy": self.policy.as_dict(),
            "scenarios": [scenario.as_dict() for scenario in self.scenarios],
            "clipped_counts": dict(sorted(self.clipped_counts.items())),
            "authority": False,
        }


def _cap(value: float, maximum: float, field_name: str, counts: dict[str, int]) -> float:
    if value > maximum:
        counts[field_name] = counts.get(field_name, 0) + 1
        return maximum
    return value


def calibrate_perturbation_scenarios(
    candidate: TriangularCycle,
    baseline_edges: Sequence[MarketEdge],
    observations: Sequence[HistoricalMarketObservation],
    *,
    baseline_snapshot_sha256: str,
    policy: PerturbationCalibrationPolicy | None = None,
) -> PerturbationCalibrationReceipt:
    """Calibrate bounded adverse scenarios from source-bound historical observations."""

    _require_sha256(baseline_snapshot_sha256, "baseline_snapshot_sha256")
    policy = policy or PerturbationCalibrationPolicy()
    if not policy.minimum_observations <= len(observations) <= policy.maximum_observations:
        raise ValueError(
            "observation count must remain within the calibration policy bounds"
        )

    baseline_by_id = {edge.edge_id: edge for edge in baseline_edges}
    if len(baseline_by_id) != len(baseline_edges):
        raise ValueError("baseline edge identifiers must be unique")
    if set(baseline_by_id) != set(candidate.edge_ids):
        raise ValueError("baseline edges must match the candidate edge set")
    ordered_baseline = tuple(baseline_by_id[edge_id] for edge_id in candidate.edge_ids)

    ordered_observations = tuple(sorted(observations, key=lambda item: item.observation_id))
    observation_ids = tuple(item.observation_id for item in ordered_observations)
    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError("observation identifiers must be unique")

    rate_adverse_magnitudes: list[list[float]] = [[], [], []]
    fee_increases: list[list[float]] = [[], [], []]
    slippage_increases: list[list[float]] = [[], [], []]
    latency_increases: list[list[float]] = [[], [], []]
    gas_increases: list[float] = []

    for observation in ordered_observations:
        observed_by_id = {edge.edge_id: edge for edge in observation.edges}
        if set(observed_by_id) != set(candidate.edge_ids):
            raise ValueError(
                f"observation {observation.observation_id!r} must match the candidate edge set"
            )
        for index, baseline in enumerate(ordered_baseline):
            observed = observed_by_id[baseline.edge_id]
            rate_shift = (observed.quoted_rate / baseline.quoted_rate - 1.0) * _BPS
            rate_adverse_magnitudes[index].append(max(0.0, -rate_shift))
            fee_increases[index].append(max(0.0, observed.fee_bps - baseline.fee_bps))
            slippage_increases[index].append(
                max(0.0, observed.slippage_bps - baseline.slippage_bps)
            )
            latency_increases[index].append(
                max(0.0, observed.latency_penalty_bps - baseline.latency_penalty_bps)
            )
        gas_increases.append(max(0.0, observation.gas_penalty_log - candidate.gas_penalty_log))

    clipped_counts: dict[str, int] = {
        "rate_shift_bps": 0,
        "fee_shift_bps": 0,
        "slippage_shift_bps": 0,
        "latency_shift_bps": 0,
        "gas_penalty_log_shift": 0,
    }
    scenarios: list[PerturbationScenario] = [
        PerturbationScenario("delta-scenario:calibrated-baseline")
    ]
    for quantile in policy.quantiles:
        token = f"q{round(quantile * 10_000):04d}"
        rate_shift = tuple(
            -_cap(
                _linear_quantile(rate_adverse_magnitudes[index], quantile),
                policy.max_abs_rate_shift_bps,
                "rate_shift_bps",
                clipped_counts,
            )
            for index in range(3)
        )
        fee_shift = tuple(
            _cap(
                _linear_quantile(fee_increases[index], quantile),
                policy.max_cost_shift_bps,
                "fee_shift_bps",
                clipped_counts,
            )
            for index in range(3)
        )
        slippage_shift = tuple(
            _cap(
                _linear_quantile(slippage_increases[index], quantile),
                policy.max_cost_shift_bps,
                "slippage_shift_bps",
                clipped_counts,
            )
            for index in range(3)
        )
        latency_shift = tuple(
            _cap(
                _linear_quantile(latency_increases[index], quantile),
                policy.max_cost_shift_bps,
                "latency_shift_bps",
                clipped_counts,
            )
            for index in range(3)
        )
        gas_shift = _cap(
            _linear_quantile(gas_increases, quantile),
            policy.max_gas_shift_log,
            "gas_penalty_log_shift",
            clipped_counts,
        )
        scenarios.append(
            PerturbationScenario(
                f"delta-scenario:calibrated-{token}",
                rate_shift_bps=rate_shift,
                fee_shift_bps=fee_shift,
                slippage_shift_bps=slippage_shift,
                latency_shift_bps=latency_shift,
                gas_penalty_log_shift=gas_shift,
            )
        )

    scenario_ids = [scenario.scenario_id for scenario in scenarios]
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError("calibration quantiles produced duplicate scenario identifiers")

    dataset_payload = [item.as_dict() for item in ordered_observations]
    dataset_sha256 = _stable_sha256(dataset_payload)
    policy_sha256 = _stable_sha256(policy.as_dict())
    scenario_set_sha256 = _stable_sha256([scenario.as_dict() for scenario in scenarios])
    receipt_seed = {
        "baseline_snapshot_sha256": baseline_snapshot_sha256,
        "candidate_id": candidate.candidate_id,
        "dataset_sha256": dataset_sha256,
        "policy_sha256": policy_sha256,
        "scenario_set_sha256": scenario_set_sha256,
        "observation_ids": list(observation_ids),
        "clipped_counts": dict(sorted(clipped_counts.items())),
        "authority": False,
    }
    receipt_hash = _stable_sha256(receipt_seed)

    return PerturbationCalibrationReceipt(
        receipt_id=f"perturbation-calibration:{receipt_hash[:24]}",
        baseline_snapshot_sha256=baseline_snapshot_sha256,
        candidate_id=candidate.candidate_id,
        dataset_sha256=dataset_sha256,
        policy_sha256=policy_sha256,
        scenario_set_sha256=scenario_set_sha256,
        observation_count=len(ordered_observations),
        observation_ids=observation_ids,
        policy=policy,
        scenarios=tuple(scenarios),
        clipped_counts=clipped_counts,
    )
