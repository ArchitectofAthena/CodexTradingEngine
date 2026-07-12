from __future__ import annotations

import copy
import json
import socket
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from eve_q.gate1_hardening import (
    build_resolution_receipt,
    validate_rollback_receipt,
)
from eve_q.gate1_soak_runner import run_bounded_soak
from eve_q.gate1_soak_scaffold import (
    CaptureBundle,
    Gate1SoakScaffoldError,
    build_soak_plan,
    refresh_artifact_id,
    validate_soak_plan,
    validate_soak_summary,
)
from eve_q.gate1_source_review import build_source_review_artifact
from eve_q.live_read_only_telemetry import (
    SourceSpec,
    TransportResult,
    build_snapshot,
    canonical_json_bytes,
)

PLAN_SCHEMA = Path("schemas/gate1_bounded_soak_plan_v0_1.schema.json")
SUMMARY_SCHEMA = Path("schemas/gate1_bounded_soak_summary_v0_1.schema.json")
PRODUCER_COMMIT = "a" * 40
CREATED_AT = "2026-07-12T01:30:00Z"
PUBLIC_ADDRESS = "93.184.216.34"


def source_candidate(*, eligible: bool = True) -> dict:
    return {
        "reviewer_id": "human:architect",
        "source": {
            "source_id": "synthetic-reviewed-source",
            "source_name": "Synthetic Reviewed Source",
            "operator": "Synthetic Test Operator",
            "source_kind": "market_snapshot",
            "endpoint_uri": "https://data.example.test/v1/market",
            "allowed_hosts": ["data.example.test"],
            "method": "GET",
            "auth_mode": "NONE",
            "credential_reference_name": None,
            "credential_proof_note": None,
            "documented_rate_limit": {"requests": 30, "per_seconds": 60},
            "expected_content_types": ["application/json"],
            "expected_max_response_bytes": 4096,
            "freshness_ttl_seconds": 300,
            "outage_expectation": "Synthetic outage returns to Gate 0.",
            "redirect_policy": "EXACT_ALLOWLIST_ONLY",
        },
        "provenance": {
            "provenance_group": "synthetic-independent-group",
            "upstream_provider": "Synthetic Test Operator",
            "upstream_concentration": "LOW",
            "source_independence_note": "Synthetic fixture for orchestration tests only.",
            "concentration_mitigation": "",
        },
        "review": {
            "terms_disposition": (
                "REVIEWED_COMPATIBLE" if eligible else "NOT_REVIEWED"
            ),
            "legal_terms_note": "Synthetic fixture; no live source is selected.",
            "transport_residual_risk": (
                "ACCEPTED_WITH_CONTROLS" if eligible else "UNRESOLVED"
            ),
            "rollback_compatible": eligible,
            "kill_switch_compatible": eligible,
            "review_notes": ["Synthetic no-network scaffold fixture."],
        },
    }


def source_review(*, eligible: bool = True) -> dict:
    return build_source_review_artifact(
        source_candidate(eligible=eligible),
        producer_commit=PRODUCER_COMMIT,
        created_at=CREATED_AT,
    )


def plan(review: dict, *, count: int = 25, interval: int = 2) -> dict:
    return build_soak_plan(
        review,
        capture_count=count,
        interval_seconds=interval,
        producer_commit=PRODUCER_COMMIT,
        created_at=CREATED_AT,
    )


def resolver(host, port, *, family, type, proto):
    assert host == "data.example.test"
    assert port == 443
    assert family == socket.AF_UNSPEC
    return [
        (
            socket.AF_INET,
            type,
            proto,
            "",
            (PUBLIC_ADDRESS, port),
        )
    ]


def capture_adapter(index: int, scheduled: datetime) -> CaptureBundle:
    spec = SourceSpec(
        source_id="synthetic-reviewed-source",
        source_kind="market_snapshot",
        url="https://data.example.test/v1/market",
        allowed_hosts=("data.example.test",),
        freshness_ttl_seconds=300,
        timeout_seconds=5.0,
        max_response_bytes=4096,
    )
    body = canonical_json_bytes(
        {
            "capture_index": index,
            "price": f"{100 + index / 10:.1f}",
            "synthetic": True,
        }
    )
    observed_at = scheduled.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    result = TransportResult(
        status=200,
        headers={"Content-Type": "application/json"},
        body=body,
        final_url=spec.url,
        retrieved_at=observed_at,
    )
    snapshot, raw_bytes, normalized_bytes = build_snapshot(
        spec,
        result,
        producer_commit=PRODUCER_COMMIT,
    )
    resolution = build_resolution_receipt(
        spec,
        producer_commit=PRODUCER_COMMIT,
        created_at=observed_at,
        resolver=resolver,
    )
    return CaptureBundle(
        snapshot=snapshot,
        raw_bytes=raw_bytes,
        normalized_bytes=normalized_bytes,
        resolution_receipt=resolution,
    )


def schema_findings(path: Path, document: dict) -> list:
    schema = json.loads(path.read_text(encoding="utf-8"))
    return list(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(document)
    )


def test_plan_is_deterministic_schema_valid_and_bound_to_eligible_review():
    review = source_review()
    first = plan(review)
    second = plan(review)

    assert first == second
    assert schema_findings(PLAN_SCHEMA, first) == []
    assert validate_soak_plan(first, source_review=review) == []
    assert first["schedule"]["capture_count"] == 25
    assert first["schedule"]["kill_switch_checked_before_every_capture"] is True
    assert first["network_mode"] == "ADAPTER_INJECTED"
    assert first["authority"] is False
    assert first["may_activate_gate_1"] is False
    assert first["may_generate_live_proposal"] is False
    assert first["may_execute"] is False
    assert first["may_move_capital"] is False


def test_hold_review_cannot_build_a_soak_plan():
    with pytest.raises(Gate1SoakScaffoldError) as exc_info:
        plan(source_review(eligible=False))

    assert exc_info.value.code == "source_not_eligible"


def test_capture_count_and_interval_are_bounded():
    review = source_review()
    with pytest.raises(Gate1SoakScaffoldError) as exc_info:
        plan(review, count=0)
    assert exc_info.value.code == "invalid_capture_count"

    with pytest.raises(Gate1SoakScaffoldError) as exc_info:
        plan(review, interval=86_401)
    assert exc_info.value.code == "invalid_interval"


def test_25_capture_scaffold_is_deterministic_and_observation_only(tmp_path: Path):
    review = source_review()
    soak_plan = plan(review, count=25, interval=2)

    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = run_bounded_soak(
        soak_plan,
        review,
        first_dir,
        capture_adapter=capture_adapter,
    )
    second = run_bounded_soak(
        soak_plan,
        review,
        second_dir,
        capture_adapter=capture_adapter,
    )

    assert first == second
    assert (first_dir / "summary.json").read_bytes() == (
        second_dir / "summary.json"
    ).read_bytes()
    assert (first_dir / "captures.jsonl").read_bytes() == (
        second_dir / "captures.jsonl"
    ).read_bytes()
    assert schema_findings(SUMMARY_SCHEMA, first) == []
    assert validate_soak_summary(first) == []
    assert first["ok"] is True
    assert first["results"] == {
        "captures_requested": 25,
        "captures_attempted": 25,
        "captures_accepted": 25,
        "rollbacks": 0,
        "unauthorized_transitions": 0,
        "ledger_sha256": first["results"]["ledger_sha256"],
    }
    assert len(list((first_dir / "captures").iterdir())) == 25
    assert list((first_dir / "rollbacks").iterdir()) == []
    assert first["authority"] is False
    assert first["may_generate_live_proposal"] is False


def test_kill_switch_is_checked_before_every_adapter_call_and_persists_rollback(
    tmp_path: Path,
):
    review = source_review()
    soak_plan = plan(review, count=10, interval=1)
    called: list[int] = []

    def adapter(index: int, scheduled: datetime) -> CaptureBundle:
        called.append(index)
        return capture_adapter(index, scheduled)

    def environment(index: int) -> dict[str, str]:
        return {
            "EVE_Q_GATE1_PILOT": "1",
            "EVE_Q_GATE1_KILL_SWITCH": "1" if index == 4 else "0",
        }

    out = tmp_path / "kill-switch"
    summary = run_bounded_soak(
        soak_plan,
        review,
        out,
        capture_adapter=adapter,
        environment_provider=environment,
    )

    assert called == [0, 1, 2, 3]
    assert summary["ok"] is False
    assert summary["results"]["captures_attempted"] == 5
    assert summary["results"]["captures_accepted"] == 4
    assert summary["results"]["rollbacks"] == 1
    assert summary["acceptance"]["full_rollback_payload_persisted_on_failure"] is True
    rollback_path = out / "rollbacks" / "0004.json"
    rollback = json.loads(rollback_path.read_text(encoding="utf-8"))
    assert validate_rollback_receipt(rollback) == []
    assert rollback["trigger"] == "kill_switch"
    assert rollback["to_gate"] == "SIMULATION_ONLY"
    assert schema_findings(SUMMARY_SCHEMA, summary) == []


def test_snapshot_tamper_stops_campaign_and_records_operator_abort(tmp_path: Path):
    review = source_review()
    soak_plan = plan(review, count=5, interval=1)

    def tampered_adapter(index: int, scheduled: datetime) -> CaptureBundle:
        bundle = capture_adapter(index, scheduled)
        if index == 2:
            return CaptureBundle(
                snapshot=bundle.snapshot,
                raw_bytes=bundle.raw_bytes + b"tamper",
                normalized_bytes=bundle.normalized_bytes,
                resolution_receipt=bundle.resolution_receipt,
            )
        return bundle

    out = tmp_path / "tamper"
    summary = run_bounded_soak(
        soak_plan,
        review,
        out,
        capture_adapter=tampered_adapter,
    )

    assert summary["ok"] is False
    assert summary["results"]["captures_attempted"] == 3
    assert summary["results"]["captures_accepted"] == 2
    assert summary["results"]["rollbacks"] == 1
    rollback = json.loads((out / "rollbacks" / "0002.json").read_text(encoding="utf-8"))
    assert rollback["trigger"] == "operator_abort"
    assert validate_rollback_receipt(rollback) == []


def test_exact_normalized_bytes_are_preserved_without_rstrip(tmp_path: Path):
    review = source_review()
    soak_plan = plan(review, count=1, interval=0)

    def trailing_lf_adapter(index: int, scheduled: datetime) -> CaptureBundle:
        bundle = capture_adapter(index, scheduled)
        normalized = bundle.normalized_bytes + b"\n\n"
        snapshot = copy.deepcopy(bundle.snapshot)
        snapshot["hashes"]["normalized_sha256"] = __import__("hashlib").sha256(
            normalized
        ).hexdigest()
        from eve_q.live_read_only_telemetry import compute_artifact_id

        snapshot["artifact_id"] = compute_artifact_id(snapshot)
        return CaptureBundle(
            snapshot=snapshot,
            raw_bytes=bundle.raw_bytes,
            normalized_bytes=normalized,
            resolution_receipt=bundle.resolution_receipt,
        )

    out = tmp_path / "trailing-lf"
    summary = run_bounded_soak(
        soak_plan,
        review,
        out,
        capture_adapter=trailing_lf_adapter,
    )

    assert summary["ok"] is True
    assert (out / "captures" / "0000" / "normalized.bin").read_bytes().endswith(
        b"\n\n"
    )


def test_plan_hash_and_authority_mutation_are_detected():
    review = source_review()
    soak_plan = plan(review)
    mutated = copy.deepcopy(soak_plan)
    mutated["authority"] = True

    findings = validate_soak_plan(mutated, source_review=review)
    assert "artifact_id does not match canonical payload hash" in findings
    assert "authority must be false" in findings

    rehashed = refresh_artifact_id(mutated)
    findings = validate_soak_plan(rehashed, source_review=review)
    assert "artifact_id does not match canonical payload hash" not in findings
    assert "authority must be false" in findings


def test_summary_mutation_cannot_grant_authority(tmp_path: Path):
    review = source_review()
    soak_plan = plan(review, count=1, interval=0)
    summary = run_bounded_soak(
        soak_plan,
        review,
        tmp_path / "run",
        capture_adapter=capture_adapter,
    )
    summary["may_execute"] = True
    summary = refresh_artifact_id(summary)

    findings = validate_soak_summary(summary)
    assert "may_execute must be false" in findings
