from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from eve_q.live_read_only_telemetry import (
    SourceSpec,
    TelemetryBoundaryError,
    TransportResult,
    build_snapshot,
    canonical_json_bytes,
    enforce_pilot_preflight,
    replay_snapshot_bundle,
    sha256_hex,
    validate_method,
    validate_snapshot,
    validate_source_spec,
    write_snapshot_bundle,
)

SCHEMA_PATH = Path("schemas/live_read_only_telemetry_snapshot_v0_1.schema.json")
NOW = datetime(2026, 7, 11, 22, 0, tzinfo=timezone.utc)
PRODUCER_COMMIT = "a" * 40


def spec(**overrides) -> SourceSpec:
    values = {
        "source_id": "public-market-observation",
        "source_kind": "market_snapshot",
        "url": "https://data.example.test/v1/market",
        "allowed_hosts": ("data.example.test",),
        "freshness_ttl_seconds": 300,
        "timeout_seconds": 5.0,
        "max_response_bytes": 1024,
    }
    values.update(overrides)
    return SourceSpec(**values)


def result(**overrides) -> TransportResult:
    values = {
        "status": 200,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": b'{"price":"123.45","source":"public"}',
        "final_url": "https://data.example.test/v1/market",
        "retrieved_at": "2026-07-11T22:00:00Z",
    }
    values.update(overrides)
    return TransportResult(**values)


def schema_findings(document: dict) -> list:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return list(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(document)
    )


def test_json_snapshot_is_schema_valid_non_authoritative_and_replayable(tmp_path):
    document, raw_bytes, normalized_bytes = build_snapshot(
        spec(),
        result(),
        producer_commit=PRODUCER_COMMIT,
    )

    assert schema_findings(document) == []
    assert validate_snapshot(
        document,
        raw_bytes,
        normalized_bytes,
        now=NOW + timedelta(seconds=1),
    ) == []
    assert normalized_bytes == canonical_json_bytes(
        {"price": "123.45", "source": "public"}
    )
    assert document["artifact_is_command"] is False
    assert document["authority"] is False
    assert document["human_promotion_required"] is True
    assert document["may_generate_live_proposal"] is False
    assert document["may_execute"] is False
    assert document["may_move_capital"] is False
    assert document["gate_posture"] == {
        "gate_0": "ACTIVE",
        "gate_1": "PILOT_ONLY",
        "gate_2_through_6": "LOCKED",
    }

    bundle = tmp_path / "snapshot"
    write_snapshot_bundle(bundle, document, raw_bytes, normalized_bytes)
    assert replay_snapshot_bundle(bundle, now=NOW) == []


def test_equivalent_json_payloads_have_identical_normalized_hashes():
    first, _, first_normalized = build_snapshot(
        spec(),
        result(body=b'{"b":2,"a":1}'),
        producer_commit=PRODUCER_COMMIT,
    )
    second, _, second_normalized = build_snapshot(
        spec(),
        result(body=b'{"a":1,"b":2}'),
        producer_commit=PRODUCER_COMMIT,
    )

    assert first_normalized == second_normalized
    assert first["hashes"]["normalized_sha256"] == second["hashes"][
        "normalized_sha256"
    ]
    assert first["hashes"]["raw_sha256"] != second["hashes"]["raw_sha256"]


def test_only_get_and_head_methods_are_allowed():
    assert validate_method("get") == "GET"
    assert validate_method("HEAD") == "HEAD"

    with pytest.raises(TelemetryBoundaryError) as exc_info:
        validate_method("POST")

    assert exc_info.value.code == "write_method_rejected"


def test_source_requires_https_and_exact_allowlisted_host():
    with pytest.raises(TelemetryBoundaryError) as exc_info:
        validate_source_spec(spec(url="http://data.example.test/v1/market"))
    assert exc_info.value.code == "scheme_not_https"

    with pytest.raises(TelemetryBoundaryError) as exc_info:
        validate_source_spec(
            spec(url="https://evil.example.test/v1/market")
        )
    assert exc_info.value.code == "host_not_allowlisted"


def test_final_redirect_target_must_remain_allowlisted():
    with pytest.raises(TelemetryBoundaryError) as exc_info:
        build_snapshot(
            spec(),
            result(final_url="https://redirect.evil.test/market"),
            producer_commit=PRODUCER_COMMIT,
        )

    assert exc_info.value.code == "host_not_allowlisted"


def test_pilot_preflight_requires_explicit_enable_and_respects_kill_switch():
    with pytest.raises(TelemetryBoundaryError) as exc_info:
        enforce_pilot_preflight({"UNRELATED": "1"})
    assert exc_info.value.code == "pilot_not_enabled"

    with pytest.raises(TelemetryBoundaryError) as exc_info:
        enforce_pilot_preflight(
            {
                "EVE_Q_GATE1_PILOT": "1",
                "EVE_Q_GATE1_KILL_SWITCH": "1",
            }
        )
    assert exc_info.value.code == "kill_switch_active"


def test_write_capable_secrets_fail_closed_without_leaking_values():
    secret_value = "never-print-this-secret"

    with pytest.raises(TelemetryBoundaryError) as exc_info:
        enforce_pilot_preflight(
            {
                "EVE_Q_GATE1_PILOT": "1",
                "WALLET_PRIVATE_KEY": secret_value,
            }
        )

    assert exc_info.value.code == "write_capable_secret_detected"
    assert "WALLET_PRIVATE_KEY" in exc_info.value.message
    assert secret_value not in exc_info.value.message

    enforce_pilot_preflight(
        {
            "EVE_Q_GATE1_PILOT": "1",
            "PUBLIC_MARKET_API_KEY": "public-or-read-only",
        }
    )


def test_malformed_json_and_unsupported_content_type_fail_closed():
    with pytest.raises(TelemetryBoundaryError) as exc_info:
        build_snapshot(
            spec(),
            result(body=b"not-json"),
            producer_commit=PRODUCER_COMMIT,
        )
    assert exc_info.value.code == "malformed_json"

    with pytest.raises(TelemetryBoundaryError) as exc_info:
        build_snapshot(
            spec(),
            result(headers={"Content-Type": "application/octet-stream"}),
            producer_commit=PRODUCER_COMMIT,
        )
    assert exc_info.value.code == "unsupported_content_type"


def test_response_size_cap_fails_closed():
    with pytest.raises(TelemetryBoundaryError) as exc_info:
        build_snapshot(
            spec(max_response_bytes=8),
            result(body=b'{"too":"large"}'),
            producer_commit=PRODUCER_COMMIT,
        )

    assert exc_info.value.code == "response_too_large"


def test_stale_snapshot_and_hash_mismatch_are_rejected():
    document, raw_bytes, normalized_bytes = build_snapshot(
        spec(freshness_ttl_seconds=30),
        result(),
        producer_commit=PRODUCER_COMMIT,
    )

    stale_findings = validate_snapshot(
        document,
        raw_bytes,
        normalized_bytes,
        now=NOW + timedelta(seconds=31),
    )
    assert "telemetry snapshot is stale" in stale_findings

    hash_findings = validate_snapshot(
        document,
        raw_bytes + b"tampered",
        normalized_bytes,
        now=NOW,
    )
    assert "raw payload hash mismatch" in hash_findings


def test_authority_and_gate_leakage_are_rejected():
    document, raw_bytes, normalized_bytes = build_snapshot(
        spec(),
        result(),
        producer_commit=PRODUCER_COMMIT,
    )
    mutated = copy.deepcopy(document)
    mutated["authority"] = True
    mutated["may_generate_live_proposal"] = True
    mutated["gate_posture"]["gate_2_through_6"] = "OPEN"

    findings = validate_snapshot(
        mutated,
        raw_bytes,
        normalized_bytes,
        now=NOW,
    )

    assert "artifact_id does not match canonical payload hash" in findings
    assert "authority must be false" in findings
    assert "may_generate_live_proposal must be false" in findings
    assert any("Gate 0 active" in finding for finding in findings)


def test_text_normalization_preserves_meaning_and_hashes():
    document, raw_bytes, normalized_bytes = build_snapshot(
        spec(),
        result(
            headers={"Content-Type": "text/plain"},
            body=b"line-1\r\nline-2\r\n",
        ),
        producer_commit=PRODUCER_COMMIT,
    )

    assert raw_bytes == b"line-1\r\nline-2\r\n"
    assert normalized_bytes == b"line-1\nline-2\n"
    assert document["normalization"]["format"] == "utf8_text_lf"
    assert document["hashes"]["normalized_sha256"] == sha256_hex(
        normalized_bytes
    )
