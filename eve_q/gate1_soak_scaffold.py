from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from eve_q.gate1_hardening import (
    Gate1HardeningError,
    build_rollback_receipt,
    validate_resolution_receipt,
    validate_rollback_receipt,
)
from eve_q.gate1_source_review import validate_source_review_artifact
from eve_q.live_read_only_telemetry import (
    TelemetryBoundaryError,
    canonical_json_bytes,
    enforce_pilot_preflight,
    iso_z,
    parse_utc,
    sha256_hex,
    validate_snapshot,
)

CONTRACT_VERSION = "eve_q_gate1_soak_scaffold_v0.1"
PLAN_ARTIFACT_TYPE = "Gate1BoundedSoakPlan"
SUMMARY_ARTIFACT_TYPE = "Gate1BoundedSoakSummary"
MIN_CAPTURE_COUNT = 1
MAX_CAPTURE_COUNT = 1_000
MAX_INTERVAL_SECONDS = 86_400
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")

GATE_POSTURE = {
    "gate_0": "ACTIVE",
    "gate_1": "PILOT_ONLY",
    "gate_2_through_6": "LOCKED",
}

NON_AUTHORITY = {
    "artifact_is_command": False,
    "authority": False,
    "human_promotion_required": True,
    "may_activate_gate_1": False,
    "may_generate_live_proposal": False,
    "may_execute": False,
    "may_move_capital": False,
}


class Gate1SoakScaffoldError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class CaptureBundle:
    snapshot: Mapping[str, Any]
    raw_bytes: bytes
    normalized_bytes: bytes
    resolution_receipt: Mapping[str, Any]


CaptureAdapter = Callable[[int, datetime], CaptureBundle]
EnvironmentProvider = Callable[[int], Mapping[str, str]]


def canonical_sha256(document: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def artifact_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(document))
    payload.pop("artifact_id", None)
    return payload


def compute_artifact_id(document: Mapping[str, Any]) -> str:
    return canonical_sha256(artifact_payload(document))


def refresh_artifact_id(document: Mapping[str, Any]) -> dict[str, Any]:
    refreshed = copy.deepcopy(dict(document))
    refreshed["artifact_id"] = compute_artifact_id(refreshed)
    return refreshed


def _validate_commit(value: str) -> str:
    if not COMMIT_RE.fullmatch(value):
        raise Gate1SoakScaffoldError(
            "invalid_producer_commit",
            "producer_commit must be exactly 40 lowercase hexadecimal characters",
        )
    return value


def _normalize_timestamp(value: str) -> str:
    try:
        parsed = parse_utc(value)
    except (TypeError, ValueError) as exc:
        raise Gate1SoakScaffoldError(
            "invalid_timestamp",
            "timestamp must be valid RFC3339 with a UTC offset",
        ) from exc
    return iso_z(parsed)


def _require_eligible_review(document: Mapping[str, Any]) -> None:
    findings = validate_source_review_artifact(document)
    if findings:
        raise Gate1SoakScaffoldError(
            "invalid_source_review",
            "source-review artifact failed validation: " + "; ".join(findings),
        )
    review = document.get("review", {})
    if review.get("observation_eligibility") != "ELIGIBLE":
        raise Gate1SoakScaffoldError(
            "source_not_eligible",
            "bounded soak requires an ELIGIBLE source-review artifact",
        )


def build_soak_plan(
    source_review: Mapping[str, Any],
    *,
    capture_count: int,
    interval_seconds: int,
    producer_commit: str,
    created_at: str,
) -> dict[str, Any]:
    _require_eligible_review(source_review)
    producer_commit = _validate_commit(producer_commit)
    created_at = _normalize_timestamp(created_at)

    if not MIN_CAPTURE_COUNT <= capture_count <= MAX_CAPTURE_COUNT:
        raise Gate1SoakScaffoldError(
            "invalid_capture_count",
            f"capture_count must be between {MIN_CAPTURE_COUNT} and {MAX_CAPTURE_COUNT}",
        )
    if not 0 <= interval_seconds <= MAX_INTERVAL_SECONDS:
        raise Gate1SoakScaffoldError(
            "invalid_interval",
            f"interval_seconds must be between 0 and {MAX_INTERVAL_SECONDS}",
        )

    source = source_review["source"]
    document: dict[str, Any] = {
        "artifact_type": PLAN_ARTIFACT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "artifact_id": "",
        "created_at": created_at,
        "producer_repository": "ArchitectofAthena/CodexTradingEngine",
        "producer_commit": producer_commit,
        "source_review_artifact_id": source_review["artifact_id"],
        "source": {
            "source_id": source["source_id"],
            "source_kind": source["source_kind"],
            "endpoint_uri": source["endpoint_uri"],
            "allowed_hosts": list(source["allowed_hosts"]),
            "method": source["method"],
            "freshness_ttl_seconds": source["freshness_ttl_seconds"],
            "expected_max_response_bytes": source["expected_max_response_bytes"],
        },
        "schedule": {
            "capture_count": capture_count,
            "interval_seconds": interval_seconds,
            "stop_on_first_failure": True,
            "kill_switch_checked_before_every_capture": True,
        },
        "network_mode": "ADAPTER_INJECTED",
        "gate_posture": dict(GATE_POSTURE),
        **NON_AUTHORITY,
    }
    document["artifact_id"] = compute_artifact_id(document)
    return document


def validate_soak_plan(
    document: Mapping[str, Any],
    *,
    source_review: Mapping[str, Any] | None = None,
) -> list[str]:
    findings: list[str] = []
    if document.get("artifact_type") != PLAN_ARTIFACT_TYPE:
        findings.append(f"artifact_type must be {PLAN_ARTIFACT_TYPE}")
    if document.get("contract_version") != CONTRACT_VERSION:
        findings.append(f"contract_version must be {CONTRACT_VERSION}")
    if document.get("artifact_id") != compute_artifact_id(document):
        findings.append("artifact_id does not match canonical payload hash")
    if not HASH_RE.fullmatch(str(document.get("artifact_id", ""))):
        findings.append("artifact_id must be a lowercase SHA-256 digest")

    try:
        _validate_commit(str(document.get("producer_commit", "")))
    except Gate1SoakScaffoldError as exc:
        findings.append(exc.message)
    try:
        _normalize_timestamp(str(document.get("created_at", "")))
    except Gate1SoakScaffoldError as exc:
        findings.append(exc.message)

    schedule = document.get("schedule", {})
    try:
        capture_count = int(schedule["capture_count"])
        interval_seconds = int(schedule["interval_seconds"])
    except (KeyError, TypeError, ValueError):
        findings.append("schedule capture_count and interval_seconds are required integers")
    else:
        if not MIN_CAPTURE_COUNT <= capture_count <= MAX_CAPTURE_COUNT:
            findings.append("capture_count is outside the bounded range")
        if not 0 <= interval_seconds <= MAX_INTERVAL_SECONDS:
            findings.append("interval_seconds is outside the bounded range")
    if schedule.get("stop_on_first_failure") is not True:
        findings.append("stop_on_first_failure must be true")
    if schedule.get("kill_switch_checked_before_every_capture") is not True:
        findings.append("kill switch must be checked before every capture")

    if document.get("network_mode") != "ADAPTER_INJECTED":
        findings.append("network_mode must be ADAPTER_INJECTED")
    if document.get("gate_posture") != GATE_POSTURE:
        findings.append("gate posture must keep Gate 0 active, Gate 1 pilot-only, and Gates 2-6 locked")
    for field, expected in NON_AUTHORITY.items():
        if document.get(field) is not expected:
            findings.append(f"{field} must be {str(expected).lower()}")

    if source_review is not None:
        try:
            _require_eligible_review(source_review)
        except Gate1SoakScaffoldError as exc:
            findings.append(exc.message)
        else:
            if document.get("source_review_artifact_id") != source_review.get("artifact_id"):
                findings.append("source_review_artifact_id does not match supplied review")
            source = document.get("source", {})
            reviewed_source = source_review.get("source", {})
            expected_source = {
                "source_id": reviewed_source.get("source_id"),
                "source_kind": reviewed_source.get("source_kind"),
                "endpoint_uri": reviewed_source.get("endpoint_uri"),
                "allowed_hosts": reviewed_source.get("allowed_hosts"),
                "method": reviewed_source.get("method"),
                "freshness_ttl_seconds": reviewed_source.get("freshness_ttl_seconds"),
                "expected_max_response_bytes": reviewed_source.get("expected_max_response_bytes"),
            }
            if source != expected_source:
                findings.append("plan source fields do not match source-review artifact")

    return sorted(set(findings))


def _default_environment_provider(index: int) -> Mapping[str, str]:
    del index
    return {
        "EVE_Q_GATE1_PILOT": "1",
        "EVE_Q_GATE1_KILL_SWITCH": "0",
    }


def _persist_capture(
    capture_dir: Path,
    bundle: CaptureBundle,
) -> None:
    capture_dir.mkdir(parents=True, exist_ok=False)
    (capture_dir / "snapshot.json").write_text(
        json.dumps(bundle.snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (capture_dir / "raw.bin").write_bytes(bundle.raw_bytes)
    # Exact normalized bytes are stored as binary so trailing line feeds remain data.
    (capture_dir / "normalized.bin").write_bytes(bundle.normalized_bytes)
    (capture_dir / "resolution_receipt.json").write_text(
        json.dumps(bundle.resolution_receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rollback_trigger(exc: BaseException) -> str:
    code = getattr(exc, "code", "")
    if code == "kill_switch_active":
        return "kill_switch"
    if isinstance(exc, Gate1HardeningError):
        return "dns_policy_failure"
    if isinstance(exc, TelemetryBoundaryError):
        return "source_outage"
    return "operator_abort"


def _base_record(index: int, scheduled_at: str) -> dict[str, Any]:
    return {
        "capture_index": index,
        "scheduled_at": scheduled_at,
        "outcome": "PENDING",
        "snapshot_artifact_id": None,
        "resolution_artifact_id": None,
        "rollback_artifact_id": None,
        "replay_findings": [],
        "reason": "not evaluated",
        **NON_AUTHORITY,
        "gate_posture": dict(GATE_POSTURE),
    }


def _record_hash(record: Mapping[str, Any]) -> str:
    payload = dict(record)
    payload.pop("record_sha256", None)
    return canonical_sha256(payload)


def run_bounded_soak(
    plan: Mapping[str, Any],
    source_review: Mapping[str, Any],
    output_dir: Path,
    *,
    capture_adapter: CaptureAdapter,
    environment_provider: EnvironmentProvider = _default_environment_provider,
) -> dict[str, Any]:
    findings = validate_soak_plan(plan, source_review=source_review)
    if findings:
        raise Gate1SoakScaffoldError(
            "invalid_soak_plan",
            "soak plan failed validation: " + "; ".join(findings),
        )

    output_dir.mkdir(parents=True, exist_ok=False)
    captures_dir = output_dir / "captures"
    rollbacks_dir = output_dir / "rollbacks"
    captures_dir.mkdir()
    rollbacks_dir.mkdir()

    start = parse_utc(str(plan["created_at"]))
    capture_count = int(plan["schedule"]["capture_count"])
    interval_seconds = int(plan["schedule"]["interval_seconds"])
    producer_commit = str(plan["producer_commit"])
    expected_source_id = str(plan["source"]["source_id"])

    records: list[dict[str, Any]] = []
    for index in range(capture_count):
        scheduled = start + timedelta(seconds=index * interval_seconds)
        scheduled_text = iso_z(scheduled)
        record = _base_record(index, scheduled_text)

        try:
            # This check happens on every iteration, before the adapter is invoked.
            enforce_pilot_preflight(environment_provider(index))
            bundle = capture_adapter(index, scheduled)

            snapshot_findings = validate_snapshot(
                bundle.snapshot,
                bundle.raw_bytes,
                bundle.normalized_bytes,
                now=scheduled,
                require_fresh=False,
            )
            resolution_findings = validate_resolution_receipt(
                bundle.resolution_receipt
            )
            if bundle.snapshot.get("source", {}).get("source_id") != expected_source_id:
                snapshot_findings.append("snapshot source_id does not match soak plan")
            if bundle.snapshot.get("producer", {}).get("commit_sha") != producer_commit:
                snapshot_findings.append("snapshot producer commit does not match soak plan")
            if bundle.resolution_receipt.get("source_id") != expected_source_id:
                resolution_findings.append("resolution source_id does not match soak plan")
            if bundle.resolution_receipt.get("producer_commit") != producer_commit:
                resolution_findings.append("resolution producer commit does not match soak plan")

            replay_findings = sorted(set(snapshot_findings + resolution_findings))
            if replay_findings:
                raise Gate1SoakScaffoldError(
                    "capture_validation_failed",
                    "; ".join(replay_findings),
                )

            capture_dir = captures_dir / f"{index:04d}"
            _persist_capture(capture_dir, bundle)
            record.update(
                outcome="ACCEPTED_OBSERVATION_ONLY",
                snapshot_artifact_id=bundle.snapshot["artifact_id"],
                resolution_artifact_id=bundle.resolution_receipt["artifact_id"],
                replay_findings=[],
                reason="snapshot and resolution receipt replayed without findings",
            )

        except Exception as exc:  # fail closed and preserve full rollback evidence
            trigger = _rollback_trigger(exc)
            rollback = build_rollback_receipt(
                producer_commit=producer_commit,
                trigger=trigger,
                started_at=scheduled_text,
                completed_at=scheduled_text,
            )
            rollback_findings = validate_rollback_receipt(rollback)
            if rollback_findings:
                raise Gate1SoakScaffoldError(
                    "rollback_receipt_invalid",
                    "; ".join(rollback_findings),
                ) from exc
            rollback_path = rollbacks_dir / f"{index:04d}.json"
            rollback_path.write_text(
                json.dumps(rollback, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            record.update(
                outcome="ROLLBACK_TO_GATE_0",
                rollback_artifact_id=rollback["artifact_id"],
                replay_findings=[],
                reason=f"{type(exc).__name__}: {exc}",
            )
            record["record_sha256"] = _record_hash(record)
            records.append(record)
            break

        record["record_sha256"] = _record_hash(record)
        records.append(record)

    accepted = sum(
        record["outcome"] == "ACCEPTED_OBSERVATION_ONLY" for record in records
    )
    rollbacks = sum(record["outcome"] == "ROLLBACK_TO_GATE_0" for record in records)
    unauthorized = sum(
        bool(record.get("authority"))
        or bool(record.get("may_activate_gate_1"))
        or bool(record.get("may_generate_live_proposal"))
        or bool(record.get("may_execute"))
        or bool(record.get("may_move_capital"))
        for record in records
    )

    summary: dict[str, Any] = {
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "artifact_id": "",
        "created_at": plan["created_at"],
        "plan_artifact_id": plan["artifact_id"],
        "source_review_artifact_id": plan["source_review_artifact_id"],
        "producer_repository": "ArchitectofAthena/CodexTradingEngine",
        "producer_commit": producer_commit,
        "results": {
            "captures_requested": capture_count,
            "captures_attempted": len(records),
            "captures_accepted": accepted,
            "rollbacks": rollbacks,
            "unauthorized_transitions": unauthorized,
            "ledger_sha256": canonical_sha256(records),
        },
        "acceptance": {
            "review_artifact_valid_and_eligible": True,
            "capture_count_bounded": True,
            "kill_switch_checked_before_every_attempt": True,
            "all_accepted_captures_replayed": accepted == len(records),
            "full_rollback_payload_persisted_on_failure": rollbacks == 0,
            "zero_unauthorized_transitions": unauthorized == 0,
            "zero_live_proposals": True,
            "zero_execution_authority": True,
            "zero_capital_authority": True,
        },
        "completed_requested_captures": accepted == capture_count,
        "ok": accepted == capture_count and rollbacks == 0 and unauthorized == 0,
        "gate_posture": dict(GATE_POSTURE),
        **NON_AUTHORITY,
    }
    summary["artifact_id"] = compute_artifact_id(summary)

    ledger_path = output_dir / "captures.jsonl"
    ledger_path.write_text(
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    (output_dir / "plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "source_review.json").write_text(
        json.dumps(source_review, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def validate_soak_summary(document: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    if document.get("artifact_type") != SUMMARY_ARTIFACT_TYPE:
        findings.append(f"artifact_type must be {SUMMARY_ARTIFACT_TYPE}")
    if document.get("contract_version") != CONTRACT_VERSION:
        findings.append(f"contract_version must be {CONTRACT_VERSION}")
    if document.get("artifact_id") != compute_artifact_id(document):
        findings.append("artifact_id does not match canonical payload hash")
    if not HASH_RE.fullmatch(str(document.get("artifact_id", ""))):
        findings.append("artifact_id must be a lowercase SHA-256 digest")
    if document.get("gate_posture") != GATE_POSTURE:
        findings.append("gate posture must remain locked")
    for field, expected in NON_AUTHORITY.items():
        if document.get(field) is not expected:
            findings.append(f"{field} must be {str(expected).lower()}")
    results = document.get("results", {})
    if int(results.get("unauthorized_transitions", -1)) != 0:
        findings.append("unauthorized_transitions must be zero")
    if document.get("ok") is True and document.get("completed_requested_captures") is not True:
        findings.append("ok summary must complete the requested capture count")
    return sorted(set(findings))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and verify the non-live Gate 1 bounded soak scaffold."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("build-plan")
    plan_parser.add_argument("--source-review", type=Path, required=True)
    plan_parser.add_argument("--capture-count", type=int, required=True)
    plan_parser.add_argument("--interval-seconds", type=int, required=True)
    plan_parser.add_argument("--producer-commit", required=True)
    plan_parser.add_argument("--created-at", required=True)
    plan_parser.add_argument("--output", type=Path, required=True)

    verify_plan_parser = subparsers.add_parser("verify-plan")
    verify_plan_parser.add_argument("--plan", type=Path, required=True)
    verify_plan_parser.add_argument("--source-review", type=Path, required=True)

    verify_summary_parser = subparsers.add_parser("verify-summary")
    verify_summary_parser.add_argument("--summary", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "build-plan":
        plan = build_soak_plan(
            _load_json(args.source_review),
            capture_count=args.capture_count,
            interval_seconds=args.interval_seconds,
            producer_commit=args.producer_commit,
            created_at=args.created_at,
        )
        _write_json(args.output, plan)
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    if args.command == "verify-plan":
        findings = validate_soak_plan(
            _load_json(args.plan),
            source_review=_load_json(args.source_review),
        )
    else:
        findings = validate_soak_summary(_load_json(args.summary))

    print(json.dumps({"valid": not findings, "findings": findings}, indent=2, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
