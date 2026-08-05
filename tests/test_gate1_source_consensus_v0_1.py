from __future__ import annotations

import copy
import json
from pathlib import Path

from eve_q.gate1_source_consensus import (
    AUTHORITY_BOUNDARY,
    ZERO_COUNTS,
    evaluate_packet,
    verify_decision,
)

ROOT = Path(__file__).resolve().parents[1]
PACKET_SCHEMA = json.loads(
    (ROOT / "schemas" / "gate1_source_consensus_packet_v0_1.schema.json").read_text(
        encoding="utf-8"
    )
)
DECISION_SCHEMA = json.loads(
    (ROOT / "schemas" / "gate1_source_consensus_decision_v0_1.schema.json").read_text(
        encoding="utf-8"
    )
)
EVALUATED_AT = "2026-08-05T02:30:00Z"


def observation(
    source_id: str,
    *,
    value: str = "10",
    unit: str = "gwei",
    decimals: int | None = 9,
    comparison_unit: str = "gwei",
    conversion: dict | None = None,
    provenance_group: str | None = None,
    operator: str | None = None,
    observed_at: str = "2026-08-05T02:29:00Z",
    expires_at: str = "2026-08-05T02:31:00Z",
    review_status: str = "ELIGIBLE",
    review_expires_at: str | None = "2026-09-04T00:00:00Z",
) -> dict:
    return {
        "source_id": source_id,
        "registry_sha256": ("a" if source_id.endswith("a") else "b") * 64,
        "provenance_group": provenance_group or f"group-{source_id}",
        "operator": operator or f"operator-{source_id}",
        "value": value,
        "unit": unit,
        "decimals": decimals,
        "comparison_unit": comparison_unit,
        "conversion": conversion or {"kind": "identity"},
        "observed_at": observed_at,
        "expires_at": expires_at,
        "review_status": review_status,
        "review_expires_at": review_expires_at,
        "authority": False,
    }


def packet(*observations: dict, tolerance: str = "0.5") -> dict:
    return {
        "packet_type": "Gate1SourceConsensusPacket",
        "schema_version": "0.1",
        "evaluation_id": "gate1-source-consensus-test-v0-1",
        "evaluated_at": EVALUATED_AT,
        "comparison_unit": "gwei",
        "absolute_tolerance": tolerance,
        "observations": list(observations),
        "unresolved_questions": [
            "Does this offline evidence justify any additional source review?"
        ],
        "authority": False,
    }


def evaluate(document: dict) -> dict:
    return evaluate_packet(
        document,
        packet_schema=PACKET_SCHEMA,
        decision_schema=DECISION_SCHEMA,
    )


def assert_locked(decision: dict) -> None:
    assert decision["authority"] == AUTHORITY_BOUNDARY
    assert decision["counts"] == ZERO_COUNTS
    assert decision["comparison"]["aggregate_value"] is None
    assert decision["comparison"]["aggregation_performed"] is False
    assert verify_decision(decision, DECISION_SCHEMA) == ()


def test_material_conflict_is_preserved_without_averaging() -> None:
    decision = evaluate(
        packet(
            observation("source-a", value="10"),
            observation("source-b", value="12"),
            tolerance="0.5",
        )
    )

    assert decision["decision"]["code"] == "HOLD_CONFLICT"
    assert decision["comparison"]["conflict_magnitude"] == "2"
    assert decision["comparison"]["observed_min"] == "10"
    assert decision["comparison"]["observed_max"] == "12"
    assert decision["decision"]["observation_only"] is False
    assert any("not averaged" in reason for reason in decision["decision"]["reasons"])
    assert_locked(decision)


def test_shared_provenance_agreement_is_concentration_hold() -> None:
    decision = evaluate(
        packet(
            observation(
                "source-a",
                value="10",
                provenance_group="same-provider-backend",
                operator="provider-a",
            ),
            observation(
                "source-b",
                value="10.1",
                provenance_group="same-provider-backend",
                operator="provider-a-mirror",
            ),
        )
    )

    assert decision["decision"]["code"] == "HOLD_CONCENTRATION"
    assert decision["comparison"]["independent_provenance"] is False
    assert decision["comparison"]["provenance_group_count"] == 1
    assert any("shared provenance" in reason for reason in decision["decision"]["reasons"])
    assert_locked(decision)


def test_stale_source_cannot_borrow_freshness() -> None:
    decision = evaluate(
        packet(
            observation("source-a", expires_at="2026-08-05T02:29:59Z"),
            observation("source-b", expires_at="2026-08-05T02:31:00Z"),
        )
    )

    assert decision["decision"]["code"] == "HOLD_STALE"
    assert "source-a" in decision["decision"]["reasons"][0]
    assert_locked(decision)


def test_unknown_decimals_or_units_block_comparison() -> None:
    unknown_decimals = evaluate(
        packet(
            observation("source-a", decimals=None),
            observation("source-b"),
        )
    )
    assert unknown_decimals["decision"]["code"] == "HOLD_UNIT_AMBIGUITY"
    assert any("unknown decimal" in reason for reason in unknown_decimals["decision"]["reasons"])
    assert_locked(unknown_decimals)

    wrong_identity = evaluate(
        packet(
            observation(
                "source-a",
                unit="wei",
                comparison_unit="gwei",
                conversion={"kind": "identity"},
            ),
            observation("source-b"),
        )
    )
    assert wrong_identity["decision"]["code"] == "HOLD_UNIT_AMBIGUITY"
    assert any("cannot change units" in reason for reason in wrong_identity["decision"]["reasons"])
    assert_locked(wrong_identity)


def test_missing_or_noneligible_review_blocks_admission() -> None:
    missing = evaluate(
        packet(
            observation(
                "source-a",
                review_status="MISSING",
                review_expires_at=None,
            ),
            observation("source-b"),
        )
    )
    assert missing["decision"]["code"] == "HOLD_SOURCE_REVIEW"
    assert_locked(missing)

    held = evaluate(
        packet(
            observation("source-a", review_status="HOLD"),
            observation("source-b"),
        )
    )
    assert held["decision"]["code"] == "HOLD_SOURCE_REVIEW"
    assert_locked(held)


def test_expired_review_blocks_admission() -> None:
    decision = evaluate(
        packet(
            observation(
                "source-a",
                review_expires_at="2026-08-05T02:30:00Z",
            ),
            observation("source-b"),
        )
    )

    assert decision["decision"]["code"] == "HOLD_REVIEW_EXPIRED"
    assert "source-a" in decision["decision"]["reasons"][0]
    assert_locked(decision)


def test_independent_reviewed_unit_compatible_agreement_is_observation_only() -> None:
    decision = evaluate(
        packet(
            observation("source-a", value="10", unit="gwei"),
            observation(
                "source-b",
                value="10000000000",
                unit="wei",
                comparison_unit="gwei",
                conversion={
                    "kind": "decimal_scale",
                    "factor": "0.000000001",
                },
            ),
            tolerance="0",
        )
    )

    assert decision["decision"]["code"] == "ACCEPT_OBSERVATION_ONLY"
    assert decision["decision"]["observation_only"] is True
    assert decision["comparison"]["independent_provenance"] is True
    assert decision["comparison"]["conflict_magnitude"] == "0"
    assert [item["normalized_value"] for item in decision["observations"]] == [
        "10",
        "10",
    ]
    assert_locked(decision)


def test_source_order_does_not_change_decision_or_receipt() -> None:
    first_packet = packet(
        observation("source-a", value="10"),
        observation("source-b", value="10.1"),
    )
    second_packet = copy.deepcopy(first_packet)
    second_packet["observations"].reverse()

    first = evaluate(first_packet)
    second = evaluate(second_packet)

    assert first["decision"] == second["decision"]
    assert first["observations"] == second["observations"]
    assert first["receipt_sha256"] == second["receipt_sha256"]


def test_identical_inputs_reproduce_exact_receipt() -> None:
    document = packet(
        observation("source-a", value="10"),
        observation("source-b", value="10.2"),
    )

    first = evaluate(document)
    second = evaluate(copy.deepcopy(document))

    assert first == second
    assert len(first["receipt_sha256"]) == 64
