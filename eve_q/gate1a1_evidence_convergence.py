"""Deterministic Gate 1A.1 evidence convergence and compact decision surface.

This module consumes a strict, inert evidence bundle and emits one content-addressed
review receipt. It does not collect telemetry, run optimizers, invoke verifiers,
activate Gate 1B, access wallets, sign, submit transactions, or move capital.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

CONTRACT_VERSION = "codex_gate1a1_evidence_convergence_v0.1"
BUNDLE_ARTIFACT_TYPE = "Gate1A1EvidenceBundle"
RECEIPT_ARTIFACT_TYPE = "Gate1A1EvidenceConvergenceReceipt"
DECISIONS = (
    "HOLD",
    "QAOA_RESEARCH_ONLY",
    "READY_FOR_GATE1B_REVIEW",
)
SECTION_KEYS = (
    "WORKFLOW",
    "SOURCE_QUORUM",
    "FRESHNESS",
    "ECONOMICS",
    "CLASSICAL_BASELINE",
    "QAOA_COMPARISON",
    "RUST_VERIFICATION",
    "ADVERSARIAL_RESULTS",
    "EXECUTION_LOCKS",
    "CHARITY_POSTURE",
    "ROLLBACK",
    "NEXT_DECISION",
)
BOUNDARY = {
    "artifact_is_command": False,
    "authority": False,
    "automatic_gate_promotion": False,
    "gate1b_activated": False,
    "may_execute": False,
    "may_sign": False,
    "may_submit_transaction": False,
    "may_access_wallet": False,
    "may_move_capital": False,
    "human_promotion_required": True,
}

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_BUNDLE_SCHEMA = _ROOT / "schemas" / "gate1a1_evidence_bundle_v0_1.schema.json"
_DEFAULT_RECEIPT_SCHEMA = _ROOT / "schemas" / "gate1a1_decision_receipt_v0_1.schema.json"
_DEFAULT_OUTPUT = _ROOT / "artifacts" / "gate1a1-evidence" / "decision-receipt.json"


class EvidenceConvergenceError(RuntimeError):
    """Raised when supplied evidence violates a strict convergence contract."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceConvergenceError(
            f"unable to load JSON {path}: {type(exc).__name__}: {exc}"
        ) from exc


def schema_errors(document: Any, schema: Mapping[str, Any]) -> tuple[str, ...]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(document),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    return tuple(
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    )


def require_schema(document: Any, schema: Mapping[str, Any], label: str) -> None:
    errors = schema_errors(document, schema)
    if errors:
        raise EvidenceConvergenceError(
            f"{label} schema validation failed: " + "; ".join(errors[:12])
        )


def _rust_reproducible(rust: Mapping[str, Any]) -> bool:
    required = (
        "source_commit_present",
        "build_command_present",
        "toolchain_pinned",
        "package_origin_recorded",
        "binary_hash_verified",
        "target_triple_recorded",
        "clean_tree",
        "schema_versions_match",
        "deterministic_replay",
    )
    return all(rust[name] is True for name in required)


def _charity_contract_complete(charity: Mapping[str, Any]) -> bool:
    return bool(
        charity["contract_complete"] is True
        and charity["simulation_only"] is True
        and charity["transfer_enabled"] is False
        and charity["impact_grants_authority"] is False
        and charity["no_data_semantics"] is True
    )


def _rollback_ready(rollback: Mapping[str, Any]) -> bool:
    return bool(
        rollback["kill_switch_ready"] is True and rollback["rollback_replay_passed"] is True
    )


def collect_hold_reasons(bundle: Mapping[str, Any]) -> tuple[str, ...]:
    source = bundle["source_quorum"]
    benchmark = bundle["benchmark"]
    rust = bundle["rust_verifier"]
    viv = bundle["viv"]
    economics = bundle["economics"]
    charity = bundle["charity"]
    rollback = bundle["rollback"]

    holds: list[str] = []

    if source["decision"] != "ACCEPT_OBSERVATION_ONLY":
        holds.append(f"SOURCE_{source['decision']}")
    if source["independent_source_count"] < 2:
        holds.append("HOLD_SOURCE_QUORUM")
    if source["material_disagreement"]:
        holds.append("HOLD_CONFLICT")
    if source["shared_provenance_concentration"]:
        holds.append("HOLD_CONCENTRATION")
    if source["stale_evidence"]:
        holds.append("HOLD_STALE")
    if source["unit_ambiguity"]:
        holds.append("HOLD_UNIT_AMBIGUITY")
    if source["missing_or_expired_review"]:
        holds.append("HOLD_SOURCE_REVIEW")

    benchmark_requirements = {
        "exact_pair_present": "HOLD_MISSING_EXACT_PAIR",
        "same_qubo_hash": "HOLD_QUBO_HASH_MISMATCH",
        "assumptions_identical": "HOLD_BENCHMARK_ASSUMPTION_DRIFT",
        "solver_versions_recorded": "HOLD_SOLVER_PROVENANCE",
        "resource_usage_recorded": "HOLD_RESOURCE_EVIDENCE",
        "repeated_seed_stability_evaluated": "HOLD_SEED_STABILITY_UNEVALUATED",
        "verifier_agreement": "HOLD_BENCHMARK_VERIFIER_DISAGREEMENT",
    }
    for field, reason in benchmark_requirements.items():
        if benchmark[field] is not True:
            holds.append(reason)

    rust_requirements = {
        "source_commit_present": "HOLD_RUST_SOURCE_COMMIT",
        "build_command_present": "HOLD_RUST_BUILD_COMMAND",
        "toolchain_pinned": "HOLD_RUST_TOOLCHAIN",
        "package_origin_recorded": "HOLD_RUST_PACKAGE_ORIGIN",
        "binary_hash_verified": "HOLD_UNVERIFIED_BINARY",
        "target_triple_recorded": "HOLD_RUST_TARGET_TRIPLE",
        "clean_tree": "HOLD_RUST_DIRTY_TREE",
        "schema_versions_match": "HOLD_RUST_SCHEMA_DRIFT",
        "deterministic_replay": "HOLD_RUST_REPLAY",
    }
    for field, reason in rust_requirements.items():
        if rust[field] is not True:
            holds.append(reason)

    if viv["required_mutations_complete"] is not True:
        holds.append("HOLD_VIV_COVERAGE")
    if viv["critical_escaped"] > 0:
        holds.append("HOLD_VIV_CRITICAL_ESCAPE")

    if economics["complete"] is not True:
        holds.append("HOLD_INCOMPLETE_ECONOMICS")
    if economics["units_explicit"] is not True:
        holds.append("HOLD_ECONOMIC_UNITS")
    if economics["frictions_included"] is not True:
        holds.append("HOLD_MISSING_FRICTIONS")

    if not _charity_contract_complete(charity):
        holds.append("HOLD_CHARITY_TARGET_CONTRACT")
    if not _rollback_ready(rollback):
        holds.append("HOLD_ROLLBACK")

    return tuple(sorted(set(holds)))


def decide(bundle: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    holds = collect_hold_reasons(bundle)
    if holds:
        return "HOLD", holds
    if bundle["benchmark"]["qaoa_value_demonstrated"] is not True:
        return "QAOA_RESEARCH_ONLY", ()
    return "READY_FOR_GATE1B_REVIEW", ()


def _compact_report(bundle: Mapping[str, Any], decision: str) -> dict[str, str]:
    source = bundle["source_quorum"]
    benchmark = bundle["benchmark"]
    rust = bundle["rust_verifier"]
    viv = bundle["viv"]
    economics = bundle["economics"]
    charity = bundle["charity"]
    rollback = bundle["rollback"]

    report = {
        "WORKFLOW": "GATE_1A1_EVIDENCE_CONVERGENCE",
        "SOURCE_QUORUM": str(source["decision"]),
        "FRESHNESS": "HOLD_STALE" if source["stale_evidence"] else "FRESH",
        "ECONOMICS": "COMPLETE" if economics["complete"] else "HOLD_INCOMPLETE",
        "CLASSICAL_BASELINE": (
            "EXACT_PAIR_PRESENT" if benchmark["exact_pair_present"] else "HOLD_MISSING_PAIR"
        ),
        "QAOA_COMPARISON": (
            "VALUE_DEMONSTRATED" if benchmark["qaoa_value_demonstrated"] else "RESEARCH_ONLY"
        ),
        "RUST_VERIFICATION": ("REPRODUCIBLE" if _rust_reproducible(rust) else "HOLD_UNVERIFIED"),
        "ADVERSARIAL_RESULTS": (
            f"BLOCKED={viv['blocked']};CRITICAL_ESCAPED={viv['critical_escaped']}"
        ),
        "EXECUTION_LOCKS": "LOCKED",
        "CHARITY_POSTURE": (
            "SIMULATION_ONLY_CONTRACT_COMPLETE"
            if _charity_contract_complete(charity)
            else "HOLD_TARGET_CONTRACT"
        ),
        "ROLLBACK": "READY" if _rollback_ready(rollback) else "HOLD",
        "NEXT_DECISION": decision,
    }
    if tuple(report) != SECTION_KEYS:
        raise EvidenceConvergenceError("compact report section order drifted")
    return report


def _evidence_summary(bundle: Mapping[str, Any]) -> dict[str, Any]:
    benchmark = bundle["benchmark"]
    viv = bundle["viv"]
    return {
        "source_quorum_decision": bundle["source_quorum"]["decision"],
        "independent_source_count": bundle["source_quorum"]["independent_source_count"],
        "exact_pair_present": benchmark["exact_pair_present"],
        "same_qubo_hash": benchmark["same_qubo_hash"],
        "qaoa_value_demonstrated": benchmark["qaoa_value_demonstrated"],
        "rust_reproducible": _rust_reproducible(bundle["rust_verifier"]),
        "viv_blocked": viv["blocked"],
        "viv_critical_escaped": viv["critical_escaped"],
        "economics_complete": bundle["economics"]["complete"],
        "charity_contract_complete": _charity_contract_complete(bundle["charity"]),
        "rollback_ready": _rollback_ready(bundle["rollback"]),
    }


def build_receipt(bundle: Mapping[str, Any], *, generated_at: str) -> dict[str, Any]:
    decision, holds = decide(bundle)
    receipt: dict[str, Any] = {
        "artifact_type": RECEIPT_ARTIFACT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "generated_at": generated_at,
        "evidence_sha256": sha256_hex(bundle),
        "decision": decision,
        "hold_reasons": list(holds),
        "qaoa_status": (
            "CANDIDATE_FOR_FURTHER_TESTING"
            if bundle["benchmark"]["qaoa_value_demonstrated"]
            else "RESEARCH_ONLY"
        ),
        "compact_report": _compact_report(bundle, decision),
        "evidence_summary": _evidence_summary(bundle),
        "boundary": dict(BOUNDARY),
        "receipt_sha256": "0" * 64,
    }
    stable_material = dict(receipt)
    stable_material.pop("generated_at")
    stable_material.pop("receipt_sha256")
    receipt["receipt_sha256"] = sha256_hex(stable_material)
    return receipt


def render_summary(receipt: Mapping[str, Any]) -> str:
    lines = ["CODEX GATE 1A.1 EVIDENCE CONVERGENCE v0.1"]
    compact = receipt["compact_report"]
    lines.extend(f"{key}: {compact[key]}" for key in SECTION_KEYS)
    if receipt["hold_reasons"]:
        lines.append("HOLDS: " + ", ".join(receipt["hold_reasons"]))
    lines.extend(
        (
            f"EVIDENCE: {receipt['evidence_sha256']}",
            f"RECEIPT: {receipt['receipt_sha256']}",
            "AUTHORITY: false",
            "GATE_1B_ACTIVATED: false",
            "CAPITAL: LOCKED",
        )
    )
    return "\n".join(lines)


def write_receipt(
    receipt: Mapping[str, Any],
    *,
    output: Path,
    receipt_schema: Mapping[str, Any],
) -> tuple[Path, Path]:
    require_schema(receipt, receipt_schema, "decision receipt")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path = output.with_suffix(".txt")
    summary_path.write_text(render_summary(receipt) + "\n", encoding="utf-8")
    return output, summary_path


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="codex-gate1a1",
        description=(
            "Converge inert Gate 1A.1 evidence into HOLD, QAOA_RESEARCH_ONLY, "
            "or READY_FOR_GATE1B_REVIEW without activating any later gate."
        ),
    )
    result.add_argument("--evidence", type=Path, required=True)
    result.add_argument("--evidence-schema", type=Path, default=_DEFAULT_BUNDLE_SCHEMA)
    result.add_argument("--receipt-schema", type=Path, default=_DEFAULT_RECEIPT_SCHEMA)
    result.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    result.add_argument("--generated-at")
    result.add_argument("--json", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        bundle = load_json(args.evidence)
        bundle_schema = load_json(args.evidence_schema)
        receipt_schema = load_json(args.receipt_schema)
        require_schema(bundle, bundle_schema, "evidence bundle")
        receipt = build_receipt(bundle, generated_at=args.generated_at or utc_now())
        paths = write_receipt(receipt, output=args.output, receipt_schema=receipt_schema)
    except (EvidenceConvergenceError, KeyError, OSError, TypeError, ValueError) as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(render_summary(receipt))
        print(f"Decision receipt: {paths[0]}")
        print(f"Compact summary: {paths[1]}")
    return 2 if receipt["decision"] == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
