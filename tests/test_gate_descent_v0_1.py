from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from eve_q.gate_descent import (
    READY_CHECKS,
    build_gate_0_to_1_draft,
    refresh_artifact_id,
    validate_gate_descent,
)

SCHEMA_PATH = Path("schemas/gate_descent_proposal_v0_1.schema.json")
EXAMPLE_PATH = Path(
    "examples/governance/gate_descent_g0_to_g1_draft_v0_1.json"
)
NOW = datetime(2026, 7, 11, 21, 5, tzinfo=timezone.utc)


def load_example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def schema_findings(document: dict) -> list:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return list(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(document)
    )


def test_draft_example_is_schema_and_semantically_valid():
    document = load_example()

    assert schema_findings(document) == []
    assert validate_gate_descent(document, now=NOW) == []
    assert document["readiness"] == "DRAFT"
    assert document["promotion_eligible"] is False
    assert document["gate_states"][0]["status"] == "ACTIVE"
    assert document["gate_states"][1]["status"] == "REQUESTED"
    assert all(
        gate["status"] == "LOCKED"
        for gate in document["gate_states"][2:]
    )


def test_builder_produces_non_authoritative_adjacent_draft():
    document = build_gate_0_to_1_draft(
        created_at="2026-07-11T21:00:00Z",
        expires_at="2026-07-12T21:00:00Z",
    )

    assert validate_gate_descent(document, now=NOW) == []
    assert document["artifact_is_command"] is False
    assert document["authority"] is False
    assert document["may_execute"] is False
    assert document["may_move_capital"] is False
    assert document["human_promotion_required"] is True


def test_skipped_gate_fails_closed():
    document = load_example()
    document["transition"]["requested_gate"] = 2
    document["gate_states"][1]["status"] = "LOCKED"
    document["gate_states"][2]["status"] = "REQUESTED"
    document = refresh_artifact_id(document)

    findings = validate_gate_descent(document, now=NOW)

    assert any("Gate 0 -> Gate 1" in finding for finding in findings)
    assert any("gate_states[1].status" in finding for finding in findings)


def test_downstream_gate_cannot_open_early():
    document = load_example()
    document["gate_states"][2]["status"] = "ACTIVE"
    document = refresh_artifact_id(document)

    findings = validate_gate_descent(document, now=NOW)

    assert any(
        "gate_states[2].status must equal LOCKED" in finding
        for finding in findings
    )


def test_stale_ttl_fails_closed():
    document = load_example()
    document["created_at"] = "2026-07-09T21:00:00Z"
    document["expires_at"] = "2026-07-10T21:00:00Z"
    document = refresh_artifact_id(document)

    findings = validate_gate_descent(document, now=NOW)

    assert "gate descent proposal TTL is stale" in findings


def test_ready_state_requires_every_check_evidence_and_rollback():
    document = load_example()
    document["readiness"] = "READY_FOR_HUMAN_REVIEW"
    document["promotion_eligible"] = True
    document = refresh_artifact_id(document)

    findings = validate_gate_descent(document, now=NOW)

    assert any("incomplete acceptance checks" in finding for finding in findings)
    assert any("missing evidence types" in finding for finding in findings)
    assert "ready proposal requires a tested rollback" in findings


def test_fully_evidenced_ready_state_is_valid_but_still_non_executing():
    document = load_example()
    document["readiness"] = "READY_FOR_HUMAN_REVIEW"
    document["promotion_eligible"] = True
    document["acceptance_checks"] = {
        check: True for check in sorted(READY_CHECKS)
    }
    document["evidence"].extend(
        [
            {
                "evidence_type": "live_read_only_soak",
                "sha256": "1" * 64,
                "uri": "artifact://gate-1/live-read-only-soak",
            },
            {
                "evidence_type": "rollback_test",
                "sha256": "2" * 64,
                "uri": "artifact://gate-1/rollback-test",
            },
            {
                "evidence_type": "threat_model",
                "sha256": "3" * 64,
                "uri": "artifact://gate-1/threat-model",
            },
        ]
    )
    document["rollback"] = {
        "target_gate": 0,
        "tested": True,
        "plan_sha256": "4" * 64,
        "test_receipt_sha256": "5" * 64,
    }
    document = refresh_artifact_id(document)

    assert schema_findings(document) == []
    assert validate_gate_descent(document, now=NOW) == []
    assert document["authority"] is False
    assert document["may_execute"] is False
    assert document["may_move_capital"] is False


def test_authority_leakage_fails_schema_and_semantics():
    document = load_example()
    document["authority"] = True
    document["may_execute"] = True
    document = refresh_artifact_id(document)

    assert schema_findings(document)
    findings = validate_gate_descent(document, now=NOW)
    assert "authority must be false" in findings
    assert "may_execute must be false" in findings


def test_canonical_artifact_id_detects_mutation():
    document = load_example()
    mutated = copy.deepcopy(document)
    mutated["connector_mode"] = "write_capable"

    findings = validate_gate_descent(mutated, now=NOW)

    assert "artifact_id does not match canonical payload hash" in findings
    assert "connector_mode must be read_only" in findings
