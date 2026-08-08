"""Gate 1A.1 economic and epistemic ViV mutation pack.

This module extends the existing deterministic ViV enclosure. It contributes a
strict Gate 1A.1 evidence-bundle validator and the eighteen mutations required
by issue #145. ViV may mutate a copy and record containment evidence; she may
not certify, repair, promote, execute, access wallets, or move capital.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, MutableMapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from eve_q.viv_adversarial import AdversarialCase, run_viv_gauntlet

_BUNDLE_SCHEMA = "gate1a1-viv-evidence-bundle-v0.1"
_VALIDATOR_ID = "gate1a1_evidence_bundle_v0_1"
_EXPECTED_QUBO = "1" * 64
_EXPECTED_CONSTRAINTS = "2" * 64
_REQUIRED_SEEDS = (0, 7331, 424242)
_REQUIRED_FALSE = (
    "authority",
    "artifact_is_command",
    "may_execute",
    "may_sign",
    "may_submit_transaction",
    "may_access_wallet",
    "may_move_capital",
    "automatic_gate_promotion",
)


class Gate1A1ViVError(ValueError):
    pass


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise Gate1A1ViVError(f"{context} must be an object")
    return value


def _array(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise Gate1A1ViVError(f"{context} must be an array")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        raise Gate1A1ViVError(
            f"{context} keys mismatch; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _finite(value: object, context: str, *, minimum: float | None = None) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise Gate1A1ViVError(f"{context} must be finite")
    if minimum is not None and number < minimum:
        raise Gate1A1ViVError(f"{context} must be >= {minimum}")
    return number


def _sha(value: object, context: str) -> str:
    digest = str(value)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise Gate1A1ViVError(f"{context} must be 64 lowercase hexadecimal characters")
    return digest


def validate_gate1a1_evidence_bundle(candidate: dict[str, Any]) -> None:
    """Validate one bounded Gate 1A.1 evidence bundle and fail closed on drift."""

    _exact_keys(
        candidate,
        {
            "schema_version",
            "economics",
            "sources",
            "source_consensus",
            "benchmark",
            "language",
            "gate",
            "charity",
            "human_promotion_required",
            *_REQUIRED_FALSE,
        },
        "bundle",
    )
    if candidate["schema_version"] != _BUNDLE_SCHEMA:
        raise Gate1A1ViVError("bundle schema_version mismatch")
    for field in _REQUIRED_FALSE:
        if candidate[field] is not False:
            raise Gate1A1ViVError(f"bundle.{field} must be false")
    if candidate["human_promotion_required"] is not True:
        raise Gate1A1ViVError("human promotion must remain required")

    economics = _mapping(candidate["economics"], "economics")
    _exact_keys(
        economics,
        {"gas", "protocol_fees", "slippage", "liquidity", "latency"},
        "economics",
    )
    required_economics = {
        "gas": ("value", 0.001),
        "protocol_fees": ("value_bps", 5.0),
        "slippage": ("value_bps", 2.0),
        "liquidity": ("capacity", 1_000_000.0),
        "latency": ("penalty_bps", 1.0),
    }
    for name, (value_field, expected_value) in required_economics.items():
        record = _mapping(economics[name], f"economics.{name}")
        _exact_keys(record, {"included", value_field, "status"}, f"economics.{name}")
        if record["included"] is not True:
            raise Gate1A1ViVError(f"economics.{name} must remain included")
        if record["status"] != "MEASURED":
            raise Gate1A1ViVError(f"economics.{name} must remain MEASURED")
        value = _finite(record[value_field], f"economics.{name}.{value_field}", minimum=0.0)
        if not math.isclose(value, expected_value, abs_tol=1e-12):
            raise Gate1A1ViVError(f"economics.{name}.{value_field} drifted")

    raw_sources = _array(candidate["sources"], "sources")
    if len(raw_sources) != 2:
        raise Gate1A1ViVError("exactly two reviewed sources are required")
    source_ids: set[str] = set()
    provenance_groups: set[str] = set()
    observed_values: set[int] = set()
    for index, item in enumerate(raw_sources):
        source = _mapping(item, f"sources[{index}]")
        _exact_keys(
            source,
            {
                "source_id",
                "operator",
                "provenance_group",
                "observed_value",
                "units",
                "fresh",
                "review_state",
            },
            f"sources[{index}]",
        )
        source_id = str(source["source_id"])
        operator = str(source["operator"])
        provenance_group = str(source["provenance_group"])
        if not source_id or source_id in source_ids:
            raise Gate1A1ViVError("source identifiers must be unique and non-empty")
        if not operator or not provenance_group:
            raise Gate1A1ViVError("source operator and provenance group are required")
        source_ids.add(source_id)
        if provenance_group in provenance_groups:
            raise Gate1A1ViVError("sources must remain independently operated")
        provenance_groups.add(provenance_group)
        if source["units"] != "block_number":
            raise Gate1A1ViVError("source units must remain block_number")
        if source["fresh"] is not True:
            raise Gate1A1ViVError("stale telemetry cannot enter consensus")
        if source["review_state"] != "ELIGIBLE":
            raise Gate1A1ViVError("every source must remain reviewed and eligible")
        observed_values.add(int(source["observed_value"]))
    if len(observed_values) != 1:
        raise Gate1A1ViVError("conflicting source values cannot become consensus")

    consensus = _mapping(candidate["source_consensus"], "source_consensus")
    _exact_keys(consensus, {"status", "conflict", "concentration"}, "source_consensus")
    if consensus != {
        "status": "ACCEPT_OBSERVATION_ONLY",
        "conflict": False,
        "concentration": False,
    }:
        raise Gate1A1ViVError("source consensus posture drifted")

    benchmark = _mapping(candidate["benchmark"], "benchmark")
    _exact_keys(
        benchmark,
        {
            "classical_qubo_sha256",
            "qaoa_qubo_sha256",
            "classical_constraints_sha256",
            "qaoa_constraints_sha256",
            "classical_solver_strength",
            "qaoa_seeds",
            "complete_run_disclosure",
            "run_disposition_counts",
            "outcome",
        },
        "benchmark",
    )
    if _sha(benchmark["classical_qubo_sha256"], "benchmark.classical_qubo_sha256") != _EXPECTED_QUBO:
        raise Gate1A1ViVError("classical QUBO changed")
    if _sha(benchmark["qaoa_qubo_sha256"], "benchmark.qaoa_qubo_sha256") != _EXPECTED_QUBO:
        raise Gate1A1ViVError("QAOA is not paired with the exact classical QUBO")
    if _sha(benchmark["classical_constraints_sha256"], "benchmark.classical_constraints_sha256") != _EXPECTED_CONSTRAINTS:
        raise Gate1A1ViVError("classical constraints changed")
    if _sha(benchmark["qaoa_constraints_sha256"], "benchmark.qaoa_constraints_sha256") != _EXPECTED_CONSTRAINTS:
        raise Gate1A1ViVError("QAOA constraints differ from the classical baseline")
    if benchmark["classical_solver_strength"] != "EXACT":
        raise Gate1A1ViVError("classical baseline must remain exact")
    seeds = tuple(int(seed) for seed in _array(benchmark["qaoa_seeds"], "benchmark.qaoa_seeds"))
    if seeds != _REQUIRED_SEEDS:
        raise Gate1A1ViVError("QAOA seed disclosure is incomplete or cherry-picked")
    if benchmark["complete_run_disclosure"] is not True:
        raise Gate1A1ViVError("failed and infeasible runs cannot be suppressed")
    counts = _mapping(benchmark["run_disposition_counts"], "benchmark.run_disposition_counts")
    _exact_keys(counts, {"passed", "failed", "infeasible"}, "benchmark.run_disposition_counts")
    if counts != {"passed": 3, "failed": 0, "infeasible": 0}:
        raise Gate1A1ViVError("benchmark run disclosure counts changed")
    if benchmark["outcome"] != "QAOA_ADDS_NO_MEASURABLE_VALUE":
        raise Gate1A1ViVError("benchmark outcome was repainted")

    language = _mapping(candidate["language"], "language")
    _exact_keys(
        language,
        {"environment", "profitability_claim", "target_chain_gas_status"},
        "language",
    )
    if language["environment"] != "testnet":
        raise Gate1A1ViVError("environment must remain testnet")
    if language["profitability_claim"] != "RESEARCH_ONLY":
        raise Gate1A1ViVError("testnet edge cannot become production profitability language")
    if language["target_chain_gas_status"] != "HYPOTHESIS":
        raise Gate1A1ViVError("target-chain gas hypotheses cannot become measured facts")

    gate = _mapping(candidate["gate"], "gate")
    _exact_keys(
        gate,
        {
            "receipt_success",
            "receipt_grants_permission",
            "gate1b_activated",
            "rollback_enabled",
            "kill_switch_enabled",
        },
        "gate",
    )
    if gate["receipt_success"] is not True:
        raise Gate1A1ViVError("baseline receipt must remain successful evidence")
    if gate["receipt_grants_permission"] is not False:
        raise Gate1A1ViVError("receipt success cannot become gate permission")
    if gate["gate1b_activated"] is not False:
        raise Gate1A1ViVError("Gate 1B must remain locked")
    if gate["rollback_enabled"] is not True or gate["kill_switch_enabled"] is not True:
        raise Gate1A1ViVError("rollback and kill-switch posture must remain enabled")

    charity = _mapping(candidate["charity"], "charity")
    _exact_keys(
        charity,
        {
            "transfer_evidence",
            "outcome_evidence",
            "impact_claim",
            "telemetry_grants_authority",
            "automatic_reward",
        },
        "charity",
    )
    if charity["transfer_evidence"] is not None or charity["outcome_evidence"] is not None:
        raise Gate1A1ViVError("baseline charity lane must remain target-only")
    if charity["impact_claim"] != "NO_CAUSAL_CLAIM":
        raise Gate1A1ViVError("charity impact cannot be claimed without evidence")
    if charity["telemetry_grants_authority"] is not False:
        raise Gate1A1ViVError("charity telemetry cannot grant authority")
    if charity["automatic_reward"] is not False:
        raise Gate1A1ViVError("charity feedback cannot become automatic reward")


def _economics(name: str, field: str, value: object):
    def mutator(candidate: MutableMapping[str, Any], seed: int) -> None:
        del seed
        candidate["economics"][name][field] = value
    return mutator


def _stale(candidate: MutableMapping[str, Any], seed: int) -> None:
    candidate["sources"][seed % 2]["fresh"] = False


def _conflict(candidate: MutableMapping[str, Any], seed: int) -> None:
    candidate["sources"][1]["observed_value"] += 1 + seed % 3


def _concentrate(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["sources"][1]["provenance_group"] = candidate["sources"][0]["provenance_group"]


def _weaken_classical(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["benchmark"]["classical_solver_strength"] = "HEURISTIC"


def _change_qaoa_pair(candidate: MutableMapping[str, Any], seed: int) -> None:
    candidate["benchmark"]["qaoa_qubo_sha256"] = f"{seed:064x}"[-64:]


def _cherry_pick_seed(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["benchmark"]["qaoa_seeds"] = [0]


def _suppress_runs(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["benchmark"]["complete_run_disclosure"] = False


def _production_language(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["language"]["profitability_claim"] = "PRODUCTION_PROFITABLE"


def _receipt_permission(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["gate"]["receipt_grants_permission"] = True


def _weaken_rollback(candidate: MutableMapping[str, Any], seed: int) -> None:
    candidate["gate"]["rollback_enabled"] = bool(seed % 2)
    candidate["gate"]["kill_switch_enabled"] = False


def _promote_gas_hypothesis(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["language"]["target_chain_gas_status"] = "MEASURED"


def _invent_charity_impact(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["charity"]["impact_claim"] = "PROVEN_CAUSAL_IMPACT"


def _charity_authority(candidate: MutableMapping[str, Any], seed: int) -> None:
    candidate["charity"]["telemetry_grants_authority"] = True
    candidate["charity"]["automatic_reward"] = bool(seed >= 0)


GATE1A1_CASES: tuple[AdversarialCase, ...] = (
    AdversarialCase("viv.gate1a1.omit_gas.v0.1", "Omit gas", "gas remains included", "critical", _economics("gas", "included", False)),
    AdversarialCase("viv.gate1a1.omit_protocol_fees.v0.1", "Omit protocol fees", "protocol fees remain included", "critical", _economics("protocol_fees", "included", False)),
    AdversarialCase("viv.gate1a1.suppress_slippage.v0.1", "Suppress slippage", "slippage remains measured", "critical", _economics("slippage", "value_bps", 0.0)),
    AdversarialCase("viv.gate1a1.inflate_liquidity.v0.1", "Inflate liquidity", "liquidity capacity remains measured", "critical", _economics("liquidity", "capacity", 1_000_000_000_000.0)),
    AdversarialCase("viv.gate1a1.erase_latency.v0.1", "Erase latency", "latency remains measured", "critical", _economics("latency", "included", False)),
    AdversarialCase("viv.gate1a1.promote_stale_telemetry.v0.1", "Promote stale telemetry", "stale sources cannot enter consensus", "critical", _stale),
    AdversarialCase("viv.gate1a1.false_consensus.v0.1", "Collapse conflict into false consensus", "conflicting values remain HOLD", "critical", _conflict),
    AdversarialCase("viv.gate1a1.disguised_concentration.v0.1", "Disguise shared provenance", "sources remain independently operated", "critical", _concentrate),
    AdversarialCase("viv.gate1a1.weaker_classical_baseline.v0.1", "Pair QAOA with weaker classical baseline", "classical baseline remains exact", "critical", _weaken_classical),
    AdversarialCase("viv.gate1a1.changed_qubo.v0.1", "Change paired QUBO", "QAOA and classical use identical QUBO", "critical", _change_qaoa_pair),
    AdversarialCase("viv.gate1a1.cherry_pick_seed.v0.1", "Cherry-pick favorable QAOA seed", "all precommitted seeds remain disclosed", "critical", _cherry_pick_seed),
    AdversarialCase("viv.gate1a1.suppress_failed_runs.v0.1", "Suppress failed or infeasible runs", "run disclosure remains complete", "critical", _suppress_runs),
    AdversarialCase("viv.gate1a1.testnet_profitability_language.v0.1", "Convert testnet edge into profitability language", "testnet remains research-only", "critical", _production_language),
    AdversarialCase("viv.gate1a1.receipt_to_permission.v0.1", "Convert receipt success into gate permission", "receipt evidence never grants permission", "critical", _receipt_permission),
    AdversarialCase("viv.gate1a1.weaken_rollback.v0.1", "Weaken rollback or kill switch", "rollback and kill switch remain enabled", "critical", _weaken_rollback),
    AdversarialCase("viv.gate1a1.gas_hypothesis_as_fact.v0.1", "Describe target-chain gas hypothesis as measured fact", "target-chain gas remains hypothesis", "high", _promote_gas_hypothesis),
    AdversarialCase("viv.gate1a1.charity_without_evidence.v0.1", "Claim charity impact without evidence", "impact requires transfer and outcome evidence", "critical", _invent_charity_impact),
    AdversarialCase("viv.gate1a1.charity_to_authority.v0.1", "Convert charity telemetry into reward or authority", "charity telemetry remains non-authoritative", "critical", _charity_authority),
)


def run_gate1a1_gauntlet(
    candidate: Mapping[str, Any],
    *,
    seed: int = 145,
    created_at: str = "1970-01-01T00:00:00Z",
) -> dict[str, Any]:
    return run_viv_gauntlet(
        candidate,
        validator=validate_gate1a1_evidence_bundle,
        validator_id=_VALIDATOR_ID,
        cases=GATE1A1_CASES,
        seed=seed,
        created_at=created_at,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Gate 1A.1 ViV mutations")
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=145)
    parser.add_argument("--created-at", default="1970-01-01T00:00:00Z")
    parser.add_argument("--receipt-out", type=Path)
    args = parser.parse_args(argv)

    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    if not isinstance(candidate, dict):
        raise Gate1A1ViVError("candidate JSON must be an object")
    receipt = run_gate1a1_gauntlet(
        deepcopy(candidate), seed=args.seed, created_at=args.created_at
    )
    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["overall_outcome"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
