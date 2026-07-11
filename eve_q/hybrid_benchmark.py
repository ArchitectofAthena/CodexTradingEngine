"""Deterministic benchmark spine for the hybrid delta research lane.

A seeded case is reconstructed into the same route and liquidity QUBOs used by the
research engine. Exact classical distributions provide a reproducible baseline,
while both selected geometries are independently checked by local Rust binaries.
The resulting simulation receipt is evidence only and always retains
``authority: false``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from eve_q.delta_robustness import DeltaRobustnessReceipt, evaluate_candidate_robustness
from eve_q.flash_liquidity import (
    FlashAmountBucket,
    FlashLiquidityCandidate,
    FlashLiquidityProvider,
    FlashVerificationEvidence,
    build_flash_liquidity_qubo,
    build_flash_verification_request,
    enumerate_flash_liquidity_candidates,
    run_rust_flash_verification,
)
from eve_q.perturbation_calibration import (
    HistoricalEdgeObservation,
    HistoricalMarketObservation,
    PerturbationCalibrationPolicy,
    PerturbationCalibrationReceipt,
    calibrate_perturbation_scenarios,
)
from eve_q.qaoa_delta import (
    MarketEdge,
    QuboModel,
    TriangularCycle,
    build_cycle_selection_qubo,
    enumerate_triangular_cycles,
    solve_qubo_exact,
)
from eve_q.qaoa_sampling import (
    QaoaConfidenceReceipt,
    build_qaoa_confidence_receipt,
    qubo_model_sha256,
)
from eve_q.receipt_emitter import build_receipt, write_receipt
from eve_q.rust_repricing import (
    RustRepricingEvidence,
    build_repricing_request,
    run_rust_repricing,
)

_CASE_SCHEMA = "hybrid-delta-benchmark-case-v0.1"
_RECEIPT_SCHEMA = "hybrid-delta-benchmark-receipt-v0.1"


def _stable_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")


def _require_exact_keys(value: Mapping[str, object], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(
            f"{context} keys mismatch; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _edge_as_dict(edge: MarketEdge) -> dict[str, object]:
    return {
        "edge_id": edge.edge_id,
        "source_asset": edge.source_asset,
        "target_asset": edge.target_asset,
        "quoted_rate": edge.quoted_rate,
        "fee_bps": edge.fee_bps,
        "slippage_bps": edge.slippage_bps,
        "latency_penalty_bps": edge.latency_penalty_bps,
        "venue": edge.venue,
        "authority": False,
    }


@dataclass(frozen=True)
class SeededBenchmarkCase:
    benchmark_id: str
    source_label: str
    edges: tuple[MarketEdge, ...]
    gas_penalty_log: float
    minimum_log_delta: float
    observations: tuple[HistoricalMarketObservation, ...]
    calibration_policy: PerturbationCalibrationPolicy
    providers: tuple[FlashLiquidityProvider, ...]
    buckets: tuple[FlashAmountBucket, ...]
    minimum_net_profit: float = 0.0
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.benchmark_id.startswith("hybrid-benchmark:"):
            raise ValueError("benchmark_id must use the hybrid-benchmark namespace")
        if not self.source_label.strip():
            raise ValueError("source_label is required")
        if len(self.edges) < 3:
            raise ValueError("benchmark cases require at least three market edges")
        edge_ids = [edge.edge_id for edge in self.edges]
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("benchmark edge identifiers must be unique")
        if not math.isfinite(self.gas_penalty_log) or self.gas_penalty_log < 0.0:
            raise ValueError("gas_penalty_log must be finite and non-negative")
        if not math.isfinite(self.minimum_log_delta):
            raise ValueError("minimum_log_delta must be finite")
        if not self.observations:
            raise ValueError("benchmark cases require historical observations")
        if not self.providers or not self.buckets:
            raise ValueError("benchmark cases require providers and amount buckets")
        if not math.isfinite(self.minimum_net_profit) or self.minimum_net_profit < 0.0:
            raise ValueError("minimum_net_profit must be finite and non-negative")
        if self.authority:
            raise ValueError("benchmark cases cannot grant authority")

    def snapshot_dict(self) -> dict[str, object]:
        return {
            "edges": [
                _edge_as_dict(edge) for edge in sorted(self.edges, key=lambda item: item.edge_id)
            ],
            "gas_penalty_log": self.gas_penalty_log,
            "minimum_log_delta": self.minimum_log_delta,
            "authority": False,
        }

    @property
    def snapshot_sha256(self) -> str:
        return _stable_sha256(self.snapshot_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": _CASE_SCHEMA,
            "benchmark_id": self.benchmark_id,
            "source_label": self.source_label,
            "snapshot": self.snapshot_dict(),
            "historical_observations": [
                observation.as_dict()
                for observation in sorted(self.observations, key=lambda item: item.observation_id)
            ],
            "calibration_policy": self.calibration_policy.as_dict(),
            "flash_liquidity": {
                "providers": [
                    provider.as_dict()
                    for provider in sorted(self.providers, key=lambda item: item.provider_id)
                ],
                "buckets": [
                    bucket.as_dict()
                    for bucket in sorted(self.buckets, key=lambda item: item.bucket_id)
                ],
                "minimum_net_profit": self.minimum_net_profit,
                "authority": False,
            },
            "authority": False,
        }

    @property
    def case_sha256(self) -> str:
        return _stable_sha256(self.as_dict())


@dataclass(frozen=True)
class HybridDeltaBenchmarkReceipt:
    receipt_id: str
    benchmark_id: str
    benchmark_sha256: str
    snapshot_sha256: str
    route_model_sha256: str
    flash_model_sha256: str
    route_model_identity_verified: bool
    flash_model_identity_verified: bool
    route_confidence: QaoaConfidenceReceipt
    route_verification: RustRepricingEvidence
    calibration: PerturbationCalibrationReceipt
    robustness: DeltaRobustnessReceipt
    flash_confidence: QaoaConfidenceReceipt
    flash_verification: FlashVerificationEvidence
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.receipt_id.startswith("hybrid-benchmark-receipt:"):
            raise ValueError("receipt_id must use the hybrid-benchmark-receipt namespace")
        if not self.benchmark_id.startswith("hybrid-benchmark:"):
            raise ValueError("benchmark_id must use the hybrid-benchmark namespace")
        for field_name, value in (
            ("benchmark_sha256", self.benchmark_sha256),
            ("snapshot_sha256", self.snapshot_sha256),
            ("route_model_sha256", self.route_model_sha256),
            ("flash_model_sha256", self.flash_model_sha256),
        ):
            _require_sha256(value, field_name)
        if not self.route_model_identity_verified or not self.flash_model_identity_verified:
            raise ValueError("benchmark receipts require identical-QUBO model verification")
        if self.route_confidence.model_sha256 != self.route_model_sha256:
            raise ValueError("route confidence receipt is not bound to the route QUBO")
        if self.flash_confidence.model_sha256 != self.flash_model_sha256:
            raise ValueError("flash confidence receipt is not bound to the flash QUBO")
        if self.route_verification.snapshot_sha256 != self.snapshot_sha256:
            raise ValueError("route verification is not bound to the seeded snapshot")
        if self.route_verification.model_sha256 != self.route_model_sha256:
            raise ValueError("route verification is not bound to the route QUBO")
        if self.calibration.baseline_snapshot_sha256 != self.snapshot_sha256:
            raise ValueError("calibration is not bound to the seeded snapshot")
        if self.robustness.baseline_snapshot_sha256 != self.snapshot_sha256:
            raise ValueError("robustness is not bound to the seeded snapshot")
        if self.robustness.scenario_set_sha256 != self.calibration.scenario_set_sha256:
            raise ValueError("robustness did not use the calibrated scenario set")
        if self.flash_verification.snapshot_sha256 != self.snapshot_sha256:
            raise ValueError("flash verification is not bound to the seeded snapshot")
        if self.flash_verification.model_sha256 != self.flash_model_sha256:
            raise ValueError("flash verification is not bound to the flash QUBO")
        if self.authority:
            raise ValueError("benchmark receipts cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": _RECEIPT_SCHEMA,
            "receipt_id": self.receipt_id,
            "benchmark_id": self.benchmark_id,
            "benchmark_sha256": self.benchmark_sha256,
            "snapshot_sha256": self.snapshot_sha256,
            "model_identity": {
                "route_model_sha256": self.route_model_sha256,
                "flash_model_sha256": self.flash_model_sha256,
                "route_model_identity_verified": self.route_model_identity_verified,
                "flash_model_identity_verified": self.flash_model_identity_verified,
                "authority": False,
            },
            "route_confidence": self.route_confidence.as_dict(),
            "route_verification": self.route_verification.as_dict(),
            "calibration": self.calibration.as_dict(),
            "robustness": self.robustness.as_dict(),
            "flash_confidence": self.flash_confidence.as_dict(),
            "flash_verification": self.flash_verification.as_dict(),
            "mode": "historical_replay",
            "human_promotion_required": True,
            "authority": False,
        }


def _parse_edge(payload: Mapping[str, object]) -> MarketEdge:
    _require_exact_keys(
        payload,
        {
            "edge_id",
            "source_asset",
            "target_asset",
            "quoted_rate",
            "fee_bps",
            "slippage_bps",
            "latency_penalty_bps",
            "venue",
            "authority",
        },
        "benchmark edge",
    )
    return MarketEdge(
        edge_id=str(payload["edge_id"]),
        source_asset=str(payload["source_asset"]),
        target_asset=str(payload["target_asset"]),
        quoted_rate=float(payload["quoted_rate"]),
        fee_bps=float(payload["fee_bps"]),
        slippage_bps=float(payload["slippage_bps"]),
        latency_penalty_bps=float(payload["latency_penalty_bps"]),
        venue=str(payload["venue"]),
        authority=bool(payload["authority"]),
    )


def _parse_historical_edge(payload: Mapping[str, object]) -> HistoricalEdgeObservation:
    _require_exact_keys(
        payload,
        {
            "edge_id",
            "quoted_rate",
            "fee_bps",
            "slippage_bps",
            "latency_penalty_bps",
            "authority",
        },
        "historical edge",
    )
    return HistoricalEdgeObservation(
        edge_id=str(payload["edge_id"]),
        quoted_rate=float(payload["quoted_rate"]),
        fee_bps=float(payload["fee_bps"]),
        slippage_bps=float(payload["slippage_bps"]),
        latency_penalty_bps=float(payload["latency_penalty_bps"]),
        authority=bool(payload["authority"]),
    )


def _parse_observation(payload: Mapping[str, object]) -> HistoricalMarketObservation:
    _require_exact_keys(
        payload,
        {
            "observation_id",
            "observed_at",
            "edges",
            "gas_penalty_log",
            "source_sha256",
            "authority",
        },
        "historical observation",
    )
    raw_edges = payload["edges"]
    if not isinstance(raw_edges, list):
        raise ValueError("historical observation edges must be an array")
    parsed_edges = tuple(_parse_historical_edge(_mapping(item, "historical edge")) for item in raw_edges)
    if len(parsed_edges) != 3:
        raise ValueError("historical observations must contain exactly three edges")
    return HistoricalMarketObservation(
        observation_id=str(payload["observation_id"]),
        observed_at=str(payload["observed_at"]),
        edges=(parsed_edges[0], parsed_edges[1], parsed_edges[2]),
        gas_penalty_log=float(payload["gas_penalty_log"]),
        source_sha256=str(payload["source_sha256"]),
        authority=bool(payload["authority"]),
    )


def benchmark_case_from_dict(payload: Mapping[str, object]) -> SeededBenchmarkCase:
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "benchmark_id",
            "source_label",
            "snapshot",
            "historical_observations",
            "calibration_policy",
            "flash_liquidity",
            "authority",
        },
        "benchmark case",
    )
    if payload["schema_version"] != _CASE_SCHEMA:
        raise ValueError("benchmark case schema_version mismatch")
    if payload["authority"] is not False:
        raise ValueError("benchmark cases cannot grant authority")

    snapshot = _mapping(payload["snapshot"], "snapshot")
    _require_exact_keys(
        snapshot,
        {"edges", "gas_penalty_log", "minimum_log_delta", "authority"},
        "snapshot",
    )
    if snapshot["authority"] is not False:
        raise ValueError("benchmark snapshots cannot grant authority")
    raw_edges = snapshot["edges"]
    if not isinstance(raw_edges, list):
        raise ValueError("snapshot edges must be an array")
    edges = tuple(_parse_edge(_mapping(item, "benchmark edge")) for item in raw_edges)

    raw_observations = payload["historical_observations"]
    if not isinstance(raw_observations, list):
        raise ValueError("historical_observations must be an array")
    observations = tuple(
        _parse_observation(_mapping(item, "historical observation"))
        for item in raw_observations
    )

    raw_policy = _mapping(payload["calibration_policy"], "calibration_policy")
    _require_exact_keys(
        raw_policy,
        {
            "quantiles",
            "minimum_observations",
            "maximum_observations",
            "max_abs_rate_shift_bps",
            "max_cost_shift_bps",
            "max_gas_shift_log",
            "authority",
        },
        "calibration_policy",
    )
    raw_quantiles = raw_policy["quantiles"]
    if not isinstance(raw_quantiles, list):
        raise ValueError("calibration quantiles must be an array")
    policy = PerturbationCalibrationPolicy(
        quantiles=tuple(float(value) for value in raw_quantiles),
        minimum_observations=int(raw_policy["minimum_observations"]),
        maximum_observations=int(raw_policy["maximum_observations"]),
        max_abs_rate_shift_bps=float(raw_policy["max_abs_rate_shift_bps"]),
        max_cost_shift_bps=float(raw_policy["max_cost_shift_bps"]),
        max_gas_shift_log=float(raw_policy["max_gas_shift_log"]),
        authority=bool(raw_policy["authority"]),
    )

    flash = _mapping(payload["flash_liquidity"], "flash_liquidity")
    _require_exact_keys(
        flash,
        {"providers", "buckets", "minimum_net_profit", "authority"},
        "flash_liquidity",
    )
    if flash["authority"] is not False:
        raise ValueError("flash benchmark inputs cannot grant authority")
    raw_providers = flash["providers"]
    raw_buckets = flash["buckets"]
    if not isinstance(raw_providers, list) or not isinstance(raw_buckets, list):
        raise ValueError("providers and buckets must be arrays")
    providers: list[FlashLiquidityProvider] = []
    for item in raw_providers:
        provider = _mapping(item, "flash provider")
        _require_exact_keys(
            provider,
            {"provider_id", "fee_bps", "capacity_by_asset", "authority"},
            "flash provider",
        )
        capacities = _mapping(provider["capacity_by_asset"], "capacity_by_asset")
        providers.append(
            FlashLiquidityProvider(
                provider_id=str(provider["provider_id"]),
                fee_bps=float(provider["fee_bps"]),
                capacity_by_asset={str(key): float(value) for key, value in capacities.items()},
                authority=bool(provider["authority"]),
            )
        )
    buckets: list[FlashAmountBucket] = []
    for item in raw_buckets:
        bucket = _mapping(item, "flash bucket")
        _require_exact_keys(
            bucket,
            {"bucket_id", "asset", "principal_amount", "authority"},
            "flash bucket",
        )
        buckets.append(
            FlashAmountBucket(
                bucket_id=str(bucket["bucket_id"]),
                asset=str(bucket["asset"]),
                principal_amount=float(bucket["principal_amount"]),
                authority=bool(bucket["authority"]),
            )
        )

    return SeededBenchmarkCase(
        benchmark_id=str(payload["benchmark_id"]),
        source_label=str(payload["source_label"]),
        edges=edges,
        gas_penalty_log=float(snapshot["gas_penalty_log"]),
        minimum_log_delta=float(snapshot["minimum_log_delta"]),
        observations=observations,
        calibration_policy=policy,
        providers=tuple(providers),
        buckets=tuple(buckets),
        minimum_net_profit=float(flash["minimum_net_profit"]),
        authority=False,
    )


def load_benchmark_case(path: str | Path) -> SeededBenchmarkCase:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return benchmark_case_from_dict(_mapping(payload, "benchmark case"))


def exact_distribution(model: QuboModel, cycles: Sequence[TriangularCycle]) -> dict[str, float]:
    """Return a one-hot Qiskit-order distribution for the exact classical optimum."""

    selection = solve_qubo_exact(model, cycles)
    selected = set(selection.selected_candidate_ids)
    assignment = tuple(1 if name in selected else 0 for name in model.variable_order)
    bitstring = "".join(str(bit) for bit in reversed(assignment))
    return {bitstring: 1.0}


def _selected_route(
    receipt: QaoaConfidenceReceipt, cycles: Sequence[TriangularCycle]
) -> TriangularCycle:
    selected = receipt.best_sample.selected_candidate_ids
    if len(selected) != 1:
        raise ValueError("benchmark route distribution must select exactly one candidate")
    by_id = {cycle.candidate_id: cycle for cycle in cycles}
    return by_id[selected[0]]


def _selected_flash_candidate(
    receipt: QaoaConfidenceReceipt, candidates: Sequence[FlashLiquidityCandidate]
) -> FlashLiquidityCandidate:
    selected = receipt.best_sample.selected_candidate_ids
    if len(selected) != 1:
        raise ValueError("benchmark flash distribution must select exactly one candidate")
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    return by_id[selected[0]]


def run_seeded_benchmark(
    case: SeededBenchmarkCase,
    *,
    route_executable: str | Path,
    flash_executable: str | Path,
    timeout_seconds: float = 2.0,
) -> HybridDeltaBenchmarkReceipt:
    """Run one deterministic historical replay through both isolated Rust verifiers."""

    cycles = enumerate_triangular_cycles(
        case.edges,
        gas_penalty_log=case.gas_penalty_log,
        minimum_log_delta=case.minimum_log_delta,
    )
    if not cycles:
        raise ValueError("seeded benchmark produced no eligible triangular cycles")
    route_model = build_cycle_selection_qubo(cycles)
    route_model_digest = qubo_model_sha256(route_model)
    route_confidence = build_qaoa_confidence_receipt(
        route_model,
        cycles,
        exact_distribution(route_model, cycles),
        solver="seeded-exact-replay",
        reps=1,
    )
    route = _selected_route(route_confidence, cycles)
    route_request = build_repricing_request(
        route_confidence,
        route,
        case.edges,
        snapshot_sha256=case.snapshot_sha256,
        minimum_log_delta=case.minimum_log_delta,
    )
    route_verification = run_rust_repricing(
        route_request,
        route,
        executable=route_executable,
        timeout_seconds=timeout_seconds,
    )

    calibration = calibrate_perturbation_scenarios(
        route,
        case.edges,
        case.observations,
        baseline_snapshot_sha256=case.snapshot_sha256,
        policy=case.calibration_policy,
    )
    robustness = evaluate_candidate_robustness(
        route_confidence,
        route,
        case.edges,
        calibration.scenarios,
        baseline_snapshot_sha256=case.snapshot_sha256,
        minimum_log_delta=case.minimum_log_delta,
        executable=route_executable,
        timeout_seconds=timeout_seconds,
    )

    flash_candidates = enumerate_flash_liquidity_candidates(
        (route,), case.providers, case.buckets
    )
    if not flash_candidates:
        raise ValueError("seeded benchmark produced no compatible liquidity geometry")
    flash_model = build_flash_liquidity_qubo(flash_candidates)
    flash_cycles = tuple(candidate.as_qaoa_cycle() for candidate in flash_candidates)
    flash_model_digest = qubo_model_sha256(flash_model)
    flash_confidence = build_qaoa_confidence_receipt(
        flash_model,
        flash_cycles,
        exact_distribution(flash_model, flash_cycles),
        solver="seeded-exact-replay",
        reps=1,
    )
    flash_candidate = _selected_flash_candidate(flash_confidence, flash_candidates)
    flash_request = build_flash_verification_request(
        flash_confidence,
        flash_candidate,
        case.edges,
        snapshot_sha256=case.snapshot_sha256,
        gas_penalty_log=route.gas_penalty_log,
        minimum_net_profit=case.minimum_net_profit,
    )
    flash_verification = run_rust_flash_verification(
        flash_request,
        executable=flash_executable,
        timeout_seconds=timeout_seconds,
    )

    seed = {
        "benchmark_id": case.benchmark_id,
        "benchmark_sha256": case.case_sha256,
        "snapshot_sha256": case.snapshot_sha256,
        "route_model_sha256": route_model_digest,
        "flash_model_sha256": flash_model_digest,
        "route_confidence": route_confidence.as_dict(),
        "route_verification": route_verification.as_dict(),
        "calibration": calibration.as_dict(),
        "robustness": robustness.as_dict(),
        "flash_confidence": flash_confidence.as_dict(),
        "flash_verification": flash_verification.as_dict(),
        "authority": False,
    }
    return HybridDeltaBenchmarkReceipt(
        receipt_id=f"hybrid-benchmark-receipt:{_stable_sha256(seed)[:24]}",
        benchmark_id=case.benchmark_id,
        benchmark_sha256=case.case_sha256,
        snapshot_sha256=case.snapshot_sha256,
        route_model_sha256=route_model_digest,
        flash_model_sha256=flash_model_digest,
        route_model_identity_verified=route_confidence.model_sha256 == route_model_digest,
        flash_model_identity_verified=flash_confidence.model_sha256 == flash_model_digest,
        route_confidence=route_confidence,
        route_verification=route_verification,
        calibration=calibration,
        robustness=robustness,
        flash_confidence=flash_confidence,
        flash_verification=flash_verification,
    )


def write_benchmark_receipt(
    receipt: HybridDeltaBenchmarkReceipt, output_path: str | Path
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(receipt.as_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def emit_benchmark_artifacts(
    receipt: HybridDeltaBenchmarkReceipt,
    *,
    receipt_path: str | Path,
    envelope_path: str | Path,
    source_commit: str,
    source_pr: int | None = None,
    root: str | Path = ".",
) -> dict[str, object]:
    """Write the deterministic receipt and its canonical artifact-only envelope."""

    write_benchmark_receipt(receipt, receipt_path)
    envelope = build_receipt(
        artifact_path=receipt_path,
        source_repo="ArchitectofAthena/CodexTradingEngine",
        source_commit=source_commit,
        source_pr=source_pr,
        artifact_type="simulation_summary",
        summary="Hybrid delta seeded benchmark receipt; evidence only, authority false.",
        root=root,
    )
    write_receipt(envelope, Path(envelope_path))
    return envelope


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a seeded hybrid delta benchmark replay.")
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--route-verifier", required=True, type=Path)
    parser.add_argument("--flash-verifier", required=True, type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--envelope-out", type=Path)
    parser.add_argument("--source-commit", default="unknown")
    parser.add_argument("--source-pr", type=int)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()

    receipt = run_seeded_benchmark(
        load_benchmark_case(args.case),
        route_executable=args.route_verifier.resolve(),
        flash_executable=args.flash_verifier.resolve(),
    )
    if args.envelope_out is None:
        write_benchmark_receipt(receipt, args.receipt_out)
    else:
        emit_benchmark_artifacts(
            receipt,
            receipt_path=args.receipt_out,
            envelope_path=args.envelope_out,
            source_commit=args.source_commit,
            source_pr=args.source_pr,
            root=args.root,
        )
    print(
        json.dumps(
            {
                "ok": True,
                "receipt_id": receipt.receipt_id,
                "benchmark_sha256": receipt.benchmark_sha256,
                "snapshot_sha256": receipt.snapshot_sha256,
                "route_energy_gap": receipt.route_confidence.energy_gap_to_classical,
                "flash_energy_gap": receipt.flash_confidence.energy_gap_to_classical,
                "robustness_class": receipt.robustness.robustness_class,
                "repayment_feasible": receipt.flash_verification.repayment_feasible,
                "authority": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
