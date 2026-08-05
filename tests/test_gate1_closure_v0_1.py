from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from eve_q.gate1_closure import (
    compute_receipt_sha256,
    validate_ready_proposal,
    validate_threat_model,
    verify_bundle,
)

THREAT_PATH = Path("examples/governance/gate1_closure_threat_model_v0_1.json")
THREAT_SCHEMA_PATH = Path("schemas/gate1_closure_threat_model_v0_1.schema.json")
PROPOSAL_PATH = Path("examples/governance/gate_descent_g0_to_g1_ready_v0_1.json")
PROPOSAL_SCHEMA_PATH = Path("schemas/gate_descent_proposal_v0_1.schema.json")
NOW = datetime(2026, 8, 5, 4, 30, tzinfo=UTC)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_closure_bundle_is_ready_for_human_review_and_non_authoritative():
    threat = load(THREAT_PATH)
    proposal = load(PROPOSAL_PATH)

    findings = verify_bundle(
        threat_model=threat,
        threat_schema=load(THREAT_SCHEMA_PATH),
        proposal=proposal,
        proposal_schema=load(PROPOSAL_SCHEMA_PATH),
        now=NOW,
    )

    assert findings == []
    assert proposal["readiness"] == "READY_FOR_HUMAN_REVIEW"
    assert proposal["authority"] is False
    assert proposal["may_execute"] is False
    assert proposal["may_move_capital"] is False
    assert threat["authority"]["may_generate_live_proposal"] is False
    assert threat["authority"]["may_sign"] is False
    assert threat["authority"]["may_submit_transaction"] is False
    assert threat["authority"]["may_use_flash_liquidity"] is False
    assert threat["authority"]["may_transfer_charity"] is False


def test_threat_model_receipt_detects_mutation():
    threat = load(THREAT_PATH)
    mutated = copy.deepcopy(threat)
    mutated["scope"]["mainnet_allowed"] = True

    findings = validate_threat_model(mutated, load(THREAT_SCHEMA_PATH))

    assert any("receipt_sha256" in finding for finding in findings)
    assert any("mainnet_allowed" in finding for finding in findings)


def test_missing_conflict_class_fails_closed():
    threat = load(THREAT_PATH)
    threat["threats"] = [
        item for item in threat["threats"] if item["class"] != "material_conflict"
    ]
    threat["receipt_sha256"] = compute_receipt_sha256(threat)

    findings = validate_threat_model(threat, load(THREAT_SCHEMA_PATH))

    assert any("material_conflict" in finding for finding in findings)


def test_gate1b_blocking_residual_risk_must_remain_visible():
    threat = load(THREAT_PATH)
    for risk in threat["residual_risks"]:
        risk["status"] = "ACCEPTED_FOR_GATE1A_ONLY"
    threat["receipt_sha256"] = compute_receipt_sha256(threat)

    findings = validate_threat_model(threat, load(THREAT_SCHEMA_PATH))

    assert "at least one residual risk must explicitly block Gate 1B" in findings


def test_human_decision_must_remain_unset():
    threat = load(THREAT_PATH)
    proposal = load(PROPOSAL_PATH)
    proposal["approved_by"] = "automatic-system"

    findings = validate_ready_proposal(
        proposal,
        load(PROPOSAL_SCHEMA_PATH),
        threat_model=threat,
        now=NOW,
    )

    assert any("human decision field must remain unset" in finding for finding in findings)


def test_proposal_threat_receipt_must_match():
    threat = load(THREAT_PATH)
    proposal = load(PROPOSAL_PATH)
    for evidence in proposal["evidence"]:
        if evidence["evidence_type"] == "threat_model":
            evidence["sha256"] = "0" * 64
    findings = validate_ready_proposal(
        proposal,
        load(PROPOSAL_SCHEMA_PATH),
        threat_model=threat,
        now=NOW,
    )

    assert "proposal must reference exactly one matching threat-model receipt" in findings


def test_proposal_authority_leakage_fails_closed():
    threat = load(THREAT_PATH)
    proposal = load(PROPOSAL_PATH)
    proposal["authority"] = True

    findings = validate_ready_proposal(
        proposal,
        load(PROPOSAL_SCHEMA_PATH),
        threat_model=threat,
        now=NOW,
    )

    assert any("authority" in finding for finding in findings)


def test_rollback_receipts_must_match_across_artifacts():
    threat = load(THREAT_PATH)
    proposal = load(PROPOSAL_PATH)
    proposal["rollback"]["test_receipt_sha256"] = "f" * 64

    findings = validate_ready_proposal(
        proposal,
        load(PROPOSAL_SCHEMA_PATH),
        threat_model=threat,
        now=NOW,
    )

    assert "proposal rollback receipt does not match threat model" in findings
