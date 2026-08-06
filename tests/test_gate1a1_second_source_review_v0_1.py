from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from eve_q.gate1a1_second_source_review import (
    BOUNDARY,
    SecondSourceReviewError,
    evaluate_candidate,
    publicnode_request_body,
    sha256_hex,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas" / "gate1a1_second_source_candidate_v0_1.schema.json").read_text(
        encoding="utf-8"
    )
)
CANDIDATE = json.loads(
    (ROOT / "registry" / "gate1a1_second_source_candidates_v0_1.json").read_text(
        encoding="utf-8"
    )
)


def test_exact_publicnode_request_body_is_content_addressed() -> None:
    assert publicnode_request_body() == {
        "jsonrpc": "2.0",
        "method": "eth_blockNumber",
        "params": [],
        "id": 1,
    }
    assert sha256_hex(publicnode_request_body()) == CANDIDATE["candidate"][
        "request_body_sha256"
    ]


def test_seed_candidate_holds_for_terms_review() -> None:
    result = evaluate_candidate(CANDIDATE, schema=SCHEMA)

    assert result["decision"]["code"] == "HOLD_TERMS_REVIEW"
    assert result["decision"]["eligible"] is False
    assert result["decision"]["capture_authorized"] is False
    assert result["boundary"] == BOUNDARY
    assert result["receipt_sha256"] != "0" * 64


def test_reviewed_terms_without_capture_holds() -> None:
    candidate = copy.deepcopy(CANDIDATE)
    candidate["candidate"]["terms_review"] = "REVIEWED"
    candidate["candidate"]["review_expires_at"] = "2026-09-05T00:00:00Z"

    result = evaluate_candidate(candidate, schema=SCHEMA)

    assert result["decision"]["code"] == "HOLD_CAPTURE_EVIDENCE"


def test_complete_evidence_routes_to_human_eligibility_review() -> None:
    candidate = copy.deepcopy(CANDIDATE)
    candidate["candidate"]["terms_review"] = "REVIEWED"
    candidate["candidate"]["live_capture_status"] = "PASS"
    candidate["candidate"]["review_expires_at"] = "2026-09-05T00:00:00Z"
    candidate["evidence"]["capture_receipt_sha256"] = "a" * 64

    result = evaluate_candidate(candidate, schema=SCHEMA)

    assert result["decision"]["code"] == "READY_FOR_ELIGIBILITY_REVIEW"
    assert result["decision"]["eligible"] is False
    assert result["decision"]["capture_authorized"] is False
    assert result["boundary"]["automatic_promotion"] is False


def test_shared_or_unknown_lineage_forces_concentration_hold() -> None:
    candidate = copy.deepcopy(CANDIDATE)
    candidate["candidate"]["relationship_to_primary"] = "SHARED_OR_UNKNOWN"
    candidate["candidate"]["terms_review"] = "REVIEWED"
    candidate["candidate"]["live_capture_status"] = "PASS"
    candidate["candidate"]["review_expires_at"] = "2026-09-05T00:00:00Z"
    candidate["evidence"]["capture_receipt_sha256"] = "b" * 64

    result = evaluate_candidate(candidate, schema=SCHEMA)

    assert result["decision"]["code"] == "HOLD_CONCENTRATION"


def test_request_hash_tamper_fails_closed() -> None:
    candidate = copy.deepcopy(CANDIDATE)
    candidate["candidate"]["request_body_sha256"] = "f" * 64

    with pytest.raises(SecondSourceReviewError, match="request body hash"):
        evaluate_candidate(candidate, schema=SCHEMA)


def test_authority_drift_fails_closed() -> None:
    candidate = copy.deepcopy(CANDIDATE)
    candidate["boundary"]["may_execute"] = True

    with pytest.raises(SecondSourceReviewError):
        evaluate_candidate(candidate, schema=SCHEMA)


def test_receipt_is_deterministic() -> None:
    first = evaluate_candidate(CANDIDATE, schema=SCHEMA)
    second = evaluate_candidate(copy.deepcopy(CANDIDATE), schema=SCHEMA)

    assert first["receipt_sha256"] == second["receipt_sha256"]
