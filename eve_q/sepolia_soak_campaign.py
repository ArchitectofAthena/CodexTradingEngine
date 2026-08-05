"""Fixed-count Gate 1A Sepolia soak campaign.

This module executes one explicitly approved 25-capture campaign against the
reviewed Sepolia Blockscout source. It checks the pilot flag and kill switch
before every attempt, uses the public-IP-pinned Gate 1 v0.2 transport, replays
the full accepted corpus, and emits a deterministic authority-false receipt.

It is not a recurring monitor and exposes no proposal, wallet, signing,
transaction, execution, or capital surface.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import socket
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from eve_q.alpha_doctor import validate_registry
from eve_q.gate1_hardening import (
    Gate1HardeningError,
    build_resolution_receipt,
    build_rollback_receipt,
    validate_resolution_receipt,
    validate_rollback_receipt,
)
from eve_q.gate1_readonly_runtime import (
    SourceSpec,
    TelemetryBoundaryError,
    build_snapshot_v2,
    enforce_gate1_preflight,
    fetch_read_only_v2,
    parse_utc,
    validate_snapshot_v2,
)
from eve_q.live_read_only_telemetry import iso_z

CONTRACT_VERSION = "codex-sepolia-gate1-soak-v0.1"
ARTIFACT_TYPE = "Gate1SepoliaSoakSummary"
SOURCE_ID = "ethereum-sepolia-blockscout-stats-v0-1"
SOURCE_HOST = "eth-sepolia.blockscout.com"
CHAIN_ID = "11155111"
CAPTURE_COUNT = 25
INTERVAL_SECONDS = 12
MAX_REQUESTS_PER_MINUTE = 5

GATE_POSTURE = {
    "gate_0": "ACTIVE",
    "gate_1a": "ACTIVE_FOR_APPROVED_ALPHA_RUNS",
    "gate_1b": "LOCKED",
    "gate_2": "LOCKED",
    "gate_3": "LOCKED",
    "gate_4_through_6": "LOCKED",
}
AUTHORITY_BOUNDARY = {
    "authority": False,
    "artifact_is_command": False,
    "network_capture_allowed_outside_campaign": False,
    "may_generate_live_proposal": False,
    "may_execute": False,
    "may_sign": False,
    "may_submit_transaction": False,
    "may_move_capital": False,
}

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_REGISTRY = _ROOT / "registry" / "alpha_testnet_sources_v0_1.json"
_DEFAULT_REGISTRY_SCHEMA = _ROOT / "schemas" / "alpha_testnet_source_registry_v0_1.schema.json"
_DEFAULT_SOURCE_SPEC = (
    _ROOT / "registry" / "source_specs" / "ethereum_sepolia_blockscout_stats_v0_1.json"
)
_DEFAULT_SUMMARY_SCHEMA = _ROOT / "schemas" / "gate1_sepolia_soak_summary_v0_1.schema.json"


class SoakCampaignError(RuntimeError):
    """Raised when the fixed-count campaign must fail closed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class CaptureEvidence:
    snapshot: Mapping[str, Any]
    raw_bytes: bytes
    normalized_bytes: bytes
    resolution_receipt: Mapping[str, Any]


CaptureAdapter = Callable[[int, datetime, Mapping[str, str]], CaptureEvidence]
EnvironmentProvider = Callable[[int], Mapping[str, str]]
Clock = Callable[[int], datetime]
Sleep = Callable[[float], None]
PostPersistHook = Callable[[int, Path], None]


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SoakCampaignError(
            "json_load_failed",
            f"unable to load JSON {path}: {type(exc).__name__}: {exc}",
        ) from exc


def _schema_errors(document: Any, schema: Mapping[str, Any]) -> tuple[str, ...]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(document),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    return tuple(
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    )


def _require_schema(document: Any, schema: Mapping[str, Any], label: str) -> None:
    errors = _schema_errors(document, schema)
    if errors:
        raise SoakCampaignError(
            "schema_validation_failed",
            f"{label} schema validation failed: " + "; ".join(errors[:8]),
        )


def _find_reviewed_source(registry: Mapping[str, Any]) -> Mapping[str, Any]:
    matches = [
        source for source in registry.get("sources", []) if source.get("source_id") == SOURCE_ID
    ]
    if len(matches) != 1:
        raise SoakCampaignError(
            "source_not_unique",
            f"registry must contain exactly one {SOURCE_ID} entry",
        )
    source = matches[0]
    if source.get("disposition") != "ELIGIBLE":
        raise SoakCampaignError(
            "source_not_eligible",
            f"source {SOURCE_ID} has not earned ELIGIBLE status",
        )
    return source


def _validate_commit(value: str) -> str:
    normalized = value.lower()
    if len(normalized) != 40 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise SoakCampaignError(
            "invalid_producer_commit",
            "producer commit must be a 40-character hexadecimal SHA",
        )
    return normalized


def validate_campaign_inputs(
    *,
    registry: Mapping[str, Any],
    registry_schema: Mapping[str, Any],
    spec: SourceSpec,
    capture_count: int,
    interval_seconds: int,
    producer_commit: str,
    campaign_start: datetime,
) -> Mapping[str, Any]:
    registry_result = validate_registry(registry, registry_schema)
    if not registry_result.valid:
        raise SoakCampaignError(
            "registry_invalid",
            "source registry is invalid: " + "; ".join(registry_result.errors[:8]),
        )
    source = _find_reviewed_source(registry)
    _validate_commit(producer_commit)

    if capture_count != CAPTURE_COUNT:
        raise SoakCampaignError(
            "capture_count_not_canonical",
            f"v0.1 campaign requires exactly {CAPTURE_COUNT} captures",
        )
    if interval_seconds != INTERVAL_SECONDS:
        raise SoakCampaignError(
            "interval_not_canonical",
            f"v0.1 campaign requires exactly {INTERVAL_SECONDS} seconds between captures",
        )
    if 60 // interval_seconds > MAX_REQUESTS_PER_MINUTE:
        raise SoakCampaignError(
            "request_rate_too_high",
            f"campaign rate may not exceed {MAX_REQUESTS_PER_MINUTE} requests per minute",
        )

    if spec.source_id != SOURCE_ID:
        raise SoakCampaignError("source_id_mismatch", "source specification ID is not approved")
    if spec.url != source.get("url"):
        raise SoakCampaignError("source_url_mismatch", "source specification URL drifted")
    if spec.allowed_hosts != (SOURCE_HOST,):
        raise SoakCampaignError(
            "source_host_mismatch",
            "source specification must allow only the reviewed Sepolia host",
        )
    if source.get("host") != SOURCE_HOST:
        raise SoakCampaignError("registry_host_mismatch", "registry host drifted")
    if source.get("chain_id") != CHAIN_ID:
        raise SoakCampaignError("chain_id_mismatch", "Sepolia chain ID drifted")
    if source.get("network_class") != "testnet" or source.get("mainnet") is not False:
        raise SoakCampaignError(
            "network_boundary_failed", "only reviewed testnet data is permitted"
        )
    if source.get("allowed_methods") != ["GET"]:
        raise SoakCampaignError("method_boundary_failed", "campaign permits GET only")
    if spec.freshness_ttl_seconds != source.get("freshness_ttl_seconds"):
        raise SoakCampaignError("freshness_drift", "source freshness TTL drifted")
    if spec.max_response_bytes != source.get("max_response_bytes"):
        raise SoakCampaignError("response_cap_drift", "source response cap drifted")

    for field in (
        "authority",
        "mainnet",
        "wallet_required",
        "signing_required",
        "transaction_submission",
        "capital_movement",
    ):
        if source.get(field) is not False:
            raise SoakCampaignError(
                "authority_boundary_failed",
                f"reviewed source requires {field}=false",
            )

    expires_at_value = source.get("review_expires_at")
    if not isinstance(expires_at_value, str):
        raise SoakCampaignError(
            "review_expiry_missing",
            "eligible source must carry a review expiry",
        )
    expires_at = parse_utc(expires_at_value)
    if campaign_start.astimezone(timezone.utc) >= expires_at:
        raise SoakCampaignError(
            "source_review_expired",
            "source review expired before the campaign began",
        )
    return source


def _default_environment_provider(index: int) -> Mapping[str, str]:
    del index
    return os.environ


def _default_clock(index: int) -> datetime:
    del index
    return datetime.now(timezone.utc)


def _require_campaign_environment(environment: Mapping[str, str]) -> None:
    if environment.get("EVE_Q_GATE1_PILOT") != "1":
        raise SoakCampaignError(
            "pilot_not_enabled",
            "set EVE_Q_GATE1_PILOT=1 for this explicit campaign",
        )
    if environment.get("EVE_Q_GATE1_KILL_SWITCH") == "1":
        raise SoakCampaignError(
            "kill_switch_active",
            "Gate 1 kill switch is active",
        )
    try:
        enforce_gate1_preflight(environment)
    except TelemetryBoundaryError as exc:
        raise SoakCampaignError(exc.code, exc.message) from exc


def make_live_capture_adapter(
    spec: SourceSpec,
    *,
    producer_commit: str,
) -> CaptureAdapter:
    commit = _validate_commit(producer_commit)

    def capture(
        index: int,
        now: datetime,
        environment: Mapping[str, str],
    ) -> CaptureEvidence:
        del index
        created_at = iso_z(now)
        resolution = build_resolution_receipt(
            spec,
            producer_commit=commit,
            created_at=created_at,
        )
        result = fetch_read_only_v2(
            spec,
            method="GET",
            environment=environment,
            now=now,
        )
        snapshot, raw_bytes, normalized_bytes = build_snapshot_v2(
            spec,
            result,
            producer_commit=commit,
            method="GET",
        )
        postflight = validate_resolution_receipt(
            resolution,
            current_spec=spec,
            resolver=socket.getaddrinfo,
        )
        if postflight:
            raise SoakCampaignError(
                "post_capture_resolution_failed",
                "; ".join(postflight),
            )
        return CaptureEvidence(
            snapshot=snapshot,
            raw_bytes=raw_bytes,
            normalized_bytes=normalized_bytes,
            resolution_receipt=resolution,
        )

    return capture


def _validate_capture(
    evidence: CaptureEvidence,
    *,
    spec: SourceSpec,
    producer_commit: str,
    now: datetime,
) -> tuple[str, str, str]:
    findings = validate_snapshot_v2(
        evidence.snapshot,
        evidence.raw_bytes,
        evidence.normalized_bytes,
        now=now,
        require_fresh=True,
    )
    findings.extend(
        validate_resolution_receipt(
            evidence.resolution_receipt,
            current_spec=spec,
        )
    )
    source = evidence.snapshot.get("source", {})
    producer = evidence.snapshot.get("producer", {})
    if source.get("source_id") != SOURCE_ID:
        findings.append("snapshot source ID does not match the campaign")
    if source.get("method") != "GET":
        findings.append("snapshot method must remain GET")
    if source.get("allowlisted_host") != SOURCE_HOST:
        findings.append("snapshot host does not match the reviewed source")
    if producer.get("commit_sha") != producer_commit:
        findings.append("snapshot producer commit does not match the campaign")

    for key in (
        "authority",
        "may_generate_live_proposal",
        "may_execute",
        "may_move_capital",
    ):
        if evidence.snapshot.get(key) is not False:
            findings.append(f"snapshot {key} must remain false")
    if findings:
        raise SoakCampaignError(
            "capture_validation_failed",
            "; ".join(sorted(set(findings))),
        )
    return (
        str(evidence.snapshot["artifact_id"]),
        str(evidence.snapshot["hashes"]["raw_sha256"]),
        str(evidence.snapshot["hashes"]["normalized_sha256"]),
    )


def _persist_capture(
    capture_dir: Path,
    evidence: CaptureEvidence,
) -> None:
    capture_dir.mkdir(parents=True, exist_ok=False)
    (capture_dir / "snapshot.json").write_text(
        json.dumps(evidence.snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (capture_dir / "raw.bin").write_bytes(evidence.raw_bytes)
    (capture_dir / "normalized.json").write_bytes(evidence.normalized_bytes)
    (capture_dir / "resolution_receipt.json").write_text(
        json.dumps(evidence.resolution_receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rollback_trigger(exc: BaseException) -> str:
    code = getattr(exc, "code", "")
    if code == "kill_switch_active":
        return "kill_switch"
    if isinstance(exc, Gate1HardeningError) or "resolution" in str(code):
        return "dns_policy_failure"
    if isinstance(exc, TelemetryBoundaryError) or code in {
        "source_timeout",
        "source_unavailable",
        "source_outage",
    }:
        return "source_outage"
    return "operator_abort"


def _replay_corpus(
    captures_dir: Path,
    *,
    spec: SourceSpec,
) -> tuple[int, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    for capture_dir in sorted(path for path in captures_dir.iterdir() if path.is_dir()):
        snapshot = _load_json(capture_dir / "snapshot.json")
        raw_bytes = (capture_dir / "raw.bin").read_bytes()
        normalized_bytes = (capture_dir / "normalized.json").read_bytes()
        resolution = _load_json(capture_dir / "resolution_receipt.json")
        findings = validate_snapshot_v2(
            snapshot,
            raw_bytes,
            normalized_bytes,
            require_fresh=False,
        )
        findings.extend(validate_resolution_receipt(resolution, current_spec=spec))
        results.append(
            {
                "capture_index": int(capture_dir.name),
                "artifact_id": snapshot.get("artifact_id"),
                "valid": not findings,
                "findings": sorted(set(findings)),
            }
        )
    return sum(result["valid"] for result in results), results


def _receipt_payload(summary: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(summary))
    payload.pop("receipt_sha256", None)
    return payload


def _render_summary(summary: Mapping[str, Any]) -> str:
    results = summary["results"]
    return "\n".join(
        (
            "CODEX GATE 1A SEPOLIA SOAK v0.1",
            f"SOURCE: {summary['source']['source_id']}",
            f"REQUESTED: {results['captures_requested']}",
            f"ATTEMPTED: {results['captures_attempted']}",
            f"ACCEPTED: {results['captures_accepted']}",
            f"REJECTED: {results['captures_rejected']}",
            f"ROLLBACKS: {results['rollbacks']}",
            f"CORPUS REPLAYED: {results['corpus_replayed']}",
            f"STATUS: {summary['status']}",
            f"RECEIPT: {summary['receipt_sha256']}",
            "LIVE PROPOSALS: 0",
            "EXECUTION: LOCKED",
            "CAPITAL: LOCKED",
            "AUTHORITY: false",
        )
    )


def run_fixed_count_soak(
    *,
    registry: Mapping[str, Any],
    registry_schema: Mapping[str, Any],
    spec: SourceSpec,
    output_dir: Path,
    producer_commit: str,
    capture_count: int = CAPTURE_COUNT,
    interval_seconds: int = INTERVAL_SECONDS,
    capture_adapter: CaptureAdapter | None = None,
    environment_provider: EnvironmentProvider = _default_environment_provider,
    clock: Clock = _default_clock,
    sleep: Sleep = time.sleep,
    post_persist_hook: PostPersistHook | None = None,
) -> dict[str, Any]:
    commit = _validate_commit(producer_commit)
    campaign_start = clock(0).astimezone(timezone.utc)
    source = validate_campaign_inputs(
        registry=registry,
        registry_schema=registry_schema,
        spec=spec,
        capture_count=capture_count,
        interval_seconds=interval_seconds,
        producer_commit=commit,
        campaign_start=campaign_start,
    )
    expires_at = parse_utc(str(source["review_expires_at"]))
    adapter = capture_adapter or make_live_capture_adapter(
        spec,
        producer_commit=commit,
    )

    output_dir.mkdir(parents=True, exist_ok=False)
    captures_dir = output_dir / "captures"
    rollbacks_dir = output_dir / "rollbacks"
    captures_dir.mkdir()
    rollbacks_dir.mkdir()

    records: list[dict[str, Any]] = []
    accepted_evidence: list[dict[str, Any]] = []
    for index in range(capture_count):
        now = clock(index).astimezone(timezone.utc)
        record: dict[str, Any] = {
            "capture_index": index,
            "attempted_at": iso_z(now),
            "outcome": "PENDING",
            "reason": None,
            "snapshot_artifact_id": None,
            "raw_sha256": None,
            "normalized_sha256": None,
            "resolution_artifact_id": None,
            "rollback_artifact_id": None,
            "authority": False,
            "may_generate_live_proposal": False,
            "may_execute": False,
            "may_sign": False,
            "may_submit_transaction": False,
            "may_move_capital": False,
        }
        try:
            environment = dict(environment_provider(index))
            _require_campaign_environment(environment)
            if now >= expires_at:
                raise SoakCampaignError(
                    "source_review_expired",
                    "source review expired during the campaign",
                )
            evidence = adapter(index, now, environment)
            artifact_id, raw_hash, normalized_hash = _validate_capture(
                evidence,
                spec=spec,
                producer_commit=commit,
                now=now,
            )
            capture_dir = captures_dir / f"{index:04d}"
            _persist_capture(capture_dir, evidence)
            if post_persist_hook is not None:
                post_persist_hook(index, capture_dir)
            record.update(
                outcome="ACCEPTED_OBSERVATION_ONLY",
                reason="capture and immediate freshness replay passed",
                snapshot_artifact_id=artifact_id,
                raw_sha256=raw_hash,
                normalized_sha256=normalized_hash,
                resolution_artifact_id=evidence.resolution_receipt["artifact_id"],
            )
            accepted_evidence.append(
                {
                    "capture_index": index,
                    "observed_at": evidence.snapshot["retrieval"]["observed_at"],
                    "expires_at": evidence.snapshot["retrieval"]["expires_at"],
                    "snapshot_artifact_id": artifact_id,
                    "raw_sha256": raw_hash,
                    "normalized_sha256": normalized_hash,
                    "resolution_artifact_id": evidence.resolution_receipt["artifact_id"],
                }
            )
        except Exception as exc:  # fail closed with a complete rollback artifact
            trigger = _rollback_trigger(exc)
            now_text = iso_z(now)
            rollback = build_rollback_receipt(
                producer_commit=commit,
                trigger=trigger,
                started_at=now_text,
                completed_at=now_text,
            )
            rollback_findings = validate_rollback_receipt(rollback)
            if rollback_findings:
                raise SoakCampaignError(
                    "rollback_invalid",
                    "; ".join(rollback_findings),
                ) from exc
            rollback_path = rollbacks_dir / f"{index:04d}.json"
            rollback_path.write_text(
                json.dumps(rollback, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            record.update(
                outcome="REJECTED_AND_ROLLED_BACK_TO_GATE_0",
                reason=f"{type(exc).__name__}: {exc}",
                rollback_artifact_id=rollback["artifact_id"],
            )
            records.append(record)
            break
        records.append(record)
        if index < capture_count - 1:
            sleep(float(interval_seconds))

    replayed, replay_records = _replay_corpus(captures_dir, spec=spec)
    attempted = len(records)
    accepted = len(accepted_evidence)
    rollbacks = sum(record["outcome"] == "REJECTED_AND_ROLLED_BACK_TO_GATE_0" for record in records)
    rejected = rollbacks
    all_replayed = replayed == accepted
    status = (
        "PASS"
        if accepted == capture_count
        and attempted == capture_count
        and rollbacks == 0
        and all_replayed
        else "HOLD"
    )
    observed_times = [item["observed_at"] for item in accepted_evidence]

    summary: dict[str, Any] = {
        "artifact_type": ARTIFACT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "generated_at": iso_z(clock(capture_count).astimezone(timezone.utc)),
        "receipt_sha256": "0" * 64,
        "producer_repository": "ArchitectofAthena/CodexTradingEngine",
        "producer_commit": commit,
        "source": {
            "source_id": SOURCE_ID,
            "network_name": source["network_name"],
            "chain_id": CHAIN_ID,
            "host": SOURCE_HOST,
            "url": spec.url,
            "method": "GET",
            "registry_sha256": sha256_hex(registry),
            "reviewed_at": source["reviewed_at"],
            "review_expires_at": source["review_expires_at"],
            "provenance_group": source["provenance_group"],
        },
        "campaign": {
            "capture_count": capture_count,
            "interval_seconds": interval_seconds,
            "maximum_requests_per_minute": MAX_REQUESTS_PER_MINUTE,
            "automatic_recurrence": False,
            "stop_on_first_failure": True,
            "kill_switch_checked_before_every_attempt": True,
        },
        "results": {
            "captures_requested": capture_count,
            "captures_attempted": attempted,
            "captures_accepted": accepted,
            "captures_rejected": rejected,
            "rollbacks": rollbacks,
            "corpus_replayed": replayed,
            "all_accepted_snapshots_replayed": all_replayed,
            "observed_at_first": min(observed_times) if observed_times else None,
            "observed_at_last": max(observed_times) if observed_times else None,
            "record_ledger_sha256": sha256_hex(records),
            "replay_ledger_sha256": sha256_hex(replay_records),
        },
        "accepted_evidence": accepted_evidence,
        "replay_records": replay_records,
        "status": status,
        "counts": {
            "live_proposals_generated": 0,
            "signatures_created": 0,
            "transactions_submitted": 0,
            "executions_performed": 0,
            "capital_movements": 0,
        },
        "residual_risks": [
            "single explorer provider and instance",
            "per-instance Blockscout API deprecation risk",
            "testnet observations are not production reliability evidence",
            "testnet observations are not production profitability evidence",
            "source eligibility expires unless re-reviewed",
        ],
        "gate_posture": dict(GATE_POSTURE),
        "authority": dict(AUTHORITY_BOUNDARY),
    }
    summary["receipt_sha256"] = sha256_hex(_receipt_payload(summary))

    (output_dir / "records.jsonl").write_text(
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records
        ),
        encoding="utf-8",
    )
    (output_dir / "replay_records.json").write_text(
        json.dumps(replay_records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.txt").write_text(
        _render_summary(summary) + "\n",
        encoding="utf-8",
    )
    return summary


def verify_summary(
    summary: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> tuple[str, ...]:
    findings = list(_schema_errors(summary, schema))
    if summary.get("receipt_sha256") != sha256_hex(_receipt_payload(summary)):
        findings.append("receipt hash does not match canonical summary evidence")
    authority = summary.get("authority", {})
    for key, expected in AUTHORITY_BOUNDARY.items():
        if authority.get(key) is not expected:
            findings.append(f"authority.{key} must be {str(expected).lower()}")
    counts = summary.get("counts", {})
    if any(counts.get(key) != 0 for key in counts):
        findings.append(
            "all proposal, signing, transaction, execution, and capital counts must be zero"
        )
    return tuple(sorted(set(findings)))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="codex-gate1-soak25",
        description="Run or verify the fixed-count Sepolia Gate 1A soak campaign.",
    )
    subparsers = result.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--registry", type=Path, default=_DEFAULT_REGISTRY)
    run.add_argument("--registry-schema", type=Path, default=_DEFAULT_REGISTRY_SCHEMA)
    run.add_argument("--source-spec", type=Path, default=_DEFAULT_SOURCE_SPEC)
    run.add_argument("--summary-schema", type=Path, default=_DEFAULT_SUMMARY_SCHEMA)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--producer-commit", required=True)
    run.add_argument("--count", type=int, default=CAPTURE_COUNT)
    run.add_argument("--interval", type=int, default=INTERVAL_SECONDS)

    verify = subparsers.add_parser("verify-summary")
    verify.add_argument("--summary", type=Path, required=True)
    verify.add_argument("--summary-schema", type=Path, default=_DEFAULT_SUMMARY_SCHEMA)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        schema = _load_json(args.summary_schema)
        if args.command == "verify-summary":
            findings = verify_summary(_load_json(args.summary), schema)
            print(json.dumps({"valid": not findings, "findings": findings}, indent=2))
            return 0 if not findings else 1

        registry = _load_json(args.registry)
        registry_schema = _load_json(args.registry_schema)
        spec = SourceSpec.from_dict(_load_json(args.source_spec))
        summary = run_fixed_count_soak(
            registry=registry,
            registry_schema=registry_schema,
            spec=spec,
            output_dir=args.output_dir,
            producer_commit=args.producer_commit,
            capture_count=args.count,
            interval_seconds=args.interval,
        )
        _require_schema(summary, schema, "soak summary")
        findings = verify_summary(summary, schema)
        if findings:
            raise SoakCampaignError("summary_invalid", "; ".join(findings))
    except (SoakCampaignError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"HOLD: {exc}")
        return 2

    print(_render_summary(summary))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
