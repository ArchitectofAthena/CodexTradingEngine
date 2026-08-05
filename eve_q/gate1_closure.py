"""Deterministic Gate 1 closure packet verification.

The closure packet consolidates evidence for human review. It does not promote a
gate, create a proposal command, sign, transact, execute, use flash liquidity,
transfer charity funds, or move capital.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from eve_q.gate_descent import validate_gate_descent

CONTRACT_VERSION = "codex-gate1-closure-v0.1"
ARTIFACT_TYPE = "Gate1ClosureThreatModel"

REQUIRED_THREAT_CLASSES = frozenset(
    {
        "source_outage",
        "dns_ip_drift",
        "redirect_host_escape",
        "payload_tamper",
        "stale_evidence",
        "malformed_oversized_payload",
        "write_secret_leakage",
        "authority_leakage",
        "material_conflict",
        "provenance_concentration",
        "unit_ambiguity",
        "source_review_expiry",
        "single_provider_dependency",
    }
)

REQUIRED_EVIDENCE_CLASSES = frozenset(
    {
        "baseline_soak",
        "source_review",
        "live_read_only_soak",
        "rollback_test",
        "epistemic_diversity",
        "contract_lineage",
    }
)

EXPECTED_COUNTS = {
    "live_proposals_generated": 0,
    "signatures_created": 0,
    "transactions_submitted": 0,
    "executions_performed": 0,
    "charity_transfers": 0,
    "capital_movements": 0,
}

EXPECTED_GATE_POSTURE = {
    "gate_0": "ACTIVE",
    "gate_1a": "ACTIVE_FOR_APPROVED_ALPHA_RUNS",
    "gate_1b": "LOCKED",
    "gate_2": "LOCKED",
    "gate_3": "LOCKED",
    "gate_4_through_6": "LOCKED",
}

EXPECTED_AUTHORITY = {
    "artifact_is_command": False,
    "authority": False,
    "human_promotion_required": True,
    "may_generate_live_proposal": False,
    "may_sign": False,
    "may_submit_transaction": False,
    "may_execute": False,
    "may_use_flash_liquidity": False,
    "may_transfer_charity": False,
    "may_move_capital": False,
}

HUMAN_DECISION_KEYS = frozenset(
    {
        "human_decision",
        "approved_by",
        "approved_at",
        "promotion_decision",
        "promotion_receipt",
    }
)


class Gate1ClosureError(RuntimeError):
    """Raised when a closure artifact cannot be loaded or verified."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def receipt_material(document: Mapping[str, Any]) -> dict[str, Any]:
    material = copy.deepcopy(dict(document))
    material.pop("receipt_sha256", None)
    return material


def compute_receipt_sha256(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(receipt_material(document))).hexdigest()


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise Gate1ClosureError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Gate1ClosureError(f"unable to load JSON {path}: {type(exc).__name__}: {exc}") from exc


def schema_findings(
    document: Any,
    schema: Mapping[str, Any],
    *,
    label: str,
) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(document),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    return [
        f"{label} schema {'.'.join(str(part) for part in error.absolute_path) or '<root>'}: "
        f"{error.message}"
        for error in errors
    ]


def validate_threat_model(
    document: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> list[str]:
    findings = schema_findings(document, schema, label="threat model")

    if document.get("artifact_type") != ARTIFACT_TYPE:
        findings.append(f"artifact_type must be {ARTIFACT_TYPE}")
    if document.get("contract_version") != CONTRACT_VERSION:
        findings.append(f"contract_version must be {CONTRACT_VERSION}")
    if document.get("receipt_sha256") != compute_receipt_sha256(document):
        findings.append("threat-model receipt_sha256 does not match canonical payload")

    threats = document.get("threats", [])
    threat_classes = {
        str(item.get("class"))
        for item in threats
        if isinstance(item, Mapping) and item.get("class")
    }
    missing_threats = sorted(REQUIRED_THREAT_CLASSES - threat_classes)
    if missing_threats:
        findings.append("threat model missing classes: " + ", ".join(missing_threats))

    evidence = document.get("evidence_lineage", [])
    evidence_classes = {
        str(item.get("class"))
        for item in evidence
        if isinstance(item, Mapping) and item.get("class")
    }
    missing_evidence = sorted(REQUIRED_EVIDENCE_CLASSES - evidence_classes)
    if missing_evidence:
        findings.append("threat model missing evidence classes: " + ", ".join(missing_evidence))

    if document.get("counts") != EXPECTED_COUNTS:
        findings.append("closure counts must remain exactly zero")
    if document.get("gate_posture") != EXPECTED_GATE_POSTURE:
        findings.append("closure gate posture does not preserve Gate 1A-only scope")
    if document.get("authority") != EXPECTED_AUTHORITY:
        findings.append("closure authority boundary is not exact")

    rollback = document.get("rollback", {})
    if not isinstance(rollback, Mapping):
        findings.append("rollback must be an object")
    else:
        if rollback.get("tested") is not True:
            findings.append("closure requires a tested rollback")
        if rollback.get("target_gate") != "SIMULATION_ONLY":
            findings.append("rollback target must be SIMULATION_ONLY")
        triggers = set(map(str, rollback.get("triggers", [])))
        expected_triggers = {
            "kill_switch",
            "source_outage",
            "dns_policy_failure",
            "operator_abort",
        }
        if triggers != expected_triggers:
            findings.append("rollback triggers must cover the complete supported set")

    residual = document.get("residual_risks", [])
    if not isinstance(residual, list) or not residual:
        findings.append("at least one residual risk must remain explicit")
    elif not any(
        isinstance(item, Mapping) and item.get("status") == "BLOCKS_GATE1B" for item in residual
    ):
        findings.append("at least one residual risk must explicitly block Gate 1B")

    scope = document.get("scope", {})
    if not isinstance(scope, Mapping):
        findings.append("scope must be an object")
    else:
        if scope.get("active_lane") != "TESTNET_READ_ONLY_ALPHA":
            findings.append("closure scope must remain TESTNET_READ_ONLY_ALPHA")
        if scope.get("mainnet_allowed") is not False:
            findings.append("mainnet_allowed must remain false")

    return sorted(set(findings))


def validate_ready_proposal(
    document: Mapping[str, Any],
    schema: Mapping[str, Any],
    *,
    threat_model: Mapping[str, Any],
    now: datetime,
) -> list[str]:
    findings = schema_findings(document, schema, label="gate descent proposal")
    findings.extend(validate_gate_descent(dict(document), now=now))

    if document.get("readiness") != "READY_FOR_HUMAN_REVIEW":
        findings.append("proposal readiness must be READY_FOR_HUMAN_REVIEW")
    if document.get("promotion_eligible") is not True:
        findings.append("ready proposal must be promotion_eligible")
    for key in sorted(HUMAN_DECISION_KEYS):
        if key in document:
            findings.append(f"human decision field must remain unset: {key}")

    threat_hash = str(threat_model.get("receipt_sha256", ""))
    evidence = document.get("evidence", [])
    matching_threats = [
        item
        for item in evidence
        if isinstance(item, Mapping)
        and item.get("evidence_type") == "threat_model"
        and item.get("sha256") == threat_hash
    ]
    if len(matching_threats) != 1:
        findings.append("proposal must reference exactly one matching threat-model receipt")

    rollback = document.get("rollback", {})
    threat_rollback = threat_model.get("rollback", {})
    if isinstance(rollback, Mapping) and isinstance(threat_rollback, Mapping):
        if rollback.get("test_receipt_sha256") != threat_rollback.get("test_receipt_sha256"):
            findings.append("proposal rollback receipt does not match threat model")
        if rollback.get("plan_sha256") != threat_rollback.get("plan_sha256"):
            findings.append("proposal rollback plan does not match threat model")

    return sorted(set(findings))


def verify_bundle(
    *,
    threat_model: Mapping[str, Any],
    threat_schema: Mapping[str, Any],
    proposal: Mapping[str, Any],
    proposal_schema: Mapping[str, Any],
    now: datetime,
) -> list[str]:
    findings = validate_threat_model(threat_model, threat_schema)
    findings.extend(
        validate_ready_proposal(
            proposal,
            proposal_schema,
            threat_model=threat_model,
            now=now,
        )
    )
    return sorted(set(findings))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="codex-gate1-closure",
        description=(
            "Verify the content-addressed Gate 1A closure packet without promoting a gate."
        ),
    )
    result.add_argument("--threat-model", type=Path, required=True)
    result.add_argument("--threat-schema", type=Path, required=True)
    result.add_argument("--proposal", type=Path, required=True)
    result.add_argument("--proposal-schema", type=Path, required=True)
    result.add_argument("--now", required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        threat_model = load_json(args.threat_model)
        threat_schema = load_json(args.threat_schema)
        proposal = load_json(args.proposal)
        proposal_schema = load_json(args.proposal_schema)
        now = parse_utc(args.now)
        findings = verify_bundle(
            threat_model=threat_model,
            threat_schema=threat_schema,
            proposal=proposal,
            proposal_schema=proposal_schema,
            now=now,
        )
    except (Gate1ClosureError, KeyError, TypeError, ValueError) as exc:
        print(f"HOLD: {exc}")
        return 2

    if findings:
        for finding in findings:
            print(f"HOLD: {finding}")
        return 1

    print("Gate 1 closure packet: PASS")
    print("readiness: READY_FOR_HUMAN_REVIEW")
    print("authority: false")
    print("automatic promotion: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
