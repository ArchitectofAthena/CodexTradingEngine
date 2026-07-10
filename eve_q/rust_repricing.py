"""Fail-closed Python bridge to the isolated Rust exact repricer.

The bridge serializes one bounded candidate request, invokes one explicitly chosen
local executable with ``shell=False``, and validates one deterministic response.
It has no wallet, RPC, scheduler, network, or capital authority.
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

from eve_q.qaoa_delta import MarketEdge, TriangularCycle
from eve_q.qaoa_sampling import QaoaConfidenceReceipt

_REQUEST_SCHEMA = "delta-repricing-request-v0.1"
_RESPONSE_SCHEMA = "delta-repricing-response-v0.1"
_MAX_PAYLOAD_BYTES = 64 * 1024
_MAX_OUTPUT_BYTES = 64 * 1024


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")


def _require_exact_keys(value: Mapping[str, object], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{context} keys mismatch; missing={missing}, extra={extra}")


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
class RustRepricingRequest:
    request_id: str
    snapshot_sha256: str
    model_sha256: str
    confidence_receipt_id: str
    candidate_id: str
    edges: tuple[Mapping[str, object], Mapping[str, object], Mapping[str, object]]
    gas_penalty_log: float
    minimum_log_delta: float
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.request_id.startswith("delta-reprice:"):
            raise ValueError("request_id must use the delta-reprice namespace")
        _require_sha256(self.snapshot_sha256, "snapshot_sha256")
        _require_sha256(self.model_sha256, "model_sha256")
        if not self.confidence_receipt_id.startswith("qaoa-confidence:"):
            raise ValueError("confidence_receipt_id must use the qaoa-confidence namespace")
        if not self.candidate_id.startswith("triangle:"):
            raise ValueError("candidate_id must use the triangle namespace")
        if len(self.edges) != 3:
            raise ValueError("exactly three edges are required")
        if not math.isfinite(self.gas_penalty_log) or self.gas_penalty_log < 0.0:
            raise ValueError("gas_penalty_log must be finite and non-negative")
        if not math.isfinite(self.minimum_log_delta):
            raise ValueError("minimum_log_delta must be finite")
        if self.authority:
            raise ValueError("repricing requests cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": _REQUEST_SCHEMA,
            "request_id": self.request_id,
            "snapshot_sha256": self.snapshot_sha256,
            "model_sha256": self.model_sha256,
            "confidence_receipt_id": self.confidence_receipt_id,
            "candidate_id": self.candidate_id,
            "edges": [dict(edge) for edge in self.edges],
            "gas_penalty_log": self.gas_penalty_log,
            "minimum_log_delta": self.minimum_log_delta,
            "authority": False,
        }


@dataclass(frozen=True)
class RustRepricingEvidence:
    request_id: str
    snapshot_sha256: str
    model_sha256: str
    confidence_receipt_id: str
    candidate_id: str
    verifier: str
    status: str
    edge_ids: tuple[str, str, str]
    asset_path: tuple[str, str, str, str]
    net_multiplier: float
    net_log_delta: float
    minimum_log_delta: float
    profitable: bool
    passes_margin: bool
    proposal_log_delta: float
    delta_drift: float
    authority: bool = False

    def __post_init__(self) -> None:
        if self.status != "verified":
            raise ValueError("Rust repricing status must be verified")
        for field_name, value in (
            ("net_multiplier", self.net_multiplier),
            ("net_log_delta", self.net_log_delta),
            ("minimum_log_delta", self.minimum_log_delta),
            ("proposal_log_delta", self.proposal_log_delta),
            ("delta_drift", self.delta_drift),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{field_name} must be finite")
        if self.authority:
            raise ValueError("Rust repricing evidence cannot grant authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": _RESPONSE_SCHEMA,
            "request_id": self.request_id,
            "snapshot_sha256": self.snapshot_sha256,
            "model_sha256": self.model_sha256,
            "confidence_receipt_id": self.confidence_receipt_id,
            "candidate_id": self.candidate_id,
            "verifier": self.verifier,
            "status": self.status,
            "verification": {
                "edge_ids": list(self.edge_ids),
                "asset_path": list(self.asset_path),
                "net_multiplier": self.net_multiplier,
                "net_log_delta": self.net_log_delta,
                "minimum_log_delta": self.minimum_log_delta,
                "profitable": self.profitable,
                "passes_margin": self.passes_margin,
                "authority": False,
            },
            "proposal_log_delta": self.proposal_log_delta,
            "delta_drift": self.delta_drift,
            "authority": False,
        }


def build_repricing_request(
    receipt: QaoaConfidenceReceipt,
    candidate: TriangularCycle,
    market_edges: Sequence[MarketEdge],
    *,
    snapshot_sha256: str,
    minimum_log_delta: float,
) -> RustRepricingRequest:
    """Bind a QAOA confidence receipt to one exact-repricing request."""

    _require_sha256(snapshot_sha256, "snapshot_sha256")
    if candidate.candidate_id not in receipt.best_sample.selected_candidate_ids:
        raise ValueError("candidate must be selected by the confidence receipt best sample")

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
        "candidate_id": candidate.candidate_id,
        "edges": ordered_edges,
        "gas_penalty_log": candidate.gas_penalty_log,
        "minimum_log_delta": minimum_log_delta,
        "authority": False,
    }
    encoded = json.dumps(seed, sort_keys=True, separators=(",", ":"), allow_nan=False)
    request_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    return RustRepricingRequest(
        request_id=f"delta-reprice:{request_hash[:24]}",
        snapshot_sha256=snapshot_sha256,
        model_sha256=receipt.model_sha256,
        confidence_receipt_id=receipt.receipt_id,
        candidate_id=candidate.candidate_id,
        edges=ordered_edges,  # type: ignore[arg-type]
        gas_penalty_log=candidate.gas_penalty_log,
        minimum_log_delta=minimum_log_delta,
    )


def run_rust_repricing(
    request: RustRepricingRequest,
    candidate: TriangularCycle,
    *,
    executable: str | Path,
    timeout_seconds: float = 2.0,
) -> RustRepricingEvidence:
    """Run the exact repricer once and fail closed on every protocol deviation."""

    executable_path = Path(executable)
    if not executable_path.is_absolute():
        raise ValueError("Rust verifier executable path must be absolute")
    if not executable_path.is_file():
        raise ValueError("Rust verifier executable does not exist")
    if timeout_seconds <= 0.0 or not math.isfinite(timeout_seconds):
        raise ValueError("timeout_seconds must be finite and positive")

    payload = json.dumps(
        request.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(payload) > _MAX_PAYLOAD_BYTES:
        raise ValueError("repricing request exceeds the 65536-byte protocol limit")

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
        raise RuntimeError("Rust repricing timed out; candidate rejected") from exc

    if len(completed.stdout) > _MAX_OUTPUT_BYTES or len(completed.stderr) > _MAX_OUTPUT_BYTES:
        raise RuntimeError("Rust repricing output exceeded the protocol limit")
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Rust repricing rejected the request: {message[:1000]}")

    try:
        response = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Rust repricing returned malformed JSON") from exc
    if not isinstance(response, dict):
        raise RuntimeError("Rust repricing response must be a JSON object")

    _require_exact_keys(
        response,
        {
            "schema_version",
            "request_id",
            "snapshot_sha256",
            "model_sha256",
            "confidence_receipt_id",
            "candidate_id",
            "verifier",
            "status",
            "verification",
            "authority",
        },
        "repricing response",
    )
    if response["schema_version"] != _RESPONSE_SCHEMA:
        raise RuntimeError("Rust repricing response schema mismatch")
    for field_name in (
        "request_id",
        "snapshot_sha256",
        "model_sha256",
        "confidence_receipt_id",
        "candidate_id",
    ):
        if response[field_name] != request.as_dict()[field_name]:
            raise RuntimeError(f"Rust repricing response changed {field_name}")
    if response["authority"] is not False:
        raise RuntimeError("Rust repricing response attempted authority escalation")
    if not isinstance(response["verifier"], str) or not response["verifier"].startswith(
        "codex-delta-verifier/"
    ):
        raise RuntimeError("Rust repricing verifier identity is invalid")
    if response["status"] != "verified":
        raise RuntimeError("Rust repricing did not complete verification")

    verification = response["verification"]
    if not isinstance(verification, dict):
        raise RuntimeError("verification must be a JSON object")
    _require_exact_keys(
        verification,
        {
            "edge_ids",
            "asset_path",
            "net_multiplier",
            "net_log_delta",
            "minimum_log_delta",
            "profitable",
            "passes_margin",
            "authority",
        },
        "verification",
    )
    if verification["authority"] is not False:
        raise RuntimeError("Rust verification attempted authority escalation")
    if tuple(verification["edge_ids"]) != candidate.edge_ids:
        raise RuntimeError("Rust verification changed the candidate edge order")
    if tuple(verification["asset_path"]) != candidate.asset_path:
        raise RuntimeError("Rust verification changed the candidate asset path")

    net_log_delta = float(verification["net_log_delta"])
    evidence = RustRepricingEvidence(
        request_id=str(response["request_id"]),
        snapshot_sha256=str(response["snapshot_sha256"]),
        model_sha256=str(response["model_sha256"]),
        confidence_receipt_id=str(response["confidence_receipt_id"]),
        candidate_id=str(response["candidate_id"]),
        verifier=str(response["verifier"]),
        status=str(response["status"]),
        edge_ids=tuple(str(value) for value in verification["edge_ids"]),  # type: ignore[arg-type]
        asset_path=tuple(str(value) for value in verification["asset_path"]),  # type: ignore[arg-type]
        net_multiplier=float(verification["net_multiplier"]),
        net_log_delta=net_log_delta,
        minimum_log_delta=float(verification["minimum_log_delta"]),
        profitable=bool(verification["profitable"]),
        passes_margin=bool(verification["passes_margin"]),
        proposal_log_delta=candidate.net_log_delta,
        delta_drift=net_log_delta - candidate.net_log_delta,
    )
    return evidence
