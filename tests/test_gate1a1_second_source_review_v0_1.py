from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

import pytest

from eve_q.gate1a1_second_source_review import (
    BOUNDARY,
    SecondSourceReviewError,
    evaluate_candidate,
    publicnode_request_body,
    sha256_hex,
    utc_now,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas" / "gate1a1_second_source_candidate_v0_1.schema.json").read_text(
        encoding="utf-8"
    )
)
CANDIDATE = json.loads(
    (ROOT / "registry" / "gate1a1_second_source_candidates_v0_1.json").read_text(encoding="utf-8")
)
EVALUATED_AT = CANDIDATE["generated_at"]


def review(candidate: dict, *, evaluated_at: str = EVALUATED_AT) -> dict:
    return evaluate_candidate(candidate, schema=SCHEMA, evaluated_at=evaluated_at)


def test_utc_now_emits_parseable_zulu_timestamp() -> None:
    value = utc_now()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    offset = parsed.utcoffset()

    assert value.endswith("Z")
    assert parsed.microsecond == 0
    assert offset is not None
    assert offset.total_seconds() == 0


def test_exact_publicnode_request_body_is_content_addressed() -> None:
    assert publicnode_request_body() == {
        "jsonrpc": "2.0",
        "method": "eth_blockNumber",
        "params": [],
        "id": 1,
    }
    assert sha256_hex(publicnode_request_body()) == CANDIDATE["candidate"]["request_body_sha256"]


def test_seed_candidate_holds_for_terms_review() -> None:
    result = review(CANDIDATE)

    assert result["decision"]["code"] == "HOLD_TERMS_REVIEW"
    assert result["decision"]["eligible"] is False
    assert result["decision"]["capture_authorized"] is False
    assert result["boundary"] == BOUNDARY
    assert result["receipt_sha256"] != "0" * 64


def reviewed_candidate() -> dict:
    candidate = copy.deepcopy(CANDIDATE)
    candidate["candidate"]["terms_review"] = "REVIEWED"
    candidate["candidate"]["review_expires_at"] = "2026-09-05T00:00:00Z"
    candidate["evidence"]["source_review_receipt_sha256"] = "1" * 64
    return candidate


def test_reviewed_terms_without_capture_holds() -> None:
    result = review(reviewed_candidate())

    assert result["decision"]["code"] == "HOLD_CAPTURE_EVIDENCE"


def test_reviewed_terms_without_immutable_receipt_hold() -> None:
    candidate = copy.deepcopy(CANDIDATE)
    candidate["candidate"]["terms_review"] = "REVIEWED"
    candidate["candidate"]["live_capture_status"] = "PASS"
    candidate["candidate"]["review_expires_at"] = "2026-09-05T00:00:00Z"
    candidate["evidence"]["capture_receipt_sha256"] = "2" * 64

    result = review(candidate)

    assert result["decision"]["code"] == "HOLD_TERMS_REVIEW"
    assert "immutable source-review receipt" in result["decision"]["reasons"][0]


def test_reviewed_terms_without_expiry_hold() -> None:
    candidate = copy.deepcopy(CANDIDATE)
    candidate["candidate"]["terms_review"] = "REVIEWED"
    candidate["candidate"]["live_capture_status"] = "PASS"
    candidate["evidence"]["source_review_receipt_sha256"] = "3" * 64
    candidate["evidence"]["capture_receipt_sha256"] = "4" * 64

    result = review(candidate)

    assert result["decision"]["code"] == "HOLD_TERMS_REVIEW"
    assert "missing a review expiry" in result["decision"]["reasons"][0]


def test_expired_review_holds_before_capture_evidence() -> None:
    candidate = copy.deepcopy(CANDIDATE)
    candidate["candidate"]["terms_review"] = "REVIEWED"
    candidate["candidate"]["live_capture_status"] = "PASS"
    candidate["candidate"]["review_expires_at"] = EVALUATED_AT
    candidate["evidence"]["source_review_receipt_sha256"] = "5" * 64
    candidate["evidence"]["capture_receipt_sha256"] = "6" * 64

    result = review(candidate)

    assert result["decision"]["code"] == "HOLD_TERMS_REVIEW"
    assert "expired" in result["decision"]["reasons"][0]


def test_review_that_expires_after_creation_cannot_be_replayed_as_fresh() -> None:
    candidate = reviewed_candidate()
    candidate["candidate"]["live_capture_status"] = "PASS"
    candidate["evidence"]["capture_receipt_sha256"] = "7" * 64

    result = review(candidate, evaluated_at="2026-10-01T00:00:00Z")

    assert result["decision"]["code"] == "HOLD_TERMS_REVIEW"
    assert "expired" in result["decision"]["reasons"][0]


def test_complete_evidence_routes_to_human_eligibility_review() -> None:
    candidate = reviewed_candidate()
    candidate["candidate"]["live_capture_status"] = "PASS"
    candidate["evidence"]["capture_receipt_sha256"] = "8" * 64

    result = review(candidate)

    assert result["decision"]["code"] == "READY_FOR_ELIGIBILITY_REVIEW"
    assert result["generated_at"] == EVALUATED_AT
    assert result["decision"]["eligible"] is False
    assert result["decision"]["capture_authorized"] is False
    assert result["boundary"]["automatic_promotion"] is False


def test_evaluation_cannot_predate_candidate_generation() -> None:
    with pytest.raises(SecondSourceReviewError, match="precedes candidate generation"):
        review(copy.deepcopy(CANDIDATE), evaluated_at="2026-08-06T16:17:59Z")


def test_shared_or_unknown_lineage_forces_concentration_hold() -> None:
    candidate = reviewed_candidate()
    candidate["candidate"]["relationship_to_primary"] = "SHARED_OR_UNKNOWN"
    candidate["candidate"]["live_capture_status"] = "PASS"
    candidate["evidence"]["capture_receipt_sha256"] = "9" * 64

    result = review(candidate)

    assert result["decision"]["code"] == "HOLD_CONCENTRATION"


def test_request_hash_tamper_fails_closed() -> None:
    candidate = copy.deepcopy(CANDIDATE)
    candidate["candidate"]["request_body_sha256"] = "f" * 64

    with pytest.raises(SecondSourceReviewError, match="request body hash"):
        review(candidate)


def test_authority_drift_fails_closed() -> None:
    candidate = copy.deepcopy(CANDIDATE)
    candidate["boundary"]["may_execute"] = True

    with pytest.raises(SecondSourceReviewError):
        review(candidate)


def test_receipt_is_deterministic_for_same_evaluation_time() -> None:
    first = review(CANDIDATE)
    second = review(copy.deepcopy(CANDIDATE))

    assert first["receipt_sha256"] == second["receipt_sha256"]


def test_receipt_changes_when_evaluation_time_changes() -> None:
    first = review(CANDIDATE)
    second = review(copy.deepcopy(CANDIDATE), evaluated_at="2026-08-06T16:19:00Z")

    assert first["receipt_sha256"] != second["receipt_sha256"]
