"""Bounded Gate 1A alpha orchestration and progressive result surface.

The operator carries procedure, not authority. It can explain the environment,
stop on source or draft holds, and run one already reviewed local fixture through
the simulation-safe research path. It has no network capture, proposal, wallet,
signing, transaction, execution, or capital surface.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from eve_q.alpha_doctor import (
    DoctorResult,
    collect_facts,
    evaluate_facts,
)
from eve_q.gate1_readonly_runtime import parse_utc
from eve_q.research_cli import build_report, write_report
from eve_q.telemetry_draft_fixture import verify_draft_hash
from shadow_cycle_runner import run_shadow_cycle

OPERATOR_VERSION = "codex-alpha-operator-v0.1"
REPORT_ARTIFACT_TYPE = "CodexAlphaOperatorReport"
RESULT_KEYS = (
    "PIPELINE",
    "SOURCE",
    "FRESHNESS",
    "ECONOMICS",
    "CLASSICAL_BASELINE",
    "QAOA_COMPARISON",
    "RUST_VERIFICATION",
    "EXECUTION",
    "ROLLBACK",
)
REQUIRED_ROUTE_FIELDS = frozenset(
    {
        "route",
        "chain",
        "expected_profit_eth",
        "gas_cost_eth",
        "slippage_eth",
        "safety_margin_eth",
    }
)
AUTHORITY_BOUNDARY = {
    "authority": False,
    "artifact_is_command": False,
    "network_capture_allowed": False,
    "may_generate_live_proposal": False,
    "may_execute": False,
    "may_sign": False,
    "may_submit_transaction": False,
    "may_move_capital": False,
}

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_REGISTRY = _ROOT / "registry" / "alpha_testnet_sources_v0_1.json"
_DEFAULT_REGISTRY_SCHEMA = _ROOT / "schemas" / "alpha_testnet_source_registry_v0_1.schema.json"
_DEFAULT_DRAFT_SCHEMA = _ROOT / "schemas" / "telemetry_draft_fixture_v0_1.schema.json"
_DEFAULT_REPORT_SCHEMA = _ROOT / "schemas" / "alpha_operator_report_v0_1.schema.json"


class AlphaOperatorError(RuntimeError):
    """Raised when the alpha procedure reaches a fail-closed hold."""


@dataclass(frozen=True, slots=True)
class ResearchResult:
    report: Mapping[str, Any]
    report_json_path: str
    report_markdown_path: str


@dataclass(frozen=True, slots=True)
class AlphaOperatorResult:
    report: Mapping[str, Any]
    summary_text: str
    exit_code: int


ResearchRunner = Callable[[Mapping[str, Any], Path, str, str], ResearchResult]


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AlphaOperatorError(
            f"unable to load JSON {path}: {type(exc).__name__}: {exc}"
        ) from exc


def _schema_errors(document: Any, schema: Mapping[str, Any]) -> tuple[str, ...]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(document),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    return tuple(
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    )


def _require_schema(document: Any, schema: Mapping[str, Any], label: str) -> None:
    errors = _schema_errors(document, schema)
    if errors:
        raise AlphaOperatorError(f"{label} schema validation failed: " + "; ".join(errors[:8]))


def _doctor_snapshot(doctor: DoctorResult) -> dict[str, Any]:
    payload = doctor.as_dict()
    return {
        "status": payload["status"],
        "holds": payload["holds"],
        "warnings": payload["warnings"],
        "repository": payload["repository"],
        "python": payload["python"],
        "gate_posture": payload["gate_posture"],
        "kill_switch_active": payload["kill_switch_active"],
        "rust_verifier": payload["rust_verifier"],
        "source_registry": payload["source_registry"],
        "authority": payload["authority"],
    }


def _rust_status(doctor: DoctorResult) -> str:
    state = doctor.facts.rust_verifier_state
    if state.startswith("HOLD_"):
        return "HOLD"
    return "NOT_RUN"


def _base_surface(doctor: DoctorResult) -> dict[str, str]:
    return {
        "PIPELINE": "NOT_RUN",
        "SOURCE": "NOT_RUN",
        "FRESHNESS": "NOT_RUN",
        "ECONOMICS": "NOT_RUN",
        "CLASSICAL_BASELINE": "NOT_RUN",
        "QAOA_COMPARISON": "NOT_RUN",
        "RUST_VERIFICATION": _rust_status(doctor),
        "EXECUTION": "LOCKED",
        "ROLLBACK": ("HOLD_KILL_SWITCH_ACTIVE" if doctor.facts.kill_switch_active else "READY"),
    }


def _stable_receipt_material(report: Mapping[str, Any]) -> dict[str, Any]:
    research = report.get("research")
    stable_research = None
    if isinstance(research, Mapping):
        embedded = research.get("report")
        stable_research = {
            "summary": embedded.get("summary") if isinstance(embedded, Mapping) else None,
            "verification": (
                embedded.get("verification") if isinstance(embedded, Mapping) else None
            ),
            "boundary": embedded.get("boundary") if isinstance(embedded, Mapping) else None,
        }
    return {
        "artifact_type": report["artifact_type"],
        "contract_version": report["contract_version"],
        "mode": report["mode"],
        "doctor": report["doctor"],
        "source": report["source"],
        "draft": report["draft"],
        "result_surface": report["result_surface"],
        "research": stable_research,
        "rollback": report["rollback"],
        "boundary": report["boundary"],
    }


def _finalize_report(report: dict[str, Any]) -> dict[str, Any]:
    report["receipt_sha256"] = sha256_hex(_stable_receipt_material(report))
    return report


def _report_template(
    *,
    mode: str,
    doctor: DoctorResult,
    surface: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "artifact_type": REPORT_ARTIFACT_TYPE,
        "contract_version": OPERATOR_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": mode,
        "receipt_sha256": "0" * 64,
        "doctor": _doctor_snapshot(doctor),
        "source": None,
        "draft": None,
        "research": None,
        "result_surface": dict(surface),
        "expected_observed": {
            "expected_behavior": "Operator supplies expected behavior in the filed alpha report.",
            "observed_behavior": "Generated result surface and linked artifacts record observed behavior.",
        },
        "rollback": {
            "kill_switch_active": doctor.facts.kill_switch_active,
            "kill_switch_variable": "EVE_Q_GATE1_KILL_SWITCH",
            "rollback_state": surface["ROLLBACK"],
        },
        "reproduction": {
            "repository_commit": doctor.facts.commit_sha,
            "python_version": doctor.facts.python_version,
            "command": None,
        },
        "publication_safety": (
            "Do not publish secrets, wallet material, private logs, personal data, "
            "or sensitive exploit details."
        ),
        "boundary": dict(AUTHORITY_BOUNDARY),
    }


def status_result(doctor: DoctorResult) -> AlphaOperatorResult:
    surface = _base_surface(doctor)
    if doctor.status == "HOLD":
        surface["PIPELINE"] = "HOLD"
        surface["SOURCE"] = "HOLD_DOCTOR"
    elif not doctor.facts.registry.eligible_source_ids:
        surface["PIPELINE"] = "HOLD"
        surface["SOURCE"] = "HOLD_NO_ELIGIBLE_SOURCE"
    else:
        surface["PIPELINE"] = "READY"
        surface["SOURCE"] = "ELIGIBLE"

    report = _report_template(mode="status", doctor=doctor, surface=surface)
    report["source"] = {
        "registry_sha256": doctor.facts.registry.registry_sha256,
        "eligible_source_ids": list(doctor.facts.registry.eligible_source_ids),
        "hold_source_ids": list(doctor.facts.registry.hold_source_ids),
        "rejected_source_ids": list(doctor.facts.registry.rejected_source_ids),
    }
    report["reproduction"]["command"] = "codex-alpha-run status"
    finalized = _finalize_report(report)
    return AlphaOperatorResult(
        report=finalized,
        summary_text=render_summary(finalized),
        exit_code=2 if surface["PIPELINE"] == "HOLD" else 0,
    )


def _validate_reviewed_draft(
    draft: Mapping[str, Any],
    *,
    expected_draft_hash: str,
    draft_schema: Mapping[str, Any],
    doctor: DoctorResult,
    now: datetime,
) -> Mapping[str, Any]:
    _require_schema(draft, draft_schema, "reviewed draft")
    try:
        verify_draft_hash(draft)
    except Exception as exc:
        raise AlphaOperatorError(str(exc)) from exc
    if draft["draft_hash"] != expected_draft_hash:
        raise AlphaOperatorError("expected draft hash does not match the exact draft")
    review = draft["operator_review"]
    if review["state"] != "REVIEWED_FOR_LOCAL_SIMULATION":
        raise AlphaOperatorError("draft is not reviewed for local simulation")
    if review["reviewed_draft_hash"] != expected_draft_hash:
        raise AlphaOperatorError("operator review does not bind the exact draft hash")
    if draft["local_simulation_eligible"] is not True:
        raise AlphaOperatorError("draft is not eligible for local simulation")
    if draft["draft_material"]["missing_assumptions"]:
        raise AlphaOperatorError("draft still contains missing economic assumptions")
    expiry = parse_utc(draft["freshness"]["expires_at"])
    if expiry < now.astimezone(timezone.utc):
        raise AlphaOperatorError("reviewed draft is stale")

    source_review = draft["draft_material"]["source_review"]
    source_id = str(source_review["source_id"])
    if source_id not in doctor.facts.registry.eligible_source_ids:
        raise AlphaOperatorError("reviewed draft source is not currently ELIGIBLE")
    if source_review["registry_sha256"] != doctor.facts.registry.registry_sha256:
        raise AlphaOperatorError("reviewed draft registry hash does not match current registry")

    for boundary in (
        draft["authority"],
        draft["draft_material"]["authority"],
    ):
        if any(value is not False for value in boundary.values()):
            raise AlphaOperatorError("reviewed draft attempts to widen authority")

    route = draft["draft_material"]["local_route_fixture"]
    missing = sorted(REQUIRED_ROUTE_FIELDS - set(route))
    if missing:
        raise AlphaOperatorError("reviewed route fixture is missing fields: " + ", ".join(missing))
    return copy.deepcopy(route)


def _default_research_runner(
    route: Mapping[str, Any],
    output_dir: Path,
    cycle_id: str,
    producer_commit: str,
) -> ResearchResult:
    run = run_shadow_cycle(
        output_dir=output_dir / "cycle",
        cycle_id=cycle_id,
        candidate_routes=[dict(route)],
        producer_commit=producer_commit,
    )
    report = build_report(run)
    json_path, markdown_path = write_report(report, output_dir)
    return ResearchResult(
        report=report,
        report_json_path=str(json_path),
        report_markdown_path=str(markdown_path),
    )


def _paired_evidence_states(research_report: Mapping[str, Any]) -> tuple[str, str, bool]:
    classical = research_report.get("classical_baseline")
    qaoa = research_report.get("qaoa_comparison")
    if qaoa is not None and classical is None:
        return "HOLD_MISSING_CLASSICAL_PAIR", "HOLD_UNPAIRED_QAOA", False
    classical_state = "NOT_AVAILABLE" if classical is None else "AVAILABLE"
    qaoa_state = "NOT_AVAILABLE" if qaoa is None else "AVAILABLE_PAIRED"
    return classical_state, qaoa_state, True


def simulate_reviewed_result(
    *,
    doctor: DoctorResult,
    draft: Mapping[str, Any],
    expected_draft_hash: str,
    draft_schema: Mapping[str, Any],
    output_dir: Path,
    cycle_id: str,
    producer_commit: str,
    now: datetime,
    research_runner: ResearchRunner = _default_research_runner,
) -> AlphaOperatorResult:
    surface = _base_surface(doctor)
    if doctor.status == "HOLD":
        surface["PIPELINE"] = "HOLD"
        surface["SOURCE"] = "HOLD_DOCTOR"
        report = _report_template(
            mode="simulate-reviewed",
            doctor=doctor,
            surface=surface,
        )
        report["reproduction"]["command"] = "codex-alpha-run simulate-reviewed"
        finalized = _finalize_report(report)
        return AlphaOperatorResult(
            report=finalized,
            summary_text=render_summary(finalized),
            exit_code=2,
        )

    try:
        route = _validate_reviewed_draft(
            draft,
            expected_draft_hash=expected_draft_hash,
            draft_schema=draft_schema,
            doctor=doctor,
            now=now,
        )
    except AlphaOperatorError as exc:
        surface["PIPELINE"] = "HOLD"
        surface["SOURCE"] = "HOLD_DRAFT"
        surface["FRESHNESS"] = "HOLD"
        report = _report_template(
            mode="simulate-reviewed",
            doctor=doctor,
            surface=surface,
        )
        report["draft"] = {
            "draft_hash": draft.get("draft_hash"),
            "expected_draft_hash": expected_draft_hash,
            "validation_hold": str(exc),
        }
        report["reproduction"]["command"] = "codex-alpha-run simulate-reviewed"
        finalized = _finalize_report(report)
        return AlphaOperatorResult(
            report=finalized,
            summary_text=render_summary(finalized),
            exit_code=2,
        )

    research = research_runner(route, output_dir / "research", cycle_id, producer_commit)
    research_report = research.report
    summary = research_report.get("summary", {})
    boundary = research_report.get("boundary", {})
    if (
        boundary.get("authority") is not False
        or boundary.get("may_execute") is not False
        or boundary.get("may_move_capital") is not False
    ):
        raise AlphaOperatorError("research report attempts to widen authority")

    classical_state, qaoa_state, paired = _paired_evidence_states(research_report)
    surface.update(
        {
            "PIPELINE": str(summary.get("pipeline", "HOLD")),
            "SOURCE": "ELIGIBLE",
            "FRESHNESS": "FRESH",
            "ECONOMICS": str(summary.get("economics", "NOT_AVAILABLE")),
            "CLASSICAL_BASELINE": classical_state,
            "QAOA_COMPARISON": qaoa_state,
            "RUST_VERIFICATION": str(
                research_report.get("rust_verification", {}).get(
                    "state",
                    "NOT_RUN",
                )
            ),
            "EXECUTION": "LOCKED",
            "ROLLBACK": "READY",
        }
    )
    if not paired:
        surface["PIPELINE"] = "HOLD"

    material = draft["draft_material"]
    report = _report_template(
        mode="simulate-reviewed",
        doctor=doctor,
        surface=surface,
    )
    report["source"] = {
        "source_id": material["source_review"]["source_id"],
        "registry_sha256": material["source_review"]["registry_sha256"],
        "network": material["network"],
        "snapshot": material["snapshot"],
    }
    report["draft"] = {
        "draft_id": draft["draft_id"],
        "draft_hash": draft["draft_hash"],
        "review_state": draft["operator_review"]["state"],
        "reviewed_draft_hash": draft["operator_review"]["reviewed_draft_hash"],
        "assumption_count": len(material["inferred_assumptions"]),
        "route_fixture_sha256": sha256_hex(route),
    }
    report["research"] = {
        "report": copy.deepcopy(dict(research_report)),
        "report_json_path": research.report_json_path,
        "report_markdown_path": research.report_markdown_path,
    }
    report["reproduction"] = {
        "repository_commit": producer_commit,
        "python_version": doctor.facts.python_version,
        "command": (
            "codex-alpha-run simulate-reviewed "
            f"--expected-draft-hash {expected_draft_hash} "
            f"--cycle-id {cycle_id}"
        ),
    }
    finalized = _finalize_report(report)
    return AlphaOperatorResult(
        report=finalized,
        summary_text=render_summary(finalized),
        exit_code=2 if surface["PIPELINE"] == "HOLD" else 0,
    )


def render_summary(report: Mapping[str, Any]) -> str:
    surface = report["result_surface"]
    lines = [
        "CODEX GATE 1A ALPHA OPERATOR v0.1",
        f"MODE: {report['mode']}",
    ]
    lines.extend(f"{key}: {surface[key]}" for key in RESULT_KEYS)
    lines.extend(
        (
            f"RECEIPT: {report['receipt_sha256']}",
            "AUTHORITY: false",
            "CAPITAL: LOCKED",
        )
    )
    return "\n".join(lines)


def render_markdown(report: Mapping[str, Any]) -> str:
    surface = report["result_surface"]
    lines = [
        "# CodexTradingEngine Gate 1A Alpha Report",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Receipt: `{report['receipt_sha256']}`",
        f"- Repository commit: `{report['reproduction']['repository_commit']}`",
        f"- Python: `{report['reproduction']['python_version']}`",
        "",
        "## Result surface",
        "",
    ]
    lines.extend(f"- {key}: **{surface[key]}**" for key in RESULT_KEYS)
    lines.extend(
        (
            "",
            "## Reproduction",
            "",
            f"`{report['reproduction']['command']}`",
            "",
            "## Expected versus observed",
            "",
            f"- Expected: {report['expected_observed']['expected_behavior']}",
            f"- Observed: {report['expected_observed']['observed_behavior']}",
            "",
            "## Publication safety",
            "",
            report["publication_safety"],
            "",
            "## Boundary",
            "",
            "This artifact is not a command. Authority is false. Execution, signing, transaction submission, and capital movement remain locked.",
            "",
        )
    )
    return "\n".join(lines)


def write_operator_report(
    result: AlphaOperatorResult,
    output_dir: Path,
    report_schema: Mapping[str, Any],
) -> tuple[Path, Path, Path]:
    _require_schema(result.report, report_schema, "alpha operator report")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "alpha-report.json"
    markdown_path = output_dir / "alpha-report.md"
    summary_path = output_dir / "alpha-summary.txt"
    json_path.write_text(
        json.dumps(result.report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(result.report), encoding="utf-8")
    summary_path.write_text(result.summary_text + "\n", encoding="utf-8")
    return json_path, markdown_path, summary_path


def _collect_doctor(args: argparse.Namespace) -> DoctorResult:
    facts = collect_facts(
        repo_root=args.repo_root,
        registry_path=args.registry,
        schema_path=args.registry_schema,
    )
    return evaluate_facts(facts, acknowledge_dirty=args.acknowledge_dirty)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="codex-alpha-run",
        description=(
            "Carry one bounded Gate 1A alpha procedure without network capture, "
            "wallet, signing, transaction, execution, or capital authority."
        ),
    )
    result.add_argument("--repo-root", type=Path, default=_ROOT)
    result.add_argument("--registry", type=Path, default=_DEFAULT_REGISTRY)
    result.add_argument(
        "--registry-schema",
        type=Path,
        default=_DEFAULT_REGISTRY_SCHEMA,
    )
    result.add_argument("--report-schema", type=Path, default=_DEFAULT_REPORT_SCHEMA)
    result.add_argument("--acknowledge-dirty", action="store_true")
    result.add_argument("--json", action="store_true")
    subparsers = result.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="explain readiness and source holds")
    status.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/alpha-status"),
    )

    simulate = subparsers.add_parser(
        "simulate-reviewed",
        help="run one exact-hash reviewed draft through local simulation",
    )
    simulate.add_argument("--draft", type=Path, required=True)
    simulate.add_argument("--expected-draft-hash", required=True)
    simulate.add_argument("--draft-schema", type=Path, default=_DEFAULT_DRAFT_SCHEMA)
    simulate.add_argument("--cycle-id")
    simulate.add_argument("--producer-commit")
    simulate.add_argument("--now")
    simulate.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/alpha-run"),
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        doctor = _collect_doctor(args)
        report_schema = _load_json(args.report_schema)
        if args.command == "status":
            operator_result = status_result(doctor)
            output_dir = args.output_dir
        else:
            draft = _load_json(args.draft)
            draft_schema = _load_json(args.draft_schema)
            expected_hash = args.expected_draft_hash.lower()
            cycle_id = args.cycle_id or f"alpha-{expected_hash[:12]}"
            producer_commit = (args.producer_commit or doctor.facts.commit_sha or "0" * 40).lower()
            if len(producer_commit) != 40 or any(
                character not in "0123456789abcdef" for character in producer_commit
            ):
                raise AlphaOperatorError("producer commit must be a 40-character hexadecimal SHA")
            now = parse_utc(args.now) if args.now else datetime.now(timezone.utc)
            operator_result = simulate_reviewed_result(
                doctor=doctor,
                draft=draft,
                expected_draft_hash=expected_hash,
                draft_schema=draft_schema,
                output_dir=args.output_dir,
                cycle_id=cycle_id,
                producer_commit=producer_commit,
                now=now,
            )
            output_dir = args.output_dir
        paths = write_operator_report(operator_result, output_dir, report_schema)
    except (AlphaOperatorError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(operator_result.report, indent=2, sort_keys=True))
    else:
        print(operator_result.summary_text)
        print(f"Alpha report JSON: {paths[0]}")
        print(f"Alpha report Markdown: {paths[1]}")
        print(f"Alpha summary: {paths[2]}")
    return operator_result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
