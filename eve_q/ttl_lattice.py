"""Typed TTL lattice and bounded-authority evaluator.

This module evaluates supplied timestamps and simulation scope against a
machine-readable manifest. It is deliberately pure: it does not schedule,
trade, sign, submit, borrow, open network connections, or move capital.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = REPO_ROOT / "contracts" / "bounded_authority_manifest_v0_2.json"
RECEIPT_SCHEMA = "codex.ttl_lattice_receipt.v0.1"
RECEIPT_VERSION = "0.1.0"


class TTLLatticeError(ValueError):
    """Raised when a manifest or evaluation snapshot is malformed."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_bounded_authority_manifest(
    path: Path | str = DEFAULT_MANIFEST_PATH,
) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _string_set(value: Any, field: str) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list):
        raise TTLLatticeError(f"{field} must be a list")
    if not all(isinstance(item, str) and item for item in value):
        raise TTLLatticeError(f"{field} must contain non-empty strings")
    return set(value)


def validate_manifest_shape(manifest: dict[str, Any]) -> list[str]:
    """Return manifest errors without mutating the manifest."""

    errors: list[str] = []
    required = {
        "manifest_id",
        "version",
        "posture",
        "authority",
        "scope",
        "degradation_rank",
        "clock_types",
        "denied_capabilities",
        "human_approval_required_for",
        "hard_invariants",
    }
    missing = sorted(required - set(manifest))
    errors.extend(f"missing manifest field: {field}" for field in missing)
    if errors:
        return errors

    posture = manifest["posture"]
    if not isinstance(posture, dict):
        errors.append("posture must be an object")
    else:
        for field in {
            "proposal_only",
            "authority_bounded_in_space",
            "authority_bounded_in_time",
            "expiry_never_self_renews",
            "human_approval_required_for_renewal",
            "receipt_is_not_command",
        }:
            if posture.get(field) is not True:
                errors.append(f"posture.{field} must be true")

    authority = manifest["authority"]
    if not isinstance(authority, dict):
        errors.append("authority must be an object")
    else:
        for field in {
            "authority",
            "execution_authority",
            "wallet_authority",
            "signing_authority",
            "capital_authority",
            "deployment_authority",
            "scheduler_authority",
        }:
            if authority.get(field) is not False:
                errors.append(f"authority.{field} must be false")
        if authority.get("human_promotion_required") is not True:
            errors.append("authority.human_promotion_required must be true")

    ranks = manifest["degradation_rank"]
    if not isinstance(ranks, dict) or not ranks:
        errors.append("degradation_rank must be a non-empty object")
        ranks = {}
    else:
        rank_values = list(ranks.values())
        if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in rank_values):
            errors.append("degradation ranks must be non-negative integers")
        if len(set(rank_values)) != len(rank_values):
            errors.append("degradation ranks must be unique")
        if "inert" not in ranks:
            errors.append("degradation_rank must define inert")

    clocks = manifest["clock_types"]
    if not isinstance(clocks, dict) or not clocks:
        errors.append("clock_types must be a non-empty object")
    else:
        for name, policy in clocks.items():
            if not isinstance(policy, dict):
                errors.append(f"clock policy must be an object: {name}")
                continue
            for field in {
                "required",
                "max_ttl_seconds",
                "expiry_target",
                "on_expiry",
                "renewal_requires_human",
            }:
                if field not in policy:
                    errors.append(f"clock {name} missing field: {field}")
            ttl = policy.get("max_ttl_seconds")
            if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
                errors.append(f"clock {name} max_ttl_seconds must be a positive integer")
            if policy.get("expiry_target") not in ranks:
                errors.append(f"clock {name} has unknown expiry_target")
            if policy.get("required") not in {True, False}:
                errors.append(f"clock {name} required must be boolean")
            if policy.get("renewal_requires_human") is not True:
                errors.append(f"clock {name} renewal_requires_human must be true")
            if not isinstance(policy.get("on_expiry"), str) or not policy.get("on_expiry"):
                errors.append(f"clock {name} on_expiry must be a non-empty string")

    scope = manifest["scope"]
    if not isinstance(scope, dict):
        errors.append("scope must be an object")
    else:
        for field in {"allowed_assets", "allowed_venues", "allowed_order_types"}:
            value = scope.get(field)
            if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
                errors.append(f"scope.{field} must be a list of non-empty strings")
        for field in {"max_position_notional_usd", "max_daily_loss_usd", "max_leverage"}:
            value = scope.get(field)
            if not _is_number(value) or float(value) < 0:
                errors.append(f"scope.{field} must be a non-negative number")

    for field in {"denied_capabilities", "human_approval_required_for", "hard_invariants"}:
        value = manifest[field]
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            errors.append(f"{field} must be a list of non-empty strings")

    return errors


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise TTLLatticeError(f"{field} must be an ISO-8601 string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise TTLLatticeError(f"{field} must be valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise TTLLatticeError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _normalized_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _scope_violations(
    requested_scope: dict[str, Any],
    manifest_scope: dict[str, Any],
) -> list[str]:
    if not isinstance(requested_scope, dict):
        raise TTLLatticeError("requested_scope must be an object")

    violations: list[str] = []
    list_pairs = {
        "assets": "allowed_assets",
        "venues": "allowed_venues",
        "order_types": "allowed_order_types",
    }
    for requested_field, allowed_field in list_pairs.items():
        requested = _string_set(requested_scope.get(requested_field, []), f"requested_scope.{requested_field}")
        allowed = set(manifest_scope[allowed_field])
        for value in sorted(requested - allowed):
            violations.append(f"scope_not_allowed:{requested_field}:{value}")

    numeric_pairs = {
        "position_notional_usd": "max_position_notional_usd",
        "daily_loss_usd": "max_daily_loss_usd",
        "leverage": "max_leverage",
    }
    for requested_field, ceiling_field in numeric_pairs.items():
        requested = requested_scope.get(requested_field, 0)
        if not _is_number(requested) or float(requested) < 0:
            raise TTLLatticeError(f"requested_scope.{requested_field} must be a non-negative number")
        ceiling = float(manifest_scope[ceiling_field])
        if float(requested) > ceiling:
            violations.append(
                f"scope_ceiling_exceeded:{requested_field}:{float(requested)}>{ceiling}"
            )

    return violations


def evaluate_ttl_lattice(
    snapshot: dict[str, Any],
    manifest: dict[str, Any] | None = None,
    manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
) -> dict[str, Any]:
    """Evaluate typed clocks and requested simulation scope.

    The receipt is evidence only. It never grants or renews authority.
    """

    if not isinstance(snapshot, dict):
        raise TTLLatticeError("snapshot must be an object")

    active_manifest = manifest or load_bounded_authority_manifest(manifest_path)
    manifest_errors = validate_manifest_shape(active_manifest)
    if manifest_errors:
        raise TTLLatticeError("invalid bounded authority manifest: " + "; ".join(manifest_errors))

    evaluated_at = _parse_timestamp(snapshot.get("evaluated_at"), "evaluated_at")
    ranks: dict[str, int] = active_manifest["degradation_rank"]
    current_state = snapshot.get("current_state")
    if current_state not in ranks:
        raise TTLLatticeError(f"unknown current_state: {current_state}")

    clocks_input = snapshot.get("clocks")
    if not isinstance(clocks_input, dict):
        raise TTLLatticeError("clocks must be an object")

    unknown_clocks = sorted(set(clocks_input) - set(active_manifest["clock_types"]))
    if unknown_clocks:
        raise TTLLatticeError("unknown clocks: " + ", ".join(unknown_clocks))

    clock_results: list[dict[str, Any]] = []
    expired_clocks: list[str] = []
    missing_required_clocks: list[str] = []
    target_states: list[str] = []
    reasons: list[str] = []

    for name in sorted(active_manifest["clock_types"]):
        policy = active_manifest["clock_types"][name]
        supplied = clocks_input.get(name)

        if supplied is None:
            if policy["required"]:
                expired_clocks.append(name)
                missing_required_clocks.append(name)
                target_states.append(policy["expiry_target"])
                reasons.append(f"required_clock_missing:{name}")
                clock_results.append(
                    {
                        "clock": name,
                        "status": "missing",
                        "required": True,
                        "observed_at": None,
                        "age_seconds": None,
                        "requested_ttl_seconds": None,
                        "effective_ttl_seconds": policy["max_ttl_seconds"],
                        "ttl_capped": False,
                        "expired": True,
                        "expiry_target": policy["expiry_target"],
                        "on_expiry": policy["on_expiry"],
                    }
                )
            continue

        if not isinstance(supplied, dict):
            raise TTLLatticeError(f"clock {name} must be an object")

        observed_at = _parse_timestamp(supplied.get("observed_at"), f"clocks.{name}.observed_at")
        if observed_at > evaluated_at:
            raise TTLLatticeError(f"clock {name} observed_at cannot be in the future")

        requested_ttl = supplied.get("ttl_seconds", policy["max_ttl_seconds"])
        if not isinstance(requested_ttl, int) or isinstance(requested_ttl, bool) or requested_ttl <= 0:
            raise TTLLatticeError(f"clock {name} ttl_seconds must be a positive integer")

        effective_ttl = min(requested_ttl, int(policy["max_ttl_seconds"]))
        ttl_capped = requested_ttl > effective_ttl
        age_exact = (evaluated_at - observed_at).total_seconds()
        age_seconds = int(age_exact)
        expired = age_exact >= effective_ttl

        if expired:
            expired_clocks.append(name)
            target_states.append(policy["expiry_target"])
            reasons.append(f"clock_expired:{name}:{policy['on_expiry']}")
        if ttl_capped:
            reasons.append(f"ttl_capped:{name}:{requested_ttl}->{effective_ttl}")

        clock_results.append(
            {
                "clock": name,
                "status": "expired" if expired else "fresh",
                "required": bool(policy["required"]),
                "observed_at": _normalized_timestamp(observed_at),
                "age_seconds": age_seconds,
                "requested_ttl_seconds": requested_ttl,
                "effective_ttl_seconds": effective_ttl,
                "ttl_capped": ttl_capped,
                "expired": expired,
                "expiry_target": policy["expiry_target"],
                "on_expiry": policy["on_expiry"],
            }
        )

    requested_scope = snapshot.get("requested_scope", {})
    scope_violations = _scope_violations(requested_scope, active_manifest["scope"])
    requested_capabilities = _string_set(
        snapshot.get("requested_capabilities", []),
        "requested_capabilities",
    )
    denied_hits = sorted(requested_capabilities & set(active_manifest["denied_capabilities"]))

    hard_stop = bool(scope_violations or denied_hits)
    if scope_violations:
        reasons.extend(scope_violations)
    if denied_hits:
        reasons.extend(f"denied_capability:{item}" for item in denied_hits)

    if hard_stop:
        effective_state = "inert"
    else:
        effective_state = current_state
        for target in target_states:
            if ranks[target] < ranks[effective_state]:
                effective_state = target

    degraded = ranks[effective_state] < ranks[current_state]
    renewal_requested = bool(snapshot.get("renewal_requested", False))
    if renewal_requested:
        reasons.append("renewal_requires_external_human_approval")

    human_approval_required = bool(
        hard_stop
        or degraded
        or expired_clocks
        or missing_required_clocks
        or renewal_requested
    )

    authority = dict(active_manifest["authority"])
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "version": RECEIPT_VERSION,
        "evaluated_at": _normalized_timestamp(evaluated_at),
        "manifest_id": active_manifest["manifest_id"],
        "manifest_version": active_manifest["version"],
        "manifest_sha256": sha256_json(active_manifest),
        "snapshot_sha256": sha256_json(snapshot),
        "current_state": current_state,
        "effective_state": effective_state,
        "degraded": degraded,
        "hard_stop": hard_stop,
        "expired_clocks": sorted(expired_clocks),
        "missing_required_clocks": sorted(missing_required_clocks),
        "clock_results": clock_results,
        "scope_violations": scope_violations,
        "denied_capability_hits": denied_hits,
        "requested_capabilities": sorted(requested_capabilities),
        "renewal_requested": renewal_requested,
        "renewal_permitted": False,
        "human_approval_required": human_approval_required,
        "reasons": sorted(set(reasons)),
        "network_calls_made": False,
        "mutation_performed": False,
        "authority": False,
        "execution_authority": False,
        "wallet_authority": False,
        "signing_authority": False,
        "capital_authority": False,
        "deployment_authority": False,
        "scheduler_authority": False,
        "human_promotion_required": True,
        "authority_manifest": authority,
        "hard_invariants": list(active_manifest["hard_invariants"]),
    }
    return receipt


__all__ = [
    "DEFAULT_MANIFEST_PATH",
    "RECEIPT_SCHEMA",
    "RECEIPT_VERSION",
    "TTLLatticeError",
    "canonical_json",
    "evaluate_ttl_lattice",
    "load_bounded_authority_manifest",
    "sha256_json",
    "validate_manifest_shape",
]
