"""Organ contract validation for CodexTradingEngine.

The organ contract is the local constitutional membrane. It defines what
Codex may emit and what it must never claim while producing artifacts.

This module validates records only. It does not execute, schedule, sign,
transfer, promote, or mutate governance state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT_PATH = REPO_ROOT / "contracts" / "organ_contract.json"

CONTRACT_REQUIRED_FIELDS = {
    "organ_id",
    "organ_type",
    "version",
    "default_mode",
    "constitutional_posture",
    "allowed_outputs",
    "forbidden_capabilities",
    "allowed_modes",
    "promotion_path",
    "hard_invariants",
}

ACTION_INTENT_FIELDS = {
    "action",
    "requested_action",
    "intent",
    "operation",
    "execution",
    "next_action",
    "automation",
    "scheduler",
    "webhook",
    "silent_remote_command_execution",
    "self_promotion",
    "governance_mutation",
}

CAPABILITY_FIELDS = {
    "capability",
    "capabilities",
    "claimed_capability",
    "claimed_capabilities",
}


def load_organ_contract(path: str | Path = DEFAULT_CONTRACT_PATH) -> dict[str, Any]:
    """Load the machine-readable organ contract."""

    contract_path = Path(path)
    return json.loads(contract_path.read_text(encoding="utf-8"))


def validate_contract_shape(contract: dict[str, Any]) -> list[str]:
    """Validate the contract document itself."""

    errors: list[str] = []

    missing = sorted(CONTRACT_REQUIRED_FIELDS - set(contract))
    if missing:
        errors.append(f"contract missing required fields: {', '.join(missing)}")

    posture = contract.get("constitutional_posture", {})
    if not isinstance(posture, dict):
        errors.append("constitutional_posture must be an object")
        return errors

    required_true_posture = {
        "proposal_only",
        "human_promotion_required",
        "ttl_required_for_autonomy",
        "no_reverse_execution_channel",
    }
    for field in sorted(required_true_posture):
        if posture.get(field) is not True:
            errors.append(f"constitutional_posture.{field} must be true")

    for list_field in [
        "allowed_outputs",
        "forbidden_capabilities",
        "allowed_modes",
        "promotion_path",
        "hard_invariants",
    ]:
        if list_field in contract and not isinstance(contract[list_field], list):
            errors.append(f"{list_field} must be a list")

    return errors


def _as_string_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value}
    return {str(value)}


def validate_receipt_against_contract(
    receipt: dict[str, Any],
    *,
    contract: dict[str, Any] | None = None,
    contract_path: str | Path = DEFAULT_CONTRACT_PATH,
) -> list[str]:
    """Validate a receipt against the organ contract."""

    errors: list[str] = []
    active_contract = contract or load_organ_contract(contract_path)

    errors.extend(validate_contract_shape(active_contract))

    allowed_outputs = set(active_contract.get("allowed_outputs", []))
    artifact_type = receipt.get("artifact_type")
    if artifact_type not in allowed_outputs:
        errors.append("artifact_type is not allowed by organ contract: " f"{artifact_type!r}")

    allowed_modes = set(active_contract.get("allowed_modes", []))
    mode = receipt.get("mode")
    if mode not in allowed_modes:
        errors.append(f"mode is not allowed by organ contract: {mode!r}")

    posture = active_contract.get("constitutional_posture", {})
    if posture.get("human_promotion_required") is True:
        if receipt.get("human_promotion_required") is not True:
            errors.append("human_promotion_required must be true by organ contract")

    forbidden_action_fields = sorted(ACTION_INTENT_FIELDS & set(receipt))
    if forbidden_action_fields:
        errors.append(
            "receipt must not contain action/execution fields: "
            + ", ".join(forbidden_action_fields)
        )

    forbidden_capabilities = set(active_contract.get("forbidden_capabilities", []))
    forbidden_direct_keys = sorted(forbidden_capabilities & set(receipt))
    if forbidden_direct_keys:
        errors.append(
            "receipt must not claim forbidden capabilities as fields: "
            + ", ".join(forbidden_direct_keys)
        )

    claimed_capabilities: set[str] = set()
    for field in CAPABILITY_FIELDS:
        if field in receipt:
            claimed_capabilities |= _as_string_set(receipt[field])

    forbidden_claims = sorted(forbidden_capabilities & claimed_capabilities)
    if forbidden_claims:
        errors.append(
            "receipt must not claim forbidden capabilities: " + ", ".join(forbidden_claims)
        )

    return errors
