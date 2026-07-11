from __future__ import annotations

import argparse
import copy
import hashlib
import ipaddress
import json
import socket
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from eve_q.live_read_only_telemetry import (
    SourceSpec,
    canonical_json_bytes,
    iso_z,
    load_source_spec,
    normalize_host,
    parse_utc,
    validate_url,
)

CONTRACT_VERSION = "eve_q_gate1_hardening_v0.1"
RESOLUTION_ARTIFACT_TYPE = "Gate1ResolutionReceipt"
ROLLBACK_ARTIFACT_TYPE = "Gate1RollbackReceipt"
RESOLVER_MODE = "system_getaddrinfo_pre_and_post"

Resolver = Callable[..., Iterable[tuple[Any, ...]]]


class Gate1HardeningError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def artifact_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(document))
    payload.pop("artifact_id", None)
    return payload


def compute_artifact_id(document: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(artifact_payload(document)))


def refresh_artifact_id(document: Mapping[str, Any]) -> dict[str, Any]:
    refreshed = copy.deepcopy(dict(document))
    refreshed["artifact_id"] = compute_artifact_id(refreshed)
    return refreshed


def _validated_host_and_port(
    url: str,
    allowed_hosts: tuple[str, ...],
) -> tuple[str, int]:
    parsed = validate_url(url, allowed_hosts)
    host = normalize_host(str(parsed.hostname or ""))
    if not host:
        raise Gate1HardeningError("missing_host", "telemetry URL has no host")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise Gate1HardeningError(
            "ip_literal_host_rejected",
            "Gate 1 sources must use a reviewed DNS hostname, not an IP literal",
        )

    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise Gate1HardeningError(
            "invalid_port",
            "telemetry URL contains an invalid port",
        ) from exc
    if port != 443:
        raise Gate1HardeningError(
            "non_standard_port_rejected",
            "Gate 1 live telemetry is restricted to HTTPS port 443",
        )
    return host, port


def _address_is_public(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise Gate1HardeningError(
            "invalid_resolved_address",
            f"resolver returned an invalid IP address: {address}",
        ) from exc

    return bool(
        parsed.is_global
        and not parsed.is_private
        and not parsed.is_loopback
        and not parsed.is_link_local
        and not parsed.is_multicast
        and not parsed.is_reserved
        and not parsed.is_unspecified
    )


def resolve_public_addresses(
    host: str,
    port: int = 443,
    *,
    resolver: Resolver = socket.getaddrinfo,
) -> tuple[str, ...]:
    try:
        records = resolver(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except (OSError, socket.gaierror) as exc:
        raise Gate1HardeningError(
            "dns_resolution_failed",
            f"DNS resolution failed for reviewed host {host}: {exc}",
        ) from exc

    addresses: set[str] = set()
    for record in records:
        if len(record) < 5:
            continue
        sockaddr = record[4]
        if not isinstance(sockaddr, Sequence) or not sockaddr:
            continue
        address = str(sockaddr[0]).split("%", 1)[0]
        addresses.add(address)

    if not addresses:
        raise Gate1HardeningError(
            "dns_no_addresses",
            f"DNS resolution returned no usable addresses for {host}",
        )

    non_public = sorted(address for address in addresses if not _address_is_public(address))
    if non_public:
        raise Gate1HardeningError(
            "non_public_address_rejected",
            "reviewed host resolved to a non-public address: " + ", ".join(non_public),
        )

    return tuple(sorted(addresses))


def preflight_source_resolution(
    spec: SourceSpec,
    *,
    resolver: Resolver = socket.getaddrinfo,
) -> tuple[str, int, tuple[str, ...]]:
    host, port = _validated_host_and_port(spec.url, spec.allowed_hosts)
    addresses = resolve_public_addresses(host, port, resolver=resolver)
    return host, port, addresses


def build_resolution_receipt(
    spec: SourceSpec,
    *,
    producer_commit: str,
    created_at: str,
    resolver: Resolver = socket.getaddrinfo,
) -> dict[str, Any]:
    if len(producer_commit) != 40 or any(
        character not in "0123456789abcdef" for character in producer_commit.lower()
    ):
        raise Gate1HardeningError(
            "invalid_producer_commit",
            "producer_commit must be a 40-character hexadecimal SHA",
        )

    parse_utc(created_at)
    host, port, addresses = preflight_source_resolution(spec, resolver=resolver)
    address_set_sha256 = sha256_hex(canonical_json_bytes(list(addresses)))

    document: dict[str, Any] = {
        "artifact_type": RESOLUTION_ARTIFACT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "created_at": created_at,
        "source_id": spec.source_id,
        "requested_uri": spec.url,
        "reviewed_host": host,
        "port": port,
        "resolver_mode": RESOLVER_MODE,
        "resolved_addresses": list(addresses),
        "address_set_sha256": address_set_sha256,
        "all_addresses_public": True,
        "producer_commit": producer_commit.lower(),
        "gate_posture": {
            "gate_0": "ACTIVE",
            "gate_1": "PILOT_ONLY",
            "gate_2_through_6": "LOCKED",
        },
        "artifact_is_command": False,
        "authority": False,
        "human_promotion_required": True,
        "may_generate_live_proposal": False,
        "may_execute": False,
        "may_move_capital": False,
    }
    return refresh_artifact_id(document)


def validate_resolution_receipt(
    document: Mapping[str, Any],
    *,
    current_spec: SourceSpec | None = None,
    resolver: Resolver | None = None,
) -> list[str]:
    findings: list[str] = []

    if document.get("artifact_type") != RESOLUTION_ARTIFACT_TYPE:
        findings.append(f"artifact_type must be {RESOLUTION_ARTIFACT_TYPE}")
    if document.get("contract_version") != CONTRACT_VERSION:
        findings.append(f"contract_version must be {CONTRACT_VERSION}")
    if document.get("artifact_id") != compute_artifact_id(document):
        findings.append("artifact_id does not match canonical payload hash")

    addresses = document.get("resolved_addresses")
    if not isinstance(addresses, list) or not addresses:
        findings.append("resolved_addresses must be a non-empty array")
        addresses = []
    else:
        non_public: list[str] = []
        for address in addresses:
            try:
                if not _address_is_public(str(address)):
                    non_public.append(str(address))
            except Gate1HardeningError:
                non_public.append(str(address))
        if non_public:
            findings.append(
                "resolution receipt contains non-public addresses: "
                + ", ".join(sorted(non_public))
            )

    expected_set_hash = sha256_hex(
        canonical_json_bytes(sorted(str(address) for address in addresses))
    )
    if document.get("address_set_sha256") != expected_set_hash:
        findings.append("address_set_sha256 does not match resolved_addresses")

    for key, expected in {
        "all_addresses_public": True,
        "artifact_is_command": False,
        "authority": False,
        "human_promotion_required": True,
        "may_generate_live_proposal": False,
        "may_execute": False,
        "may_move_capital": False,
    }.items():
        if document.get(key) is not expected:
            findings.append(f"{key} must be {str(expected).lower()}")

    if document.get("resolver_mode") != RESOLVER_MODE:
        findings.append(f"resolver_mode must be {RESOLVER_MODE}")
    if document.get("port") != 443:
        findings.append("port must be 443")
    if document.get("gate_posture") != {
        "gate_0": "ACTIVE",
        "gate_1": "PILOT_ONLY",
        "gate_2_through_6": "LOCKED",
    }:
        findings.append("gate posture must keep Gate 0 active and Gates 2-6 locked")

    if current_spec is not None:
        try:
            current_host, current_port = _validated_host_and_port(
                current_spec.url,
                current_spec.allowed_hosts,
            )
        except Exception as exc:  # normalized as a validation finding
            findings.append(f"current source spec is invalid: {exc}")
        else:
            if document.get("source_id") != current_spec.source_id:
                findings.append("source_id does not match current source spec")
            if document.get("requested_uri") != current_spec.url:
                findings.append("requested_uri does not match current source spec")
            if document.get("reviewed_host") != current_host:
                findings.append("reviewed_host does not match current source spec")
            if document.get("port") != current_port:
                findings.append("port does not match current source spec")

            if resolver is not None:
                try:
                    current_addresses = resolve_public_addresses(
                        current_host,
                        current_port,
                        resolver=resolver,
                    )
                except Gate1HardeningError as exc:
                    findings.append(f"current DNS resolution failed closed: {exc.code}")
                else:
                    recorded = tuple(sorted(str(address) for address in addresses))
                    if current_addresses != recorded:
                        findings.append(
                            "DNS resolution changed between preflight and verification"
                        )

    return findings


def build_rollback_receipt(
    *,
    producer_commit: str,
    trigger: str,
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    if trigger not in {
        "kill_switch",
        "source_outage",
        "dns_policy_failure",
        "operator_abort",
    }:
        raise Gate1HardeningError(
            "invalid_rollback_trigger",
            f"unsupported rollback trigger: {trigger}",
        )
    if len(producer_commit) != 40 or any(
        character not in "0123456789abcdef" for character in producer_commit.lower()
    ):
        raise Gate1HardeningError(
            "invalid_producer_commit",
            "producer_commit must be a 40-character hexadecimal SHA",
        )

    started = parse_utc(started_at)
    completed = parse_utc(completed_at)
    if completed < started:
        raise Gate1HardeningError(
            "rollback_time_reversed",
            "completed_at cannot precede started_at",
        )

    document: dict[str, Any] = {
        "artifact_type": ROLLBACK_ARTIFACT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "created_at": completed_at,
        "trigger": trigger,
        "started_at": started_at,
        "completed_at": completed_at,
        "from_gate": "LIVE_READ_ONLY_TELEMETRY_PILOT",
        "to_gate": "SIMULATION_ONLY",
        "actions": {
            "pilot_disabled": True,
            "network_capture_stopped": True,
            "pending_capture_abandoned": True,
            "gate_0_restored": True,
            "gate_2_through_6_locked": True,
        },
        "producer_commit": producer_commit.lower(),
        "artifact_is_command": False,
        "authority": False,
        "human_promotion_required": True,
        "may_generate_live_proposal": False,
        "may_execute": False,
        "may_move_capital": False,
    }
    return refresh_artifact_id(document)


def validate_rollback_receipt(document: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    if document.get("artifact_type") != ROLLBACK_ARTIFACT_TYPE:
        findings.append(f"artifact_type must be {ROLLBACK_ARTIFACT_TYPE}")
    if document.get("contract_version") != CONTRACT_VERSION:
        findings.append(f"contract_version must be {CONTRACT_VERSION}")
    if document.get("artifact_id") != compute_artifact_id(document):
        findings.append("artifact_id does not match canonical payload hash")

    try:
        started = parse_utc(str(document["started_at"]))
        completed = parse_utc(str(document["completed_at"]))
    except (KeyError, TypeError, ValueError) as exc:
        findings.append(f"rollback timestamps are invalid: {exc}")
    else:
        if completed < started:
            findings.append("completed_at cannot precede started_at")

    if document.get("from_gate") != "LIVE_READ_ONLY_TELEMETRY_PILOT":
        findings.append("from_gate must be LIVE_READ_ONLY_TELEMETRY_PILOT")
    if document.get("to_gate") != "SIMULATION_ONLY":
        findings.append("to_gate must be SIMULATION_ONLY")

    actions = document.get("actions", {})
    expected_actions = {
        "pilot_disabled": True,
        "network_capture_stopped": True,
        "pending_capture_abandoned": True,
        "gate_0_restored": True,
        "gate_2_through_6_locked": True,
    }
    if actions != expected_actions:
        findings.append("rollback actions do not prove restoration to Gate 0")

    for key, expected in {
        "artifact_is_command": False,
        "authority": False,
        "human_promotion_required": True,
        "may_generate_live_proposal": False,
        "may_execute": False,
        "may_move_capital": False,
    }.items():
        if document.get(key) is not expected:
            findings.append(f"{key} must be {str(expected).lower()}")

    return findings


def write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate 1 DNS/IP-class preflight and rollback receipts."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight-source", type=Path)
    group.add_argument("--verify-resolution-receipt", type=Path)
    group.add_argument("--write-rollback-receipt", type=Path)
    group.add_argument("--validate-rollback-receipt", type=Path)
    parser.add_argument("--source-spec", type=Path)
    parser.add_argument("--receipt-out", type=Path)
    parser.add_argument("--producer-commit")
    parser.add_argument("--trigger", default="operator_abort")
    parser.add_argument("--now")
    args = parser.parse_args()

    now = parse_utc(args.now) if args.now else datetime.now(timezone.utc)
    now_text = iso_z(now)

    if args.preflight_source:
        if args.receipt_out is None or not args.producer_commit:
            parser.error(
                "--preflight-source requires --receipt-out and --producer-commit"
            )
        spec = load_source_spec(args.preflight_source)
        receipt = build_resolution_receipt(
            spec,
            producer_commit=args.producer_commit,
            created_at=now_text,
        )
        write_json(args.receipt_out, receipt)
        print(args.receipt_out)
        return 0

    if args.verify_resolution_receipt:
        if args.source_spec is None:
            parser.error("--verify-resolution-receipt requires --source-spec")
        document = json.loads(
            args.verify_resolution_receipt.read_text(encoding="utf-8")
        )
        spec = load_source_spec(args.source_spec)
        findings = validate_resolution_receipt(
            document,
            current_spec=spec,
            resolver=socket.getaddrinfo,
        )
        if findings:
            for finding in findings:
                print(finding)
            return 1
        print("Gate 1 resolution receipt: PASS")
        return 0

    if args.write_rollback_receipt:
        if not args.producer_commit:
            parser.error("--write-rollback-receipt requires --producer-commit")
        receipt = build_rollback_receipt(
            producer_commit=args.producer_commit,
            trigger=args.trigger,
            started_at=now_text,
            completed_at=now_text,
        )
        write_json(args.write_rollback_receipt, receipt)
        print(args.write_rollback_receipt)
        return 0

    document = json.loads(
        args.validate_rollback_receipt.read_text(encoding="utf-8")
    )
    findings = validate_rollback_receipt(document)
    if findings:
        for finding in findings:
            print(finding)
        return 1
    print("Gate 1 rollback receipt: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
