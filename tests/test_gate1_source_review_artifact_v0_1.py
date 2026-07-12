from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from eve_q.gate1_source_review import (
    Gate1SourceReviewError,
    build_source_review_artifact,
    refresh_artifact_id,
    validate_source_review_artifact,
)

SCHEMA_PATH = Path("schemas/gate1_source_review_artifact_v0_1.schema.json")
TEMPLATE_PATH = Path("examples/telemetry/source_review_candidate_template_v0_1.json")
PRODUCER_COMMIT = "a" * 40
CREATED_AT = "2026-07-12T01:00:00Z"


def candidate(**overrides):
    document = {
        "reviewer_id": "human:architect",
        "source": {
            "source_id": "reviewed-public-market-source",
            "source_name": "Reviewed Public Market Source",
            "operator": "Example Data Operator",
            "source_kind": "market_snapshot",
            "endpoint_uri": "https://data.example.test/v1/market",
            "allowed_hosts": ["data.example.test"],
            "method": "GET",
            "auth_mode": "NONE",
            "credential_reference_name": None,
            "credential_proof_note": None,
            "documented_rate_limit": {
                "requests": 30,
                "per_seconds": 60,
            },
            "expected_content_types": ["application/json"],
            "expected_max_response_bytes": 1_048_576,
            "freshness_ttl_seconds": 300,
            "outage_expectation": "Transient outages fail closed and return the pilot to Gate 0.",
            "redirect_policy": "EXACT_ALLOWLIST_ONLY",
        },
        "provenance": {
            "provenance_group": "example-independent-market-data",
            "upstream_provider": "Example Data Operator",
            "upstream_concentration": "LOW",
            "source_independence_note": "Operator documents a direct source rather than a shared aggregator.",
            "concentration_mitigation": "",
        },
        "review": {
            "terms_disposition": "REVIEWED_COMPATIBLE",
            "legal_terms_note": "Human reviewer recorded compatibility with bounded read-only research use.",
            "transport_residual_risk": "ACCEPTED_WITH_CONTROLS",
            "rollback_compatible": True,
            "kill_switch_compatible": True,
            "review_notes": ["No credential required."],
        },
    }
    for key, value in overrides.items():
        if key in {"source", "provenance", "review"}:
            document[key].update(value)
        else:
            document[key] = value
    return document


def schema_findings(document: dict) -> list:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return list(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(document)
    )


def build(document=None):
    return build_source_review_artifact(
        document or candidate(),
        producer_commit=PRODUCER_COMMIT,
        created_at=CREATED_AT,
    )


def test_eligible_public_source_is_deterministic_schema_valid_and_non_authoritative():
    first = build()
    second = build()

    assert first == second
    assert schema_findings(first) == []
    assert validate_source_review_artifact(first) == []
    assert first["review"]["observation_eligibility"] == "ELIGIBLE"
    assert first["source"]["method"] == "GET"
    assert first["artifact_is_command"] is False
    assert first["authority"] is False
    assert first["may_activate_gate_1"] is False
    assert first["may_generate_live_proposal"] is False
    assert first["may_execute"] is False
    assert first["may_move_capital"] is False


def test_template_is_deliberately_hold_and_not_a_committed_live_source():
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    artifact = build_source_review_artifact(
        template,
        producer_commit=PRODUCER_COMMIT,
        created_at=CREATED_AT,
    )

    assert schema_findings(artifact) == []
    assert validate_source_review_artifact(artifact) == []
    assert artifact["review"]["observation_eligibility"] == "HOLD"
    assert artifact["source"]["endpoint_uri"].endswith("example.test/v1/observation")
    assert artifact["may_activate_gate_1"] is False


def test_http_post_embedded_credentials_and_nonstandard_port_fail_closed():
    with pytest.raises(Gate1SourceReviewError) as exc_info:
        build(candidate(source={"endpoint_uri": "http://data.example.test/v1/market"}))
    assert exc_info.value.code == "scheme_not_https"

    with pytest.raises(Gate1SourceReviewError) as exc_info:
        build(candidate(source={"method": "POST"}))
    assert exc_info.value.code == "write_method_rejected"

    with pytest.raises(Gate1SourceReviewError) as exc_info:
        build(candidate(source={"endpoint_uri": "https://user:pass@data.example.test/v1/market"}))
    assert exc_info.value.code == "embedded_credentials_rejected"

    with pytest.raises(Gate1SourceReviewError) as exc_info:
        build(candidate(source={"endpoint_uri": "https://data.example.test:8443/v1/market"}))
    assert exc_info.value.code == "non_standard_port_rejected"


def test_host_must_be_exactly_allowlisted_without_wildcards():
    with pytest.raises(Gate1SourceReviewError) as exc_info:
        build(candidate(source={"allowed_hosts": ["other.example.test"]}))
    assert exc_info.value.code == "host_not_allowlisted"

    with pytest.raises(Gate1SourceReviewError) as exc_info:
        build(candidate(source={"allowed_hosts": ["*.example.test"]}))
    assert exc_info.value.code == "invalid_allowlist_host"


def test_read_only_credential_requires_explicit_safe_reference_and_proof():
    reviewed = candidate(
        source={
            "auth_mode": "READ_ONLY_CREDENTIAL",
            "credential_reference_name": "EXAMPLE_READ_ONLY_API_KEY",
            "credential_proof_note": "Provider account role is documented as read-only and cannot submit orders.",
        }
    )
    artifact = build(reviewed)
    assert artifact["review"]["observation_eligibility"] == "ELIGIBLE"

    with pytest.raises(Gate1SourceReviewError) as exc_info:
        build(
            candidate(
                source={
                    "auth_mode": "READ_ONLY_CREDENTIAL",
                    "credential_reference_name": "EXAMPLE_API_KEY",
                    "credential_proof_note": "No role proof.",
                }
            )
        )
    assert exc_info.value.code == "credential_not_demonstrably_read_only"

    with pytest.raises(Gate1SourceReviewError) as exc_info:
        build(
            candidate(
                source={
                    "auth_mode": "READ_ONLY_CREDENTIAL",
                    "credential_reference_name": "WALLET_READ_ONLY_KEY",
                    "credential_proof_note": "Unsafe wallet-shaped reference.",
                }
            )
        )
    assert exc_info.value.code == "write_capable_credential_reference_rejected"


def test_unresolved_controls_hold_and_incompatible_terms_or_transport_reject():
    hold = build(
        candidate(
            review={
                "terms_disposition": "NOT_REVIEWED",
                "transport_residual_risk": "UNRESOLVED",
                "rollback_compatible": False,
                "kill_switch_compatible": False,
            }
        )
    )
    assert hold["review"]["observation_eligibility"] == "HOLD"
    assert len(hold["review"]["decision_reasons"]) == 4

    rejected_terms = build(
        candidate(review={"terms_disposition": "REVIEWED_RESTRICTED"})
    )
    assert rejected_terms["review"]["observation_eligibility"] == "REJECT"

    rejected_transport = build(
        candidate(review={"transport_residual_risk": "REJECTED"})
    )
    assert rejected_transport["review"]["observation_eligibility"] == "REJECT"


def test_high_concentration_without_mitigation_holds():
    artifact = build(
        candidate(
            provenance={
                "upstream_concentration": "HIGH",
                "concentration_mitigation": "",
            }
        )
    )
    assert artifact["review"]["observation_eligibility"] == "HOLD"
    assert any("concentration" in item for item in artifact["review"]["decision_reasons"])


def test_hash_authority_and_decision_mutation_are_detected():
    artifact = build()
    mutated = copy.deepcopy(artifact)
    mutated["authority"] = True
    mutated["review"]["observation_eligibility"] = "REJECT"

    findings = validate_source_review_artifact(mutated)

    assert "artifact_id does not match canonical payload hash" in findings
    assert "authority must be false" in findings
    assert "observation_eligibility does not match review controls" in findings


def test_rehashing_cannot_hide_authority_escalation():
    artifact = build()
    artifact["may_generate_live_proposal"] = True
    artifact = refresh_artifact_id(artifact)

    findings = validate_source_review_artifact(artifact)

    assert "artifact_id does not match canonical payload hash" not in findings
    assert "may_generate_live_proposal must be false" in findings


def test_schema_rejects_unknown_properties_and_gate_promotion():
    artifact = build()
    artifact["unexpected"] = "nope"
    artifact["gate_posture"]["gate_1"] = "ACTIVE"

    findings = schema_findings(artifact)

    assert findings
    assert any("Additional properties" in finding.message for finding in findings)
    assert any("PILOT_ONLY" in finding.message for finding in findings)


def test_invalid_commit_and_timestamp_fail_closed():
    with pytest.raises(Gate1SourceReviewError) as exc_info:
        build_source_review_artifact(
            candidate(),
            producer_commit="not-a-commit",
            created_at=CREATED_AT,
        )
    assert exc_info.value.code == "invalid_producer_commit"

    with pytest.raises(Gate1SourceReviewError) as exc_info:
        build_source_review_artifact(
            candidate(),
            producer_commit=PRODUCER_COMMIT,
            created_at="2026-07-12T01:00:00",
        )
    assert exc_info.value.code == "invalid_created_at"
