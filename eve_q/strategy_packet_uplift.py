"""Strict bridge from SpiralBloom strategy packets to Codex seeded verification.

The consumer accepts only ``local_strategy_packet_v0.1`` records, reconstructs the
local candidate universe before accepting any hint, and runs packet-guided candidates
through the same exact-classical, Rust repricing, calibrated perturbation, and
repayment membranes as the local benchmark.

Remote evidence remains evidence. It never becomes a fast-path dependency or
execution authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from eve_q.delta_robustness import evaluate_candidate_robustness
from eve_q.flash_liquidity import (
    FlashAmountBucket,
    FlashLiquidityCandidate,
    FlashLiquidityProvider,
    build_flash_liquidity_qubo,
    build_flash_verification_request,
    enumerate_flash_liquidity_candidates,
    run_rust_flash_verification,
)
from eve_q.hybrid_benchmark import (
    SeededBenchmarkCase,
    exact_distribution,
    load_benchmark_case,
    run_seeded_benchmark,
)
from eve_q.perturbation_calibration import calibrate_perturbation_scenarios
from eve_q.qaoa_delta import (
    QuboModel,
    TriangularCycle,
    build_cycle_selection_qubo,
    enumerate_triangular_cycles,
)
from eve_q.qaoa_sampling import (
    build_qaoa_confidence_receipt,
    qubo_model_sha256,
)
from eve_q.rust_repricing import build_repricing_request, run_rust_repricing

_PACKET_VERSION = "local_strategy_packet_v0.1"
_CONSUMPTION_SCHEMA = "codex-strategy-packet-consumption-v0.1"
_UPLIFT_SCHEMA = "codex-planning-uplift-receipt-v0.1"
_ALLOWED_PROVIDERS = {"openai", "claude", "deepseek", "gemini", "grok"}
_ALLOWED_DATA_CLASSES = {"public", "sanitized", "abstracted_internal"}
_REQUIRED_PROHIBITED_ACTIONS = {
    "autonomous_execution",
    "capital_movement",
    "deployment",
    "git_mutation",
    "mempool_submission",
    "rpc_submission",
    "scheduler_authority",
    "transaction_signing",
    "wallet_access",
}
_DENIED_EVIDENCE_FIELDS = {"output_text", "raw_response", "response_body", "headers"}
_HEX64 = set("0123456789abcdef")
_TOP_LEVEL_KEYS = {
    "packet_id",
    "packet_version",
    "compiled_at",
    "expires_at",
    "ttl_seconds",
    "request_sha256",
    "task",
    "lineage",
    "remote_evidence",
    "evidence_summary",
    "proposals",
    "local_fast_path",
    "prohibited_actions",
    "stores_raw_provider_responses",
    "authority",
}


class StrategyPacketError(ValueError):
    """Raised when a strategy packet cannot cross the Codex membrane."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], context: str
) -> None:
    actual = set(value)
    if actual != expected:
        raise StrategyPacketError(
            f"{context} keys mismatch; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise StrategyPacketError(f"{context} must be an object")
    return value


def _array(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise StrategyPacketError(f"{context} must be an array")
    return value


def _require_hash(value: Any, context: str, length: int = 64) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or any(character not in _HEX64 for character in value)
    ):
        raise StrategyPacketError(
            f"{context} must be {length} lowercase hexadecimal characters"
        )
    return value


def _parse_time(value: Any, context: str) -> datetime:
    if not isinstance(value, str):
        raise StrategyPacketError(f"{context} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StrategyPacketError(f"{context} is not valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise StrategyPacketError(f"{context} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _nonempty_strings(value: Any, context: str, *, maximum: int = 64) -> tuple[str, ...]:
    items = _array(value, context)
    if len(items) > maximum:
        raise StrategyPacketError(f"{context} exceeds the bounded item limit")
    if any(not isinstance(item, str) or not item.strip() for item in items):
        raise StrategyPacketError(f"{context} must contain non-empty strings")
    return tuple(items)


def _one_hot_distribution(model: QuboModel, candidate_id: str) -> dict[str, float]:
    if candidate_id not in model.variable_order:
        raise StrategyPacketError(f"Unknown candidate for one-hot evidence: {candidate_id}")
    assignment = tuple(1 if name == candidate_id else 0 for name in model.variable_order)
    bitstring = "".join(str(bit) for bit in reversed(assignment))
    return {bitstring: 1.0}


@dataclass(frozen=True)
class CodexEvaluationHint:
    proposal_id: str
    summary: str
    benchmark_id: str
    route_candidate_id: str
    allowed_provider_ids: tuple[str, ...]
    allowed_bucket_ids: tuple[str, ...]
    evaluation_mode: str = "compare_only"
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.proposal_id.strip() or not self.summary.strip():
            raise StrategyPacketError("proposal_id and summary are required")
        if not self.benchmark_id.startswith("hybrid-benchmark:"):
            raise StrategyPacketError("benchmark_id must use the hybrid-benchmark namespace")
        if not self.route_candidate_id.startswith("triangle:"):
            raise StrategyPacketError("route_candidate_id must use the triangle namespace")
        if self.evaluation_mode != "compare_only":
            raise StrategyPacketError("Only compare_only evaluation is permitted")
        if self.authority:
            raise StrategyPacketError("Codex evaluation hints cannot grant authority")

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "summary": self.summary,
            "benchmark_id": self.benchmark_id,
            "route_candidate_id": self.route_candidate_id,
            "allowed_provider_ids": list(self.allowed_provider_ids),
            "allowed_bucket_ids": list(self.allowed_bucket_ids),
            "evaluation_mode": self.evaluation_mode,
            "authority": False,
        }


@dataclass(frozen=True)
class ConsumedStrategyPacket:
    packet_id: str
    request_sha256: str
    compiled_at: str
    expires_at: str
    task_class: str
    source_snapshot_manifest_cid: str | None
    source_repository_commits: tuple[tuple[str, str], ...]
    evidence_sha256: str
    successful_evidence_count: int
    hints: tuple[CodexEvaluationHint, ...]
    authority: bool = False

    def __post_init__(self) -> None:
        _require_hash(self.packet_id, "packet_id")
        _require_hash(self.request_sha256, "request_sha256")
        _require_hash(self.evidence_sha256, "evidence_sha256")
        if self.successful_evidence_count < 0:
            raise StrategyPacketError("successful_evidence_count cannot be negative")
        if not self.hints:
            raise StrategyPacketError("At least one Codex evaluation hint is required")
        if self.authority:
            raise StrategyPacketError("Consumed packets cannot grant authority")

    def as_dict(self) -> dict[str, Any]:
        seed = {
            "schema_version": _CONSUMPTION_SCHEMA,
            "packet_id": self.packet_id,
            "request_sha256": self.request_sha256,
            "compiled_at": self.compiled_at,
            "expires_at": self.expires_at,
            "task_class": self.task_class,
            "lineage": {
                "source_snapshot_manifest_cid": self.source_snapshot_manifest_cid,
                "source_repository_commits": [
                    {"repository": repository, "commit": commit}
                    for repository, commit in self.source_repository_commits
                ],
            },
            "evidence_sha256": self.evidence_sha256,
            "successful_evidence_count": self.successful_evidence_count,
            "hints": [hint.as_dict() for hint in self.hints],
            "remote_dependency": False,
            "human_promotion_required": True,
            "authority": False,
        }
        return {"consumption_id": f"codex-consumption:{sha256_json(seed)[:24]}", **seed}


def _validate_task(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    task = _mapping(packet["task"], "task")
    _require_exact_keys(
        task,
        {"task_id", "task_class", "data_class", "objective", "constraints"},
        "task",
    )
    if not isinstance(task["task_id"], str) or not task["task_id"].strip():
        raise StrategyPacketError("task.task_id is required")
    if not isinstance(task["task_class"], str) or not task["task_class"].strip():
        raise StrategyPacketError("task.task_class is required")
    if task["data_class"] not in _ALLOWED_DATA_CLASSES:
        raise StrategyPacketError("task.data_class is not permitted")
    if not isinstance(task["objective"], str) or not task["objective"].strip():
        raise StrategyPacketError("task.objective is required")
    _nonempty_strings(task["constraints"], "task.constraints")
    return task


def _validate_lineage(
    packet: Mapping[str, Any],
    *,
    expected_manifest_cid: str | None,
    expected_repository_commits: Mapping[str, str] | None,
) -> tuple[str | None, tuple[tuple[str, str], ...]]:
    lineage = _mapping(packet["lineage"], "lineage")
    _require_exact_keys(
        lineage,
        {"source_snapshot_manifest_cid", "source_repository_commits"},
        "lineage",
    )
    manifest_cid = lineage["source_snapshot_manifest_cid"]
    if manifest_cid is not None and (
        not isinstance(manifest_cid, str) or not manifest_cid.strip()
    ):
        raise StrategyPacketError("lineage source manifest CID is invalid")
    if expected_manifest_cid is not None and manifest_cid != expected_manifest_cid:
        raise StrategyPacketError("strategy packet snapshot-manifest CID mismatch")

    commits: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(
        _array(lineage["source_repository_commits"], "source_repository_commits")
    ):
        item = _mapping(raw, f"source_repository_commits[{index}]")
        _require_exact_keys(item, {"repository", "commit"}, f"source commit {index}")
        repository = item["repository"]
        commit = item["commit"]
        if not isinstance(repository, str) or not repository.strip():
            raise StrategyPacketError("source repository name is invalid")
        _require_hash(commit, f"source commit for {repository}", length=40)
        if repository in seen:
            raise StrategyPacketError(f"duplicate source repository lineage: {repository}")
        seen.add(repository)
        commits.append((repository, commit))

    if expected_repository_commits:
        actual = dict(commits)
        for repository, expected in expected_repository_commits.items():
            if actual.get(repository) != expected:
                raise StrategyPacketError(
                    f"strategy packet source commit mismatch for {repository}"
                )
    return manifest_cid, tuple(sorted(commits))


def _validate_remote_evidence(packet: Mapping[str, Any]) -> tuple[str, int]:
    raw_evidence = _array(packet["remote_evidence"], "remote_evidence")
    normalized: list[Mapping[str, Any]] = []
    positions: dict[str, int] = {}
    successful = 0

    expected_keys = {
        "provider",
        "model",
        "role",
        "status",
        "created_at",
        "prompt_sha256",
        "response_sha256",
        "position",
        "claims",
        "uncertainties",
        "latency_ms",
        "usage",
        "estimated_cost_usd",
        "authority",
    }
    for index, raw in enumerate(raw_evidence):
        item = _mapping(raw, f"remote_evidence[{index}]")
        _require_exact_keys(item, expected_keys, f"remote_evidence[{index}]")
        if set(item) & _DENIED_EVIDENCE_FIELDS:
            raise StrategyPacketError("raw provider material is forbidden")
        if item["provider"] not in _ALLOWED_PROVIDERS:
            raise StrategyPacketError(f"unknown provider: {item['provider']}")
        if not isinstance(item["model"], str) or not item["model"].strip():
            raise StrategyPacketError("remote evidence model is required")
        if not isinstance(item["role"], str) or not item["role"].strip():
            raise StrategyPacketError("remote evidence role is required")
        if item["status"] not in {"ok", "error", "unavailable"}:
            raise StrategyPacketError("remote evidence status is invalid")
        _parse_time(item["created_at"], "remote evidence created_at")
        _require_hash(item["prompt_sha256"], "prompt_sha256")
        if item["status"] == "ok":
            _require_hash(item["response_sha256"], "response_sha256")
            successful += 1
        elif item["response_sha256"] is not None:
            _require_hash(item["response_sha256"], "response_sha256")
        if item["position"] not in {"support", "oppose", "mixed", "uncertain"}:
            raise StrategyPacketError("remote evidence position is invalid")
        claims = _nonempty_strings(item["claims"], "remote evidence claims", maximum=12)
        uncertainties = _nonempty_strings(
            item["uncertainties"], "remote evidence uncertainties", maximum=12
        )
        if item["status"] == "ok" and (not claims or not uncertainties):
            raise StrategyPacketError(
                "successful evidence requires bounded claims and uncertainties"
            )
        latency = item["latency_ms"]
        if latency is not None and (
            not isinstance(latency, (int, float))
            or not math.isfinite(float(latency))
            or float(latency) < 0
        ):
            raise StrategyPacketError("remote evidence latency is invalid")
        if not isinstance(item["usage"], dict):
            raise StrategyPacketError("remote evidence usage must be an object")
        cost = item["estimated_cost_usd"]
        if (
            not isinstance(cost, (int, float))
            or not math.isfinite(float(cost))
            or float(cost) < 0
        ):
            raise StrategyPacketError("remote evidence estimated cost is invalid")
        if item["authority"] is not False:
            raise StrategyPacketError("remote evidence authority must be false")
        positions[item["position"]] = positions.get(item["position"], 0) + 1
        normalized.append(item)

    summary = _mapping(packet["evidence_summary"], "evidence_summary")
    _require_exact_keys(
        summary,
        {
            "requested_provider_count",
            "observed_provider_count",
            "successful_evidence_count",
            "failed_or_unavailable_count",
            "positions",
            "agreement_is_not_truth",
            "remote_output_may_not_override_local_scores",
        },
        "evidence_summary",
    )
    observed_providers = len({item["provider"] for item in normalized})
    if summary["observed_provider_count"] != observed_providers:
        raise StrategyPacketError("evidence_summary observed_provider_count mismatch")
    if summary["successful_evidence_count"] != successful:
        raise StrategyPacketError("evidence_summary successful_evidence_count mismatch")
    if summary["failed_or_unavailable_count"] != len(normalized) - successful:
        raise StrategyPacketError("evidence_summary failed count mismatch")
    if summary["positions"] != dict(sorted(positions.items())):
        raise StrategyPacketError("evidence_summary positions mismatch")
    if summary["agreement_is_not_truth"] is not True:
        raise StrategyPacketError("provider agreement may not be treated as truth")
    if summary["remote_output_may_not_override_local_scores"] is not True:
        raise StrategyPacketError("remote evidence may not override local scores")
    return sha256_json(normalized), successful


def _validate_fast_path(packet: Mapping[str, Any]) -> None:
    fast = _mapping(packet["local_fast_path"], "local_fast_path")
    _require_exact_keys(
        fast,
        {
            "remote_dependency",
            "offline_behavior",
            "stale_behavior",
            "deterministic_revalidation_required",
            "rust_arithmetic_verification_required_when_applicable",
            "perturbation_test_required",
            "human_promotion_required",
        },
        "local_fast_path",
    )
    required = {
        "remote_dependency": False,
        "stale_behavior": "reject",
        "deterministic_revalidation_required": True,
        "rust_arithmetic_verification_required_when_applicable": True,
        "perturbation_test_required": True,
        "human_promotion_required": True,
    }
    for key, expected in required.items():
        if fast[key] != expected:
            raise StrategyPacketError(f"local_fast_path.{key} violates Codex policy")
    if fast["offline_behavior"] not in {"continue_local", "no_proposal"}:
        raise StrategyPacketError("local_fast_path.offline_behavior is invalid")


def _parse_hints(
    packet: Mapping[str, Any], case: SeededBenchmarkCase
) -> tuple[CodexEvaluationHint, ...]:
    cycles = enumerate_triangular_cycles(
        case.edges,
        gas_penalty_log=case.gas_penalty_log,
        minimum_log_delta=case.minimum_log_delta,
    )
    route_ids = {cycle.candidate_id for cycle in cycles}
    provider_ids = {provider.provider_id for provider in case.providers}
    bucket_ids = {bucket.bucket_id for bucket in case.buckets}
    hints: list[CodexEvaluationHint] = []
    seen: set[str] = set()

    for index, raw in enumerate(_array(packet["proposals"], "proposals")):
        proposal = _mapping(raw, f"proposals[{index}]")
        _require_exact_keys(
            proposal,
            {
                "proposal_id",
                "summary",
                "assumptions",
                "local_tests",
                "codex_evaluation",
            },
            f"proposals[{index}]",
        )
        proposal_id = proposal["proposal_id"]
        summary = proposal["summary"]
        if not isinstance(proposal_id, str) or not proposal_id.strip():
            raise StrategyPacketError("proposal_id is required")
        if proposal_id in seen:
            raise StrategyPacketError(f"duplicate proposal_id: {proposal_id}")
        seen.add(proposal_id)
        if not isinstance(summary, str) or not summary.strip():
            raise StrategyPacketError("proposal summary is required")
        _nonempty_strings(proposal["assumptions"], "proposal assumptions")
        _nonempty_strings(proposal["local_tests"], "proposal local_tests")

        evaluation = _mapping(proposal["codex_evaluation"], "codex_evaluation")
        _require_exact_keys(
            evaluation,
            {
                "benchmark_id",
                "route_candidate_id",
                "allowed_provider_ids",
                "allowed_bucket_ids",
                "evaluation_mode",
                "authority",
            },
            "codex_evaluation",
        )
        providers = _nonempty_strings(
            evaluation["allowed_provider_ids"], "allowed_provider_ids"
        )
        buckets = _nonempty_strings(
            evaluation["allowed_bucket_ids"], "allowed_bucket_ids"
        )
        if not providers or not buckets:
            raise StrategyPacketError(
                "Codex evaluation requires at least one provider and amount bucket"
            )
        hint = CodexEvaluationHint(
            proposal_id=proposal_id,
            summary=summary,
            benchmark_id=str(evaluation["benchmark_id"]),
            route_candidate_id=str(evaluation["route_candidate_id"]),
            allowed_provider_ids=providers,
            allowed_bucket_ids=buckets,
            evaluation_mode=str(evaluation["evaluation_mode"]),
            authority=bool(evaluation["authority"]),
        )
        if hint.benchmark_id != case.benchmark_id:
            raise StrategyPacketError("proposal benchmark_id does not match local case")
        if hint.route_candidate_id not in route_ids:
            raise StrategyPacketError(
                f"proposal references unknown local route: {hint.route_candidate_id}"
            )
        unknown_providers = sorted(set(providers) - provider_ids)
        unknown_buckets = sorted(set(buckets) - bucket_ids)
        if unknown_providers:
            raise StrategyPacketError(
                f"proposal references unknown providers: {unknown_providers}"
            )
        if unknown_buckets:
            raise StrategyPacketError(
                f"proposal references unknown buckets: {unknown_buckets}"
            )
        hints.append(hint)
    if not hints:
        raise StrategyPacketError("No Codex evaluation hints were supplied")
    return tuple(sorted(hints, key=lambda item: item.proposal_id))


def consume_strategy_packet(
    packet: Mapping[str, Any],
    case: SeededBenchmarkCase,
    *,
    now: datetime | None = None,
    expected_manifest_cid: str | None = None,
    expected_repository_commits: Mapping[str, str] | None = None,
) -> ConsumedStrategyPacket:
    """Validate a strategy packet and bind its hints to the local candidate universe."""

    _require_exact_keys(packet, _TOP_LEVEL_KEYS, "strategy packet")
    if packet["packet_version"] != _PACKET_VERSION:
        raise StrategyPacketError("Unsupported strategy packet version")
    if packet["authority"] is not False:
        raise StrategyPacketError("Strategy packet authority must be false")
    if packet["stores_raw_provider_responses"] is not False:
        raise StrategyPacketError("Raw provider responses may not cross the membrane")
    _require_hash(packet["packet_id"], "packet_id")
    _require_hash(packet["request_sha256"], "request_sha256")

    packet_core = {key: value for key, value in packet.items() if key != "packet_id"}
    if sha256_json(packet_core) != packet["packet_id"]:
        raise StrategyPacketError("Strategy packet hash mismatch")

    compiled = _parse_time(packet["compiled_at"], "compiled_at")
    expires = _parse_time(packet["expires_at"], "expires_at")
    ttl = packet["ttl_seconds"]
    if not isinstance(ttl, int) or not 1 <= ttl <= 86400:
        raise StrategyPacketError("ttl_seconds must be in [1, 86400]")
    if int((expires - compiled).total_seconds()) != ttl:
        raise StrategyPacketError("ttl_seconds does not match the packet timestamps")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if expires <= current:
        raise StrategyPacketError("Strategy packet is expired")

    task = _validate_task(packet)
    manifest_cid, commits = _validate_lineage(
        packet,
        expected_manifest_cid=expected_manifest_cid,
        expected_repository_commits=expected_repository_commits,
    )
    evidence_sha256, successful = _validate_remote_evidence(packet)
    _validate_fast_path(packet)

    prohibited = set(
        _nonempty_strings(packet["prohibited_actions"], "prohibited_actions")
    )
    if not _REQUIRED_PROHIBITED_ACTIONS.issubset(prohibited):
        missing = sorted(_REQUIRED_PROHIBITED_ACTIONS - prohibited)
        raise StrategyPacketError(f"strategy packet omitted prohibited actions: {missing}")

    hints = _parse_hints(packet, case)
    return ConsumedStrategyPacket(
        packet_id=packet["packet_id"],
        request_sha256=packet["request_sha256"],
        compiled_at=packet["compiled_at"],
        expires_at=packet["expires_at"],
        task_class=task["task_class"],
        source_snapshot_manifest_cid=manifest_cid,
        source_repository_commits=commits,
        evidence_sha256=evidence_sha256,
        successful_evidence_count=successful,
        hints=hints,
    )


def _select_flash_candidate(
    confidence: Any, candidates: Sequence[FlashLiquidityCandidate]
) -> FlashLiquidityCandidate:
    selected = confidence.best_sample.selected_candidate_ids
    if len(selected) != 1:
        raise StrategyPacketError("packet-guided flash QUBO must select one candidate")
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    return by_id[selected[0]]


def _evaluate_hint(
    hint: CodexEvaluationHint,
    case: SeededBenchmarkCase,
    cycles: Sequence[TriangularCycle],
    route_model: QuboModel,
    *,
    route_executable: str | Path,
    flash_executable: str | Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    route_by_id = {cycle.candidate_id: cycle for cycle in cycles}
    route = route_by_id[hint.route_candidate_id]
    route_confidence = build_qaoa_confidence_receipt(
        route_model,
        cycles,
        _one_hot_distribution(route_model, route.candidate_id),
        solver="strategy-packet-one-hot-replay",
        reps=1,
    )
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

    providers_by_id = {provider.provider_id: provider for provider in case.providers}
    buckets_by_id = {bucket.bucket_id: bucket for bucket in case.buckets}
    providers: tuple[FlashLiquidityProvider, ...] = tuple(
        providers_by_id[provider_id] for provider_id in hint.allowed_provider_ids
    )
    buckets: tuple[FlashAmountBucket, ...] = tuple(
        buckets_by_id[bucket_id] for bucket_id in hint.allowed_bucket_ids
    )
    flash_candidates = enumerate_flash_liquidity_candidates(
        (route,), providers, buckets
    )
    if not flash_candidates:
        raise StrategyPacketError(
            f"proposal {hint.proposal_id} produced no local flash geometry"
        )
    flash_model = build_flash_liquidity_qubo(flash_candidates)
    flash_cycles = tuple(candidate.as_qaoa_cycle() for candidate in flash_candidates)
    flash_confidence = build_qaoa_confidence_receipt(
        flash_model,
        flash_cycles,
        exact_distribution(flash_model, flash_cycles),
        solver="strategy-packet-exact-replay",
        reps=1,
    )
    flash_candidate = _select_flash_candidate(flash_confidence, flash_candidates)
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
    return {
        "proposal": hint.as_dict(),
        "route_model_sha256": qubo_model_sha256(route_model),
        "route_confidence": route_confidence.as_dict(),
        "route_verification": route_verification.as_dict(),
        "calibration": calibration.as_dict(),
        "robustness": robustness.as_dict(),
        "flash_model_sha256": qubo_model_sha256(flash_model),
        "flash_confidence": flash_confidence.as_dict(),
        "flash_candidate": flash_candidate.as_dict(),
        "flash_verification": flash_verification.as_dict(),
        "locally_verified": bool(
            route_verification.passes_margin
            and robustness.survival_count > 0
            and flash_verification.capacity_ok
            and flash_verification.borrowed_asset_matches_route
            and flash_verification.repayment_feasible
        ),
        "authority": False,
    }


def run_seeded_planning_uplift(
    packet: Mapping[str, Any],
    case: SeededBenchmarkCase,
    *,
    route_executable: str | Path,
    flash_executable: str | Path,
    now: datetime | None = None,
    expected_manifest_cid: str | None = None,
    expected_repository_commits: Mapping[str, str] | None = None,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    """Compare packet-guided candidates with the deterministic local-only baseline."""

    consumed = consume_strategy_packet(
        packet,
        case,
        now=now,
        expected_manifest_cid=expected_manifest_cid,
        expected_repository_commits=expected_repository_commits,
    )
    baseline = run_seeded_benchmark(
        case,
        route_executable=route_executable,
        flash_executable=flash_executable,
        timeout_seconds=timeout_seconds,
    )
    cycles = enumerate_triangular_cycles(
        case.edges,
        gas_penalty_log=case.gas_penalty_log,
        minimum_log_delta=case.minimum_log_delta,
    )
    route_model = build_cycle_selection_qubo(cycles)
    evaluations = [
        _evaluate_hint(
            hint,
            case,
            cycles,
            route_model,
            route_executable=route_executable,
            flash_executable=flash_executable,
            timeout_seconds=timeout_seconds,
        )
        for hint in consumed.hints
    ]

    baseline_route_id = baseline.route_confidence.best_sample.selected_candidate_ids[0]
    baseline_metrics = {
        "route_candidate_id": baseline_route_id,
        "route_net_log_delta": baseline.route_verification.net_log_delta,
        "robustness_survival_rate": baseline.robustness.survival_rate,
        "worst_case_log_delta": baseline.robustness.worst_case_log_delta,
        "projected_net_profit": baseline.flash_verification.net_profit,
        "repayment_feasible": baseline.flash_verification.repayment_feasible,
        "authority": False,
    }

    comparisons: list[dict[str, Any]] = []
    for evaluation in evaluations:
        route_verification = evaluation["route_verification"]["verification"]
        robustness = evaluation["robustness"]
        flash_verification = evaluation["flash_verification"]["verification"]
        delta = {
            "proposal_id": evaluation["proposal"]["proposal_id"],
            "route_candidate_id": evaluation["proposal"]["route_candidate_id"],
            "adds_route_diversity": (
                evaluation["proposal"]["route_candidate_id"] != baseline_route_id
            ),
            "route_energy_gap_to_local_exact": evaluation["route_confidence"][
                "energy_gap_to_classical"
            ],
            "route_net_log_delta_delta": (
                route_verification["net_log_delta"]
                - baseline_metrics["route_net_log_delta"]
            ),
            "robustness_survival_rate_delta": (
                robustness["survival_rate"]
                - baseline_metrics["robustness_survival_rate"]
            ),
            "worst_case_log_delta_delta": (
                robustness["worst_case_log_delta"]
                - baseline_metrics["worst_case_log_delta"]
            ),
            "projected_net_profit_delta": (
                flash_verification["net_profit"]
                - baseline_metrics["projected_net_profit"]
            ),
            "repayment_feasible": flash_verification["repayment_feasible"],
            "locally_verified": evaluation["locally_verified"],
            "authority": False,
        }
        if (
            delta["locally_verified"]
            and (
                delta["robustness_survival_rate_delta"] > 1e-15
                or delta["worst_case_log_delta_delta"] > 1e-15
                or delta["projected_net_profit_delta"] > 1e-12
                or delta["adds_route_diversity"]
            )
        ):
            delta["uplift_class"] = "positive"
        elif delta["locally_verified"]:
            delta["uplift_class"] = "neutral"
        else:
            delta["uplift_class"] = "rejected"
        comparisons.append(delta)

    classes = {item["uplift_class"] for item in comparisons}
    if "positive" in classes:
        overall = "positive"
    elif "neutral" in classes:
        overall = "neutral"
    else:
        overall = "no_verified_uplift"

    core = {
        "schema_version": _UPLIFT_SCHEMA,
        "benchmark_id": case.benchmark_id,
        "benchmark_sha256": case.case_sha256,
        "snapshot_sha256": case.snapshot_sha256,
        "strategy_packet": consumed.as_dict(),
        "local_baseline": baseline.as_dict(),
        "packet_guided_evaluations": evaluations,
        "comparisons": comparisons,
        "overall_uplift_class": overall,
        "negative_or_zero_result_is_valid_evidence": True,
        "provider_agreement_is_not_truth": True,
        "remote_dependency": False,
        "historical_replay": True,
        "human_promotion_required": True,
        "authority": False,
    }
    return {
        "receipt_id": f"planning-uplift:{sha256_json(core)[:24]}",
        **core,
    }


def write_uplift_receipt(receipt: Mapping[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consume one SpiralBloom strategy packet and run seeded uplift replay."
    )
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--route-verifier", required=True, type=Path)
    parser.add_argument("--flash-verifier", required=True, type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--now")
    parser.add_argument("--expected-manifest-cid")
    parser.add_argument(
        "--expected-source-commit",
        action="append",
        default=[],
        metavar="REPOSITORY=SHA",
    )
    args = parser.parse_args()

    expected_commits: dict[str, str] = {}
    for entry in args.expected_source_commit:
        if "=" not in entry:
            raise SystemExit("--expected-source-commit must be REPOSITORY=SHA")
        repository, commit = entry.split("=", 1)
        expected_commits[repository] = commit

    packet = _mapping(
        json.loads(args.packet.read_text(encoding="utf-8")), "strategy packet"
    )
    replay_now = _parse_time(args.now, "--now") if args.now else None
    receipt = run_seeded_planning_uplift(
        packet,
        load_benchmark_case(args.case),
        route_executable=args.route_verifier.resolve(),
        flash_executable=args.flash_verifier.resolve(),
        now=replay_now,
        expected_manifest_cid=args.expected_manifest_cid,
        expected_repository_commits=expected_commits or None,
    )
    write_uplift_receipt(receipt, args.receipt_out)
    print(
        json.dumps(
            {
                "ok": True,
                "receipt_id": receipt["receipt_id"],
                "overall_uplift_class": receipt["overall_uplift_class"],
                "proposal_count": len(receipt["comparisons"]),
                "authority": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
