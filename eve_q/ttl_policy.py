"""Pure TTL policy evaluator for CodexTradingEngine.

This module evaluates declared TTL policy state. It does not schedule work,
touch wallets, open network connections, or grant runtime authority.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TTL_POLICY_PATH = REPO_ROOT / "contracts" / "ttl_policy.json"


def load_ttl_policy(path: Path | str = DEFAULT_TTL_POLICY_PATH) -> dict[str, Any]:
    """Load the machine-readable TTL policy."""
    return json.loads(Path(path).read_text())


def _as_string_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    return {str(item) for item in value}


def validate_ttl_policy_shape(policy: dict[str, Any]) -> list[str]:
    """Return structural policy errors without mutating policy."""
    errors: list[str] = []

    required_fields = {
        "policy_id",
        "version",
        "posture",
        "authority_rank",
        "modes",
        "ttl_shortening_signals",
        "graceful_degradation_triggers",
        "hard_stop_triggers",
        "human_approval_required_for",
        "safe_outputs_after_degradation",
        "hard_invariants",
    }

    missing = sorted(required_fields - set(policy))
    errors.extend(f"missing required TTL policy field: {field}" for field in missing)

    if errors:
        return errors

    posture = policy["posture"]
    required_true_posture = {
        "authority_expires",
        "uncertainty_degrades_permission",
        "graceful_degradation_preferred",
        "hard_stop_on_forbidden_capability",
        "human_approval_required_for_renewal",
    }

    for field in sorted(required_true_posture):
        if posture.get(field) is not True:
            errors.append(f"TTL posture must declare {field}=true")

    modes = policy["modes"]
    ranks = policy["authority_rank"]

    if not isinstance(modes, dict):
        errors.append("TTL policy modes must be an object")
        return errors

    if not isinstance(ranks, dict):
        errors.append("TTL policy authority_rank must be an object")
        return errors

    for mode, mode_policy in modes.items():
        if mode not in ranks:
            errors.append(f"mode missing authority rank: {mode}")

        target = mode_policy.get("degradation_target")
        if target not in modes:
            errors.append(f"mode has unknown degradation target: {mode}->{target}")
            continue

        if target not in ranks:
            errors.append(f"degradation target missing authority rank: {target}")
            continue

        if mode in ranks and ranks[target] > ranks[mode]:
            errors.append(f"degradation increases authority: {mode}->{target}")

        if mode_policy.get("ttl_required") is True:
            max_ttl = mode_policy.get("max_ttl_minutes")
            if not isinstance(max_ttl, int) or max_ttl <= 0:
                errors.append(f"TTL-required mode lacks positive max TTL: {mode}")

    list_fields = {
        "ttl_shortening_signals",
        "graceful_degradation_triggers",
        "hard_stop_triggers",
        "human_approval_required_for",
        "safe_outputs_after_degradation",
        "hard_invariants",
    }

    for field in sorted(list_fields):
        if not isinstance(policy[field], list):
            errors.append(f"TTL policy field must be a list: {field}")

    return errors


def _cap_ttl_minutes(
    current_ttl_minutes: Any,
    mode_policy: dict[str, Any],
) -> int | None:
    max_ttl = mode_policy.get("max_ttl_minutes")

    if current_ttl_minutes is None:
        return max_ttl

    ttl = int(current_ttl_minutes)

    if max_ttl is None:
        return ttl

    return min(ttl, int(max_ttl))


def _shorten_ttl_minutes(ttl_minutes: int | None) -> int | None:
    if ttl_minutes is None:
        return None
    return max(1, ttl_minutes // 2)


def evaluate_ttl_state(
    state: dict[str, Any],
    policy: dict[str, Any] | None = None,
    policy_path: Path | str = DEFAULT_TTL_POLICY_PATH,
) -> dict[str, Any]:
    """Evaluate a proposed TTL state against policy.

    The result is advisory and artifact-safe. It cannot grant authority.
    """
    if policy is None:
        policy = load_ttl_policy(policy_path)

    errors = validate_ttl_policy_shape(policy)
    mode = state.get("mode")

    base_result: dict[str, Any] = {
        "valid": False,
        "mode": mode,
        "effective_mode": None,
        "degraded_to": None,
        "hard_stop": False,
        "ttl_minutes": None,
        "ttl_shortened": False,
        "safe_outputs": [],
        "human_approval_required": False,
        "reverse_execution_channel_opened": False,
        "reasons": [],
        "errors": errors,
    }

    if errors:
        return base_result

    modes = policy["modes"]
    if mode not in modes:
        base_result["errors"] = [*errors, f"unknown TTL mode: {mode}"]
        return base_result

    mode_policy = modes[mode]
    target = mode_policy["degradation_target"]
    safe_outputs = list(policy["safe_outputs_after_degradation"])

    signals = _as_string_set(state.get("signals"))
    requested_capabilities = _as_string_set(state.get("requested_capabilities"))
    claimed_capabilities = _as_string_set(state.get("claimed_capabilities"))
    capability_claims = requested_capabilities | claimed_capabilities

    hard_stop_triggers = set(policy["hard_stop_triggers"])
    hard_hits = sorted(capability_claims & hard_stop_triggers)

    ttl_minutes = _cap_ttl_minutes(state.get("current_ttl_minutes"), mode_policy)
    ttl_shortened = False
    reasons: list[str] = []

    if hard_hits:
        reasons.extend(f"hard_stop:{hit}" for hit in hard_hits)
        return {
            **base_result,
            "valid": True,
            "effective_mode": "artifact_only",
            "degraded_to": "artifact_only",
            "hard_stop": True,
            "ttl_minutes": None,
            "ttl_shortened": False,
            "safe_outputs": safe_outputs,
            "human_approval_required": True,
            "reasons": reasons,
            "errors": [],
        }

    shortening_hits = sorted(signals & set(policy["ttl_shortening_signals"]))
    if mode_policy.get("ttl_required") is True and shortening_hits:
        ttl_minutes = _shorten_ttl_minutes(ttl_minutes)
        ttl_shortened = True
        reasons.extend(f"ttl_shortened:{hit}" for hit in shortening_hits)

    graceful_hits = sorted(signals & set(policy["graceful_degradation_triggers"]))
    ttl_expired = bool(state.get("ttl_expired", False))
    ttl_missing = (
        mode_policy.get("ttl_required") is True and state.get("current_ttl_minutes") is None
    )

    should_degrade = ttl_expired or bool(graceful_hits) or ttl_missing

    if ttl_expired:
        reasons.append("ttl_expired")

    if ttl_missing:
        reasons.append("ttl_required_but_missing")

    reasons.extend(f"graceful_degradation:{hit}" for hit in graceful_hits)

    effective_mode = target if should_degrade else mode
    degraded_to = effective_mode if should_degrade else None

    return {
        **base_result,
        "valid": True,
        "effective_mode": effective_mode,
        "degraded_to": degraded_to,
        "hard_stop": False,
        "ttl_minutes": ttl_minutes,
        "ttl_shortened": ttl_shortened,
        "safe_outputs": safe_outputs if should_degrade else [],
        "human_approval_required": should_degrade,
        "reasons": reasons,
        "errors": [],
    }
