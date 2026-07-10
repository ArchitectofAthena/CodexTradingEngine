"""Deterministic perturbed-state robustness evidence for verified delta candidates.

The module creates bounded alternate market states and routes each state through the
isolated Rust exact repricer. It emits research evidence only. It cannot sign,
submit, borrow, schedule, move capital, or grant authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from eve_q.qaoa_delta import MarketEdge, TriangularCycle
from eve_q.qaoa_sampling import QaoaConfidenceReceipt
from eve_q.rust_repricing import build_repricing_request, run_rust_repricing

_BPS = 10_000.0
_MAX_SCENARIOS = 256


def _require_vector(values: tuple[float, float, float], field_name: str) -> None:
    if len(values) != 3:
        raise ValueError(f"{field_name} must contain exactly three values")
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{field_name} values must be finite")


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")


@dataclass(frozen=True)
class PerturbationScenario:
    """One bounded alternate state aligned to the candidate's three-edge order."""

    scenario_id: str
    rate_shift_bps: tuple[float, float, float] = (0.0, 0.0, 0.0)
    fee_shift_bps: tuple[float, float, float] = (0.0, 0.0, 0.0)
    slippage_shift_bps: tuple[float, float, float] = (0.0, 0.0, 0.0)
    latency_shift_bps: tuple[float, float, float] = (0.0, 0.0, 0.0)
    gas_penalty_log_shift: float = 0.0
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.scenario_id.startswith("delta-scenario:"):
            raise ValueError("scenario_id must use the delta-scenario namespace")
        for field_name, values in (
            ("rate_shift_bps", self.rate_shift_bps),
            ("fee_shift_bps", self.fee_shift_bps),
            ("slippage_shift_bps", self.slippage_shift_bps),
            ("latency_shift_bps", self.latency_shift_bps),
        ):
            _require_vector(values, field_name)
        if any(not -5_000.0 <= value <= 5_000.0 for value in self.rate_shift_bps):
            raise ValueError("rate_shift_bps values must remain in [-5000, 5000]")
        for field_name, values in (
            ("fee_shift_bps", self.fee_shift_bps),
            ("slippage_shift_bps", self.slippage_shift_bps),
            ("latency_shift_bps", self.latency_shift_bps),
        ):
            if any(not 0.0 <= value <= 5_000.0 for value in values):
                raise ValueError(f"{field_name} values must remain in [0, 5000]")
        if not math.isfinite(self.gas_penalty_log_shift) or self.gas_penalty_log_shift < 0.0:
            raise ValueError("gas_penalty_log_shift must be finite and non-negative")
        if self.authority:
            raise ValueError("perturbation scenarios cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "rate_shift_bps": list(self.rate_shift_bps),
            "fee_shift_bps": list(self.fee_shift_bps),
            "slippage_shift_bps": list(self.slippage_shift_bps),
            "latency_shift_bps": list(self.latency_shift_bps),
            "gas_penalty_log_shift": self.gas_penalty_log_shift,
            "authority": False,
        }


@dataclass(frozen=True)
class ScenarioRobustnessResult:
    scenario: PerturbationScenario
    scenario_snapshot_sha256: str
    request_id: str
    net_log_delta: float
    minimum_log_delta: float
    profitable: bool
    passes_margin: bool
    delta_drift: float
    failure_reasons: tuple[str, ...]
    authority: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.scenario_snapshot_sha256, "scenario_snapshot_sha256")
        if not self.request_id.startswith("delta-reprice:"):
            raise ValueError("request_id must use the delta-reprice namespace")
        for field_name, value in (
            ("net_log_delta", self.net_log_delta),
            ("minimum_log_delta", self.minimum_log_delta),
            ("delta_drift", self.delta_drift),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{field_name} must be finite")
        expected_reasons: list[str] = []
        if not self.profitable:
            expected_reasons.append("not_profitable")
        if not self.passes_margin:
            expected_reasons.append("below_minimum_margin")
        if self.failure_reasons != tuple(expected_reasons):
            raise ValueError("failure_reasons must match the verification outcome")
        if self.authority:
            raise ValueError("scenario results cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario": self.scenario.as_dict(),
            "scenario_snapshot_sha256": self.scenario_snapshot_sha256,
            "request_id": self.request_id,
            "net_log_delta": self.net_log_delta,
            "minimum_log_delta": self.minimum_log_delta,
            "profitable": self.profitable,
            "passes_margin": self.passes_margin,
            "delta_drift": self.delta_drift,
            "failure_reasons": list(self.failure_reasons),
            "authority": False,
        }


@dataclass(frozen=True)
class DeltaRobustnessReceipt:
    receipt_id: str
    baseline_snapshot_sha256: str
    model_sha256: str
    confidence_receipt_id: str
    candidate_id: str
    scenario_set_sha256: str
    scenario_count: int
    survival_count: int
    survival_rate: float
    worst_case_log_delta: float
    median_log_delta: float
    margin_failure_reasons: Mapping[str, int]
    robustness_class: str
    results: tuple[ScenarioRobustnessResult, ...]
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.receipt_id.startswith("delta-robustness:"):
            raise ValueError("receipt_id must use the delta-robustness namespace")
        _require_sha256(self.baseline_snapshot_sha256, "baseline_snapshot_sha256")
        _require_sha256(self.model_sha256, "model_sha256")
        _require_sha256(self.scenario_set_sha256, "scenario_set_sha256")
        if not self.confidence_receipt_id.startswith("qaoa-confidence:"):
            raise ValueError("confidence_receipt_id must use the qaoa-confidence namespace")
        if not self.candidate_id.startswith("triangle:"):
            raise ValueError("candidate_id must use the triangle namespace")
        if self.scenario_count != len(self.results) or self.scenario_count < 1:
            raise ValueError("scenario_count must match a non-empty result set")
        if self.survival_count != sum(result.passes_margin for result in self.results):
            raise ValueError("survival_count must match the scenario results")
        expected_rate = self.survival_count / self.scenario_count
        if not math.isclose(self.survival_rate, expected_rate, abs_tol=1e-15):
            raise ValueError("survival_rate must match survival_count / scenario_count")
        if not all(
            math.isfinite(value)
            for value in (self.survival_rate, self.worst_case_log_delta, self.median_log_delta)
        ):
            raise ValueError("robustness summary values must be finite")
        if self.robustness_class not in {"robust", "resilient", "conditional", "fragile", "failed"}:
            raise ValueError("robustness_class is invalid")
        if self.authority:
            raise ValueError("robustness receipts cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "delta-robustness-receipt-v0.1",
            "receipt_id": self.receipt_id,
            "baseline_snapshot_sha256": self.baseline_snapshot_sha256,
            "model_sha256": self.model_sha256,
            "confidence_receipt_id": self.confidence_receipt_id,
            "candidate_id": self.candidate_id,
            "scenario_set_sha256": self.scenario_set_sha256,
            "scenario_count": self.scenario_count,
            "survival_count": self.survival_count,
            "survival_rate": self.survival_rate,
            "worst_case_log_delta": self.worst_case_log_delta,
            "median_log_delta": self.median_log_delta,
            "margin_failure_reasons": dict(sorted(self.margin_failure_reasons.items())),
            "robustness_class": self.robustness_class,
            "results": [result.as_dict() for result in self.results],
            "authority": False,
        }


def standard_adverse_scenarios() -> tuple[PerturbationScenario, ...]:
    """Return deterministic teaching scenarios; values are not market calibration."""

    return (
        PerturbationScenario("delta-scenario:baseline"),
        PerturbationScenario("delta-scenario:reserve-soft", rate_shift_bps=(-5.0, -5.0, -5.0)),
        PerturbationScenario("delta-scenario:reserve-hard", rate_shift_bps=(-15.0, -15.0, -15.0)),
        PerturbationScenario("delta-scenario:slippage-spike", slippage_shift_bps=(10.0, 10.0, 10.0)),
        PerturbationScenario("delta-scenario:latency-spike", latency_shift_bps=(5.0, 5.0, 5.0)),
        PerturbationScenario("delta-scenario:gas-spike", gas_penalty_log_shift=0.005),
        PerturbationScenario(
            "delta-scenario:combined-adverse",
            rate_shift_bps=(-10.0, -10.0, -10.0),
            fee_shift_bps=(2.0, 2.0, 2.0),
            slippage_shift_bps=(8.0, 8.0, 8.0),
            latency_shift_bps=(4.0, 4.0, 4.0),
            gas_penalty_log_shift=0.003,
        ),
    )


def _apply_scenario(
    candidate: TriangularCycle,
    market_edges: Sequence[MarketEdge],
    scenario: PerturbationScenario,
) -> tuple[tuple[MarketEdge, MarketEdge, MarketEdge], TriangularCycle]:
    edges_by_id = {edge.edge_id: edge for edge in market_edges}
    if len(edges_by_id) != len(market_edges):
        raise ValueError("market edge identifiers must be unique")
    try:
        ordered = tuple(edges_by_id[edge_id] for edge_id in candidate.edge_ids)
    except KeyError as exc:
        raise ValueError(f"candidate references missing market edge {exc.args[0]!r}") from exc

    perturbed: list[MarketEdge] = []
    for index, edge in enumerate(ordered):
        quoted_rate = edge.quoted_rate * (1.0 + scenario.rate_shift_bps[index] / _BPS)
        fee_bps = edge.fee_bps + scenario.fee_shift_bps[index]
        slippage_bps = edge.slippage_bps + scenario.slippage_shift_bps[index]
        latency_bps = edge.latency_penalty_bps + scenario.latency_shift_bps[index]
        if quoted_rate <= 0.0:
            raise ValueError("scenario produced a non-positive quoted rate")
        if any(value >= _BPS for value in (fee_bps, slippage_bps, latency_bps)):
            raise ValueError("scenario produced a cost assumption at or above 10000 bps")
        perturbed.append(
            MarketEdge(
                edge_id=edge.edge_id,
                source_asset=edge.source_asset,
                target_asset=edge.target_asset,
                quoted_rate=quoted_rate,
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
                latency_penalty_bps=latency_bps,
                venue=edge.venue,
            )
        )

    gas_penalty = candidate.gas_penalty_log + scenario.gas_penalty_log_shift
    net_multiplier = math.prod(edge.effective_rate for edge in perturbed)
    net_log_delta = math.log(net_multiplier) - gas_penalty
    perturbed_candidate = TriangularCycle(
        candidate_id=candidate.candidate_id,
        edge_ids=candidate.edge_ids,
        asset_path=candidate.asset_path,
        net_multiplier=net_multiplier,
        net_log_delta=net_log_delta,
        gas_penalty_log=gas_penalty,
    )
    return (perturbed[0], perturbed[1], perturbed[2]), perturbed_candidate


def _scenario_snapshot_sha256(
    baseline_snapshot_sha256: str,
    scenario: PerturbationScenario,
    edges: Sequence[MarketEdge],
    candidate: TriangularCycle,
) -> str:
    payload = {
        "baseline_snapshot_sha256": baseline_snapshot_sha256,
        "scenario": scenario.as_dict(),
        "candidate_id": candidate.candidate_id,
        "gas_penalty_log": candidate.gas_penalty_log,
        "edges": [
            {
                "edge_id": edge.edge_id,
                "quoted_rate": edge.quoted_rate,
                "fee_bps": edge.fee_bps,
                "slippage_bps": edge.slippage_bps,
                "latency_penalty_bps": edge.latency_penalty_bps,
            }
            for edge in edges
        ],
        "authority": False,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _classify(survival_rate: float) -> str:
    if math.isclose(survival_rate, 1.0, abs_tol=1e-15):
        return "robust"
    if survival_rate >= 0.8:
        return "resilient"
    if survival_rate >= 0.5:
        return "conditional"
    if survival_rate > 0.0:
        return "fragile"
    return "failed"


def evaluate_candidate_robustness(
    receipt: QaoaConfidenceReceipt,
    candidate: TriangularCycle,
    market_edges: Sequence[MarketEdge],
    scenarios: Sequence[PerturbationScenario],
    *,
    baseline_snapshot_sha256: str,
    minimum_log_delta: float,
    executable: str | Path,
    timeout_seconds: float = 2.0,
) -> DeltaRobustnessReceipt:
    """Reprice a selected candidate across deterministic alternate states."""

    _require_sha256(baseline_snapshot_sha256, "baseline_snapshot_sha256")
    if not scenarios:
        raise ValueError("at least one perturbation scenario is required")
    if len(scenarios) > _MAX_SCENARIOS:
        raise ValueError(f"scenario count exceeds the {_MAX_SCENARIOS}-scenario limit")
    scenario_ids = [scenario.scenario_id for scenario in scenarios]
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError("scenario identifiers must be unique")
    ordered_scenarios = tuple(sorted(scenarios, key=lambda item: item.scenario_id))

    results: list[ScenarioRobustnessResult] = []
    reason_counts: dict[str, int] = {}
    for scenario in ordered_scenarios:
        perturbed_edges, perturbed_candidate = _apply_scenario(candidate, market_edges, scenario)
        scenario_snapshot = _scenario_snapshot_sha256(
            baseline_snapshot_sha256,
            scenario,
            perturbed_edges,
            perturbed_candidate,
        )
        request = build_repricing_request(
            receipt,
            perturbed_candidate,
            perturbed_edges,
            snapshot_sha256=scenario_snapshot,
            minimum_log_delta=minimum_log_delta,
        )
        evidence = run_rust_repricing(
            request,
            perturbed_candidate,
            executable=executable,
            timeout_seconds=timeout_seconds,
        )
        reasons: list[str] = []
        if not evidence.profitable:
            reasons.append("not_profitable")
        if not evidence.passes_margin:
            reasons.append("below_minimum_margin")
        for reason in reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        results.append(
            ScenarioRobustnessResult(
                scenario=scenario,
                scenario_snapshot_sha256=scenario_snapshot,
                request_id=evidence.request_id,
                net_log_delta=evidence.net_log_delta,
                minimum_log_delta=evidence.minimum_log_delta,
                profitable=evidence.profitable,
                passes_margin=evidence.passes_margin,
                delta_drift=evidence.delta_drift,
                failure_reasons=tuple(reasons),
            )
        )

    survival_count = sum(result.passes_margin for result in results)
    survival_rate = survival_count / len(results)
    deltas = [result.net_log_delta for result in results]
    scenario_set_payload = [scenario.as_dict() for scenario in ordered_scenarios]
    scenario_set_sha256 = hashlib.sha256(
        json.dumps(
            scenario_set_payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    receipt_seed = {
        "baseline_snapshot_sha256": baseline_snapshot_sha256,
        "model_sha256": receipt.model_sha256,
        "confidence_receipt_id": receipt.receipt_id,
        "candidate_id": candidate.candidate_id,
        "scenario_set_sha256": scenario_set_sha256,
        "results": [result.as_dict() for result in results],
        "authority": False,
    }
    receipt_hash = hashlib.sha256(
        json.dumps(receipt_seed, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    ).hexdigest()

    return DeltaRobustnessReceipt(
        receipt_id=f"delta-robustness:{receipt_hash[:24]}",
        baseline_snapshot_sha256=baseline_snapshot_sha256,
        model_sha256=receipt.model_sha256,
        confidence_receipt_id=receipt.receipt_id,
        candidate_id=candidate.candidate_id,
        scenario_set_sha256=scenario_set_sha256,
        scenario_count=len(results),
        survival_count=survival_count,
        survival_rate=survival_rate,
        worst_case_log_delta=min(deltas),
        median_log_delta=statistics.median(deltas),
        margin_failure_reasons=reason_counts,
        robustness_class=_classify(survival_rate),
        results=tuple(results),
    )
