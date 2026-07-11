from __future__ import annotations

import copy
import json
import socket
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from eve_q.gate1_hardening import (
    Gate1HardeningError,
    build_resolution_receipt,
    build_rollback_receipt,
    preflight_source_resolution,
    refresh_artifact_id,
    resolve_public_addresses,
    validate_resolution_receipt,
    validate_rollback_receipt,
)
from eve_q.live_read_only_telemetry import SourceSpec

RESOLUTION_SCHEMA = Path("schemas/gate1_resolution_receipt_v0_1.schema.json")
ROLLBACK_SCHEMA = Path("schemas/gate1_rollback_receipt_v0_1.schema.json")
PRODUCER_COMMIT = "a" * 40
CREATED_AT = "2026-07-11T22:30:00Z"


def source_spec(**overrides) -> SourceSpec:
    values = {
        "source_id": "reviewed-public-source",
        "source_kind": "market_snapshot",
        "url": "https://data.example.test/v1/market",
        "allowed_hosts": ("data.example.test",),
        "freshness_ttl_seconds": 300,
        "timeout_seconds": 5.0,
        "max_response_bytes": 1024,
    }
    values.update(overrides)
    return SourceSpec(**values)


def resolver_for(*addresses: str):
    def resolver(host, port, *, family, type, proto):
        assert host == "data.example.test"
        assert port == 443
        assert family == socket.AF_UNSPEC
        assert type == socket.SOCK_STREAM
        assert proto == socket.IPPROTO_TCP
        records = []
        for address in addresses:
            record_family = socket.AF_INET6 if ":" in address else socket.AF_INET
            sockaddr = (address, port, 0, 0) if record_family == socket.AF_INET6 else (address, port)
            records.append(
                (record_family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)
            )
        return records

    return resolver


def schema_findings(path: Path, document: dict) -> list:
    schema = json.loads(path.read_text(encoding="utf-8"))
    return list(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(document)
    )


def test_public_resolution_is_sorted_deduplicated_and_schema_valid():
    resolver = resolver_for("2606:2800:220:1:248:1893:25c8:1946", "93.184.216.34", "93.184.216.34")

    host, port, addresses = preflight_source_resolution(
        source_spec(),
        resolver=resolver,
    )

    assert host == "data.example.test"
    assert port == 443
    assert addresses == (
        "2606:2800:220:1:248:1893:25c8:1946",
        "93.184.216.34",
    )

    receipt = build_resolution_receipt(
        source_spec(),
        producer_commit=PRODUCER_COMMIT,
        created_at=CREATED_AT,
        resolver=resolver,
    )

    assert schema_findings(RESOLUTION_SCHEMA, receipt) == []
    assert validate_resolution_receipt(receipt) == []
    assert receipt["artifact_is_command"] is False
    assert receipt["authority"] is False
    assert receipt["may_generate_live_proposal"] is False
    assert receipt["may_execute"] is False
    assert receipt["may_move_capital"] is False


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.7",
        "169.254.1.9",
        "224.0.0.1",
        "0.0.0.0",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_non_public_ip_classes_fail_closed(address):
    with pytest.raises(Gate1HardeningError) as exc_info:
        resolve_public_addresses(
            "data.example.test",
            resolver=resolver_for(address),
        )

    assert exc_info.value.code == "non_public_address_rejected"


def test_mixed_public_and_private_resolution_fails_closed():
    with pytest.raises(Gate1HardeningError) as exc_info:
        resolve_public_addresses(
            "data.example.test",
            resolver=resolver_for("93.184.216.34", "10.1.2.3"),
        )

    assert exc_info.value.code == "non_public_address_rejected"
    assert "10.1.2.3" in exc_info.value.message


def test_ip_literal_and_non_standard_port_are_rejected():
    with pytest.raises(Gate1HardeningError) as exc_info:
        preflight_source_resolution(
            source_spec(
                url="https://93.184.216.34/v1/market",
                allowed_hosts=("93.184.216.34",),
            ),
            resolver=resolver_for("93.184.216.34"),
        )
    assert exc_info.value.code == "ip_literal_host_rejected"

    with pytest.raises(Gate1HardeningError) as exc_info:
        preflight_source_resolution(
            source_spec(url="https://data.example.test:8443/v1/market"),
            resolver=resolver_for("93.184.216.34"),
        )
    assert exc_info.value.code == "non_standard_port_rejected"


def test_dns_failure_fails_closed():
    def failed_resolver(*args, **kwargs):
        raise socket.gaierror("synthetic outage")

    with pytest.raises(Gate1HardeningError) as exc_info:
        resolve_public_addresses(
            "data.example.test",
            resolver=failed_resolver,
        )

    assert exc_info.value.code == "dns_resolution_failed"


def test_preflight_and_postflight_dns_drift_is_rejected():
    first = resolver_for("93.184.216.34")
    second = resolver_for("93.184.216.35")
    receipt = build_resolution_receipt(
        source_spec(),
        producer_commit=PRODUCER_COMMIT,
        created_at=CREATED_AT,
        resolver=first,
    )

    findings = validate_resolution_receipt(
        receipt,
        current_spec=source_spec(),
        resolver=second,
    )

    assert "DNS resolution changed between preflight and verification" in findings


def test_resolution_receipt_detects_hash_and_authority_mutation():
    receipt = build_resolution_receipt(
        source_spec(),
        producer_commit=PRODUCER_COMMIT,
        created_at=CREATED_AT,
        resolver=resolver_for("93.184.216.34"),
    )
    mutated = copy.deepcopy(receipt)
    mutated["authority"] = True
    mutated["resolved_addresses"] = ["93.184.216.35"]

    findings = validate_resolution_receipt(mutated)

    assert "artifact_id does not match canonical payload hash" in findings
    assert "address_set_sha256 does not match resolved_addresses" in findings
    assert "authority must be false" in findings


def test_rollback_receipt_is_schema_valid_non_authoritative_and_returns_gate_0():
    receipt = build_rollback_receipt(
        producer_commit=PRODUCER_COMMIT,
        trigger="kill_switch",
        started_at=CREATED_AT,
        completed_at=CREATED_AT,
    )

    assert schema_findings(ROLLBACK_SCHEMA, receipt) == []
    assert validate_rollback_receipt(receipt) == []
    assert receipt["from_gate"] == "LIVE_READ_ONLY_TELEMETRY_PILOT"
    assert receipt["to_gate"] == "SIMULATION_ONLY"
    assert all(receipt["actions"].values())
    assert receipt["authority"] is False
    assert receipt["may_generate_live_proposal"] is False
    assert receipt["may_execute"] is False
    assert receipt["may_move_capital"] is False


def test_rollback_receipt_detects_incomplete_restore_and_mutation():
    receipt = build_rollback_receipt(
        producer_commit=PRODUCER_COMMIT,
        trigger="source_outage",
        started_at=CREATED_AT,
        completed_at=CREATED_AT,
    )
    mutated = copy.deepcopy(receipt)
    mutated["actions"]["gate_0_restored"] = False
    mutated = refresh_artifact_id(mutated)

    findings = validate_rollback_receipt(mutated)

    assert "rollback actions do not prove restoration to Gate 0" in findings
