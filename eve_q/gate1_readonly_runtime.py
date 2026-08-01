"""Deployable Gate 1 runtime for bounded public telemetry observation.

Gate 1 is the least consequential deployable surface: it performs only explicit,
allowlisted HTTPS GET/HEAD requests, emits immutable review artifacts, and carries
no proposal, signing, transaction, execution, wallet, or capital authority.

The legacy pilot module remains available for historical replay. This v0.2
runtime is the released, operator-invoked Gate 1 surface. Gates 2 through 6 stay
locked.
"""

from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import os
import shutil
import socket
import ssl
import tempfile
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from eve_q.live_read_only_telemetry import (
    ALLOWED_METHODS,
    ARTIFACT_TYPE,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_TTL_SECONDS,
    PARSER_VERSION,
    SourceSpec,
    TelemetryBoundaryError,
    TransportResult,
    canonical_json_bytes,
    normalize_host,
    normalize_payload,
    parse_utc,
    sha256_hex,
    snapshot_payload,
    validate_method,
)

CONTRACT_VERSION = "eve_q_live_read_only_telemetry_v0.2"
COMPONENT = "gate1_readonly_runtime_v0_2"
GATE_POSTURE = {
    "gate_0": "ACTIVE",
    "gate_1": "OPEN_READ_ONLY",
    "gate_2_through_6": "LOCKED",
}
MAX_REDIRECTS = 3
SAFE_HEAD_HEADERS = frozenset(
    {"cache-control", "content-length", "content-type", "etag", "last-modified"}
)

Resolver = Callable[..., Sequence[tuple[Any, ...]]]


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to a previously validated public IP address."""

    def __init__(
        self,
        hostname: str,
        port: int,
        address: str,
        *,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__(hostname, port=port, timeout=timeout, context=context)
        self._address = address

    def connect(self) -> None:
        raw = socket.create_connection(
            (self._address, self.port),
            timeout=self.timeout,
        )
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def strict_validate_url(
    url: str,
    allowed_hosts: tuple[str, ...],
) -> urllib.parse.ParseResult:
    """Validate an HTTPS URL against exact hosts and the default TLS port."""

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https":
        raise TelemetryBoundaryError("scheme_not_https", "Gate 1 requires HTTPS")
    if parsed.username or parsed.password:
        raise TelemetryBoundaryError(
            "credentials_in_url",
            "credentials may not be embedded in Gate 1 URLs",
        )
    if not parsed.hostname:
        raise TelemetryBoundaryError("missing_host", "Gate 1 URL has no host")
    normalized_allowed = {normalize_host(item) for item in allowed_hosts}
    if normalize_host(parsed.hostname) not in normalized_allowed:
        raise TelemetryBoundaryError(
            "host_not_allowlisted",
            f"host is not allowlisted: {parsed.hostname}",
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise TelemetryBoundaryError("invalid_port", "Gate 1 URL has an invalid port") from exc
    if port not in {None, 443}:
        raise TelemetryBoundaryError(
            "non_default_https_port",
            "Gate 1 permits only the default HTTPS port 443",
        )
    return parsed


def validate_source_spec_v2(spec: SourceSpec) -> None:
    if not spec.source_id.strip():
        raise TelemetryBoundaryError("missing_source_id", "source_id is required")
    if spec.source_kind not in {
        "market_snapshot",
        "onchain_snapshot",
        "policy_snapshot",
        "impact_snapshot",
    }:
        raise TelemetryBoundaryError(
            "unsupported_source_kind",
            f"unsupported source_kind: {spec.source_kind}",
        )
    if not spec.allowed_hosts:
        raise TelemetryBoundaryError(
            "empty_allowlist",
            "at least one allowed host is required",
        )
    if not 1 <= spec.freshness_ttl_seconds <= MAX_TTL_SECONDS:
        raise TelemetryBoundaryError(
            "invalid_freshness_ttl",
            f"freshness_ttl_seconds must be between 1 and {MAX_TTL_SECONDS}",
        )
    if not 0 < spec.timeout_seconds <= 60:
        raise TelemetryBoundaryError(
            "invalid_timeout",
            "timeout_seconds must be greater than zero and no more than 60",
        )
    if not 1 <= spec.max_response_bytes <= 10_485_760:
        raise TelemetryBoundaryError(
            "invalid_response_cap",
            "max_response_bytes must be between 1 and 10485760",
        )
    strict_validate_url(spec.url, spec.allowed_hosts)


def resolve_public_addresses(
    hostname: str,
    *,
    port: int = 443,
    resolver: Resolver = socket.getaddrinfo,
) -> tuple[str, ...]:
    """Resolve once, reject mixed/private results, and return pinned addresses."""

    try:
        records = resolver(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise TelemetryBoundaryError(
            "dns_resolution_failed",
            f"unable to resolve allowlisted host: {hostname}",
        ) from exc

    addresses = sorted({str(record[4][0]) for record in records if record[4]})
    if not addresses:
        raise TelemetryBoundaryError(
            "dns_resolution_empty",
            f"allowlisted host resolved to no addresses: {hostname}",
        )

    rejected: list[str] = []
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            rejected.append(address)
            continue
        if not parsed.is_global:
            rejected.append(address)
    if rejected:
        raise TelemetryBoundaryError(
            "non_public_address",
            "allowlisted host resolved to a non-public address",
        )
    return tuple(addresses)


def dangerous_secret_names(environment: Mapping[str, str]) -> list[str]:
    """Detect write-capable secret names without trusting cosmetic prefixes."""

    from eve_q.live_read_only_telemetry import WRITE_SECRET_PATTERNS

    findings: list[str] = []
    for name, value in environment.items():
        if not value:
            continue
        normalized = name.upper()
        if any(pattern.search(normalized) for pattern in WRITE_SECRET_PATTERNS):
            findings.append(name)
    return sorted(findings)


def enforce_gate1_preflight(environment: Mapping[str, str]) -> None:
    """Fail closed on kill switch or write-capable credentials.

    Gate 1 is open for explicit operator invocation, so no pilot-enable flag is
    required. Absence of a command still means absence of a network request.
    """

    if environment.get("EVE_Q_GATE1_KILL_SWITCH") == "1":
        raise TelemetryBoundaryError(
            "kill_switch_active",
            "Gate 1 read-only telemetry is disabled by the kill switch",
        )
    dangerous = dangerous_secret_names(environment)
    if dangerous:
        raise TelemetryBoundaryError(
            "write_capable_secret_detected",
            "write-capable secret names detected: " + ", ".join(dangerous),
        )


def _request_target(parsed: urllib.parse.ParseResult) -> str:
    target = parsed.path or "/"
    if parsed.params:
        target += ";" + parsed.params
    if parsed.query:
        target += "?" + parsed.query
    return target


def fetch_read_only_v2(
    spec: SourceSpec,
    *,
    method: str = "GET",
    environment: Mapping[str, str] | None = None,
    now: datetime | None = None,
    resolver: Resolver = socket.getaddrinfo,
) -> TransportResult:
    """Perform a public-IP-pinned, bounded HTTPS GET or HEAD request."""

    validate_source_spec_v2(spec)
    normalized_method = validate_method(method)
    enforce_gate1_preflight(environment or os.environ)
    current_url = spec.url
    visited: set[str] = set()
    context = ssl.create_default_context()

    try:
        for redirect_count in range(MAX_REDIRECTS + 1):
            if current_url in visited:
                raise TelemetryBoundaryError(
                    "redirect_loop",
                    "Gate 1 source entered a redirect loop",
                )
            visited.add(current_url)
            parsed = strict_validate_url(current_url, spec.allowed_hosts)
            hostname = str(parsed.hostname)
            addresses = resolve_public_addresses(hostname, resolver=resolver)
            connection = PinnedHTTPSConnection(
                hostname,
                443,
                addresses[0],
                timeout=spec.timeout_seconds,
                context=context,
            )
            try:
                connection.request(
                    normalized_method,
                    _request_target(parsed),
                    headers={
                        "Accept": "application/json, text/plain;q=0.8",
                        "Host": hostname,
                        "User-Agent": "EVE_Q-Gate1-read-only-v0.2",
                    },
                )
                response = connection.getresponse()
                status = int(response.status)
                headers = {str(key): str(value) for key, value in response.getheaders()}
                location = next(
                    (value for key, value in headers.items() if key.lower() == "location"),
                    None,
                )
                if status in {301, 302, 303, 307, 308}:
                    response.read(DEFAULT_MAX_RESPONSE_BYTES + 1)
                    if not location:
                        raise TelemetryBoundaryError(
                            "redirect_without_location",
                            "Gate 1 source redirected without a Location header",
                        )
                    if redirect_count >= MAX_REDIRECTS:
                        raise TelemetryBoundaryError(
                            "too_many_redirects",
                            f"Gate 1 exceeded {MAX_REDIRECTS} redirects",
                        )
                    current_url = urllib.parse.urljoin(current_url, location)
                    continue
                if not 200 <= status < 300:
                    raise TelemetryBoundaryError(
                        "http_status_rejected",
                        f"read-only source returned HTTP {status}",
                    )
                body = response.read(spec.max_response_bytes + 1)
                if len(body) > spec.max_response_bytes:
                    raise TelemetryBoundaryError(
                        "response_too_large",
                        f"response exceeded {spec.max_response_bytes} bytes",
                    )
                retrieved = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
                return TransportResult(
                    status=status,
                    headers=headers,
                    body=body,
                    final_url=current_url,
                    retrieved_at=retrieved.isoformat().replace("+00:00", "Z"),
                )
            finally:
                connection.close()
    except TelemetryBoundaryError:
        raise
    except socket.timeout as exc:
        raise TelemetryBoundaryError("source_timeout", "read-only source timed out") from exc
    except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
        raise TelemetryBoundaryError(
            "source_unavailable",
            f"read-only source unavailable: {type(exc).__name__}",
        ) from exc

    raise TelemetryBoundaryError("source_unavailable", "read-only source was unavailable")


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return str(value)
    return None


def _content_type(headers: Mapping[str, str]) -> str:
    value = _header_value(headers, "content-type") or ""
    return value.split(";", 1)[0].strip().lower()


def _safe_head_metadata(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key.lower(): str(value)
        for key, value in sorted(headers.items(), key=lambda item: item[0].lower())
        if key.lower() in SAFE_HEAD_HEADERS
    }


def compute_artifact_id_v2(document: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(snapshot_payload(document)))


def build_snapshot_v2(
    spec: SourceSpec,
    result: TransportResult,
    *,
    producer_commit: str,
    method: str = "GET",
) -> tuple[dict[str, Any], bytes, bytes]:
    validate_source_spec_v2(spec)
    normalized_method = validate_method(method)
    if len(producer_commit) != 40 or any(
        character not in "0123456789abcdef" for character in producer_commit.lower()
    ):
        raise TelemetryBoundaryError(
            "invalid_producer_commit",
            "producer_commit must be a 40-character hexadecimal SHA",
        )
    if not 200 <= result.status < 300:
        raise TelemetryBoundaryError(
            "http_status_rejected",
            f"read-only source returned HTTP {result.status}",
        )
    strict_validate_url(result.final_url, spec.allowed_hosts)
    if len(result.body) > spec.max_response_bytes:
        raise TelemetryBoundaryError(
            "response_too_large",
            f"response exceeded {spec.max_response_bytes} bytes",
        )

    content_type = _content_type(result.headers)
    if normalized_method == "HEAD":
        if result.body:
            raise TelemetryBoundaryError(
                "head_body_rejected",
                "HEAD responses must not carry a payload body",
            )
        normalized_payload: Any = _safe_head_metadata(result.headers)
        normalized_bytes = canonical_json_bytes(normalized_payload)
        normalization_format = "head_metadata"
    else:
        normalized_payload, normalized_bytes, normalization_format = normalize_payload(
            result.body,
            content_type,
        )

    retrieved_at = parse_utc(result.retrieved_at)
    expires_at = retrieved_at + timedelta(seconds=spec.freshness_ttl_seconds)
    final_host = urllib.parse.urlparse(result.final_url).hostname
    if not final_host:
        raise TelemetryBoundaryError("missing_host", "final URL has no host")

    document: dict[str, Any] = {
        "artifact_type": ARTIFACT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "created_at": result.retrieved_at,
        "source": {
            "source_id": spec.source_id,
            "source_kind": spec.source_kind,
            "requested_uri": spec.url,
            "final_uri": result.final_url,
            "allowlisted_host": normalize_host(final_host),
            "method": normalized_method,
        },
        "retrieval": {
            "retrieved_at": result.retrieved_at,
            "observed_at": result.retrieved_at,
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "freshness_ttl_seconds": spec.freshness_ttl_seconds,
            "http_status": result.status,
            "content_type": content_type,
            "content_length": len(result.body),
        },
        "hashes": {
            "raw_sha256": sha256_hex(result.body),
            "normalized_sha256": sha256_hex(normalized_bytes),
        },
        "normalization": {
            "format": normalization_format,
            "parser_version": PARSER_VERSION,
        },
        "producer": {
            "repository": "ArchitectofAthena/CodexTradingEngine",
            "component": COMPONENT,
            "commit_sha": producer_commit.lower(),
        },
        "storage": {
            "raw_relative_path": "raw.bin",
            "normalized_relative_path": "normalized.json",
        },
        "normalized_payload": normalized_payload,
        "gate_posture": dict(GATE_POSTURE),
        "artifact_is_command": False,
        "authority": False,
        "human_promotion_required": True,
        "may_generate_live_proposal": False,
        "may_execute": False,
        "may_move_capital": False,
    }
    document["artifact_id"] = compute_artifact_id_v2(document)
    return document, result.body, normalized_bytes


def validate_snapshot_v2(
    document: Mapping[str, Any],
    raw_bytes: bytes,
    normalized_bytes: bytes,
    *,
    now: datetime | None = None,
    require_fresh: bool = True,
) -> list[str]:
    findings: list[str] = []
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if document.get("artifact_type") != ARTIFACT_TYPE:
        findings.append(f"artifact_type must be {ARTIFACT_TYPE}")
    if document.get("contract_version") != CONTRACT_VERSION:
        findings.append(f"contract_version must be {CONTRACT_VERSION}")
    if document.get("artifact_id") != compute_artifact_id_v2(document):
        findings.append("artifact_id does not match canonical payload hash")
    hashes = document.get("hashes", {})
    if hashes.get("raw_sha256") != sha256_hex(raw_bytes):
        findings.append("raw payload hash mismatch")
    if hashes.get("normalized_sha256") != sha256_hex(normalized_bytes):
        findings.append("normalized payload hash mismatch")
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
    if document.get("gate_posture") != GATE_POSTURE:
        findings.append("only Gate 1 read-only may be open; Gates 2-6 must remain locked")
    retrieval = document.get("retrieval", {})
    try:
        retrieved_at = parse_utc(str(retrieval["retrieved_at"]))
        expires_at = parse_utc(str(retrieval["expires_at"]))
        ttl_seconds = int(retrieval["freshness_ttl_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        findings.append(f"invalid freshness fields: {exc}")
    else:
        if int((expires_at - retrieved_at).total_seconds()) != ttl_seconds:
            findings.append("freshness TTL does not match retrieval timestamps")
        if require_fresh and expires_at <= now_utc:
            findings.append("telemetry snapshot is stale")
    source = document.get("source", {})
    if source.get("method") not in ALLOWED_METHODS:
        findings.append("snapshot method must be GET or HEAD")
    return findings


def _write_private(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    path.chmod(0o600)
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def write_snapshot_bundle_atomic(
    output_dir: Path,
    document: dict[str, Any],
    raw_bytes: bytes,
    normalized_bytes: bytes,
) -> Path:
    """Commit a complete bundle atomically or leave no target directory."""

    target = output_dir.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"output directory already exists: {target}")
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        _write_private(staging / "raw.bin", raw_bytes)
        _write_private(staging / "normalized.json", normalized_bytes + b"\n")
        _write_private(
            staging / "snapshot.json",
            (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        os.replace(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target / "snapshot.json"


def replay_snapshot_bundle_v2(
    bundle_dir: Path,
    *,
    now: datetime | None = None,
    require_fresh: bool = False,
) -> list[str]:
    document = json.loads((bundle_dir / "snapshot.json").read_text(encoding="utf-8"))
    raw_bytes = (bundle_dir / "raw.bin").read_bytes()
    normalized_bytes = (bundle_dir / "normalized.json").read_bytes().rstrip(b"\n")
    return validate_snapshot_v2(
        document,
        raw_bytes,
        normalized_bytes,
        now=now,
        require_fresh=require_fresh,
    )


def load_source_spec(path: Path) -> SourceSpec:
    document = json.loads(path.read_text(encoding="utf-8"))
    return SourceSpec.from_dict(document)


def status_document() -> dict[str, Any]:
    return {
        "artifact_type": "CodexGateStatus",
        "contract_version": "codex_gate_status_v0.2",
        "gate_posture": dict(GATE_POSTURE),
        "transport": {
            "methods": sorted(ALLOWED_METHODS),
            "scheme": "https",
            "port": 443,
            "dns_policy": "public_ip_only_pinned_connection",
            "redirect_limit": MAX_REDIRECTS,
        },
        "artifact_is_command": False,
        "authority": False,
        "human_promotion_required": True,
        "may_generate_live_proposal": False,
        "may_execute": False,
        "may_move_capital": False,
    }


def _print_json(document: Mapping[str, Any]) -> None:
    print(json.dumps(document, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Codex Gate 1 read-only runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="emit the released gate posture")

    capture = subparsers.add_parser("capture", help="capture one bounded source")
    capture.add_argument("--source", type=Path, required=True)
    capture.add_argument("--output-dir", type=Path, required=True)
    capture.add_argument("--producer-commit", required=True)
    capture.add_argument("--method", choices=sorted(ALLOWED_METHODS), default="GET")

    replay = subparsers.add_parser("replay", help="validate a captured bundle")
    replay.add_argument("--bundle", type=Path, required=True)
    replay.add_argument("--require-fresh", action="store_true")
    replay.add_argument("--now")

    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            _print_json(status_document())
            return 0
        if args.command == "replay":
            now = parse_utc(args.now) if args.now else None
            findings = replay_snapshot_bundle_v2(
                args.bundle,
                now=now,
                require_fresh=args.require_fresh,
            )
            _print_json({"ok": not findings, "findings": findings, "authority": False})
            return 0 if not findings else 1

        spec = load_source_spec(args.source)
        result = fetch_read_only_v2(spec, method=args.method)
        document, raw_bytes, normalized_bytes = build_snapshot_v2(
            spec,
            result,
            producer_commit=args.producer_commit,
            method=args.method,
        )
        snapshot_path = write_snapshot_bundle_atomic(
            args.output_dir,
            document,
            raw_bytes,
            normalized_bytes,
        )
        _print_json(
            {
                "ok": True,
                "snapshot": str(snapshot_path),
                "artifact_id": document["artifact_id"],
                "gate_posture": dict(GATE_POSTURE),
                "authority": False,
            }
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError, TelemetryBoundaryError) as exc:
        code = exc.code if isinstance(exc, TelemetryBoundaryError) else type(exc).__name__
        _print_json({"ok": False, "error": code, "authority": False})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
