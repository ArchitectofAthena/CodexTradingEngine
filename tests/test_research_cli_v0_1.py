from __future__ import annotations

import json
from pathlib import Path

from eve_q.research_cli import load_routes, main


def test_canonical_research_command_writes_readable_report(tmp_path: Path):
    output = tmp_path / "run"

    result = main(
        [
            "--output-dir",
            str(output),
            "--cycle-id",
            "public-review-fixture",
            "--producer-commit",
            "a" * 40,
        ]
    )

    assert result == 0
    json_path = output / "research-report.json"
    markdown_path = output / "research-report.md"
    assert json_path.exists()
    assert markdown_path.exists()

    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["artifact_type"] == "CodexResearchReport"
    assert report["summary"]["pipeline"] == "READY"
    assert report["summary"]["execution"] == "LOCKED"
    assert report["boundary"] == {
        "artifact_is_command": False,
        "authority": False,
        "human_promotion_required": True,
        "may_broadcast": False,
        "may_execute": False,
        "may_move_capital": False,
        "may_sign": False,
    }
    text = markdown_path.read_text(encoding="utf-8")
    assert "Pipeline: **READY**" in text
    assert "Execution: **LOCKED**" in text
    assert "not a trading instruction" in text


def test_routes_file_drives_the_same_report_path(tmp_path: Path):
    routes = tmp_path / "routes.json"
    routes.write_text(
        json.dumps(
            [
                {
                    "route": "fixture-base-weth-usdc-weth",
                    "chain": "base",
                    "expected_profit_eth": "0.02",
                    "gas_cost_eth": "0.005",
                    "slippage_eth": "0.001",
                    "safety_margin_eth": "0.002",
                }
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "run"

    result = main(
        [
            "--routes",
            str(routes),
            "--output-dir",
            str(output),
            "--producer-commit",
            "b" * 40,
        ]
    )

    assert result == 0
    report = json.loads((output / "research-report.json").read_text(encoding="utf-8"))
    assert report["summary"]["selected_route"] == "fixture-base-weth-usdc-weth"


def test_routes_file_rejects_missing_fields(tmp_path: Path):
    routes = tmp_path / "routes.json"
    routes.write_text(json.dumps([{"route": "incomplete"}]), encoding="utf-8")

    try:
        load_routes(routes)
    except RuntimeError as exc:
        assert "missing fields" in str(exc)
    else:
        raise AssertionError("incomplete route should fail closed")


def test_invalid_producer_commit_returns_usage_error(tmp_path: Path):
    result = main(
        [
            "--output-dir",
            str(tmp_path / "run"),
            "--producer-commit",
            "not-a-sha",
        ]
    )

    assert result == 2
