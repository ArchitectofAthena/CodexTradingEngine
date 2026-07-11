from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

CONTRACT_VERSION = "eve_q_live_read_only_telemetry_v0.1"
ARTIFACT_TYPE = "LiveReadOnlyTelemetrySnapshot"
PARSER_VERSION = "live-read-only-normalizer-v0.1"
ALLOWED_METHODS = frozenset({"GET", "HEAD"})
MAX_TTL_SECONDS = 86_400
DEFAULT_MAX_RESPONSE_BYTES = 1_048_576
DEFAULT_TIMEOUT_SECONDS = 10.0

WRITE_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"(^|_)PRIVATE_KEY($|_)",
        r"(^|_)SEED_PHRASE($|_)",
        r"(^|_)MNEMONIC($|_)",
        r"(^|_)WALLET_SEED($|_)",
        r"(^|_)SIGNING_KEY($|_)",
        r"(^|_)TRADING_API_KEY($|_)",
        r"(^|_)TRADING_SECRET($|_)",
        r"(^|_)EXCHANGE_API_SECRET($|_)",
        r"(^|_)ORDER_API_KEY($|_)",
        r"(^|_)BINANCE_SECRET($|_)",
        r"(^|_)COINBASE_API_SECRET($|_)",
    )
)

READ_ONLY_NAME_MARKERS = (
    "READ_ONLY",
    "READONLY",
    "PUBLIC",
)


class TelemetryBoundaryError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    source_kind: str
    url: str
    allowed_hosts: tuple[str, ...]
    freshness_ttl_seconds: int = 300
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "SourceSpec":
        return cls(
            source_id=str(document["source_id"]),
            source_kind=str(document["source_kind"]),
            url=str(document["url"]),
            allowed_hosts=tuple(str(host) for host in document["allowed_hosts"]),
            freshness_ttl_seconds=int(document.get("freshness_ttl_seconds", 300)),
            timeout_seconds=float(
                document.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
            ),
            max_response_bytes=int(
                document.get(
                    "max_response_bytes",
                    DEFAULT_MAX_RESPONSE_BYTES,
                )
            ),
        )


@dataclass(frozen=True)
class TransportResult:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str
    retrieved_at: str


def canonical_json_bytes(document: Any) -> bytes:
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_host(host: str) -> str:
    return host.strip().rstrip(".").lower()


def host_is_allowlisted(host: str, allowed_hosts: tuple[str, ...]) -> bool:
    normalized = normalize_host(host)
    return normalized in {normalize_host(item) for item in allowed_hosts}


def validate_url(url: str, allowed_hosts: tuple[str, ...]) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https":
        raise TelemetryBoundaryError(
            "scheme_not_https",
            "live telemetry requires HTTPS",
        )
    if parsed.username or parsed.password:
        raise TelemetryBoundaryError(
            "credentials_in_url",
            "credentials may not be embedded in telemetry URLs",
        )
    if not parsed.hostname:
        raise TelemetryBoundaryError("missing_host", "telemetry URL has no host")
    if not host_is_allowlisted(parsed.hostname, allowed_hosts):
        raise TelemetryBoundaryError(
            "host_not_allowlisted",
            f"host is not allowlisted: {parsed.hostname}",
        )
    return parsed


def validate_source_spec(spec: SourceSpec) -> None:
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
    validate_url(spec.url, spec.allowed_hosts)


def dangerous_secret_names(environment: Mapping[str, str]) -> list[str]:
    findings: list[str] = []
    for name, value in environment.items():
        if not value:
            continue
        normalized = name.upper()
        if any(marker in normalized for marker in READ_ONLY_NAME_MARKERS):
            continue
        if any(pattern.search(normalized) for pattern in WRITE_SECRET_PATTERNS):
            findings.append(name)
    return sorted(findings)


def enforce_pilot_preflight(environment: Mapping[str, str]) -> None:
    if environment.get("EVE_Q_GATE1_KILL_SWITCH") == "1":
        raise TelemetryBoundaryError(
            "kill_switch_active",
            "Gate 1 pilot is disabled; remain at Gate 0 simulation-only",
        )
    if environment.get("EVE_Q_GATE1_PILOT") != "1":
        raise TelemetryBoundaryError(
            "pilot_not_enabled",
            "set EVE_Q_GATE1_PILOT=1 for an explicit read-only pilot run",
        )
    dangerous = dangerous_secret_names(environment)
    if dangerous:
        raise TelemetryBoundaryError(
            "write_capable_secret_detected",
            "write-capable secret names detected: " + ", ".join(dangerous),
        )


def validate_method(method: str) -> str:
    normalized = method.upper()
    if normalized not in ALLOWED_METHODS:
        raise TelemetryBoundaryError(
            "write_method_rejected",
            f"HTTP method is not read-only: {normalized}",
        )
    return normalized


class AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: tuple[str, ...]):
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Mapping[str, str],
        newurl: str,
    ) -> urllib.request.Request | None:
        validate_url(newurl, self.allowed_hosts)
        method = validate_method(req.get_method())
        return urllib.request.Request(
            newurl,
            headers=dict(req.headers),
            method=method,
        )


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return str(value)
    return None


def _content_type(headers: Mapping[str, str]) -> str:
    value = _header_value(headers, "content-type") or ""
    return value.split(";", 1)[0].strip().lower()


def normalize_payload(body: bytes, content_type: str) -> tuple[Any, bytes, str]:
    is_json = content_type == "application/json" or content_type.endswith("+json")
    if is_json:
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TelemetryBoundaryError(
                "malformed_json",
                f"response is not valid UTF-8 JSON: {exc}",
            ) from exc
        return parsed, canonical_json_bytes(parsed), "canonical_json"

    if content_type == "text/plain":
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TelemetryBoundaryError(
                "malformed_text",
                "text/plain response is not valid UTF-8",
            ) from exc
        normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
        return normalized_text, normalized_text.encode("utf-8"), "utf8_text_lf"

    raise TelemetryBoundaryError(
        "unsupported_content_type",
        f"unsupported content type: {content_type or '<missing>'}",
    )


def fetch_read_only(
    spec: SourceSpec,
    *,
    method: str = "GET",
    environment: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> TransportResult:
    validate_source_spec(spec)
    normalized_method = validate_method(method)
    enforce_pilot_preflight(environment or os.environ)

    request = urllib.request.Request(
        spec.url,
        headers={
            "Accept": "application/json, text/plain;q=0.8",
            "User-Agent": "EVE_Q-live-read-only-telemetry-v0.1",
        },
        method=normalized_method,
    )
    context = ssl.create_default_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        AllowlistedRedirectHandler(spec.allowed_hosts),
    )
    retrieved = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    try:
        with opener.open(request, timeout=spec.timeout_seconds) as response:
            status = int(response.getcode())
            final_url = str(response.geturl())
            validate_url(final_url, spec.allowed_hosts)
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
            headers = {str(key): str(value) for key, value in response.headers.items()}
    except TelemetryBoundaryError:
        raise
    except urllib.error.HTTPError as exc:
        raise TelemetryBoundaryError(
            "http_error",
            f"read-only source returned HTTP {exc.code}",
        ) from exc
    except urllib.error.URLError as exc:
        raise TelemetryBoundaryError(
            "source_unavailable",
            f"read-only source unavailable: {exc.reason}",
        ) from exc
    except TimeoutError as exc:
        raise TelemetryBoundaryError(
            "source_timeout",
            "read-only source timed out",
        ) from exc

    return TransportResult(
        status=status,
        headers=headers,
        body=body,
        final_url=final_url,
        retrieved_at=iso_z(retrieved),
    )


def snapshot_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(document)
    payload.pop("artifact_id", None)
    return payload


def compute_artifact_id(document: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(snapshot_payload(document)))


def build_snapshot(
    spec: SourceSpec,
    result: TransportResult,
    *,
    producer_commit: str,
    method: str = "GET",
) -> tuple[dict[str, Any], bytes, bytes]:
    validate_source_spec(spec)
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
    validate_url(result.final_url, spec.allowed_hosts)
    if len(result.body) > spec.max_response_bytes:
        raise TelemetryBoundaryError(
            "response_too_large",
            f"response exceeded {spec.max_response_bytes} bytes",
        )

    content_type = _content_type(result.headers)
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
            "expires_at": iso_z(expires_at),
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
            "component": "live_read_only_telemetry_v0_1",
            "commit_sha": producer_commit.lower(),
        },
        "storage": {
            "raw_relative_path": "raw.bin",
            "normalized_relative_path": "normalized.json",
        },
        "normalized_payload": normalized_payload,
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
    document["artifact_id"] = compute_artifact_id(document)
    return document, result.body, normalized_bytes


def validate_snapshot(
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
    if document.get("artifact_id") != compute_artifact_id(document):
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

    posture = document.get("gate_posture", {})
    if posture != {
        "gate_0": "ACTIVE",
        "gate_1": "PILOT_ONLY",
        "gate_2_through_6": "LOCKED",
    }:
        findings.append("gate posture must keep Gate 0 active and Gates 2-6 locked")

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


def write_snapshot_bundle(
    output_dir: Path,
    document: dict[str, Any],
    raw_bytes: bytes,
    normalized_bytes: bytes,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "raw.bin").write_bytes(raw_bytes)
    (output_dir / "normalized.json").write_bytes(normalized_bytes + b"\n")
    snapshot_path = output_dir / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return snapshot_path


def replay_snapshot_bundle(
    bundle_dir: Path,
    *,
    now: datetime | None = None,
    require_fresh: bool = False,
) -> list[str]:
    document = json.loads((bundle_dir / "snapshot.json").read_text(encoding="utf-8"))
    raw_bytes = (bundle_dir / "raw.bin").read_bytes()
    normalized_bytes = (bundle_dir / "normalized.json").read_bytes().rstrip(b"\n")
    return validate_snapshot(
        document,
        raw_bytes,
        normalized_bytes,
        now=now,
        require_fresh=require_fresh,
    )


def load_source_spec(path: Path) -> SourceSpec:
    return SourceSpec.from_dict(json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture or replay a Gate 1 pilot read-only telemetry snapshot."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture", type=Path, help="SourceSpec JSON file")
    group.add_argument("--replay", type=Path, help="Snapshot bundle directory")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--producer-commit")
    parser.add_argument("--method", default="GET")
    parser.add_argument("--now")
    parser.add_argument("--require-fresh", action="store_true")
    args = parser.parse_args()

    now = parse_utc(args.now) if args.now else None

    if args.replay:
        findings = replay_snapshot_bundle(
            args.replay,
            now=now,
            require_fresh=args.require_fresh,
        )
        if findings:
            for finding in findings:
                print(finding)
            return 1
        print("Read-only telemetry replay: PASS")
        return 0

    if args.output_dir is None or not args.producer_commit:
        parser.error("--capture requires --output-dir and --producer-commit")

    spec = load_source_spec(args.capture)
    result = fetch_read_only(
        spec,
        method=args.method,
        now=now,
    )
    document, raw_bytes, normalized_bytes = build_snapshot(
        spec,
        result,
        producer_commit=args.producer_commit,
        method=args.method,
    )
    snapshot_path = write_snapshot_bundle(
        args.output_dir,
        document,
        raw_bytes,
        normalized_bytes,
    )
    print(snapshot_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
