from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from eve_q.gate1_readonly_runtime import (
    GATE_POSTURE,
    build_snapshot_v2,
    dangerous_secret_names,
    enforce_gate1_preflight,
    resolve_public_addresses,
    status_document,
    strict_validate_url,
    validate_snapshot_v2,
    write_snapshot_bundle_atomic,
)
from eve_q.live_read_only_telemetry import (
    SourceSpec,
    TelemetryBoundaryError,
    TransportResult,
)

SCHEMA_PATH = Path("schemas/live_read_only_telemetry_snapshot_v0_2.schema.json")
PRODUCER_COMMIT = "b" * 40
NOW = datetime(2026, 8, 1, 16, 0, tzinfo=timezone.utc)


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
        "body": b'{"price":"123.45"}',
        "final_url": "https://data.example.test/v1/market",
        "retrieved_at": "2026-08-01T16:00:00Z",
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


def resolver_for(*addresses: str):
    def resolver(host: str, port: int, *, type: int):
        del host, type
        return [
            (2, 1, 6, "", (address, port))
            for address in addresses
        ]

    return resolver


def test_status_releases_only_gate1_read_only():
    status = status_document()

    assert status["gate_posture"] == GATE_POSTURE
    assert status["gate_posture"]["gate_1"] == "OPEN_READ_ONLY"
    assert status["gate_posture"]["gate_2_through_6"] == "LOCKED"
    assert status["authority"] is False
    assert status["may_execute"] is False
    assert status["may_move_capital"] is False


def test_url_requires_exact_host_https_and_port_443():
    strict_validate_url(spec().url, spec().allowed_hosts)

    with pytest.raises(TelemetryBoundaryError) as exc_info:
        strict_validate_url(
            "https://data.example.test:8443/v1/market",
            spec().allowed_hosts,
        )
    assert exc_info.value.code == "non_default_https_port"

    with pytest.raises(TelemetryBoundaryError) as exc_info:
        strict_validate_url(
            "https://data.example.test.evil.invalid/v1/market",
            spec().allowed_hosts,
        )
    assert exc_info.value.code == "host_not_allowlisted"


def test_dns_resolution_rejects_private_and_mixed_results():
    assert resolve_public_addresses(
        "data.example.test",
        resolver=resolver_for("93.184.216.34"),
    ) == ("93.184.216.34",)

    for addresses in [
        ("127.0.0.1",),
        ("10.0.0.7",),
        ("169.254.169.254",),
        ("93.184.216.34", "10.0.0.7"),
    ]:
        with pytest.raises(TelemetryBoundaryError) as exc_info:
            resolve_public_addresses(
                "data.example.test",
                resolver=resolver_for(*addresses),
            )
        assert exc_info.value.code == "non_public_address"


def test_cosmetic_public_or_read_only_prefixes_do_not_hide_write_secrets():
    findings = dangerous_secret_names(
        {
            "PUBLIC_WALLET_PRIVATE_KEY": "secret",
            "READ_ONLY_SIGNING_KEY": "secret",
            "PUBLIC_MARKET_API_KEY": "read-only-token",
        }
    )

    assert "PUBLIC_WALLET_PRIVATE_KEY" in findings
    assert "READ_ONLY_SIGNING_KEY" in findings
    assert "PUBLIC_MARKET_API_KEY" not in findings

    with pytest.raises(TelemetryBoundaryError) as exc_info:
        enforce_gate1_preflight(
            {
                "PUBLIC_WALLET_PRIVATE_KEY": "never-echo-this",
            }
        )
    assert exc_info.value.code == "write_capable_secret_detected"
    assert "never-echo-this" not in exc_info.value.message


def test_gate1_is_open_for_explicit_invocation_but_kill_switch_still_wins():
    enforce_gate1_preflight({})

    with pytest.raises(TelemetryBoundaryError) as exc_info:
        enforce_gate1_preflight({"EVE_Q_GATE1_KILL_SWITCH": "1"})
    assert exc_info.value.code == "kill_switch_active"


def test_head_capture_produces_schema_valid_header_metadata():
    document, raw_bytes, normalized_bytes = build_snapshot_v2(
        spec(),
        result(
            headers={
                "Content-Type": "application/json",
                "ETag": "abc123",
                "Set-Cookie": "must-not-enter-artifact=1",
            },
            body=b"",
        ),
        producer_commit=PRODUCER_COMMIT,
        method="HEAD",
    )

    assert schema_findings(document) == []
    assert document["normalization"]["format"] == "head_metadata"
    assert json.loads(normalized_bytes) == {
        "content-type": "application/json",
        "etag": "abc123",
    }
    assert "set-cookie" not in document["normalized_payload"]
    assert validate_snapshot_v2(
        document,
        raw_bytes,
        normalized_bytes,
        now=NOW,
    ) == []


def test_head_capture_rejects_unexpected_body():
    with pytest.raises(TelemetryBoundaryError) as exc_info:
        build_snapshot_v2(
            spec(),
            result(body=b"unexpected"),
            producer_commit=PRODUCER_COMMIT,
            method="HEAD",
        )
    assert exc_info.value.code == "head_body_rejected"


def test_atomic_bundle_is_complete_private_and_non_overwriting(tmp_path):
    document, raw_bytes, normalized_bytes = build_snapshot_v2(
        spec(),
        result(),
        producer_commit=PRODUCER_COMMIT,
    )
    output = tmp_path / "capture"

    snapshot_path = write_snapshot_bundle_atomic(
        output,
        document,
        raw_bytes,
        normalized_bytes,
    )

    assert snapshot_path == output / "snapshot.json"
    assert sorted(path.name for path in output.iterdir()) == [
        "normalized.json",
        "raw.bin",
        "snapshot.json",
    ]
    assert (output / "snapshot.json").stat().st_mode & 0o077 == 0
    assert not list(tmp_path.glob(".capture.*"))

    with pytest.raises(FileExistsError):
        write_snapshot_bundle_atomic(
            output,
            document,
            raw_bytes,
            normalized_bytes,
        )


def test_gate_leakage_is_rejected_without_unlocking_later_gates():
    document, raw_bytes, normalized_bytes = build_snapshot_v2(
        spec(),
        result(),
        producer_commit=PRODUCER_COMMIT,
    )
    mutated = copy.deepcopy(document)
    mutated["gate_posture"]["gate_2_through_6"] = "OPEN"
    mutated["may_generate_live_proposal"] = True

    findings = validate_snapshot_v2(
        mutated,
        raw_bytes,
        normalized_bytes,
        now=NOW,
    )

    assert "artifact_id does not match canonical payload hash" in findings
    assert "may_generate_live_proposal must be false" in findings
    assert any("Gates 2-6" in finding for finding in findings)
