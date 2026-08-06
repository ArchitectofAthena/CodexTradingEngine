"""Deterministic Gate 1A.1 second-source candidate review.

This module reviews inert source metadata only. It performs no network request,
creates no proposal, and grants no wallet, signing, transaction, execution, or
capital authority.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ARTIFACT_TYPE = "Gate1A1SecondSourceCandidate"
CONTRACT_VERSION = "codex-gate1a1-second-source-v0.1"
DECISIONS = frozenset(
    {
        "HOLD_TERMS_REVIEW",
        "HOLD_CAPTURE_EVIDENCE",
        "HOLD_CONCENTRATION",
        "READY_FOR_ELIGIBILITY_REVIEW",
    }
)
BOUNDARY = {
    "artifact_is_command": False,
    "authority": False,
    "network_capture_performed": False,
    "may_generate_live_proposal": False,
    "may_execute": False,
    "may_sign": False,
    "may_submit_transaction": False,
    "may_access_wallet": False,
    "may_move_capital": False,
    "automatic_promotion": False,
    "human_promotion_required": True,
}

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_SCHEMA = _ROOT / "schemas" / "gate1a1_second_source_candidate_v0_1.schema.json"
_DEFAULT_CANDIDATE = _ROOT / "registry" / "gate1a1_second_source_candidates_v0_1.json"


class SecondSourceReviewError(RuntimeError):
    """Raised when candidate metadata is malformed or widens authority."""


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


def publicnode_request_body() -> dict[str, Any]:
    """Return the only request body described by this candidate contract."""

    return {
        "jsonrpc": "2.0",
        "method": "eth_blockNumber",
        "params": [],
        "id": 1,
    }


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SecondSourceReviewError(
            f"unable to load JSON {path}: {type(exc).__name__}: {exc}"
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


def require_schema(document: Any, schema: Mapping[str, Any]) -> None:
    errors = _schema_errors(document, schema)
    if errors:
        raise SecondSourceReviewError(
            "second-source candidate schema validation failed: " + "; ".join(errors[:8])
        )


def _parse_review_time(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise SecondSourceReviewError(f"{field_name} is required")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SecondSourceReviewError(f"{field_name} is not a valid date-time") from exc
    if parsed.tzinfo is None:
        raise SecondSourceReviewError(f"{field_name} must include a UTC offset")
    return parsed


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _receipt_material(document: Mapping[str, Any]) -> dict[str, Any]:
    material = copy.deepcopy(dict(document))
    material.pop("receipt_sha256", None)
    return material


def evaluate_candidate(
    candidate: Mapping[str, Any],
    *,
    schema: Mapping[str, Any],
    evaluated_at: str,
) -> dict[str, Any]:
    """Evaluate one candidate at an explicit time without capture or promotion."""

    require_schema(candidate, schema)
    expected_request_hash = sha256_hex(publicnode_request_body())
    declared_request_hash = str(candidate["candidate"]["request_body_sha256"])
    if declared_request_hash != expected_request_hash:
        raise SecondSourceReviewError(
            "candidate request body hash does not match exact allowlisted RPC body"
        )
    if candidate["boundary"] != BOUNDARY:
        raise SecondSourceReviewError(
            "candidate attempts to widen the second-source authority boundary"
        )

    candidate_generated_at = _parse_review_time(candidate["generated_at"], "generated_at")
    evaluation_time = _parse_review_time(evaluated_at, "evaluated_at")
    if evaluation_time < candidate_generated_at:
        raise SecondSourceReviewError("evaluated_at precedes candidate generation")

    relationship = candidate["candidate"]["relationship_to_primary"]
    terms = candidate["candidate"]["terms_review"]
    source_review_receipt = candidate["evidence"]["source_review_receipt_sha256"]
    capture = candidate["candidate"]["live_capture_status"]
    capture_receipt = candidate["evidence"]["capture_receipt_sha256"]
    review_expires_at = candidate["candidate"]["review_expires_at"]

    if relationship != "DISTINCT_OPERATOR_CANDIDATE":
        code = "HOLD_CONCENTRATION"
        reasons = ["operator or upstream independence is shared, unknown, or unresolved"]
    elif terms != "REVIEWED":
        code = "HOLD_TERMS_REVIEW"
        reasons = ["terms and rate-limit review is not complete"]
    elif source_review_receipt is None:
        code = "HOLD_TERMS_REVIEW"
        reasons = ["reviewed source metadata lacks an immutable source-review receipt"]
    elif review_expires_at is None:
        code = "HOLD_TERMS_REVIEW"
        reasons = ["reviewed source metadata is missing a review expiry"]
    elif _parse_review_time(review_expires_at, "review_expires_at") <= evaluation_time:
        code = "HOLD_TERMS_REVIEW"
        reasons = ["source review is expired at the candidate evaluation time"]
    elif capture != "PASS" or capture_receipt is None:
        code = "HOLD_CAPTURE_EVIDENCE"
        reasons = [
            "no bounded live capture receipt proves endpoint and response-contract behavior"
        ]
    else:
        code = "READY_FOR_ELIGIBILITY_REVIEW"
        reasons = [
            "candidate metadata, immutable source review, fresh expiry, distinct-operator posture, and bounded capture evidence are complete",
            "human eligibility review remains required",
        ]

    if code not in DECISIONS:
        raise AssertionError(f"unexpected decision: {code}")

    result = copy.deepcopy(dict(candidate))
    result["generated_at"] = evaluated_at
    result["decision"] = {
        "code": code,
        "reasons": reasons,
        "eligible": False,
        "capture_authorized": False,
        "human_review_required": True,
    }
    result["receipt_sha256"] = sha256_hex(_receipt_material(result))
    require_schema(result, schema)
    return result


def render_summary(result: Mapping[str, Any]) -> str:
    candidate = result["candidate"]
    decision = result["decision"]
    return "\n".join(
        (
            "CODEX GATE 1A.1 SECOND-SOURCE REVIEW v0.1",
            f"EVALUATED_AT: {result['generated_at']}",
            f"SOURCE: {candidate['source_id']}",
            f"OPERATOR: {candidate['operator']}",
            f"RPC_METHOD: {candidate['rpc_method']}",
            f"TERMS: {candidate['terms_review']}",
            f"LIVE_CAPTURE: {candidate['live_capture_status']}",
            f"DECISION: {decision['code']}",
            "ELIGIBLE: false",
            "CAPTURE_AUTHORIZED: false",
            "AUTHORITY: false",
            f"RECEIPT: {result['receipt_sha256']}",
        )
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="codex-gate1a1-source-review",
        description=(
            "Review one inert Gate 1A.1 source candidate without network capture or authority."
        ),
    )
    result.add_argument("--candidate", type=Path, default=_DEFAULT_CANDIDATE)
    result.add_argument("--schema", type=Path, default=_DEFAULT_SCHEMA)
    result.add_argument(
        "--evaluated-at",
        help="Explicit evaluation time for deterministic replay; defaults to current UTC time.",
    )
    result.add_argument("--output", type=Path)
    result.add_argument("--json", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        candidate = _load_json(args.candidate)
        schema = _load_json(args.schema)
        reviewed = evaluate_candidate(
            candidate,
            schema=schema,
            evaluated_at=args.evaluated_at or utc_now(),
        )
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(reviewed, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except (SecondSourceReviewError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(reviewed, indent=2, sort_keys=True))
    else:
        print(render_summary(reviewed))
    return 0 if reviewed["decision"]["code"] == "READY_FOR_ELIGIBILITY_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
