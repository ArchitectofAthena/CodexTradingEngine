from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any, Mapping, MutableMapping, Sequence

from eve_q.viv_adversarial import AdversarialCase, ViVAdversarialError, run_viv_gauntlet

DELTA_ROBUSTNESS_SCHEMA = "delta-robustness-receipt-v0.1"
DELTA_ROBUSTNESS_VALIDATOR_ID = "delta_robustness_receipt"

_ROBUSTNESS_CLASSES = {"robust", "resilient", "conditional", "fragile", "failed"}
_HEX = set("0123456789abcdef")


def _stable_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ViVAdversarialError(f"{field_name} must be an object")
    return value


def _require_list(value: object, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ViVAdversarialError(f"{field_name} must be a list")
    return value


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ViVAdversarialError(f"{field_name} must be a boolean")
    return value


def _require_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ViVAdversarialError(f"{field_name} must be an integer")
    return value


def _require_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ViVAdversarialError(f"{field_name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ViVAdversarialError(f"{field_name} must be finite")
    return number


def _require_sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in _HEX for char in value):
        raise ViVAdversarialError(
            f"{field_name} must be 64 lowercase hexadecimal characters"
        )
    return value


def _require_vector(
    value: object,
    field_name: str,
    *,
    minimum: float,
    maximum: float,
) -> tuple[float, float, float]:
    items = _require_list(value, field_name)
    if len(items) != 3:
        raise ViVAdversarialError(f"{field_name} must contain exactly three values")
    numbers = tuple(_require_finite(item, field_name) for item in items)
    if any(number < minimum or number > maximum for number in numbers):
        raise ViVAdversarialError(
            f"{field_name} values must remain in [{minimum}, {maximum}]"
        )
    return numbers  # type: ignore[return-value]


def _classify(survival_rate: float) -> str:
    if math.isclose(survival_rate, 1.0, abs_tol=1e-15):
        return "robust"
    if survival_rate >= 0.8:
        return "resilient"
    if survival_rate >= 0.5:
        return "conditional"
    if survival_rate > 0.0:
        return "fragile"
    return "failed"


def _validate_scenario(scenario: Mapping[str, Any], index: int) -> None:
    prefix = f"results[{index}].scenario"
    scenario_id = scenario.get("scenario_id")
    if not isinstance(scenario_id, str) or not scenario_id.startswith("delta-scenario:"):
        raise ViVAdversarialError(f"{prefix}.scenario_id must use delta-scenario namespace")
    _require_vector(
        scenario.get("rate_shift_bps"),
        f"{prefix}.rate_shift_bps",
        minimum=-5_000.0,
        maximum=5_000.0,
    )
    for field_name in ("fee_shift_bps", "slippage_shift_bps", "latency_shift_bps"):
        _require_vector(
            scenario.get(field_name),
            f"{prefix}.{field_name}",
            minimum=0.0,
            maximum=5_000.0,
        )
    gas_shift = _require_finite(
        scenario.get("gas_penalty_log_shift"),
        f"{prefix}.gas_penalty_log_shift",
    )
    if gas_shift < 0.0:
        raise ViVAdversarialError(f"{prefix}.gas_penalty_log_shift cannot be negative")
    if scenario.get("authority") is not False:
        raise ViVAdversarialError(f"{prefix}.authority must be false")


def _validate_result(result: Mapping[str, Any], index: int) -> tuple[str, bool, float, tuple[str, ...]]:
    prefix = f"results[{index}]"
    scenario = _require_mapping(result.get("scenario"), f"{prefix}.scenario")
    _validate_scenario(scenario, index)
    scenario_id = str(scenario["scenario_id"])

    _require_sha256(result.get("scenario_snapshot_sha256"), f"{prefix}.scenario_snapshot_sha256")
    request_id = result.get("request_id")
    if not isinstance(request_id, str) or not request_id.startswith("delta-reprice:"):
        raise ViVAdversarialError(f"{prefix}.request_id must use delta-reprice namespace")

    net_log_delta = _require_finite(result.get("net_log_delta"), f"{prefix}.net_log_delta")
    _require_finite(result.get("minimum_log_delta"), f"{prefix}.minimum_log_delta")
    _require_finite(result.get("delta_drift"), f"{prefix}.delta_drift")
    profitable = _require_bool(result.get("profitable"), f"{prefix}.profitable")
    passes_margin = _require_bool(result.get("passes_margin"), f"{prefix}.passes_margin")

    reasons_raw = _require_list(result.get("failure_reasons"), f"{prefix}.failure_reasons")
    if any(not isinstance(reason, str) for reason in reasons_raw):
        raise ViVAdversarialError(f"{prefix}.failure_reasons must contain strings")
    reasons = tuple(reasons_raw)
    expected: list[str] = []
    if not profitable:
        expected.append("not_profitable")
    if not passes_margin:
        expected.append("below_minimum_margin")
    if reasons != tuple(expected):
        raise ViVAdversarialError(f"{prefix}.failure_reasons do not match result semantics")
    if result.get("authority") is not False:
        raise ViVAdversarialError(f"{prefix}.authority must be false")

    return scenario_id, passes_margin, net_log_delta, reasons


def expected_delta_robustness_receipt_id(artifact: Mapping[str, Any]) -> str:
    results = _require_list(artifact.get("results"), "results")
    receipt_seed = {
        "baseline_snapshot_sha256": artifact.get("baseline_snapshot_sha256"),
        "model_sha256": artifact.get("model_sha256"),
        "confidence_receipt_id": artifact.get("confidence_receipt_id"),
        "candidate_id": artifact.get("candidate_id"),
        "scenario_set_sha256": artifact.get("scenario_set_sha256"),
        "results": results,
        "authority": False,
    }
    return f"delta-robustness:{_stable_sha256(receipt_seed)[:24]}"


def validate_delta_robustness_artifact(artifact: dict[str, Any]) -> None:
    if not isinstance(artifact, dict):
        raise ViVAdversarialError("delta robustness artifact must be an object")
    if artifact.get("schema_version") != DELTA_ROBUSTNESS_SCHEMA:
        raise ViVAdversarialError("delta robustness schema mismatch")
    if artifact.get("authority") is not False:
        raise ViVAdversarialError("delta robustness authority must be false")

    _require_sha256(artifact.get("baseline_snapshot_sha256"), "baseline_snapshot_sha256")
    _require_sha256(artifact.get("model_sha256"), "model_sha256")
    _require_sha256(artifact.get("scenario_set_sha256"), "scenario_set_sha256")

    confidence_receipt_id = artifact.get("confidence_receipt_id")
    if not isinstance(confidence_receipt_id, str) or not confidence_receipt_id.startswith(
        "qaoa-confidence:"
    ):
        raise ViVAdversarialError("confidence_receipt_id must use qaoa-confidence namespace")
    candidate_id = artifact.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id.startswith("triangle:"):
        raise ViVAdversarialError("candidate_id must use triangle namespace")

    results = _require_list(artifact.get("results"), "results")
    if not results:
        raise ViVAdversarialError("results must be non-empty")
    scenario_ids: list[str] = []
    passes: list[bool] = []
    deltas: list[float] = []
    reason_counts: dict[str, int] = {}
    scenarios: list[Mapping[str, Any]] = []

    for index, raw_result in enumerate(results):
        result = _require_mapping(raw_result, f"results[{index}]")
        scenario_id, passes_margin, net_log_delta, reasons = _validate_result(result, index)
        scenario_ids.append(scenario_id)
        passes.append(passes_margin)
        deltas.append(net_log_delta)
        scenarios.append(_require_mapping(result.get("scenario"), f"results[{index}].scenario"))
        for reason in reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    if scenario_ids != sorted(scenario_ids):
        raise ViVAdversarialError("scenario results must be sorted by scenario_id")
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ViVAdversarialError("scenario identifiers must be unique")

    scenario_set_sha256 = _stable_sha256(scenarios)
    if artifact.get("scenario_set_sha256") != scenario_set_sha256:
        raise ViVAdversarialError("scenario_set_sha256 mismatch")

    scenario_count = _require_int(artifact.get("scenario_count"), "scenario_count")
    survival_count = _require_int(artifact.get("survival_count"), "survival_count")
    if scenario_count != len(results):
        raise ViVAdversarialError("scenario_count mismatch")
    expected_survival_count = sum(passes)
    if survival_count != expected_survival_count:
        raise ViVAdversarialError("survival_count mismatch")

    survival_rate = _require_finite(artifact.get("survival_rate"), "survival_rate")
    expected_survival_rate = expected_survival_count / len(results)
    if not math.isclose(survival_rate, expected_survival_rate, abs_tol=1e-15):
        raise ViVAdversarialError("survival_rate mismatch")

    worst_case = _require_finite(artifact.get("worst_case_log_delta"), "worst_case_log_delta")
    if not math.isclose(worst_case, min(deltas), abs_tol=1e-15):
        raise ViVAdversarialError("worst_case_log_delta mismatch")
    median = _require_finite(artifact.get("median_log_delta"), "median_log_delta")
    if not math.isclose(median, statistics.median(deltas), abs_tol=1e-15):
        raise ViVAdversarialError("median_log_delta mismatch")

    failure_summary = _require_mapping(
        artifact.get("margin_failure_reasons"),
        "margin_failure_reasons",
    )
    normalized_failure_summary: dict[str, int] = {}
    for reason, count in failure_summary.items():
        if not isinstance(reason, str):
            raise ViVAdversarialError("margin_failure_reasons keys must be strings")
        normalized_failure_summary[reason] = _require_int(
            count,
            f"margin_failure_reasons.{reason}",
        )
    if normalized_failure_summary != reason_counts:
        raise ViVAdversarialError("margin_failure_reasons mismatch")

    robustness_class = artifact.get("robustness_class")
    if robustness_class not in _ROBUSTNESS_CLASSES:
        raise ViVAdversarialError("robustness_class is invalid")
    if robustness_class != _classify(expected_survival_rate):
        raise ViVAdversarialError("robustness_class mismatch")

    receipt_id = artifact.get("receipt_id")
    if not isinstance(receipt_id, str) or receipt_id != expected_delta_robustness_receipt_id(artifact):
        raise ViVAdversarialError("delta robustness receipt_id mismatch")


def _flip_authority(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["authority"] = True


def _inflate_survival_count(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    current = candidate.get("survival_count")
    candidate["survival_count"] = (current if isinstance(current, int) else 0) + 1


def _inflate_survival_rate(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    current = candidate.get("survival_rate")
    candidate["survival_rate"] = 0.0 if current == 1.0 else 1.0


def _promote_robustness_class(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    candidate["robustness_class"] = (
        "failed" if candidate.get("robustness_class") == "robust" else "robust"
    )


def _suppress_worst_case(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    results = candidate.get("results")
    if isinstance(results, list) and results:
        deltas = [
            result.get("net_log_delta")
            for result in results
            if isinstance(result, Mapping) and isinstance(result.get("net_log_delta"), (int, float))
        ]
        if deltas:
            candidate["worst_case_log_delta"] = max(float(value) for value in deltas)
            if math.isclose(
                float(candidate["worst_case_log_delta"]),
                min(float(value) for value in deltas),
                abs_tol=1e-15,
            ):
                candidate["worst_case_log_delta"] = float(candidate["worst_case_log_delta"]) + 1.0
            return
    candidate["worst_case_log_delta"] = 1.0


def _delete_result(candidate: MutableMapping[str, Any], seed: int) -> None:
    results = candidate.get("results")
    if isinstance(results, list) and results:
        results.pop(seed % len(results))


def _suppress_failure_summary(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    current = candidate.get("margin_failure_reasons")
    candidate["margin_failure_reasons"] = (
        {"not_profitable": 1} if current == {} else {}
    )


def _tamper_scenario_set(candidate: MutableMapping[str, Any], seed: int) -> None:
    del seed
    current = candidate.get("scenario_set_sha256")
    candidate["scenario_set_sha256"] = "f" * 64 if current != "f" * 64 else "e" * 64


def _tamper_receipt_id(candidate: MutableMapping[str, Any], seed: int) -> None:
    candidate["receipt_id"] = f"delta-robustness:viv{seed:021x}"[-41:]


def _flip_margin_result(candidate: MutableMapping[str, Any], seed: int) -> None:
    results = candidate.get("results")
    if not isinstance(results, list) or not results:
        return
    index = seed % len(results)
    result = results[index]
    if isinstance(result, MutableMapping):
        result["passes_margin"] = not bool(result.get("passes_margin"))


DEFAULT_MARKET_CASES: tuple[AdversarialCase, ...] = (
    AdversarialCase(
        "viv.market.authority_flip.v0.2",
        "Market receipt authority flip",
        "authority must remain false",
        "critical",
        _flip_authority,
    ),
    AdversarialCase(
        "viv.market.survival_count_inflation.v0.2",
        "Survival count inflation",
        "survival_count must match scenario results",
        "critical",
        _inflate_survival_count,
    ),
    AdversarialCase(
        "viv.market.survival_rate_inflation.v0.2",
        "Survival rate inflation",
        "survival_rate must be recomputed from results",
        "critical",
        _inflate_survival_rate,
    ),
    AdversarialCase(
        "viv.market.class_promotion.v0.2",
        "Robustness class promotion",
        "robustness_class must match survival rate",
        "high",
        _promote_robustness_class,
    ),
    AdversarialCase(
        "viv.market.worst_case_suppression.v0.2",
        "Worst-case suppression",
        "worst_case_log_delta must remain the minimum observed delta",
        "critical",
        _suppress_worst_case,
    ),
    AdversarialCase(
        "viv.market.result_deletion.v0.2",
        "Scenario result deletion",
        "scenario_count and content address must match results",
        "high",
        _delete_result,
    ),
    AdversarialCase(
        "viv.market.failure_summary_suppression.v0.2",
        "Failure summary suppression",
        "margin_failure_reasons must match scenario failures",
        "high",
        _suppress_failure_summary,
    ),
    AdversarialCase(
        "viv.market.scenario_set_tamper.v0.2",
        "Scenario-set hash tamper",
        "scenario_set_sha256 must match ordered scenarios",
        "critical",
        _tamper_scenario_set,
    ),
    AdversarialCase(
        "viv.market.receipt_id_tamper.v0.2",
        "Receipt ID tamper",
        "receipt_id must match canonical robustness evidence",
        "critical",
        _tamper_receipt_id,
    ),
    AdversarialCase(
        "viv.market.margin_result_flip.v0.2",
        "Per-scenario margin result flip",
        "passes_margin and failure semantics must remain coherent",
        "critical",
        _flip_margin_result,
    ),
)


def run_viv_market_gauntlet(
    artifact: Mapping[str, Any],
    *,
    seed: int = 0,
    created_at: str = "1970-01-01T00:00:00Z",
) -> dict[str, Any]:
    return run_viv_gauntlet(
        artifact,
        validator=validate_delta_robustness_artifact,
        validator_id=DELTA_ROBUSTNESS_VALIDATOR_ID,
        cases=DEFAULT_MARKET_CASES,
        seed=seed,
        created_at=created_at,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run ViV's deterministic market evidence gauntlet."
    )
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--created-at", default="1970-01-01T00:00:00Z")
    parser.add_argument("--receipt-out", type=Path, default=None)
    args = parser.parse_args()

    try:
        artifact = json.loads(args.candidate.read_text(encoding="utf-8"))
        if not isinstance(artifact, dict):
            raise ViVAdversarialError("candidate JSON must be an object")
        receipt = run_viv_market_gauntlet(
            artifact,
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
