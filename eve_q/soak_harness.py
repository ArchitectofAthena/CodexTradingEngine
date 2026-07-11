from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from eve_q.proposal_artifact import sha256_hex, validate_proposal_semantics
from shadow_cycle_runner import run_shadow_cycle


DEFAULT_CYCLES = 100
DEFAULT_SEED = 424242
CONTRACT_VERSION = "eve_q_cross_repo_v0.1"


@dataclass(frozen=True)
class ControlPlaneModules:
    validator: Any
    builders: Any
    schema_root: Path


class SoakHarnessError(RuntimeError):
    pass


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SoakHarnessError(f"could not load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_control_plane(root: Path) -> ControlPlaneModules:
    validator_path = root / "tools" / "validate_eve_q_contract_v0_1.py"
    builders_path = root / "tests" / "test_eve_q_cross_repo_contract_v0_1.py"
    schema_root = root / "schemas"

    for path in (validator_path, builders_path, schema_root):
        if not path.exists():
            raise SoakHarnessError(f"missing control-plane dependency: {path}")

    return ControlPlaneModules(
        validator=load_module("eve_q_soak_control_validator", validator_path),
        builders=load_module("eve_q_soak_control_builders", builders_path),
        schema_root=schema_root,
    )


def decimal_step(value: int, places: int = 6) -> Decimal:
    return Decimal(value) / (Decimal(10) ** places)


def perturbed_routes(index: int, seed: int) -> list[dict[str, Any]]:
    """Create deterministic, bounded route perturbations for one cycle."""
    rng = random.Random((seed * 1_000_003) + index)

    route_a = {
        "route": "mock-base-weth-usdc-weth",
        "chain": "base",
        "expected_profit_eth": Decimal("0.018")
        + decimal_step(rng.randint(0, 8_000)),
        "gas_cost_eth": Decimal("0.0035")
        + decimal_step(rng.randint(0, 2_000)),
        "slippage_eth": Decimal("0.0005")
        + decimal_step(rng.randint(0, 1_200)),
        "safety_margin_eth": Decimal("0.0010")
        + decimal_step(rng.randint(0, 1_000)),
    }
    route_b = {
        "route": "mock-base-weth-dai-weth",
        "chain": "base",
        "expected_profit_eth": Decimal("0.014")
        + decimal_step(rng.randint(0, 9_000)),
        "gas_cost_eth": Decimal("0.0030")
        + decimal_step(rng.randint(0, 2_500)),
        "slippage_eth": Decimal("0.0007")
        + decimal_step(rng.randint(0, 1_500)),
        "safety_margin_eth": Decimal("0.0008")
        + decimal_step(rng.randint(0, 1_200)),
    }

    routes = [route_a, route_b]
    if index % 2:
        routes.reverse()
    return routes


def build_control_chain(
    proposal: dict[str, Any],
    modules: ControlPlaneModules,
) -> list[dict[str, Any]]:
    validator = modules.validator
    builders = modules.builders

    proposal_hash = validator.artifact_sha256(proposal)
    evidence = builders.evidence(proposal_hash)
    evidence_hash = validator.artifact_sha256(evidence)
    gate = builders.gate(proposal_hash, evidence_hash)
    gate_hash = validator.artifact_sha256(gate)
    promotion = builders.promotion(proposal_hash, gate_hash)
    promotion_hash = validator.artifact_sha256(promotion)
    registry = builders.registry(gate_hash, [proposal_hash, evidence_hash])
    execution = builders.execution(proposal_hash, gate_hash, promotion_hash)

    return [proposal, evidence, gate, promotion, registry, execution]


def finding_codes(findings: list[Any]) -> set[str]:
    return {str(getattr(finding, "code", "unknown")) for finding in findings}


def mutation_checks(
    proposal: dict[str, Any],
    modules: ControlPlaneModules,
    now: datetime,
) -> dict[str, bool]:
    """Return True only when each invalid mutation fails closed."""
    validator = modules.validator
    schema_root = modules.schema_root
    chain = build_control_chain(proposal, modules)

    stale = copy.deepcopy(proposal)
    stale["ttl"]["expires_at"] = iso_z(now - timedelta(seconds=1))
    stale_rejected = "proposal TTL is stale" in validate_proposal_semantics(
        stale,
        now=now,
    )

    missing_provenance = copy.deepcopy(proposal)
    missing_provenance.pop("bounded_inputs", None)
    missing_rejected = bool(
        validate_proposal_semantics(missing_provenance, now=now)
    ) and bool(validator.validate_artifact(missing_provenance, schema_root))

    self_promotion = copy.deepcopy(proposal)
    self_promotion["authority"] = True
    self_promotion["human_promotion_required"] = False
    self_promotion["prohibited_actions"] = [
        action
        for action in self_promotion["prohibited_actions"]
        if action != "self_promotion"
    ]
    self_promotion_rejected = bool(
        validate_proposal_semantics(self_promotion, now=now)
    ) and bool(validator.validate_artifact(self_promotion, schema_root))

    herding_evidence = copy.deepcopy(chain[1])
    herding_evidence["evidence_state"] = "HERDING_RISK"
    herding_gate = copy.deepcopy(chain[2])
    herding_gate["evidence_bundle_sha256"] = validator.artifact_sha256(
        herding_evidence
    )
    herding_gate["evidence_state"] = "HERDING_RISK"
    herding_gate["decision"] = "COMMIT"
    herding_commit_rejected = bool(
        validator.validate_artifact(herding_gate, schema_root)
    )
    herding_gate["decision"] = "HOLD"
    herding_hold_valid = not validator.validate_artifact(herding_gate, schema_root)

    new_contradiction = copy.deepcopy(chain[2])
    new_contradiction["contradiction_status"] = "new"
    new_contradiction["decision"] = "HOLD"
    new_not_reopen_rejected = bool(
        validator.validate_artifact(new_contradiction, schema_root)
    )
    new_contradiction["decision"] = "REOPEN"
    new_reopen_valid = not validator.validate_artifact(
        new_contradiction,
        schema_root,
    )

    inferred_execution = copy.deepcopy(chain[-1])
    inferred_execution["observed"] = False
    inferred_execution["inferred"] = True
    inferred_rejected = bool(
        validator.validate_artifact(inferred_execution, schema_root)
    )

    capital_without_promotion = copy.deepcopy(chain)
    execution = capital_without_promotion[-1]
    execution["execution_mode"] = "manual_external"
    execution["executor"] = {
        "executor_id": "soak-invalid-manual-executor",
        "executor_type": "human_external",
    }
    execution["capital_movement_occurred"] = True
    execution["human_promotion_receipt_sha256"] = "f" * 64
    capital_findings = validator.validate_chain(
        capital_without_promotion,
        schema_root,
    )
    capital_rejected = (
        "capital_movement_without_known_promotion"
        in finding_codes(capital_findings)
    )

    hash_mismatch = copy.deepcopy(chain)
    hash_mismatch[2]["evidence_bundle_sha256"] = "e" * 64
    hash_findings = validator.validate_chain(hash_mismatch, schema_root)
    hash_mismatch_rejected = "unknown_reference" in finding_codes(hash_findings)

    return {
        "stale_ttl_rejected": stale_rejected,
        "missing_provenance_rejected": missing_rejected,
        "self_promotion_rejected": self_promotion_rejected,
        "herding_commit_rejected": herding_commit_rejected,
        "herding_hold_valid": herding_hold_valid,
        "new_contradiction_not_reopen_rejected": new_not_reopen_rejected,
        "new_contradiction_reopen_valid": new_reopen_valid,
        "inferred_execution_rejected": inferred_rejected,
        "capital_without_promotion_rejected": capital_rejected,
        "hash_mismatch_rejected": hash_mismatch_rejected,
    }


def append_jsonl(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(document, sort_keys=True) + "\n")


def run_soak_campaign(
    *,
    cycles: int,
    seed: int,
    output_dir: Path,
    producer_commit: str,
    control_plane_root: Path,
    started_at: datetime | None = None,
) -> dict[str, Any]:
    if cycles < 1:
        raise SoakHarnessError("cycles must be at least 1")
    if len(producer_commit) != 40:
        raise SoakHarnessError("producer_commit must be a 40-character commit SHA")

    modules = load_control_plane(control_plane_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    cycle_root = output_dir / "cycles"
    chain_root = output_dir / "chains"
    chain_root.mkdir(parents=True, exist_ok=True)
    ledger_path = output_dir / "campaign.jsonl"
    summary_path = output_dir / "summary.json"

    proposal_schema = json.loads(
        Path("schemas/proposal_artifact_v0_1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    proposal_validator = Draft202012Validator(
        proposal_schema,
        format_checker=FormatChecker(),
    )

    campaign_start = (started_at or datetime.now(timezone.utc)).astimezone(
        timezone.utc
    )
    primary_hashes: list[str] = []
    replay_hashes: list[str] = []
    selected_scores: set[str] = set()
    selected_routes: set[str] = set()
    proposal_failures = 0
    chain_failures = 0
    unauthorized_promotions = 0
    replay_failures = 0
    first_proposal: dict[str, Any] | None = None

    for index in range(cycles):
        issued = campaign_start + timedelta(seconds=index)
        completed = issued + timedelta(milliseconds=250)
        cycle_id = f"soak-{seed}-{index:04d}"
        routes = perturbed_routes(index, seed)

        run = run_shadow_cycle(
            output_dir=cycle_root,
            cycle_id=cycle_id,
            candidate_routes=routes,
            producer_commit=producer_commit,
            impact_category="medical_access",
            created_at=iso_z(issued),
            completed_at=iso_z(completed),
        )
        proposal = run.proposal_artifact
        if first_proposal is None:
            first_proposal = copy.deepcopy(proposal)

        schema_errors = list(proposal_validator.iter_errors(proposal))
        semantic_errors = validate_proposal_semantics(
            proposal,
            now=campaign_start,
        )
        if schema_errors or semantic_errors or not run.validation.valid:
            proposal_failures += 1

        proposal_hash = sha256_hex(proposal)
        primary_hashes.append(proposal_hash)
        selected_scores.add(str(run.receipt.actual_profit_eth))
        selected_routes.add(str(run.receipt.selected_route))

        chain = build_control_chain(proposal, modules)
        chain_findings = modules.validator.validate_chain(
            chain,
            modules.schema_root,
        )
        if chain_findings:
            chain_failures += 1

        gate = chain[2]
        promotion = chain[3]
        execution = chain[-1]
        if (
            gate.get("execution_authority") is not False
            or gate.get("capital_movement_authorized") is not False
            or promotion.get("may_execute") is not False
            or execution.get("capital_movement_occurred") is not False
        ):
            unauthorized_promotions += 1

        chain_path = chain_root / f"{cycle_id}.json"
        chain_path.write_text(
            json.dumps(chain, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        replay = run_shadow_cycle(
            output_dir=cycle_root,
            cycle_id=cycle_id,
            candidate_routes=routes,
            producer_commit=producer_commit,
            impact_category="medical_access",
            created_at=iso_z(issued),
            completed_at=iso_z(completed),
        )
        replay_hash = sha256_hex(replay.proposal_artifact)
        replay_hashes.append(replay_hash)
        if replay_hash != proposal_hash:
            replay_failures += 1

        append_jsonl(
            ledger_path,
            {
                "event_type": "eve_q_soak_cycle",
                "contract_version": CONTRACT_VERSION,
                "cycle_index": index,
                "cycle_id": cycle_id,
                "proposal_sha256": proposal_hash,
                "replay_sha256": replay_hash,
                "deterministic_replay": replay_hash == proposal_hash,
                "receipt_valid": run.validation.valid,
                "trust_increment_allowed": run.validation.trust_increment_allowed,
                "selected_route": run.receipt.selected_route,
                "actual_profit_eth": str(run.receipt.actual_profit_eth),
                "charity_due_eth": str(run.receipt.charity_due_eth),
                "proposal_schema_valid": not schema_errors,
                "proposal_semantic_valid": not semantic_errors,
                "control_chain_valid": not chain_findings,
                "authority": proposal["authority"],
                "human_promotion_required": proposal[
                    "human_promotion_required"
                ],
                "autonomous_capital_movement": proposal[
                    "autonomous_capital_movement"
                ],
                "capital_movement_occurred": execution[
                    "capital_movement_occurred"
                ],
            },
        )

    assert first_proposal is not None
    mutations = mutation_checks(first_proposal, modules, campaign_start)

    acceptance = {
        "all_cycles_valid": proposal_failures == 0 and chain_failures == 0,
        "zero_unauthorized_promotions": unauthorized_promotions == 0,
        "all_replays_deterministic": replay_failures == 0,
        "route_scores_changed": len(selected_scores) > 1,
        "route_selection_exercised": len(selected_routes) > 1,
        **mutations,
    }
    ok = all(acceptance.values())

    summary = {
        "ok": ok,
        "contract_version": CONTRACT_VERSION,
        "campaign": {
            "cycles_requested": cycles,
            "seed": seed,
            "started_at": iso_z(campaign_start),
            "producer_commit": producer_commit,
            "control_plane_root": str(control_plane_root),
            "output_dir": str(output_dir),
        },
        "results": {
            "proposal_failures": proposal_failures,
            "chain_failures": chain_failures,
            "unauthorized_promotions": unauthorized_promotions,
            "replay_failures": replay_failures,
            "distinct_selected_scores": len(selected_scores),
            "distinct_selected_routes": len(selected_routes),
            "primary_hash_count": len(primary_hashes),
            "replay_hash_count": len(replay_hashes),
        },
        "mutations": mutations,
        "acceptance": acceptance,
        "artifacts": {
            "ledger": str(ledger_path),
            "summary": str(summary_path),
            "chains": str(chain_root),
        },
        "authority": False,
        "may_execute": False,
        "may_move_capital": False,
        "human_promotion_required": True,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic EVE_Q++ shadow perturbation and soak checks."
    )
    parser.add_argument("--cycles", type=int, default=DEFAULT_CYCLES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--producer-commit", required=True)
    parser.add_argument(
        "--control-plane-root",
        type=Path,
        default=Path.home() / "spiralbloom-os",
    )
    args = parser.parse_args()

    try:
        summary = run_soak_campaign(
            cycles=args.cycles,
            seed=args.seed,
            output_dir=args.output_dir,
            producer_commit=args.producer_commit,
            control_plane_root=args.control_plane_root,
        )
    except (SoakHarnessError, OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
