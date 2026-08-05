from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from eve_q.alpha_doctor import (
    DoctorFacts,
    RegistrySummary,
    evaluate_facts,
)
from eve_q.alpha_operator import (
    AUTHORITY_BOUNDARY,
    AlphaOperatorResult,
    ResearchResult,
    simulate_reviewed_result,
    status_result,
    write_operator_report,
)
from eve_q.telemetry_draft_fixture import (
    AUTHORITY_BOUNDARY as DRAFT_AUTHORITY_BOUNDARY,
)
from eve_q.telemetry_draft_fixture import sha256_hex as draft_sha256

ROOT = Path(__file__).resolve().parents[1]
DRAFT_SCHEMA = json.loads(
    (ROOT / "schemas" / "telemetry_draft_fixture_v0_1.schema.json").read_text(encoding="utf-8")
)
REPORT_SCHEMA = json.loads(
    (ROOT / "schemas" / "alpha_operator_report_v0_1.schema.json").read_text(encoding="utf-8")
)
NOW = datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc)
REGISTRY_HASH = "a" * 64


def doctor(*, eligible: bool, hold: bool = False):
    registry = RegistrySummary(
        valid=not hold,
        errors=("invalid registry",) if hold else (),
        eligible_source_ids=("reviewed-sepolia-source",) if eligible else (),
        hold_source_ids=(),
        rejected_source_ids=(),
        registry_sha256=REGISTRY_HASH,
    )
    facts = DoctorFacts(
        repo_root=str(ROOT),
        commit_sha="b" * 40,
        git_error=None,
        dirty_paths=(),
        python_version="3.13.0",
        package_origin=str(ROOT / "eve_q" / "__init__.py"),
        kill_switch_active=False,
        dangerous_secret_names=(),
        rust_verifier_path=str(ROOT / "rust" / "delta-verifier" / "Cargo.toml"),
        rust_verifier_expected_sha256=None,
        rust_verifier_actual_sha256="c" * 64,
        rust_verifier_state="CHECKOUT_LOCAL",
        registry=registry,
    )
    return evaluate_facts(facts)


def reviewed_draft() -> dict:
    material = {
        "snapshot": {
            "artifact_id": "1" * 64,
            "raw_sha256": "2" * 64,
            "normalized_sha256": "3" * 64,
            "observed_at": "2026-08-05T00:50:00Z",
            "expires_at": "2026-08-05T01:30:00Z",
        },
        "source_review": {
            "registry_id": "codex.gate1a.testnet-source-registry.v0.1",
            "registry_sha256": REGISTRY_HASH,
            "source_id": "reviewed-sepolia-source",
            "source_review_evidence": ["receipt:source-review"],
            "source_reviewed_at": "2026-08-05T00:40:00Z",
        },
        "mapping": {
            "mapping_id": "sepolia-route-mapping-v0-1",
            "mapping_sha256": "4" * 64,
        },
        "network": {
            "network_name": "Ethereum Sepolia",
            "chain_id": "11155111",
            "network_class": "testnet",
        },
        "observed_fields": [
            {
                "target_field": "expected_profit_eth",
                "source_pointer": "/normalized_payload/quote/expected_profit_wei",
                "original_value": "20000000000000000",
                "unit": "wei",
                "observed_at": "2026-08-05T00:50:00Z",
            }
        ],
        "transformed_fields": [
            {
                "target_field": "expected_profit_eth",
                "input_value": "20000000000000000",
                "output_value": "0.02",
                "input_unit": "wei",
                "output_unit": "ETH",
                "conversion": "decimal_scale factor=0.000000000000000001",
            }
        ],
        "inferred_assumptions": [
            {
                "field": "gas_cost_eth",
                "value": "0.005",
                "unit": "ETH",
                "basis": "operator fixture",
                "operator_supplied": True,
            },
            {
                "field": "slippage_eth",
                "value": "0.001",
                "unit": "ETH",
                "basis": "operator fixture",
                "operator_supplied": True,
            },
            {
                "field": "safety_margin_eth",
                "value": "0.002",
                "unit": "ETH",
                "basis": "operator fixture",
                "operator_supplied": True,
            },
        ],
        "missing_assumptions": [],
        "local_route_fixture": {
            "route": "testnet-weth-usdc-weth",
            "chain": "Ethereum Sepolia",
            "expected_profit_eth": "0.02",
            "gas_cost_eth": "0.005",
            "slippage_eth": "0.001",
            "safety_margin_eth": "0.002",
        },
        "authority": dict(DRAFT_AUTHORITY_BOUNDARY),
    }
    digest = draft_sha256(material)
    return {
        "artifact_type": "TelemetryDraftFixture",
        "adapter_version": "codex-telemetry-draft-v0.1",
        "schema_version": "0.1",
        "draft_id": f"draft-{digest[:24]}",
        "draft_hash": digest,
        "draft_material": material,
        "freshness": {
            "state": "fresh",
            "evaluated_at": "2026-08-05T00:55:00Z",
            "expires_at": "2026-08-05T01:30:00Z",
        },
        "operator_review": {
            "state": "REVIEWED_FOR_LOCAL_SIMULATION",
            "reviewed_draft_hash": digest,
            "reviewer": "Architect",
            "reviewed_at": "2026-08-05T00:56:00Z",
            "note": "Reviewed for local simulation only.",
        },
        "local_simulation_eligible": True,
        "authority": dict(DRAFT_AUTHORITY_BOUNDARY),
    }


def research_runner(
    route: dict,
    output_dir: Path,
    cycle_id: str,
    producer_commit: str,
) -> ResearchResult:
    report = {
        "summary": {
            "pipeline": "READY",
            "economics": "POSITIVE_EDGE",
            "execution": "LOCKED",
            "selected_route": route["route"],
            "mode": "SIMULATION_ONLY",
            "chain": route["chain"],
            "actual_profit_eth": "0.012",
            "charity_due_eth": "0.0018",
        },
        "verification": {
            "receipt_valid": True,
            "trust_increment_allowed": True,
            "findings": [],
        },
        "artifacts": {
            "receipt": str(output_dir / "cycle" / "receipt.json"),
            "proposal": str(output_dir / "cycle" / "proposal.json"),
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
    return ResearchResult(
        report=report,
        report_json_path=str(output_dir / "research-report.json"),
        report_markdown_path=str(output_dir / "research-report.md"),
    )


def simulate(draft: dict, tmp_path: Path, runner=research_runner) -> AlphaOperatorResult:
    return simulate_reviewed_result(
        doctor=doctor(eligible=True),
        draft=draft,
        expected_draft_hash=draft["draft_hash"],
        draft_schema=DRAFT_SCHEMA,
        output_dir=tmp_path,
        cycle_id="alpha-test-001",
        producer_commit="b" * 40,
        now=NOW,
        research_runner=runner,
    )


def test_status_holds_when_no_source_is_eligible() -> None:
    result = status_result(doctor(eligible=False))

    assert result.exit_code == 2
    assert result.report["result_surface"]["PIPELINE"] == "HOLD"
    assert result.report["result_surface"]["SOURCE"] == "HOLD_NO_ELIGIBLE_SOURCE"
    assert result.report["result_surface"]["EXECUTION"] == "LOCKED"
    assert result.report["boundary"] == AUTHORITY_BOUNDARY


def test_status_is_ready_when_environment_and_source_are_eligible() -> None:
    result = status_result(doctor(eligible=True))

    assert result.exit_code == 0
    assert result.report["result_surface"]["PIPELINE"] == "READY"
    assert result.report["result_surface"]["SOURCE"] == "ELIGIBLE"
    assert result.report["result_surface"]["ECONOMICS"] == "NOT_RUN"


def test_doctor_hold_blocks_the_operator() -> None:
    result = status_result(doctor(eligible=False, hold=True))

    assert result.exit_code == 2
    assert result.report["result_surface"]["SOURCE"] == "HOLD_DOCTOR"


def test_exact_reviewed_draft_runs_local_simulation(tmp_path: Path) -> None:
    result = simulate(reviewed_draft(), tmp_path)
    surface = result.report["result_surface"]

    assert result.exit_code == 0
    assert surface["PIPELINE"] == "READY"
    assert surface["SOURCE"] == "ELIGIBLE"
    assert surface["FRESHNESS"] == "FRESH"
    assert surface["ECONOMICS"] == "POSITIVE_EDGE"
    assert surface["CLASSICAL_BASELINE"] == "NOT_AVAILABLE"
    assert surface["QAOA_COMPARISON"] == "NOT_AVAILABLE"
    assert surface["RUST_VERIFICATION"] == "NOT_RUN"
    assert surface["EXECUTION"] == "LOCKED"
    assert result.report["boundary"]["may_move_capital"] is False


def test_wrong_hash_or_unreviewed_draft_holds(tmp_path: Path) -> None:
    draft = reviewed_draft()
    wrong_hash = simulate_reviewed_result(
        doctor=doctor(eligible=True),
        draft=draft,
        expected_draft_hash="0" * 64,
        draft_schema=DRAFT_SCHEMA,
        output_dir=tmp_path,
        cycle_id="alpha-test-001",
        producer_commit="b" * 40,
        now=NOW,
        research_runner=research_runner,
    )
    assert wrong_hash.exit_code == 2
    assert wrong_hash.report["result_surface"]["SOURCE"] == "HOLD_DRAFT"

    unreviewed = reviewed_draft()
    unreviewed["operator_review"]["state"] = "DRAFT_UNREVIEWED"
    unreviewed["operator_review"]["reviewed_draft_hash"] = None
    unreviewed["operator_review"]["reviewer"] = None
    unreviewed["operator_review"]["reviewed_at"] = None
    unreviewed["operator_review"]["note"] = None
    unreviewed["local_simulation_eligible"] = False
    held = simulate(unreviewed, tmp_path)
    assert held.exit_code == 2
    assert held.report["result_surface"]["PIPELINE"] == "HOLD"


def test_stale_or_missing_route_field_holds(tmp_path: Path) -> None:
    stale = reviewed_draft()
    stale["freshness"]["expires_at"] = "2026-08-05T00:59:00Z"
    stale["draft_material"]["snapshot"]["expires_at"] = "2026-08-05T00:59:00Z"
    stale["draft_hash"] = draft_sha256(stale["draft_material"])
    stale["draft_id"] = f"draft-{stale['draft_hash'][:24]}"
    stale["operator_review"]["reviewed_draft_hash"] = stale["draft_hash"]
    held_stale = simulate(stale, tmp_path)
    assert held_stale.exit_code == 2

    missing = reviewed_draft()
    del missing["draft_material"]["local_route_fixture"]["gas_cost_eth"]
    missing["draft_hash"] = draft_sha256(missing["draft_material"])
    missing["draft_id"] = f"draft-{missing['draft_hash'][:24]}"
    missing["operator_review"]["reviewed_draft_hash"] = missing["draft_hash"]
    held_missing = simulate(missing, tmp_path)
    assert held_missing.exit_code == 2


def test_registry_hash_drift_holds(tmp_path: Path) -> None:
    draft = reviewed_draft()
    draft["draft_material"]["source_review"]["registry_sha256"] = "d" * 64
    draft["draft_hash"] = draft_sha256(draft["draft_material"])
    draft["draft_id"] = f"draft-{draft['draft_hash'][:24]}"
    draft["operator_review"]["reviewed_draft_hash"] = draft["draft_hash"]

    result = simulate(draft, tmp_path)
    assert result.exit_code == 2
    assert "registry hash" in result.report["draft"]["validation_hold"]


def test_unpaired_qaoa_is_a_visible_hold(tmp_path: Path) -> None:
    def unpaired_runner(
        route: dict,
        output_dir: Path,
        cycle_id: str,
        producer_commit: str,
    ) -> ResearchResult:
        result = research_runner(route, output_dir, cycle_id, producer_commit)
        report = copy.deepcopy(dict(result.report))
        report["qaoa_comparison"] = {
            "objective_value": "1.0",
            "input_qubo_sha256": "e" * 64,
        }
        return ResearchResult(
            report=report,
            report_json_path=result.report_json_path,
            report_markdown_path=result.report_markdown_path,
        )

    result = simulate(reviewed_draft(), tmp_path, unpaired_runner)

    assert result.exit_code == 2
    assert result.report["result_surface"]["PIPELINE"] == "HOLD"
    assert result.report["result_surface"]["CLASSICAL_BASELINE"] == "HOLD_MISSING_CLASSICAL_PAIR"
    assert result.report["result_surface"]["QAOA_COMPARISON"] == "HOLD_UNPAIRED_QAOA"


def test_receipt_is_deterministic_for_identical_stable_evidence(tmp_path: Path) -> None:
    draft = reviewed_draft()
    first = simulate(draft, tmp_path / "first")
    second = simulate(copy.deepcopy(draft), tmp_path / "second")

    assert first.report["receipt_sha256"] == second.report["receipt_sha256"]


def test_structured_report_writes_json_markdown_and_summary(tmp_path: Path) -> None:
    result = simulate(reviewed_draft(), tmp_path / "run")
    paths = write_operator_report(result, tmp_path / "report", REPORT_SCHEMA)

    assert all(path.is_file() for path in paths)
    payload = json.loads(paths[0].read_text(encoding="utf-8"))
    assert payload["receipt_sha256"] == result.report["receipt_sha256"]
    assert payload["boundary"]["authority"] is False
    assert "PIPELINE: READY" in paths[2].read_text(encoding="utf-8")
