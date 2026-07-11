from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "eve_q_gate_descent_v0.1"
ARTIFACT_TYPE = "GateDescentProposal"
MAX_TTL_SECONDS = 86_400

GATES: tuple[str, ...] = (
    "SIMULATION_ONLY",
    "LIVE_READ_ONLY_TELEMETRY",
    "LIVE_PROPOSAL_GENERATION",
    "TESTNET_MANUAL_EXTERNAL",
    "CAPPED_MANUAL_EXTERNAL",
    "EXECUTION_ASSISTANCE",
    "NARROW_AUTOMATION",
)

REQUIRED_PROHIBITED_ACTIONS = frozenset(
    {
        "wallet_access",
        "signing",
        "order_submission",
        "transaction_construction",
        "transaction_broadcast",
        "capital_movement",
        "self_promotion",
        "multi_gate_descent",
    }
)

READY_EVIDENCE_TYPES = frozenset(
    {
        "baseline_soak",
        "live_read_only_soak",
        "rollback_test",
        "threat_model",
    }
)

READY_CHECKS = frozenset(
    {
        "adjacent_gate_only",
        "all_downstream_gates_locked",
        "read_only_interfaces_only",
        "zero_write_capable_secrets",
        "live_inputs_content_addressed",
        "replayable_snapshots_retained",
        "stale_input_rejection_proven",
        "malformed_input_rejection_proven",
        "source_outage_behavior_proven",
        "rollback_to_simulation_proven",
        "bounded_live_read_only_soak_passed",
        "no_execution_surface_introduced",
    }
)


def canonical_json_bytes(document: dict[str, Any]) -> bytes:
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def artifact_payload(document: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(document)
    payload.pop("artifact_id", None)
    return payload


def compute_artifact_id(document: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(artifact_payload(document))).hexdigest()


def refresh_artifact_id(document: dict[str, Any]) -> dict[str, Any]:
    refreshed = copy.deepcopy(document)
    refreshed["artifact_id"] = compute_artifact_id(refreshed)
    return refreshed


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _evidence_types(document: dict[str, Any]) -> set[str]:
    evidence = document.get("evidence", [])
    if not isinstance(evidence, list):
        return set()
    return {
        str(item.get("evidence_type"))
        for item in evidence
        if isinstance(item, dict) and item.get("evidence_type")
    }


def validate_gate_descent(
    document: dict[str, Any],
    *,
    now: datetime | None = None,
) -> list[str]:
    """Return semantic findings. An empty list means the proposal is valid."""
    findings: list[str] = []
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    if document.get("artifact_type") != ARTIFACT_TYPE:
        findings.append(f"artifact_type must be {ARTIFACT_TYPE}")
    if document.get("contract_version") != CONTRACT_VERSION:
        findings.append(f"contract_version must be {CONTRACT_VERSION}")

    expected_id = compute_artifact_id(document)
    if document.get("artifact_id") != expected_id:
        findings.append("artifact_id does not match canonical payload hash")

    try:
        created_at = parse_utc(str(document["created_at"]))
        expires_at = parse_utc(str(document["expires_at"]))
        ttl_seconds = int(document["ttl_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        findings.append(f"invalid TTL fields: {exc}")
    else:
        actual_ttl = int((expires_at - created_at).total_seconds())
        if ttl_seconds != actual_ttl:
            findings.append("ttl_seconds does not match created_at/expires_at")
        if ttl_seconds < 1 or ttl_seconds > MAX_TTL_SECONDS:
            findings.append(f"ttl_seconds must be between 1 and {MAX_TTL_SECONDS}")
        if expires_at <= now_utc:
            findings.append("gate descent proposal TTL is stale")

    gate_states = document.get("gate_states")
    if not isinstance(gate_states, list) or len(gate_states) != len(GATES):
        findings.append(f"gate_states must contain exactly {len(GATES)} gates")
    else:
        expected_statuses = ("ACTIVE", "REQUESTED") + ("LOCKED",) * (
            len(GATES) - 2
        )
        for index, (expected_name, expected_status) in enumerate(
            zip(GATES, expected_statuses, strict=True)
        ):
            gate = gate_states[index]
            if not isinstance(gate, dict):
                findings.append(f"gate_states[{index}] must be an object")
                continue
            if gate.get("index") != index:
                findings.append(f"gate_states[{index}].index must equal {index}")
            if gate.get("name") != expected_name:
                findings.append(
                    f"gate_states[{index}].name must equal {expected_name}"
                )
            if gate.get("status") != expected_status:
                findings.append(
                    f"gate_states[{index}].status must equal {expected_status}"
                )

    transition = document.get("transition", {})
    if not isinstance(transition, dict):
        findings.append("transition must be an object")
    else:
        current_gate = transition.get("current_gate")
        requested_gate = transition.get("requested_gate")
        if current_gate != 0 or requested_gate != 1:
            findings.append("v0.1 permits only adjacent Gate 0 -> Gate 1")
        if (
            isinstance(current_gate, int)
            and isinstance(requested_gate, int)
            and requested_gate - current_gate != 1
        ):
            findings.append("exactly one adjacent gate may be requested")
        if transition.get("one_gate_only") is not True:
            findings.append("transition.one_gate_only must be true")
        if transition.get("downstream_inheritance") is not False:
            findings.append("transition.downstream_inheritance must be false")

    for key, expected in {
        "artifact_is_command": False,
        "authority": False,
        "human_promotion_required": True,
        "may_execute": False,
        "may_move_capital": False,
        "write_capable_secrets_present": False,
    }.items():
        if document.get(key) is not expected:
            findings.append(f"{key} must be {str(expected).lower()}")

    if document.get("connector_mode") != "read_only":
        findings.append("connector_mode must be read_only")

    prohibited = document.get("prohibited_actions", [])
    if not isinstance(prohibited, list):
        findings.append("prohibited_actions must be an array")
    else:
        missing = sorted(REQUIRED_PROHIBITED_ACTIONS - set(map(str, prohibited)))
        if missing:
            findings.append(
                "prohibited_actions missing required entries: " + ", ".join(missing)
            )

    readiness = document.get("readiness")
    promotion_eligible = document.get("promotion_eligible")
    checks = document.get("acceptance_checks", {})
    rollback = document.get("rollback", {})
    evidence_types = _evidence_types(document)

    if not isinstance(checks, dict):
        findings.append("acceptance_checks must be an object")
        checks = {}
    missing_checks = sorted(READY_CHECKS - set(checks))
    if missing_checks:
        findings.append("acceptance_checks missing: " + ", ".join(missing_checks))

    if readiness == "DRAFT":
        if promotion_eligible is not False:
            findings.append("DRAFT proposals cannot be promotion eligible")
    elif readiness == "READY_FOR_HUMAN_REVIEW":
        if promotion_eligible is not True:
            findings.append(
                "READY_FOR_HUMAN_REVIEW requires promotion_eligible=true"
            )
        failed_checks = sorted(
            check for check in READY_CHECKS if checks.get(check) is not True
        )
        if failed_checks:
            findings.append(
                "ready proposal has incomplete acceptance checks: "
                + ", ".join(failed_checks)
            )
        missing_evidence = sorted(READY_EVIDENCE_TYPES - evidence_types)
        if missing_evidence:
            findings.append(
                "ready proposal missing evidence types: "
                + ", ".join(missing_evidence)
            )
        if not isinstance(rollback, dict) or rollback.get("tested") is not True:
            findings.append("ready proposal requires a tested rollback")
        elif rollback.get("target_gate") != 0:
            findings.append("rollback target must be Gate 0")
    else:
        findings.append("readiness must be DRAFT or READY_FOR_HUMAN_REVIEW")

    return findings


def build_gate_0_to_1_draft(
    *,
    created_at: str,
    expires_at: str,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    checks = {name: False for name in sorted(READY_CHECKS)}
    checks["adjacent_gate_only"] = True
    checks["all_downstream_gates_locked"] = True
    checks["read_only_interfaces_only"] = True
    checks["zero_write_capable_secrets"] = True
    checks["no_execution_surface_introduced"] = True

    document: dict[str, Any] = {
        "artifact_type": ARTIFACT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "created_at": created_at,
        "expires_at": expires_at,
        "ttl_seconds": int(
            (parse_utc(expires_at) - parse_utc(created_at)).total_seconds()
        ),
        "readiness": "DRAFT",
        "promotion_eligible": False,
        "transition": {
            "current_gate": 0,
            "requested_gate": 1,
            "one_gate_only": True,
            "downstream_inheritance": False,
        },
        "gate_states": [
            {
                "index": index,
                "name": name,
                "status": (
                    "ACTIVE"
                    if index == 0
                    else "REQUESTED"
                    if index == 1
                    else "LOCKED"
                ),
            }
            for index, name in enumerate(GATES)
        ],
        "connector_mode": "read_only",
        "write_capable_secrets_present": False,
        "acceptance_checks": checks,
        "evidence": evidence or [],
        "rollback": {
            "target_gate": 0,
            "tested": False,
            "plan_sha256": None,
            "test_receipt_sha256": None,
        },
        "prohibited_actions": sorted(REQUIRED_PROHIBITED_ACTIONS),
        "artifact_is_command": False,
        "authority": False,
        "human_promotion_required": True,
        "may_execute": False,
        "may_move_capital": False,
    }
    return refresh_artifact_id(document)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build or validate an EVE_Q++ Gate 0 -> Gate 1 descent proposal."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--validate", type=Path)
    group.add_argument("--write-draft", type=Path)
    parser.add_argument("--created-at")
    parser.add_argument("--expires-at")
    parser.add_argument("--now")
    args = parser.parse_args()

    if args.write_draft:
        if not args.created_at or not args.expires_at:
            parser.error("--write-draft requires --created-at and --expires-at")
        document = build_gate_0_to_1_draft(
            created_at=args.created_at,
            expires_at=args.expires_at,
        )
        args.write_draft.parent.mkdir(parents=True, exist_ok=True)
        args.write_draft.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(args.write_draft)
        return 0

    document = json.loads(args.validate.read_text(encoding="utf-8"))
    now = parse_utc(args.now) if args.now else None
    findings = validate_gate_descent(document, now=now)
    if findings:
        for finding in findings:
            print(finding)
        return 1
    print("Gate descent proposal: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
