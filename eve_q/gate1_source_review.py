from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

CONTRACT_VERSION = "eve_q_gate1_source_review_v0.1"
ARTIFACT_TYPE = "Gate1SourceReviewArtifact"
ALLOWED_METHODS = frozenset({"GET", "HEAD"})
ALLOWED_SOURCE_KINDS = frozenset(
    {
        "market_snapshot",
        "onchain_snapshot",
        "policy_snapshot",
        "impact_snapshot",
    }
)
ALLOWED_CONTENT_TYPES = frozenset({"application/json", "text/plain"})
MAX_TTL_SECONDS = 86_400
MAX_RESPONSE_BYTES = 10_485_760
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
CID_RE = re.compile(r"^(?:Qm[1-9A-HJ-NP-Za-km-z]{44}|b[a-z2-7]{20,})$")
READ_ONLY_MARKERS = ("READ_ONLY", "READONLY")
FORBIDDEN_CREDENTIAL_MARKERS = (
    "PRIVATE_KEY",
    "SEED_PHRASE",
    "MNEMONIC",
    "SIGNING_KEY",
    "TRADING_SECRET",
    "ORDER_SECRET",
    "WALLET",
)


class Gate1SourceReviewError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def canonical_json_bytes(document: Any) -> bytes:
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def artifact_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(document)
    payload.pop("artifact_id", None)
    return payload


def compute_artifact_id(document: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(artifact_payload(document)))


def refresh_artifact_id(document: Mapping[str, Any]) -> dict[str, Any]:
    refreshed = dict(document)
    refreshed["artifact_id"] = compute_artifact_id(refreshed)
    return refreshed


def normalize_created_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Gate1SourceReviewError(
            "invalid_created_at",
            "created_at must be a valid RFC3339 timestamp",
        ) from exc
    if parsed.tzinfo is None:
        raise Gate1SourceReviewError(
            "invalid_created_at",
            "created_at must include a UTC offset",
        )
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_host(value: str) -> str:
    return value.strip().rstrip(".").lower()


def _require_text(value: Any, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise Gate1SourceReviewError("missing_field", f"{field} is required")
    return text


def _validate_commit(value: str) -> None:
    if not COMMIT_RE.fullmatch(value):
        raise Gate1SourceReviewError(
            "invalid_producer_commit",
            "producer_commit must be exactly 40 lowercase hexadecimal characters",
        )


def _validate_source(source: Mapping[str, Any]) -> dict[str, Any]:
    source_id = _require_text(source.get("source_id"), "source.source_id")
    source_name = _require_text(source.get("source_name"), "source.source_name")
    operator = _require_text(source.get("operator"), "source.operator")
    source_kind = _require_text(source.get("source_kind"), "source.source_kind")
    if source_kind not in ALLOWED_SOURCE_KINDS:
        raise Gate1SourceReviewError(
            "unsupported_source_kind",
            f"unsupported source_kind: {source_kind}",
        )

    endpoint_uri = _require_text(source.get("endpoint_uri"), "source.endpoint_uri")
    parsed = urllib.parse.urlparse(endpoint_uri)
    if parsed.scheme.lower() != "https":
        raise Gate1SourceReviewError(
            "scheme_not_https",
            "source endpoint must use HTTPS",
        )
    if parsed.username or parsed.password:
        raise Gate1SourceReviewError(
            "embedded_credentials_rejected",
            "credentials may not be embedded in the endpoint URI",
        )
    if not parsed.hostname:
        raise Gate1SourceReviewError("missing_host", "source endpoint has no host")
    if parsed.port not in (None, 443):
        raise Gate1SourceReviewError(
            "non_standard_port_rejected",
            "Gate 1 source review permits HTTPS port 443 only",
        )

    allowed_hosts_raw = source.get("allowed_hosts")
    if not isinstance(allowed_hosts_raw, list) or not allowed_hosts_raw:
        raise Gate1SourceReviewError(
            "empty_allowlist",
            "source.allowed_hosts must contain at least one exact host",
        )
    allowed_hosts = sorted({normalize_host(str(item)) for item in allowed_hosts_raw})
    if any(not host or "*" in host or "/" in host for host in allowed_hosts):
        raise Gate1SourceReviewError(
            "invalid_allowlist_host",
            "allowed hosts must be exact hostnames without wildcards or paths",
        )
    endpoint_host = normalize_host(parsed.hostname)
    if endpoint_host not in allowed_hosts:
        raise Gate1SourceReviewError(
            "host_not_allowlisted",
            f"endpoint host is not exactly allowlisted: {endpoint_host}",
        )

    method = _require_text(source.get("method"), "source.method").upper()
    if method not in ALLOWED_METHODS:
        raise Gate1SourceReviewError(
            "write_method_rejected",
            f"method is not read-only: {method}",
        )

    auth_mode = _require_text(source.get("auth_mode"), "source.auth_mode")
    if auth_mode not in {"NONE", "READ_ONLY_CREDENTIAL"}:
        raise Gate1SourceReviewError(
            "invalid_auth_mode",
            "auth_mode must be NONE or READ_ONLY_CREDENTIAL",
        )

    credential_reference_name = source.get("credential_reference_name")
    credential_proof_note = source.get("credential_proof_note")
    if auth_mode == "NONE":
        if credential_reference_name is not None or credential_proof_note is not None:
            raise Gate1SourceReviewError(
                "unexpected_credential_metadata",
                "credential metadata must be null when auth_mode is NONE",
            )
    else:
        credential_reference_name = _require_text(
            credential_reference_name,
            "source.credential_reference_name",
        ).upper()
        credential_proof_note = _require_text(
            credential_proof_note,
            "source.credential_proof_note",
        )
        if not any(marker in credential_reference_name for marker in READ_ONLY_MARKERS):
            raise Gate1SourceReviewError(
                "credential_not_demonstrably_read_only",
                "credential reference name must explicitly declare READ_ONLY or READONLY",
            )
        if any(marker in credential_reference_name for marker in FORBIDDEN_CREDENTIAL_MARKERS):
            raise Gate1SourceReviewError(
                "write_capable_credential_reference_rejected",
                "credential reference name contains a prohibited write-capable marker",
            )

    content_types_raw = source.get("expected_content_types")
    if not isinstance(content_types_raw, list) or not content_types_raw:
        raise Gate1SourceReviewError(
            "missing_content_types",
            "expected_content_types must be a non-empty list",
        )
    content_types = sorted({str(item).strip().lower() for item in content_types_raw})
    unsupported = sorted(set(content_types) - ALLOWED_CONTENT_TYPES)
    if unsupported:
        raise Gate1SourceReviewError(
            "unsupported_content_type",
            "unsupported expected content types: " + ", ".join(unsupported),
        )

    freshness_ttl_seconds = int(source.get("freshness_ttl_seconds", 0))
    if not 1 <= freshness_ttl_seconds <= MAX_TTL_SECONDS:
        raise Gate1SourceReviewError(
            "invalid_freshness_ttl",
            f"freshness_ttl_seconds must be between 1 and {MAX_TTL_SECONDS}",
        )

    expected_max_response_bytes = int(source.get("expected_max_response_bytes", 0))
    if not 1 <= expected_max_response_bytes <= MAX_RESPONSE_BYTES:
        raise Gate1SourceReviewError(
            "invalid_response_cap",
            f"expected_max_response_bytes must be between 1 and {MAX_RESPONSE_BYTES}",
        )

    rate_limit = source.get("documented_rate_limit")
    if not isinstance(rate_limit, Mapping):
        raise Gate1SourceReviewError(
            "missing_rate_limit",
            "documented_rate_limit must be an object",
        )
    requests = int(rate_limit.get("requests", 0))
    per_seconds = int(rate_limit.get("per_seconds", 0))
    if requests < 1 or per_seconds < 1:
        raise Gate1SourceReviewError(
            "invalid_rate_limit",
            "documented rate limit values must be positive integers",
        )

    redirect_policy = _require_text(
        source.get("redirect_policy"),
        "source.redirect_policy",
    )
    if redirect_policy not in {"NO_REDIRECTS", "EXACT_ALLOWLIST_ONLY"}:
        raise Gate1SourceReviewError(
            "invalid_redirect_policy",
            "redirect_policy must be NO_REDIRECTS or EXACT_ALLOWLIST_ONLY",
        )

    return {
        "source_id": source_id,
        "source_name": source_name,
        "operator": operator,
        "source_kind": source_kind,
        "endpoint_uri": endpoint_uri,
        "allowed_hosts": allowed_hosts,
        "method": method,
        "auth_mode": auth_mode,
        "credential_reference_name": credential_reference_name,
        "credential_proof_note": credential_proof_note,
        "documented_rate_limit": {
            "requests": requests,
            "per_seconds": per_seconds,
        },
        "expected_content_types": content_types,
        "expected_max_response_bytes": expected_max_response_bytes,
        "freshness_ttl_seconds": freshness_ttl_seconds,
        "outage_expectation": _require_text(
            source.get("outage_expectation"),
            "source.outage_expectation",
        ),
        "redirect_policy": redirect_policy,
    }


def _validate_provenance(provenance: Mapping[str, Any]) -> dict[str, Any]:
    concentration = _require_text(
        provenance.get("upstream_concentration"),
        "provenance.upstream_concentration",
    )
    if concentration not in {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}:
        raise Gate1SourceReviewError(
            "invalid_upstream_concentration",
            "upstream_concentration must be LOW, MEDIUM, HIGH, or UNKNOWN",
        )
    return {
        "provenance_group": _require_text(
            provenance.get("provenance_group"),
            "provenance.provenance_group",
        ),
        "upstream_provider": _require_text(
            provenance.get("upstream_provider"),
            "provenance.upstream_provider",
        ),
        "upstream_concentration": concentration,
        "source_independence_note": _require_text(
            provenance.get("source_independence_note"),
            "provenance.source_independence_note",
        ),
        "concentration_mitigation": str(
            provenance.get("concentration_mitigation", "")
        ).strip(),
    }


def _build_review(review: Mapping[str, Any], provenance: Mapping[str, Any]) -> dict[str, Any]:
    terms_disposition = _require_text(
        review.get("terms_disposition"),
        "review.terms_disposition",
    )
    if terms_disposition not in {
        "REVIEWED_COMPATIBLE",
        "REVIEWED_RESTRICTED",
        "NOT_REVIEWED",
    }:
        raise Gate1SourceReviewError(
            "invalid_terms_disposition",
            "terms_disposition is not recognized",
        )

    transport_risk = _require_text(
        review.get("transport_residual_risk"),
        "review.transport_residual_risk",
    )
    if transport_risk not in {
        "ACCEPTED_WITH_CONTROLS",
        "REJECTED",
        "UNRESOLVED",
    }:
        raise Gate1SourceReviewError(
            "invalid_transport_risk",
            "transport_residual_risk is not recognized",
        )

    rollback_compatible = bool(review.get("rollback_compatible"))
    kill_switch_compatible = bool(review.get("kill_switch_compatible"))
    legal_terms_note = _require_text(
        review.get("legal_terms_note"),
        "review.legal_terms_note",
    )
    review_notes_raw = review.get("review_notes", [])
    if not isinstance(review_notes_raw, list):
        raise Gate1SourceReviewError(
            "invalid_review_notes",
            "review_notes must be a list",
        )
    review_notes = sorted({str(item).strip() for item in review_notes_raw if str(item).strip()})

    reasons: list[str] = []
    decision = "ELIGIBLE"

    if terms_disposition == "REVIEWED_RESTRICTED":
        decision = "REJECT"
        reasons.append("source terms are incompatible with the bounded pilot")
    elif transport_risk == "REJECTED":
        decision = "REJECT"
        reasons.append("transport residual risk was rejected")
    else:
        if terms_disposition == "NOT_REVIEWED":
            reasons.append("source terms have not been reviewed")
        if transport_risk == "UNRESOLVED":
            reasons.append("transport residual risk remains unresolved")
        if not rollback_compatible:
            reasons.append("source is not yet proven rollback-compatible")
        if not kill_switch_compatible:
            reasons.append("source is not yet proven kill-switch-compatible")
        if (
            provenance["upstream_concentration"] == "HIGH"
            and not provenance["concentration_mitigation"]
        ):
            reasons.append("high upstream concentration lacks a mitigation note")
        if reasons:
            decision = "HOLD"

    if not reasons:
        reasons.append("all observation-eligibility controls passed review")

    return {
        "terms_disposition": terms_disposition,
        "legal_terms_note": legal_terms_note,
        "transport_residual_risk": transport_risk,
        "rollback_compatible": rollback_compatible,
        "kill_switch_compatible": kill_switch_compatible,
        "review_notes": review_notes,
        "observation_eligibility": decision,
        "decision_reasons": reasons,
    }


def build_source_review_artifact(
    candidate: Mapping[str, Any],
    *,
    producer_commit: str,
    created_at: str,
) -> dict[str, Any]:
    _validate_commit(producer_commit)
    reviewer_id = _require_text(candidate.get("reviewer_id"), "reviewer_id")
    source_raw = candidate.get("source")
    provenance_raw = candidate.get("provenance")
    review_raw = candidate.get("review")
    if not isinstance(source_raw, Mapping):
        raise Gate1SourceReviewError("missing_source", "source must be an object")
    if not isinstance(provenance_raw, Mapping):
        raise Gate1SourceReviewError(
            "missing_provenance",
            "provenance must be an object",
        )
    if not isinstance(review_raw, Mapping):
        raise Gate1SourceReviewError("missing_review", "review must be an object")

    source = _validate_source(source_raw)
    provenance = _validate_provenance(provenance_raw)
    review = _build_review(review_raw, provenance)

    document: dict[str, Any] = {
        "artifact_type": ARTIFACT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "artifact_id": "",
        "created_at": normalize_created_at(created_at),
        "reviewer_id": reviewer_id,
        "source": source,
        "provenance": provenance,
        "review": review,
        "producer_repository": "ArchitectofAthena/CodexTradingEngine",
        "producer_commit": producer_commit,
        "gate_posture": {
            "gate_0": "ACTIVE",
            "gate_1": "PILOT_ONLY",
            "gate_2_through_6": "LOCKED",
        },
        "artifact_is_command": False,
        "authority": False,
        "human_promotion_required": True,
        "may_activate_gate_1": False,
        "may_generate_live_proposal": False,
        "may_execute": False,
        "may_move_capital": False,
    }
    document["artifact_id"] = compute_artifact_id(document)
    return document


def validate_source_review_artifact(document: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    if document.get("artifact_type") != ARTIFACT_TYPE:
        findings.append("artifact_type is not Gate1SourceReviewArtifact")
    if document.get("contract_version") != CONTRACT_VERSION:
        findings.append("contract_version is not eve_q_gate1_source_review_v0.1")
    if document.get("artifact_id") != compute_artifact_id(document):
        findings.append("artifact_id does not match canonical payload hash")
    if not HASH_RE.fullmatch(str(document.get("artifact_id", ""))):
        findings.append("artifact_id must be a lowercase SHA-256 hex digest")
    try:
        _validate_commit(str(document.get("producer_commit", "")))
    except Gate1SourceReviewError as exc:
        findings.append(exc.message)
    try:
        normalize_created_at(str(document.get("created_at", "")))
    except Gate1SourceReviewError as exc:
        findings.append(exc.message)

    for field, expected in {
        "artifact_is_command": False,
        "authority": False,
        "human_promotion_required": True,
        "may_activate_gate_1": False,
        "may_generate_live_proposal": False,
        "may_execute": False,
        "may_move_capital": False,
    }.items():
        if document.get(field) is not expected:
            findings.append(f"{field} must be {str(expected).lower()}")

    gate_posture = document.get("gate_posture")
    if gate_posture != {
        "gate_0": "ACTIVE",
        "gate_1": "PILOT_ONLY",
        "gate_2_through_6": "LOCKED",
    }:
        findings.append("gate_posture must preserve Gate 0 active, Gate 1 pilot-only, and Gate 2-6 locked")

    try:
        source = _validate_source(document.get("source", {}))
        provenance = _validate_provenance(document.get("provenance", {}))
        declared_review = document.get("review", {})
        rebuilt_review = _build_review(declared_review, provenance)
        if declared_review.get("observation_eligibility") != rebuilt_review["observation_eligibility"]:
            findings.append("observation_eligibility does not match review controls")
        if declared_review.get("decision_reasons") != rebuilt_review["decision_reasons"]:
            findings.append("decision_reasons do not match review controls")
        if source["method"] not in ALLOWED_METHODS:
            findings.append("source method is not observation-only")
    except Gate1SourceReviewError as exc:
        findings.append(exc.message)

    return sorted(set(findings))


def write_artifact(document: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build or verify a bounded Gate 1 source-review artifact."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--candidate", type=Path, required=True)
    build_parser.add_argument("--producer-commit", required=True)
    build_parser.add_argument("--created-at", required=True)
    build_parser.add_argument("--output", type=Path, required=True)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--artifact", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "build":
        artifact = build_source_review_artifact(
            _load_json(args.candidate),
            producer_commit=args.producer_commit,
            created_at=args.created_at,
        )
        write_artifact(artifact, args.output)
        print(json.dumps(artifact, indent=2, sort_keys=True))
        return 0

    artifact = _load_json(args.artifact)
    findings = validate_source_review_artifact(artifact)
    print(json.dumps({"valid": not findings, "findings": findings}, indent=2, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
