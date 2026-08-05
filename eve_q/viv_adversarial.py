from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping

from eve_q.immutable_receipts import canonical_json_bytes, sha256_hex
from eve_q.simulation_runs import validate_simulation_run

VIV_ADVERSARIAL_SCHEMA = "eve_q.viv_adversarial_receipt.v0.1"
VIV_ADVERSARIAL_VERSION = "0.1.0"
VIV_ROLE = "sandboxed_adversarial_tester"

Validator = Callable[[dict[str, Any]], None]
Mutator = Callable[[MutableMapping[str, Any], int], None]


class ViVAdversarialError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdversarialCase:
    case_id: str
    name: str
    target_invariant: str
    severity: str
    mutator: Mutator

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id is required")
        if not self.name.strip():
            raise ValueError("name is required")
        if not self.target_invariant.strip():
            raise ValueError("target_invariant is required")
        if self.severity not in {"low", "medium", "high", "critical"}:
            raise ValueError("unsupported severity")


def _set_authority(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["authority"] = True


def _set_execution(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["may_execute"] = True


def _set_capital(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["may_move_capital"] = True


def _turn_artifact_into_command(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["artifact_is_command"] = True


def _flip_environment(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["environment"] = "live"


def _inject_command_field(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    metadata = candidate.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata = deepcopy(metadata)
    metadata["command"] = "broadcast-now-without-review"
    candidate["metadata"] = metadata


def _corrupt_counts(candidate: MutableMapping[str, Any], seed: int) -> None:
    candidate_count = candidate.get("candidate_count")
    accepted_count = candidate.get("accepted_count")
    if not isinstance(candidate_count, int) or isinstance(candidate_count, bool):
        candidate["candidate_count"] = 1
        candidate["accepted_count"] = 1
        candidate["rejected_count"] = 1
        return
    if not isinstance(accepted_count, int) or isinstance(accepted_count, bool):
        accepted_count = 0
    candidate["accepted_count"] = accepted_count + 1 + (seed % 3)


def _tamper_digest(candidate: MutableMapping[str, Any], seed: int) -> None:
    candidate["simulation_run_id"] = f"sha256:viv-tamper-{seed}"


def _remove_human_gate(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["human_promotion_required"] = False


DEFAULT_SIMULATION_CASES: tuple[AdversarialCase, ...] = (
    AdversarialCase(
        case_id="viv.authority_flip.v0.1",
        name="Authority flip",
        target_invariant="authority must remain false or absent",
        severity="critical",
        mutator=_set_authority,
    ),
    AdversarialCase(
        case_id="viv.execution_flip.v0.1",
        name="Execution flip",
        target_invariant="may_execute must remain false",
        severity="critical",
        mutator=_set_execution,
    ),
    AdversarialCase(
        case_id="viv.capital_flip.v0.1",
        name="Capital movement flip",
        target_invariant="may_move_capital must remain false",
        severity="critical",
        mutator=_set_capital,
    ),
    AdversarialCase(
        case_id="viv.command_artifact_flip.v0.1",
        name="Artifact-command conversion",
        target_invariant="artifact_is_command must remain false",
        severity="critical",
        mutator=_turn_artifact_into_command,
    ),
    AdversarialCase(
        case_id="viv.environment_escape.v0.1",
        name="Simulation-to-live environment escape",
        target_invariant="environment must remain simulation",
        severity="critical",
        mutator=_flip_environment,
    ),
    AdversarialCase(
        case_id="viv.command_field_injection.v0.1",
        name="Nested command-field injection",
        target_invariant="forbidden command-shaped paths must be rejected",
        severity="high",
        mutator=_inject_command_field,
    ),
    AdversarialCase(
        case_id="viv.count_corruption.v0.1",
        name="Simulation count corruption",
        target_invariant="accepted plus rejected must equal candidate count",
        severity="high",
        mutator=_corrupt_counts,
    ),
    AdversarialCase(
        case_id="viv.digest_tamper.v0.1",
        name="Content-address tamper",
        target_invariant="simulation_run_id must match canonical content",
        severity="high",
        mutator=_tamper_digest,
    ),
    AdversarialCase(
        case_id="viv.human_gate_removal.v0.1",
        name="Human-promotion gate removal",
        target_invariant="human_promotion_required must remain true",
        severity="critical",
        mutator=_remove_human_gate,
    ),
)


def _stable_hash(payload: object) -> str:
    return sha256(canonical_json_bytes(payload)).hexdigest()


def _case_seed(root_seed: int, case_id: str) -> int:
    digest = sha256(f"{root_seed}:{case_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _validate_candidate(candidate: Mapping[str, Any], validator: Validator) -> None:
    try:
        validator(deepcopy(dict(candidate)))
    except Exception as exc:  # validator contracts deliberately use typed exceptions
        raise ViVAdversarialError(f"baseline candidate is invalid: {exc}") from exc


def _run_case(
    candidate: Mapping[str, Any],
    validator: Validator,
    case: AdversarialCase,
    root_seed: int,
) -> dict[str, Any]:
    mutated = deepcopy(dict(candidate))
    derived_seed = _case_seed(root_seed, case.case_id)
    case.mutator(mutated, derived_seed)
    mutated_hash = "sha256:" + sha256_hex(canonical_json_bytes(mutated))

    try:
        validator(deepcopy(mutated))
    except Exception as exc:  # rejection is the expected containment path
        return {
            "case_id": case.case_id,
            "name": case.name,
            "target_invariant": case.target_invariant,
            "severity": case.severity,
            "derived_seed": derived_seed,
            "status": "blocked",
            "mutated_artifact_hash": mutated_hash,
            "validator_exception_type": type(exc).__name__,
            "validator_message": str(exc),
        }

    return {
        "case_id": case.case_id,
        "name": case.name,
        "target_invariant": case.target_invariant,
        "severity": case.severity,
        "derived_seed": derived_seed,
        "status": "escaped",
        "mutated_artifact_hash": mutated_hash,
        "validator_exception_type": None,
        "validator_message": None,
    }


def _receipt_digest_source(receipt: Mapping[str, Any]) -> dict[str, Any]:
    digest_source = dict(receipt)
    digest_source.pop("receipt_id", None)
    return digest_source


def expected_receipt_id(receipt: Mapping[str, Any]) -> str:
    return "sha256:" + sha256_hex(canonical_json_bytes(_receipt_digest_source(receipt)))


def run_viv_gauntlet(
    candidate: Mapping[str, Any],
    *,
    validator: Validator,
    validator_id: str,
    cases: Iterable[AdversarialCase] = DEFAULT_SIMULATION_CASES,
    seed: int = 0,
    created_at: str = "1970-01-01T00:00:00Z",
) -> dict[str, Any]:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ViVAdversarialError("seed must be an integer")
    if not validator_id.strip():
        raise ViVAdversarialError("validator_id is required")
    if not isinstance(candidate, Mapping):
        raise ViVAdversarialError("candidate must be a mapping")

    baseline = deepcopy(dict(candidate))
    baseline_bytes = canonical_json_bytes(baseline)
    _validate_candidate(baseline, validator)

    case_list = tuple(cases)
    if not case_list:
        raise ViVAdversarialError("at least one adversarial case is required")
    case_ids = [case.case_id for case in case_list]
    if len(case_ids) != len(set(case_ids)):
        raise ViVAdversarialError("adversarial case IDs must be unique")

    results = [
        _run_case(baseline, validator, case, seed)
        for case in sorted(case_list, key=lambda item: item.case_id)
    ]
    blocked_count = sum(result["status"] == "blocked" for result in results)
    escaped_count = sum(result["status"] == "escaped" for result in results)
    overall_outcome = "pass" if escaped_count == 0 else "fail"
    candidate_unchanged = canonical_json_bytes(candidate) == baseline_bytes

    receipt: dict[str, Any] = {
        "schema": VIV_ADVERSARIAL_SCHEMA,
        "version": VIV_ADVERSARIAL_VERSION,
        "role": VIV_ROLE,
        "validator_id": validator_id,
        "seed": seed,
        "created_at": created_at,
        "candidate_hash": "sha256:" + sha256_hex(baseline_bytes),
        "case_count": len(results),
        "blocked_count": blocked_count,
        "escaped_count": escaped_count,
        "overall_outcome": overall_outcome,
        "candidate_unchanged": candidate_unchanged,
        "cases": results,
        "repair_required": escaped_count > 0,
        "self_certifying": False,
        "authority": False,
        "artifact_is_command": False,
        "network_access": False,
        "dynamic_code_loading": False,
        "human_promotion_required": True,
        "may_execute": False,
        "may_deploy": False,
        "may_merge": False,
        "may_sign": False,
        "may_broadcast": False,
        "may_access_wallet": False,
        "may_move_capital": False,
        "may_mutate_canonical_memory": False,
        "boundary_law": [
            "ViV may break the candidate, never the enclosure.",
            "A blocked mutation is evidence, not certification.",
            "An escaped mutation returns to the builder repair loop.",
            "The adversary records. The human promotes.",
        ],
    }
    receipt["receipt_id"] = expected_receipt_id(receipt)
    validate_viv_receipt(receipt)

    if canonical_json_bytes(candidate) != baseline_bytes:
        raise ViVAdversarialError("candidate changed during adversarial evaluation")

    return receipt


def validate_viv_receipt(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema") != VIV_ADVERSARIAL_SCHEMA:
        raise ViVAdversarialError("ViV receipt schema mismatch")
    if receipt.get("role") != VIV_ROLE:
        raise ViVAdversarialError("ViV role mismatch")

    protected_false = (
        "self_certifying",
        "authority",
        "artifact_is_command",
        "network_access",
        "dynamic_code_loading",
        "may_execute",
        "may_deploy",
        "may_merge",
        "may_sign",
        "may_broadcast",
        "may_access_wallet",
        "may_move_capital",
        "may_mutate_canonical_memory",
    )
    for field_name in protected_false:
        if receipt.get(field_name) is not False:
            raise ViVAdversarialError(f"{field_name} must be false")
    if receipt.get("human_promotion_required") is not True:
        raise ViVAdversarialError("human promotion must be required")
    if receipt.get("candidate_unchanged") is not True:
        raise ViVAdversarialError("candidate_unchanged must be true")

    cases = receipt.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ViVAdversarialError("cases must be a non-empty list")
    statuses = [case.get("status") for case in cases if isinstance(case, dict)]
    if len(statuses) != len(cases):
        raise ViVAdversarialError("every case must be an object")
    if any(status not in {"blocked", "escaped"} for status in statuses):
        raise ViVAdversarialError("unsupported case status")

    blocked_count = sum(status == "blocked" for status in statuses)
    escaped_count = sum(status == "escaped" for status in statuses)
    if receipt.get("case_count") != len(cases):
        raise ViVAdversarialError("case_count mismatch")
    if receipt.get("blocked_count") != blocked_count:
        raise ViVAdversarialError("blocked_count mismatch")
    if receipt.get("escaped_count") != escaped_count:
        raise ViVAdversarialError("escaped_count mismatch")
    expected_outcome = "pass" if escaped_count == 0 else "fail"
    if receipt.get("overall_outcome") != expected_outcome:
        raise ViVAdversarialError("overall_outcome mismatch")
    if receipt.get("repair_required") is not (escaped_count > 0):
        raise ViVAdversarialError("repair_required mismatch")
    if receipt.get("receipt_id") != expected_receipt_id(receipt):
        raise ViVAdversarialError("receipt_id digest mismatch")


_VALIDATORS: dict[str, Validator] = {
    "simulation_run": validate_simulation_run,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic ViV adversarial cases against a JSON artifact."
    )
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--validator", choices=sorted(_VALIDATORS), default="simulation_run")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--created-at", default="1970-01-01T00:00:00Z")
    parser.add_argument("--receipt-out", type=Path, default=None)
    args = parser.parse_args()

    try:
        candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
        if not isinstance(candidate, dict):
            raise ViVAdversarialError("candidate JSON must be an object")
        receipt = run_viv_gauntlet(
            candidate,
            validator=_VALIDATORS[args.validator],
            validator_id=args.validator,
            seed=args.seed,
            created_at=args.created_at,
        )
        if args.receipt_out is not None:
            args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
            args.receipt_out.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except (OSError, json.JSONDecodeError, ViVAdversarialError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1

    print(json.dumps({"ok": True, "receipt": receipt}, sort_keys=True))
    return 0 if receipt["overall_outcome"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
