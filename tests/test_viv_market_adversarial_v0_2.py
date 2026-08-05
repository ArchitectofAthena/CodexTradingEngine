from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import jsonschema
import pytest

from eve_q.viv_adversarial import run_viv_gauntlet
from eve_q.viv_market_adversarial import (
    DEFAULT_MARKET_CASES,
    DELTA_ROBUSTNESS_VALIDATOR_ID,
    ViVAdversarialError,
    expected_delta_robustness_receipt_id,
    run_viv_market_gauntlet,
    validate_delta_robustness_artifact,
)

ROOT = Path(__file__).resolve().parents[1]


def stable_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def scenario(
    scenario_id: str,
    *,
    rate_shift: float = 0.0,
    slippage_shift: float = 0.0,
) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "rate_shift_bps": [rate_shift, rate_shift, rate_shift],
        "fee_shift_bps": [0.0, 0.0, 0.0],
        "slippage_shift_bps": [slippage_shift, slippage_shift, slippage_shift],
        "latency_shift_bps": [0.0, 0.0, 0.0],
        "gas_penalty_log_shift": 0.0,
        "authority": False,
    }


def result(
    scenario_payload: dict[str, object],
    *,
    net_log_delta: float,
    profitable: bool,
    passes_margin: bool,
    token: str,
) -> dict[str, object]:
    reasons: list[str] = []
    if not profitable:
        reasons.append("not_profitable")
    if not passes_margin:
        reasons.append("below_minimum_margin")
    return {
        "scenario": scenario_payload,
        "scenario_snapshot_sha256": token * 64,
        "request_id": f"delta-reprice:{token * 24}",
        "net_log_delta": net_log_delta,
        "minimum_log_delta": 0.001,
        "profitable": profitable,
        "passes_margin": passes_margin,
        "delta_drift": 0.0,
        "failure_reasons": reasons,
        "authority": False,
    }


def valid_artifact() -> dict[str, object]:
    scenarios = [
        scenario("delta-scenario:baseline"),
        scenario(
            "delta-scenario:stress",
            rate_shift=-15.0,
            slippage_shift=10.0,
        ),
    ]
    results = [
        result(
            scenarios[0],
            net_log_delta=0.02,
            profitable=True,
            passes_margin=True,
            token="a",
        ),
        result(
            scenarios[1],
            net_log_delta=-0.01,
            profitable=False,
            passes_margin=False,
            token="b",
        ),
    ]
    artifact: dict[str, object] = {
        "schema_version": "delta-robustness-receipt-v0.1",
        "receipt_id": "pending",
        "baseline_snapshot_sha256": "c" * 64,
        "model_sha256": "d" * 64,
        "confidence_receipt_id": "qaoa-confidence:fixture",
        "candidate_id": "triangle:fixture",
        "scenario_set_sha256": stable_sha256(scenarios),
        "scenario_count": 2,
        "survival_count": 1,
        "survival_rate": 0.5,
        "worst_case_log_delta": -0.01,
        "median_log_delta": 0.005,
        "margin_failure_reasons": {
            "not_profitable": 1,
            "below_minimum_margin": 1,
        },
        "robustness_class": "conditional",
        "results": results,
        "authority": False,
    }
    artifact["receipt_id"] = expected_delta_robustness_receipt_id(artifact)
    return artifact


def test_valid_delta_robustness_artifact_passes() -> None:
    validate_delta_robustness_artifact(valid_artifact())


def test_market_gauntlet_blocks_every_default_attack() -> None:
    receipt = run_viv_market_gauntlet(
        valid_artifact(),
        seed=7331,
        created_at="2026-08-05T00:00:00Z",
    )

    assert receipt["validator_id"] == DELTA_ROBUSTNESS_VALIDATOR_ID
    assert receipt["case_count"] == len(DEFAULT_MARKET_CASES) == 10
    assert receipt["blocked_count"] == 10
    assert receipt["escaped_count"] == 0
    assert receipt["overall_outcome"] == "pass"
    assert receipt["repair_required"] is False


def test_market_gauntlet_preserves_original_artifact() -> None:
    artifact = valid_artifact()
    before = deepcopy(artifact)

    receipt = run_viv_market_gauntlet(artifact, seed=9)

    assert artifact == before
    assert receipt["candidate_unchanged"] is True


def test_permissive_validator_exposes_every_escape() -> None:
    receipt = run_viv_gauntlet(
        valid_artifact(),
        validator=lambda artifact: None,
        validator_id="intentionally_permissive_fixture",
        cases=DEFAULT_MARKET_CASES,
        seed=12,
    )

    assert receipt["escaped_count"] == len(DEFAULT_MARKET_CASES)
    assert receipt["blocked_count"] == 0
    assert receipt["overall_outcome"] == "fail"
    assert receipt["repair_required"] is True


def test_receipt_id_tamper_is_rejected() -> None:
    artifact = valid_artifact()
    artifact["receipt_id"] = "delta-robustness:000000000000000000000000"

    with pytest.raises(ViVAdversarialError, match="receipt_id mismatch"):
        validate_delta_robustness_artifact(artifact)


def test_duplicate_scenario_id_is_rejected() -> None:
    artifact = valid_artifact()
    results = artifact["results"]
    assert isinstance(results, list)
    first = results[0]
    second = results[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    first_scenario = first["scenario"]
    second_scenario = second["scenario"]
    assert isinstance(first_scenario, dict)
    assert isinstance(second_scenario, dict)
    second_scenario["scenario_id"] = first_scenario["scenario_id"]

    with pytest.raises(ViVAdversarialError, match="scenario identifiers must be unique"):
        validate_delta_robustness_artifact(artifact)


def test_failure_summary_suppression_is_rejected() -> None:
    artifact = valid_artifact()
    artifact["margin_failure_reasons"] = {}

    with pytest.raises(ViVAdversarialError, match="margin_failure_reasons mismatch"):
        validate_delta_robustness_artifact(artifact)


def test_market_receipt_conforms_to_viv_schema() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "viv_adversarial_receipt_v0_1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    receipt = run_viv_market_gauntlet(valid_artifact(), seed=1)

    jsonschema.validate(receipt, schema)


def test_market_receipt_preserves_non_authority_locks() -> None:
    receipt = run_viv_market_gauntlet(valid_artifact(), seed=1)

    for field_name in (
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
    ):
        assert receipt[field_name] is False
    assert receipt["human_promotion_required"] is True


def test_cli_writes_market_gauntlet_receipt(tmp_path: Path) -> None:
    candidate_path = tmp_path / "robustness.json"
    receipt_path = tmp_path / "viv-market-receipt.json"
    candidate_path.write_text(
        json.dumps(valid_artifact(), sort_keys=True),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.viv_market_adversarial",
            "--candidate",
            str(candidate_path),
            "--seed",
            "7331",
            "--created-at",
            "2026-08-05T00:00:00Z",
            "--receipt-out",
            str(receipt_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert output["ok"] is True
    assert receipt["overall_outcome"] == "pass"
    assert receipt["blocked_count"] == 10
