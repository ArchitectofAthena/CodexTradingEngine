"""Simulation-only flash-liquidity geometry for hybrid delta research.

The module expands a verified triangular route into provider, borrowed-asset, and
amount-bucket choices. QAOA may rank the combined geometry; a separate local Rust
binary independently verifies capacity and repayment arithmetic. Nothing here can
borrow, sign, submit, schedule, move capital, or grant authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from eve_q.qaoa_delta import MarketEdge, QuboModel, TriangularCycle
from eve_q.qaoa_sampling import QaoaConfidenceReceipt

_BPS = 10_000.0
_MAX_PAYLOAD_BYTES = 64 * 1024
_MAX_OUTPUT_BYTES = 64 * 1024
_REQUEST_SCHEMA = "flash-liquidity-request-v0.1"
_RESPONSE_SCHEMA = "flash-liquidity-response-v0.1"


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")


def _stable_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _edge_dict(edge: MarketEdge) -> dict[str, object]:
    return {
        "edge_id": edge.edge_id,
        "source_asset": edge.source_asset,
        "target_asset": edge.target_asset,
        "quoted_rate": edge.quoted_rate,
        "fee_bps": edge.fee_bps,
        "slippage_bps": edge.slippage_bps,
        "latency_penalty_bps": edge.latency_penalty_bps,
    }


@dataclass(frozen=True)
class FlashLiquidityProvider:
    provider_id: str
    fee_bps: float
    capacity_by_asset: Mapping[str, float]
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.provider_id.startswith("flash-provider:"):
            raise ValueError("provider_id must use the flash-provider namespace")
        if not math.isfinite(self.fee_bps) or not 0.0 <= self.fee_bps < _BPS:
            raise ValueError("fee_bps must be finite in [0, 10000)")
        if not self.capacity_by_asset:
            raise ValueError("capacity_by_asset cannot be empty")
        for asset, capacity in self.capacity_by_asset.items():
            if not asset.strip():
                raise ValueError("capacity assets must be non-empty")
            if not math.isfinite(capacity) or capacity <= 0.0:
                raise ValueError("provider capacities must be finite and positive")
        if self.authority:
            raise ValueError("flash-liquidity providers cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "fee_bps": self.fee_bps,
            "capacity_by_asset": dict(sorted(self.capacity_by_asset.items())),
            "authority": False,
        }


@dataclass(frozen=True)
class FlashAmountBucket:
    bucket_id: str
    asset: str
    principal_amount: float
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.bucket_id.startswith("flash-bucket:"):
            raise ValueError("bucket_id must use the flash-bucket namespace")
        if not self.asset.strip():
            raise ValueError("asset is required")
        if not math.isfinite(self.principal_amount) or self.principal_amount <= 0.0:
            raise ValueError("principal_amount must be finite and positive")
        if self.authority:
            raise ValueError("flash amount buckets cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "bucket_id": self.bucket_id,
            "asset": self.asset,
            "principal_amount": self.principal_amount,
            "authority": False,
        }


@dataclass(frozen=True)
class FlashLiquidityCandidate:
    candidate_id: str
    route_candidate_id: str
    edge_ids: tuple[str, str, str]
    asset_path: tuple[str, str, str, str]
    provider_id: str
    borrowed_asset: str
    amount_bucket_id: str
    principal_amount: float
    provider_fee_bps: float
    available_capacity: float
    repayment_amount: float
    projected_output_amount: float
    projected_net_profit: float
    net_log_delta: float
    feasible: bool
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.candidate_id.startswith("flash-geometry:"):
            raise ValueError("candidate_id must use the flash-geometry namespace")
        if not self.route_candidate_id.startswith("triangle:"):
            raise ValueError("route_candidate_id must use the triangle namespace")
        if len(self.edge_ids) != 3 or len(set(self.edge_ids)) != 3:
            raise ValueError("flash candidates require three distinct route edges")
        if len(self.asset_path) != 4 or self.asset_path[0] != self.asset_path[-1]:
            raise ValueError("asset_path must be a closed triangular route")
        for field_name, value in (
            ("principal_amount", self.principal_amount),
            ("provider_fee_bps", self.provider_fee_bps),
            ("available_capacity", self.available_capacity),
            ("repayment_amount", self.repayment_amount),
            ("projected_output_amount", self.projected_output_amount),
            ("projected_net_profit", self.projected_net_profit),
            ("net_log_delta", self.net_log_delta),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{field_name} must be finite")
        if self.principal_amount <= 0.0 or self.available_capacity <= 0.0:
            raise ValueError("principal and capacity must be positive")
        if not 0.0 <= self.provider_fee_bps < _BPS:
            raise ValueError("provider_fee_bps must be in [0, 10000)")
        expected_feasible = (
            self.borrowed_asset == self.asset_path[0]
            and self.principal_amount <= self.available_capacity
            and self.projected_output_amount >= self.repayment_amount
            and self.projected_net_profit >= 0.0
        )
        if self.feasible is not expected_feasible:
            raise ValueError("feasible must match capacity, route asset, and repayment arithmetic")
        if self.authority:
            raise ValueError("flash-liquidity candidates cannot grant authority")

    def as_qaoa_cycle(self) -> TriangularCycle:
        return TriangularCycle(
            candidate_id=self.candidate_id,
            edge_ids=self.edge_ids,
            asset_path=self.asset_path,
            net_multiplier=math.exp(self.net_log_delta),
            net_log_delta=self.net_log_delta,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "route_candidate_id": self.route_candidate_id,
            "edge_ids": list(self.edge_ids),
            "asset_path": list(self.asset_path),
            "provider_id": self.provider_id,
            "borrowed_asset": self.borrowed_asset,
            "amount_bucket_id": self.amount_bucket_id,
            "principal_amount": self.principal_amount,
            "provider_fee_bps": self.provider_fee_bps,
            "available_capacity": self.available_capacity,
            "repayment_amount": self.repayment_amount,
            "projected_output_amount": self.projected_output_amount,
            "projected_net_profit": self.projected_net_profit,
            "net_log_delta": self.net_log_delta,
            "feasible": self.feasible,
            "authority": False,
        }


def _flash_candidate_id(route_id: str, provider_id: str, bucket_id: str) -> str:
    digest = hashlib.sha256(f"{route_id}|{provider_id}|{bucket_id}".encode("utf-8")).hexdigest()
    return f"flash-geometry:{digest[:20]}"


def enumerate_flash_liquidity_candidates(
    routes: Sequence[TriangularCycle],
    providers: Sequence[FlashLiquidityProvider],
    buckets: Sequence[FlashAmountBucket],
) -> tuple[FlashLiquidityCandidate, ...]:
    """Expand route, provider, and amount-bucket choices deterministically."""

    route_ids = [route.candidate_id for route in routes]
    provider_ids = [provider.provider_id for provider in providers]
    bucket_ids = [bucket.bucket_id for bucket in buckets]
    if len(set(route_ids)) != len(route_ids):
        raise ValueError("route candidate identifiers must be unique")
    if len(set(provider_ids)) != len(provider_ids):
        raise ValueError("provider identifiers must be unique")
    if len(set(bucket_ids)) != len(bucket_ids):
        raise ValueError("amount bucket identifiers must be unique")

    candidates: list[FlashLiquidityCandidate] = []
    for route in sorted(routes, key=lambda item: item.candidate_id):
        borrowed_asset = route.asset_path[0]
        route_multiplier_after_gas = math.exp(route.net_log_delta)
        for provider in sorted(providers, key=lambda item: item.provider_id):
            capacity = provider.capacity_by_asset.get(borrowed_asset)
            if capacity is None:
                continue
            for bucket in sorted(buckets, key=lambda item: item.bucket_id):
                if bucket.asset != borrowed_asset:
                    continue
                repayment = bucket.principal_amount * (1.0 + provider.fee_bps / _BPS)
                projected_output = bucket.principal_amount * route_multiplier_after_gas
                net_profit = projected_output - repayment
                net_log_delta = math.log(projected_output / repayment)
                feasible = bucket.principal_amount <= capacity and net_profit >= 0.0
                candidates.append(
                    FlashLiquidityCandidate(
                        candidate_id=_flash_candidate_id(
                            route.candidate_id, provider.provider_id, bucket.bucket_id
                        ),
                        route_candidate_id=route.candidate_id,
                        edge_ids=route.edge_ids,
                        asset_path=route.asset_path,
                        provider_id=provider.provider_id,
                        borrowed_asset=borrowed_asset,
                        amount_bucket_id=bucket.bucket_id,
                        principal_amount=bucket.principal_amount,
                        provider_fee_bps=provider.fee_bps,
                        available_capacity=capacity,
                        repayment_amount=repayment,
                        projected_output_amount=projected_output,
                        projected_net_profit=net_profit,
                        net_log_delta=net_log_delta,
                        feasible=feasible,
                    )
                )
    return tuple(sorted(candidates, key=lambda item: item.candidate_id))


def build_flash_liquidity_qubo(
    candidates: Sequence[FlashLiquidityCandidate],
    *,
    selection_penalty: float = 10.0,
    infeasible_penalty: float = 100.0,
) -> QuboModel:
    """Build an at-most-one selection QUBO over route-plus-liquidity geometry."""

    if not math.isfinite(selection_penalty) or selection_penalty <= 0.0:
        raise ValueError("selection_penalty must be finite and positive")
    if not math.isfinite(infeasible_penalty) or infeasible_penalty <= 0.0:
        raise ValueError("infeasible_penalty must be finite and positive")
    ordered = tuple(sorted(candidates, key=lambda item: item.candidate_id))
    ids = tuple(candidate.candidate_id for candidate in ordered)
    if len(set(ids)) != len(ids):
        raise ValueError("flash candidate identifiers must be unique")
    linear = {
        candidate.candidate_id: (
            -candidate.net_log_delta
            if candidate.feasible
            else infeasible_penalty + abs(candidate.net_log_delta)
        )
        for candidate in ordered
    }
    quadratic = {
        (left.candidate_id, right.candidate_id): selection_penalty
        for index, left in enumerate(ordered)
        for right in ordered[index + 1 :]
    }
    return QuboModel(variable_order=ids, linear=linear, quadratic=quadratic)


@dataclass(frozen=True)
class FlashVerificationRequest:
    request_id: str
    snapshot_sha256: str
    model_sha256: str
    confidence_receipt_id: str
    flash_candidate: FlashLiquidityCandidate
    edges: tuple[Mapping[str, object], Mapping[str, object], Mapping[str, object]]
    gas_penalty_log: float
    minimum_net_profit: float
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.request_id.startswith("flash-verify:"):
            raise ValueError("request_id must use the flash-verify namespace")
        _require_sha256(self.snapshot_sha256, "snapshot_sha256")
        _require_sha256(self.model_sha256, "model_sha256")
        if not self.confidence_receipt_id.startswith("qaoa-confidence:"):
            raise ValueError("confidence_receipt_id must use the qaoa-confidence namespace")
        if len(self.edges) != 3:
            raise ValueError("exactly three route edges are required")
        if not math.isfinite(self.gas_penalty_log) or self.gas_penalty_log < 0.0:
            raise ValueError("gas_penalty_log must be finite and non-negative")
        if not math.isfinite(self.minimum_net_profit) or self.minimum_net_profit < 0.0:
            raise ValueError("minimum_net_profit must be finite and non-negative")
        if self.authority:
            raise ValueError("flash verification requests cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": _REQUEST_SCHEMA,
            "request_id": self.request_id,
            "snapshot_sha256": self.snapshot_sha256,
            "model_sha256": self.model_sha256,
            "confidence_receipt_id": self.confidence_receipt_id,
            "flash_candidate_id": self.flash_candidate.candidate_id,
            "route_candidate_id": self.flash_candidate.route_candidate_id,
            "edges": [dict(edge) for edge in self.edges],
            "gas_penalty_log": self.gas_penalty_log,
            "provider_id": self.flash_candidate.provider_id,
            "borrowed_asset": self.flash_candidate.borrowed_asset,
            "amount_bucket_id": self.flash_candidate.amount_bucket_id,
            "principal_amount": self.flash_candidate.principal_amount,
            "provider_fee_bps": self.flash_candidate.provider_fee_bps,
            "available_capacity": self.flash_candidate.available_capacity,
            "minimum_net_profit": self.minimum_net_profit,
            "authority": False,
        }


@dataclass(frozen=True)
class FlashVerificationEvidence:
    request_id: str
    snapshot_sha256: str
    model_sha256: str
    confidence_receipt_id: str
    flash_candidate_id: str
    route_candidate_id: str
    verifier: str
    route_net_log_delta: float
    route_output_amount: float
    repayment_amount: float
    net_profit: float
    capacity_ok: bool
    borrowed_asset_matches_route: bool
    repayment_feasible: bool
    authority: bool = False

    def __post_init__(self) -> None:
        for field_name, value in (
            ("route_net_log_delta", self.route_net_log_delta),
            ("route_output_amount", self.route_output_amount),
            ("repayment_amount", self.repayment_amount),
            ("net_profit", self.net_profit),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{field_name} must be finite")
        if self.authority:
            raise ValueError("flash verification evidence cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": _RESPONSE_SCHEMA,
            "request_id": self.request_id,
            "snapshot_sha256": self.snapshot_sha256,
            "model_sha256": self.model_sha256,
            "confidence_receipt_id": self.confidence_receipt_id,
            "flash_candidate_id": self.flash_candidate_id,
            "route_candidate_id": self.route_candidate_id,
            "verifier": self.verifier,
            "status": "verified",
            "verification": {
                "route_net_log_delta": self.route_net_log_delta,
                "route_output_amount": self.route_output_amount,
                "repayment_amount": self.repayment_amount,
                "net_profit": self.net_profit,
                "capacity_ok": self.capacity_ok,
                "borrowed_asset_matches_route": self.borrowed_asset_matches_route,
                "repayment_feasible": self.repayment_feasible,
                "authority": False,
            },
            "authority": False,
        }


def build_flash_verification_request(
    receipt: QaoaConfidenceReceipt,
    candidate: FlashLiquidityCandidate,
    market_edges: Sequence[MarketEdge],
    *,
    snapshot_sha256: str,
    gas_penalty_log: float,
    minimum_net_profit: float = 0.0,
) -> FlashVerificationRequest:
    _require_sha256(snapshot_sha256, "snapshot_sha256")
    if candidate.candidate_id not in receipt.best_sample.selected_candidate_ids:
        raise ValueError("flash candidate must be selected by the confidence receipt best sample")
    edges_by_id = {edge.edge_id: edge for edge in market_edges}
    if len(edges_by_id) != len(market_edges):
        raise ValueError("market edge identifiers must be unique")
    try:
        ordered_edges = tuple(_edge_dict(edges_by_id[edge_id]) for edge_id in candidate.edge_ids)
    except KeyError as exc:
        raise ValueError(f"candidate references missing market edge {exc.args[0]!r}") from exc
    seed = {
        "snapshot_sha256": snapshot_sha256,
        "model_sha256": receipt.model_sha256,
        "confidence_receipt_id": receipt.receipt_id,
        "candidate": candidate.as_dict(),
        "edges": ordered_edges,
        "gas_penalty_log": gas_penalty_log,
        "minimum_net_profit": minimum_net_profit,
        "authority": False,
    }
    return FlashVerificationRequest(
        request_id=f"flash-verify:{_stable_hash(seed)[:24]}",
        snapshot_sha256=snapshot_sha256,
        model_sha256=receipt.model_sha256,
        confidence_receipt_id=receipt.receipt_id,
        flash_candidate=candidate,
        edges=ordered_edges,  # type: ignore[arg-type]
        gas_penalty_log=gas_penalty_log,
        minimum_net_profit=minimum_net_profit,
    )


def run_rust_flash_verification(
    request: FlashVerificationRequest,
    *,
    executable: str | Path,
    timeout_seconds: float = 2.0,
) -> FlashVerificationEvidence:
    executable_path = Path(executable)
    if not executable_path.is_absolute():
        raise ValueError("Rust flash verifier executable path must be absolute")
    if not executable_path.is_file():
        raise ValueError("Rust flash verifier executable does not exist")
    if timeout_seconds <= 0.0 or not math.isfinite(timeout_seconds):
        raise ValueError("timeout_seconds must be finite and positive")
    request_dict = request.as_dict()
    payload = json.dumps(request_dict, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(payload) > _MAX_PAYLOAD_BYTES:
        raise ValueError("flash verification request exceeds the 65536-byte protocol limit")
    try:
        completed = subprocess.run(
            [str(executable_path)],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
            shell=False,
            close_fds=True,
            cwd=executable_path.parent,
            env={"PATH": os.environ.get("PATH", "")},
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Rust flash verification timed out; candidate rejected") from exc
    if len(completed.stdout) > _MAX_OUTPUT_BYTES or len(completed.stderr) > _MAX_OUTPUT_BYTES:
        raise RuntimeError("Rust flash verification output exceeded the protocol limit")
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Rust flash verification rejected the request: {message[:1000]}")
    try:
        response = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Rust flash verification returned malformed JSON") from exc
    if not isinstance(response, dict):
        raise RuntimeError("Rust flash verification response must be a JSON object")
    expected_top = {
        "schema_version", "request_id", "snapshot_sha256", "model_sha256",
        "confidence_receipt_id", "flash_candidate_id", "route_candidate_id",
        "verifier", "status", "verification", "authority",
    }
    if set(response) != expected_top:
        raise RuntimeError("Rust flash verification response keys mismatch")
    if response["schema_version"] != _RESPONSE_SCHEMA or response["status"] != "verified":
        raise RuntimeError("Rust flash verification response schema or status mismatch")
    for field_name in (
        "request_id", "snapshot_sha256", "model_sha256", "confidence_receipt_id",
        "flash_candidate_id", "route_candidate_id",
    ):
        if response[field_name] != request_dict[field_name]:
            raise RuntimeError(f"Rust flash verification changed {field_name}")
    if response["authority"] is not False:
        raise RuntimeError("Rust flash verification attempted authority escalation")
    if not isinstance(response["verifier"], str) or not response["verifier"].startswith(
        "codex-flash-liquidity-verifier/"
    ):
        raise RuntimeError("Rust flash verifier identity is invalid")
    verification = response["verification"]
    expected_verification = {
        "route_net_log_delta", "route_output_amount", "repayment_amount", "net_profit",
        "capacity_ok", "borrowed_asset_matches_route", "repayment_feasible", "authority",
    }
    if not isinstance(verification, dict) or set(verification) != expected_verification:
        raise RuntimeError("Rust flash verification payload keys mismatch")
    if verification["authority"] is not False:
        raise RuntimeError("Rust flash verification payload attempted authority escalation")
    return FlashVerificationEvidence(
        request_id=str(response["request_id"]),
        snapshot_sha256=str(response["snapshot_sha256"]),
        model_sha256=str(response["model_sha256"]),
        confidence_receipt_id=str(response["confidence_receipt_id"]),
        flash_candidate_id=str(response["flash_candidate_id"]),
        route_candidate_id=str(response["route_candidate_id"]),
        verifier=str(response["verifier"]),
        route_net_log_delta=float(verification["route_net_log_delta"]),
        route_output_amount=float(verification["route_output_amount"]),
        repayment_amount=float(verification["repayment_amount"]),
        net_profit=float(verification["net_profit"]),
        capacity_ok=bool(verification["capacity_ok"]),
        borrowed_asset_matches_route=bool(verification["borrowed_asset_matches_route"]),
        repayment_feasible=bool(verification["repayment_feasible"]),
    )
