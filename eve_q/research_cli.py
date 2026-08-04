"""Canonical simulation → verification → report command for public users."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

from shadow_cycle_runner import run_shadow_cycle

DEFAULT_PRODUCER_COMMIT = "0" * 40


class ResearchCliError(RuntimeError):
    """Raised for invalid local research inputs."""


def json_value(value: Any) -> Any:
    """Convert common research values into JSON-safe representations."""

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def load_routes(path: Path | None) -> list[dict[str, Any]] | None:
    """Load an optional local candidate-route array."""

    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchCliError(f"could not read routes file: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        raise ResearchCliError("routes file must contain a non-empty JSON array")
    if not all(isinstance(item, dict) for item in payload):
        raise ResearchCliError("every route candidate must be a JSON object")
    required = {
        "route",
        "chain",
        "expected_profit_eth",
        "gas_cost_eth",
        "slippage_eth",
        "safety_margin_eth",
    }
    for index, route in enumerate(payload):
        missing = sorted(required - set(route))
        if missing:
            raise ResearchCliError(
                f"route candidate {index} is missing fields: {', '.join(missing)}"
            )
        for field in required - {"route", "chain"}:
            try:
                Decimal(str(route[field]))
            except (ValueError, ArithmeticError) as exc:
                raise ResearchCliError(
                    f"route candidate {index} has invalid {field}"
                ) from exc
    return [dict(item) for item in payload]


def economics_state(actual_profit: Decimal) -> str:
    """Separate modeled economics from pipeline readiness."""

    return "POSITIVE_EDGE" if actual_profit > 0 else "HOLD_NON_POSITIVE_EDGE"


def build_report(run: Any) -> dict[str, Any]:
    """Build one human-oriented, non-authoritative research report."""

    receipt = run.receipt
    validation = run.validation
    pipeline = "READY" if validation.valid else "HOLD"
    report: dict[str, Any] = {
        "artifact_type": "CodexResearchReport",
        "contract_version": "codex_research_report_v0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "pipeline": pipeline,
            "economics": economics_state(receipt.actual_profit_eth),
            "execution": "LOCKED",
            "selected_route": receipt.selected_route,
            "mode": receipt.mode,
            "chain": receipt.chain,
            "actual_profit_eth": str(receipt.actual_profit_eth),
            "charity_due_eth": str(receipt.charity_due_eth),
        },
        "verification": {
            "receipt_valid": bool(validation.valid),
            "trust_increment_allowed": bool(validation.trust_increment_allowed),
            "findings": json_value(getattr(validation, "findings", [])),
        },
        "artifacts": {
            "receipt": str(run.receipt_path),
            "proposal": str(run.proposal_path),
            "proposal_artifact": json_value(run.proposal_artifact),
        },
        "boundary": {
            "artifact_is_command": False,
            "authority": False,
            "human_promotion_required": True,
            "may_execute": False,
            "may_sign": False,
            "may_broadcast": False,
            "may_move_capital": False,
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    """Render the canonical report into a compact readable page."""

    summary = report["summary"]
    verification = report["verification"]
    artifacts = report["artifacts"]
    boundary = report["boundary"]
    lines = [
        "# CodexTradingEngine Research Report",
        "",
        f"Generated: `{report['created_at']}`",
        "",
        "## Result",
        "",
        f"- Pipeline: **{summary['pipeline']}**",
        f"- Economics: **{summary['economics']}**",
        f"- Execution: **{summary['execution']}**",
        f"- Mode: `{summary['mode']}`",
        f"- Chain: `{summary['chain']}`",
        f"- Selected route: `{summary['selected_route']}`",
        f"- Modeled net result: `{summary['actual_profit_eth']} ETH`",
        f"- Charity allocation proposal: `{summary['charity_due_eth']} ETH`",
        "",
        "## Verification",
        "",
        f"- Receipt valid: `{verification['receipt_valid']}`",
        f"- Trust increment allowed: `{verification['trust_increment_allowed']}`",
        f"- Receipt artifact: `{artifacts['receipt']}`",
        f"- Proposal artifact: `{artifacts['proposal']}`",
        "",
        "## Boundary",
        "",
        f"- Authority: `{boundary['authority']}`",
        f"- Human promotion required: `{boundary['human_promotion_required']}`",
        f"- May execute: `{boundary['may_execute']}`",
        f"- May sign: `{boundary['may_sign']}`",
        f"- May broadcast: `{boundary['may_broadcast']}`",
        f"- May move capital: `{boundary['may_move_capital']}`",
        "",
        "This report records a local simulation and verification pass. It is not a trading instruction or promise of profit.",
        "",
    ]
    return "\n".join(lines)


def write_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    """Write JSON and Markdown views of the same canonical report."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "research-report.json"
    markdown_path = output_dir / "research-report.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="codex-research",
        description=(
            "Run one local simulation-safe route cycle, verify its receipt, and "
            "emit one readable report. No wallet, signing, broadcast, or capital path."
        ),
    )
    result.add_argument(
        "--routes",
        type=Path,
        help="Optional JSON array of local candidate routes.",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/research-run"),
        help="Directory for receipt, proposal, and report artifacts.",
    )
    result.add_argument("--cycle-id", help="Optional deterministic cycle identifier.")
    result.add_argument(
        "--producer-commit",
        default=DEFAULT_PRODUCER_COMMIT,
        help="40-character producer commit SHA recorded in the proposal artifact.",
    )
    result.add_argument(
        "--json",
        action="store_true",
        help="Print the complete report JSON instead of the concise result.",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if len(args.producer_commit) != 40 or any(
        character not in "0123456789abcdefABCDEF"
        for character in args.producer_commit
    ):
        print("error: --producer-commit must be a 40-character hexadecimal SHA", file=sys.stderr)
        return 2

    try:
        routes = load_routes(args.routes)
        cycle_dir = args.output_dir / "cycle"
        run = run_shadow_cycle(
            output_dir=cycle_dir,
            cycle_id=args.cycle_id,
            candidate_routes=routes,
            producer_commit=args.producer_commit.lower(),
        )
        report = build_report(run)
        json_path, markdown_path = write_report(report, args.output_dir)
    except (ResearchCliError, OSError, RuntimeError, ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        summary = report["summary"]
        print(
            " | ".join(
                [
                    f"PIPELINE={summary['pipeline']}",
                    f"ECONOMICS={summary['economics']}",
                    f"EXECUTION={summary['execution']}",
                ]
            )
        )
        print(f"Report JSON: {json_path}")
        print(f"Report Markdown: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
