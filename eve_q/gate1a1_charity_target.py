"""Simulation-only charity target contract for Gate 1A.1.

The contract separates transfer evidence, observed outcome evidence, modeled
contribution, unsupported causal claims, and explicit no-data semantics. It may
produce review evidence only. It cannot access wallets, transfer value, update
rewards automatically, or promote a later gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

_CONTRACT_SCHEMA = "gate1a1-charity-target-contract-v0.1"
_RECEIPT_SCHEMA = "gate1a1-charity-target-receipt-v0.1"
_PIPELINE = (
    "telemetry_observed",
    "counterfactual_impact_estimated",
    "uncertainty_preserved",
    "human_review",
    "no_transfer",
)
_REQUIRED_LOCKS = {
    "authority": False,
    "artifact_is_command": False,
    "automatic_gate_promotion": False,
    "gate1b_activated": False,
    "may_execute": False,
    "may_sign": False,
    "may_submit_transaction": False,
    "may_access_wallet": False,
    "may_move_capital": False,
    "human_promotion_required": True,
}


class CharityTargetError(ValueError):
    pass


def canonical_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise CharityTargetError(f"{context} must be an object")
    return value


def _array(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise CharityTargetError(f"{context} must be an array")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        raise CharityTargetError(
            f"{context} keys mismatch; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _sha(value: object, context: str) -> str:
    digest = str(value)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise CharityTargetError(f"{context} must be 64 lowercase hexadecimal characters")
    return digest


def _validate_locks(payload: Mapping[str, object], context: str) -> None:
    for name, expected in _REQUIRED_LOCKS.items():
        if payload.get(name) is not expected:
            raise CharityTargetError(f"{context}.{name} must be {expected!r}")


def _nested_status(contract: Mapping[str, object], field: str) -> str:
    value = contract.get(field)
    if not isinstance(value, dict):
        return "MALFORMED"
    return str(value.get("status", "UNKNOWN"))


def contract_seed(contract: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in contract.items() if key != "contract_id"}


def validate_contract(contract: Mapping[str, object]) -> None:
    _exact_keys(
        contract,
        {
            "schema_version",
            "contract_id",
            "pipeline",
            "donation_transfer_evidence",
            "observed_outcome_evidence",
            "modeled_contribution",
            "unsupported_causal_claim",
            "no_data_semantics",
            "human_review",
            "reward_posture",
            "transfer_posture",
            *set(_REQUIRED_LOCKS),
        },
        "contract",
    )
    if contract["schema_version"] != _CONTRACT_SCHEMA:
        raise CharityTargetError("contract schema_version mismatch")
    _validate_locks(contract, "contract")
    pipeline = tuple(str(item) for item in _array(contract["pipeline"], "contract.pipeline"))
    if pipeline != _PIPELINE:
        raise CharityTargetError("charity pipeline order or stages drifted")

    transfer_evidence = _mapping(
        contract["donation_transfer_evidence"], "donation_transfer_evidence"
    )
    _exact_keys(
        transfer_evidence,
        {"status", "transaction_reference", "receipt_sha256"},
        "donation_transfer_evidence",
    )
    if transfer_evidence != {
        "status": "ABSENT",
        "transaction_reference": None,
        "receipt_sha256": None,
    }:
        raise CharityTargetError("donation transfer evidence must remain explicitly absent")

    outcome = _mapping(contract["observed_outcome_evidence"], "observed_outcome_evidence")
    _exact_keys(outcome, {"status", "observations", "provenance"}, "observed_outcome_evidence")
    if outcome["status"] != "NO_DATA":
        raise CharityTargetError("observed outcome evidence must remain NO_DATA")
    if _array(outcome["observations"], "observed_outcome_evidence.observations"):
        raise CharityTargetError("NO_DATA cannot contain invented observations")
    if outcome["provenance"] is not None:
        raise CharityTargetError("NO_DATA cannot claim outcome provenance")

    modeled = _mapping(contract["modeled_contribution"], "modeled_contribution")
    _exact_keys(
        modeled,
        {"status", "estimate", "uncertainty_interval", "assumptions_sha256"},
        "modeled_contribution",
    )
    if modeled["status"] != "MODEL_ONLY":
        raise CharityTargetError("modeled contribution must remain MODEL_ONLY")
    estimate = float(modeled["estimate"])
    interval = [
        float(value)
        for value in _array(
            modeled["uncertainty_interval"], "modeled_contribution.uncertainty_interval"
        )
    ]
    if (
        not math.isfinite(estimate)
        or len(interval) != 2
        or not all(math.isfinite(value) for value in interval)
        or interval[0] > estimate
        or estimate > interval[1]
    ):
        raise CharityTargetError("modeled contribution uncertainty interval is invalid")
    _sha(modeled["assumptions_sha256"], "modeled_contribution.assumptions_sha256")

    unsupported = _mapping(contract["unsupported_causal_claim"], "unsupported_causal_claim")
    _exact_keys(unsupported, {"present", "claim"}, "unsupported_causal_claim")
    if unsupported != {"present": False, "claim": None}:
        raise CharityTargetError("unsupported causal claims are forbidden")

    no_data = _mapping(contract["no_data_semantics"], "no_data_semantics")
    _exact_keys(no_data, {"meaning", "not_equivalent_to"}, "no_data_semantics")
    if no_data["meaning"] != "NO_OBSERVATION_AVAILABLE":
        raise CharityTargetError("no-data meaning drifted")
    forbidden_equivalences = tuple(
        str(item)
        for item in _array(
            no_data["not_equivalent_to"], "no_data_semantics.not_equivalent_to"
        )
    )
    if forbidden_equivalences != (
        "ZERO_IMPACT",
        "NEGATIVE_IMPACT",
        "TRANSFER_FAILED",
        "NO_CHARITY_VALUE",
    ):
        raise CharityTargetError("no-data equivalence protections drifted")

    human_review = _mapping(contract["human_review"], "human_review")
    _exact_keys(human_review, {"required", "decision", "reviewer"}, "human_review")
    if human_review != {"required": True, "decision": "PENDING", "reviewer": None}:
        raise CharityTargetError("human review must remain required and pending")

    reward = _mapping(contract["reward_posture"], "reward_posture")
    _exact_keys(
        reward,
        {"automatic_update", "may_rewrite_reward_function", "human_promotion_required"},
        "reward_posture",
    )
    if reward != {
        "automatic_update": False,
        "may_rewrite_reward_function": False,
        "human_promotion_required": True,
    }:
        raise CharityTargetError("charity telemetry cannot update rewards automatically")

    transfer = _mapping(contract["transfer_posture"], "transfer_posture")
    _exact_keys(
        transfer,
        {"enabled", "attempted", "wallet_access", "transaction_submission"},
        "transfer_posture",
    )
    if transfer != {
        "enabled": False,
        "attempted": False,
        "wallet_access": False,
        "transaction_submission": False,
    }:
        raise CharityTargetError("charity target contract must remain transfer-free")

    expected_id = f"gate1a1-charity-target:{canonical_sha256(contract_seed(contract))[:24]}"
    if contract["contract_id"] != expected_id:
        raise CharityTargetError("contract_id does not match the contract payload")


def build_receipt(contract: Mapping[str, object]) -> dict[str, object]:
    """Validate the target contract and emit an inert deterministic receipt."""

    reasons: list[str] = []
    try:
        contract_digest = canonical_sha256(contract)
    except (TypeError, ValueError) as exc:
        contract_digest = "0" * 64
        reasons.append(f"contract digest unavailable: {exc}")

    try:
        validate_contract(contract)
    except (TypeError, ValueError) as exc:
        reasons.append(str(exc))

    status = (
        "SIMULATION_ONLY_CONTRACT_COMPLETE"
        if not reasons
        else "HOLD_CHARITY_TARGET_CONTRACT"
    )
    receipt_seed = {
        "schema_version": _RECEIPT_SCHEMA,
        "contract_id": str(contract.get("contract_id", "UNKNOWN")),
        "contract_sha256": contract_digest,
        "status": status,
        "hold_reasons": reasons,
        "transfer_evidence_status": _nested_status(contract, "donation_transfer_evidence"),
        "outcome_evidence_status": _nested_status(contract, "observed_outcome_evidence"),
        "modeled_contribution_status": _nested_status(contract, "modeled_contribution"),
        "no_data_means_zero": False,
        "transfer_enabled": False,
        "reward_update_enabled": False,
        **_REQUIRED_LOCKS,
    }
    return {
        "receipt_id": f"gate1a1-charity-receipt:{canonical_sha256(receipt_seed)[:24]}",
        **receipt_seed,
    }


def load_contract(path: str | Path) -> Mapping[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return _mapping(payload, "contract")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Gate 1A.1 charity target contract")
    parser.add_argument("contract")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    receipt = build_receipt(load_contract(args.contract))
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(receipt, sort_keys=True))
    return 2 if receipt["status"].startswith("HOLD") else 0


if __name__ == "__main__":
    raise SystemExit(main())
