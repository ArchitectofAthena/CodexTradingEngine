"""Fixed classical/QAOA benchmark corpus for Gate 1A.1.

The corpus binds classical and QAOA evidence to the same immutable QUBO,
constraints, economics-assumption digests, verifier posture, and precommitted
promotion policy. It is a research evidence surface only and cannot grant
trading, wallet, signing, transaction, gate-promotion, or capital authority.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import statistics
from collections.abc import Mapping, Sequence
from pathlib import Path

_CORPUS_SCHEMA = "gate1a1-fixed-benchmark-corpus-v0.1"
_REPORT_SCHEMA = "gate1a1-fixed-benchmark-report-v0.1"
_ALLOWED_OUTCOMES = {
    "HOLD",
    "QAOA_RESEARCH_ONLY",
    "QAOA_ADDS_NO_MEASURABLE_VALUE",
    "QAOA_CANDIDATE_FOR_FURTHER_TESTING",
}
_REQUIRED_LOCKS = {
    "authority": False,
    "artifact_is_command": False,
    "automatic_gate_promotion": False,
    "gate1b_activated": False,
    "may_execute": False,
    "may_sign": False,
    "may_submit_transaction": False,
    "may_access_wallet": False,
    "may_move_capital": False,
    "human_promotion_required": True,
}


def canonical_sha256(payload: object) -> str:
    """Return a stable SHA-256 digest over canonical JSON."""

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _sequence(value: object, context: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be an array")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{context} keys mismatch; missing={missing}, extra={extra}")


def _require_sha256(value: object, context: str) -> str:
    digest = str(value)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError(f"{context} must be 64 lowercase hexadecimal characters")
    return digest


def _require_finite(value: object, context: str, *, minimum: float | None = None) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{context} must be finite")
    if minimum is not None and number < minimum:
        raise ValueError(f"{context} must be >= {minimum}")
    return number


def _validate_locks(payload: Mapping[str, object], context: str) -> None:
    for name, expected in _REQUIRED_LOCKS.items():
        if payload.get(name) is not expected:
            raise ValueError(f"{context}.{name} must be {expected!r}")


def _qubo_payload_without_hash(qubo: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in qubo.items() if key != "qubo_sha256"}


def _run_payload_without_hash(run: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in run.items() if key != "run_sha256"}


def _corpus_payload_without_id(corpus: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in corpus.items() if key != "corpus_id"}


def _parse_qubo(
    qubo: Mapping[str, object],
) -> tuple[
    tuple[str, ...],
    dict[str, float],
    dict[tuple[str, str], float],
    float,
    tuple[Mapping[str, object], ...],
]:
    _exact_keys(
        qubo,
        {
            "variable_order",
            "linear",
            "quadratic",
            "constant",
            "constraints",
            "assumptions",
            "qubo_sha256",
            "authority",
        },
        "qubo",
    )
    if qubo["authority"] is not False:
        raise ValueError("qubo.authority must be false")

    variable_order = tuple(
        str(item) for item in _sequence(qubo["variable_order"], "qubo.variable_order")
    )
    if not variable_order or len(set(variable_order)) != len(variable_order):
        raise ValueError("qubo.variable_order must contain unique variables")

    linear: dict[str, float] = {}
    for item in _sequence(qubo["linear"], "qubo.linear"):
        pair = _sequence(item, "qubo.linear item")
        if len(pair) != 2:
            raise ValueError("qubo.linear items must be [variable, coefficient]")
        variable = str(pair[0])
        if variable not in variable_order or variable in linear:
            raise ValueError("qubo.linear contains an unknown or duplicate variable")
        linear[variable] = _require_finite(pair[1], f"qubo.linear[{variable}]")
    if set(linear) != set(variable_order):
        raise ValueError("qubo.linear must define every variable exactly once")

    quadratic: dict[tuple[str, str], float] = {}
    for item in _sequence(qubo["quadratic"], "qubo.quadratic"):
        triple = _sequence(item, "qubo.quadratic item")
        if len(triple) != 3:
            raise ValueError("qubo.quadratic items must be [left, right, coefficient]")
        left, right = str(triple[0]), str(triple[1])
        if left not in variable_order or right not in variable_order or left == right:
            raise ValueError("qubo.quadratic contains invalid variables")
        ordered = tuple(sorted((left, right)))
        if ordered in quadratic:
            raise ValueError("qubo.quadratic contains a duplicate pair")
        quadratic[ordered] = _require_finite(
            triple[2], f"qubo.quadratic[{left},{right}]"
        )

    constraints = tuple(
        _mapping(item, "qubo.constraint")
        for item in _sequence(qubo["constraints"], "qubo.constraints")
    )
    for constraint in constraints:
        _exact_keys(constraint, {"type", "variables"}, "qubo.constraint")
        if constraint["type"] not in {"at_most_one", "exactly_one"}:
            raise ValueError("unsupported qubo constraint type")
        names = tuple(
            str(item)
            for item in _sequence(constraint["variables"], "constraint.variables")
        )
        if (
            not names
            or len(set(names)) != len(names)
            or not set(names).issubset(variable_order)
        ):
            raise ValueError("constraint.variables must be unique known variables")

    assumptions = _mapping(qubo["assumptions"], "qubo.assumptions")
    _exact_keys(
        assumptions,
        {
            "fee_model_sha256",
            "gas_model_sha256",
            "latency_model_sha256",
            "slippage_model_sha256",
            "liquidity_model_sha256",
            "failure_model_sha256",
        },
        "qubo.assumptions",
    )
    for key, value in assumptions.items():
        _require_sha256(value, f"qubo.assumptions.{key}")

    expected_hash = canonical_sha256(_qubo_payload_without_hash(qubo))
    if _require_sha256(qubo["qubo_sha256"], "qubo.qubo_sha256") != expected_hash:
        raise ValueError("qubo.qubo_sha256 does not match the immutable QUBO payload")

    constant = _require_finite(qubo["constant"], "qubo.constant")
    return variable_order, linear, quadratic, constant, constraints


def _objective(
    variable_order: Sequence[str],
    linear: Mapping[str, float],
    quadratic: Mapping[tuple[str, str], float],
    constant: float,
    assignment: Sequence[int],
) -> float:
    bits = {name: assignment[index] for index, name in enumerate(variable_order)}
    value = constant + sum(linear[name] * bits[name] for name in variable_order)
    value += sum(
        coefficient * bits[left] * bits[right]
        for (left, right), coefficient in quadratic.items()
    )
    return value


def _feasible(
    variable_order: Sequence[str],
    constraints: Sequence[Mapping[str, object]],
    assignment: Sequence[int],
) -> bool:
    bits = {name: assignment[index] for index, name in enumerate(variable_order)}
    for constraint in constraints:
        count = sum(
            bits[str(name)]
            for name in _sequence(constraint["variables"], "constraint.variables")
        )
        if constraint["type"] == "at_most_one" and count > 1:
            return False
        if constraint["type"] == "exactly_one" and count != 1:
            return False
    return True


def _exact_classical_solution(
    variable_order: Sequence[str],
    linear: Mapping[str, float],
    quadratic: Mapping[tuple[str, str], float],
    constant: float,
    constraints: Sequence[Mapping[str, object]],
) -> tuple[tuple[int, ...], float]:
    best_assignment: tuple[int, ...] | None = None
    best_objective = math.inf
    for assignment in itertools.product((0, 1), repeat=len(variable_order)):
        if not _feasible(variable_order, constraints, assignment):
            continue
        objective = _objective(variable_order, linear, quadratic, constant, assignment)
        if objective < best_objective - 1e-12 or (
            math.isclose(objective, best_objective, abs_tol=1e-12)
            and (best_assignment is None or assignment < best_assignment)
        ):
            best_assignment = assignment
            best_objective = objective
    if best_assignment is None:
        raise ValueError("QUBO constraints have no feasible assignment")
    return best_assignment, best_objective


def _validate_run(
    run: Mapping[str, object],
    *,
    context: str,
    variable_order: Sequence[str],
    linear: Mapping[str, float],
    quadratic: Mapping[tuple[str, str], float],
    constant: float,
    constraints: Sequence[Mapping[str, object]],
    include_seed: bool,
) -> tuple[tuple[int, ...], float, bool, float, float, int | None]:
    expected_keys = {
        "assignment",
        "objective_value",
        "feasible",
        "runtime_ms",
        "resource_units",
        "verifier_result",
        "run_sha256",
        "authority",
    }
    if include_seed:
        expected_keys.add("seed")
    _exact_keys(run, expected_keys, context)
    if run["authority"] is not False:
        raise ValueError(f"{context}.authority must be false")
    if run["verifier_result"] != "PASS":
        raise ValueError(f"{context}.verifier_result must be PASS")

    assignment = tuple(
        int(bit) for bit in _sequence(run["assignment"], f"{context}.assignment")
    )
    if len(assignment) != len(variable_order) or any(bit not in (0, 1) for bit in assignment):
        raise ValueError(f"{context}.assignment must match the QUBO variable order")
    objective = _require_finite(run["objective_value"], f"{context}.objective_value")
    derived_objective = _objective(
        variable_order, linear, quadratic, constant, assignment
    )
    if not math.isclose(objective, derived_objective, abs_tol=1e-12):
        raise ValueError(f"{context}.objective_value does not match the immutable QUBO")
    feasible = bool(run["feasible"])
    if feasible != _feasible(variable_order, constraints, assignment):
        raise ValueError(f"{context}.feasible does not match the immutable constraints")
    runtime_ms = _require_finite(
        run["runtime_ms"], f"{context}.runtime_ms", minimum=0.0
    )
    resource_units = _require_finite(
        run["resource_units"], f"{context}.resource_units", minimum=0.0
    )
    expected_hash = canonical_sha256(_run_payload_without_hash(run))
    if _require_sha256(run["run_sha256"], f"{context}.run_sha256") != expected_hash:
        raise ValueError(f"{context}.run_sha256 does not match the run payload")
    seed = int(run["seed"]) if include_seed else None
    return assignment, objective, feasible, runtime_ms, resource_units, seed


def _validate_policy(policy: Mapping[str, object]) -> dict[str, float | int | bool]:
    _exact_keys(
        policy,
        {
            "same_qubo_hash_required",
            "feasibility_not_worse",
            "objective_tolerance",
            "candidate_min_runtime_improvement_fraction",
            "candidate_max_resource_ratio",
            "repeated_seed_stability_required",
            "minimum_seed_count",
            "maximum_objective_spread",
            "verifier_agreement_required",
            "human_review_required",
        },
        "policy",
    )
    for key in (
        "same_qubo_hash_required",
        "feasibility_not_worse",
        "repeated_seed_stability_required",
        "verifier_agreement_required",
        "human_review_required",
    ):
        if policy[key] is not True:
            raise ValueError(f"policy.{key} must be true")
    minimum_seed_count = int(policy["minimum_seed_count"])
    if minimum_seed_count < 2:
        raise ValueError("policy.minimum_seed_count must be at least 2")
    return {
        "same_qubo_hash_required": True,
        "feasibility_not_worse": True,
        "objective_tolerance": _require_finite(
            policy["objective_tolerance"],
            "policy.objective_tolerance",
            minimum=0.0,
        ),
        "candidate_min_runtime_improvement_fraction": _require_finite(
            policy["candidate_min_runtime_improvement_fraction"],
            "policy.candidate_min_runtime_improvement_fraction",
            minimum=0.0,
        ),
        "candidate_max_resource_ratio": _require_finite(
            policy["candidate_max_resource_ratio"],
            "policy.candidate_max_resource_ratio",
            minimum=0.0,
        ),
        "repeated_seed_stability_required": True,
        "minimum_seed_count": minimum_seed_count,
        "maximum_objective_spread": _require_finite(
            policy["maximum_objective_spread"],
            "policy.maximum_objective_spread",
            minimum=0.0,
        ),
        "verifier_agreement_required": True,
        "human_review_required": True,
    }


def _evaluate_case(
    case: Mapping[str, object], policy: Mapping[str, float | int | bool]
) -> dict[str, object]:
    _exact_keys(
        case,
        {
            "case_id",
            "description",
            "qubo",
            "classical",
            "qaoa",
            "expected_outcome",
            "authority",
        },
        "case",
    )
    case_id = str(case["case_id"])
    if not case_id.startswith("gate1a1-benchmark-case:"):
        raise ValueError("case.case_id must use the gate1a1-benchmark-case namespace")
    if not str(case["description"]).strip():
        raise ValueError("case.description is required")
    if case["authority"] is not False:
        raise ValueError("case.authority must be false")
    if case["expected_outcome"] not in _ALLOWED_OUTCOMES - {"HOLD"}:
        raise ValueError("case.expected_outcome is not allowed")

    qubo = _mapping(case["qubo"], "case.qubo")
    variable_order, linear, quadratic, constant, constraints = _parse_qubo(qubo)
    qubo_sha256 = str(qubo["qubo_sha256"])

    classical = _mapping(case["classical"], "case.classical")
    _exact_keys(classical, {"solver", "solver_version", "run"}, "case.classical")
    if not str(classical["solver"]).strip() or not str(classical["solver_version"]).strip():
        raise ValueError("classical solver and version are required")
    classical_run = _mapping(classical["run"], "case.classical.run")
    (
        classical_assignment,
        classical_objective,
        classical_feasible,
        classical_runtime,
        classical_resources,
        _,
    ) = _validate_run(
        classical_run,
        context="case.classical.run",
        variable_order=variable_order,
        linear=linear,
        quadratic=quadratic,
        constant=constant,
        constraints=constraints,
        include_seed=False,
    )
    if not classical_feasible:
        raise ValueError("classical baseline must be feasible")
    exact_assignment, exact_objective = _exact_classical_solution(
        variable_order, linear, quadratic, constant, constraints
    )
    if classical_assignment != exact_assignment or not math.isclose(
        classical_objective, exact_objective, abs_tol=1e-12
    ):
        raise ValueError("classical baseline is not the deterministic exact optimum")

    qaoa = _mapping(case["qaoa"], "case.qaoa")
    _exact_keys(
        qaoa,
        {
            "sampler",
            "backend",
            "backend_version",
            "depth",
            "optimizer",
            "optimizer_version",
            "shots",
            "same_qubo_sha256",
            "runs",
            "authority",
        },
        "case.qaoa",
    )
    if qaoa["authority"] is not False:
        raise ValueError("case.qaoa.authority must be false")
    for field in ("sampler", "backend", "backend_version", "optimizer", "optimizer_version"):
        if not str(qaoa[field]).strip():
            raise ValueError(f"case.qaoa.{field} is required")
    if int(qaoa["depth"]) < 1 or int(qaoa["shots"]) < 1:
        raise ValueError("case.qaoa depth and shots must be positive")
    if (
        _require_sha256(qaoa["same_qubo_sha256"], "case.qaoa.same_qubo_sha256")
        != qubo_sha256
    ):
        raise ValueError("QAOA evidence is not bound to the classical QUBO")

    raw_runs = _sequence(qaoa["runs"], "case.qaoa.runs")
    if len(raw_runs) < int(policy["minimum_seed_count"]):
        raise ValueError("QAOA evidence does not meet the precommitted seed count")
    qaoa_objectives: list[float] = []
    qaoa_runtimes: list[float] = []
    qaoa_resources: list[float] = []
    qaoa_assignments: list[tuple[int, ...]] = []
    seeds: set[int] = set()
    for index, item in enumerate(raw_runs):
        run = _mapping(item, f"case.qaoa.runs[{index}]")
        assignment, objective, feasible, runtime_ms, resource_units, seed = _validate_run(
            run,
            context=f"case.qaoa.runs[{index}]",
            variable_order=variable_order,
            linear=linear,
            quadratic=quadratic,
            constant=constant,
            constraints=constraints,
            include_seed=True,
        )
        assert seed is not None
        if seed in seeds:
            raise ValueError("QAOA seeds must be unique")
        seeds.add(seed)
        if bool(policy["feasibility_not_worse"]) and not feasible:
            raise ValueError("QAOA feasibility is worse than the classical baseline")
        qaoa_objectives.append(objective)
        qaoa_runtimes.append(runtime_ms)
        qaoa_resources.append(resource_units)
        qaoa_assignments.append(assignment)

    spread = max(qaoa_objectives) - min(qaoa_objectives)
    stable = spread <= float(policy["maximum_objective_spread"])
    if bool(policy["repeated_seed_stability_required"]) and not stable:
        outcome = "QAOA_RESEARCH_ONLY"
    else:
        tolerance = float(policy["objective_tolerance"])
        not_worse = all(
            value <= classical_objective + tolerance for value in qaoa_objectives
        )
        all_agree = all(
            assignment == classical_assignment for assignment in qaoa_assignments
        )
        median_runtime = statistics.median(qaoa_runtimes)
        median_resources = statistics.median(qaoa_resources)
        runtime_improvement = (
            (classical_runtime - median_runtime) / classical_runtime
            if classical_runtime > 0.0
            else -math.inf
        )
        resource_ratio = (
            median_resources / classical_resources
            if classical_resources > 0.0
            else math.inf
        )
        candidate = (
            not_worse
            and all_agree
            and runtime_improvement
            >= float(policy["candidate_min_runtime_improvement_fraction"])
            and resource_ratio <= float(policy["candidate_max_resource_ratio"])
        )
        if candidate:
            outcome = "QAOA_CANDIDATE_FOR_FURTHER_TESTING"
        elif not_worse and all_agree:
            outcome = "QAOA_ADDS_NO_MEASURABLE_VALUE"
        else:
            outcome = "QAOA_RESEARCH_ONLY"

    if outcome != case["expected_outcome"]:
        raise ValueError(
            f"case.expected_outcome mismatch: expected {case['expected_outcome']}, "
            f"derived {outcome}"
        )

    median_runtime = statistics.median(qaoa_runtimes)
    median_resources = statistics.median(qaoa_resources)
    return {
        "case_id": case_id,
        "qubo_sha256": qubo_sha256,
        "classical_solver": f"{classical['solver']}@{classical['solver_version']}",
        "qaoa_backend": f"{qaoa['backend']}@{qaoa['backend_version']}",
        "qaoa_sampler": str(qaoa["sampler"]),
        "qaoa_optimizer": f"{qaoa['optimizer']}@{qaoa['optimizer_version']}",
        "depth": int(qaoa["depth"]),
        "shots": int(qaoa["shots"]),
        "seed_count": len(seeds),
        "classical_objective": classical_objective,
        "qaoa_objective_min": min(qaoa_objectives),
        "qaoa_objective_max": max(qaoa_objectives),
        "objective_spread": spread,
        "solution_agreement": all(
            assignment == classical_assignment for assignment in qaoa_assignments
        ),
        "classical_runtime_ms": classical_runtime,
        "qaoa_median_runtime_ms": median_runtime,
        "classical_resource_units": classical_resources,
        "qaoa_median_resource_units": median_resources,
        "verifier_agreement": True,
        "outcome": outcome,
        "authority": False,
    }


def evaluate_corpus(corpus: Mapping[str, object]) -> dict[str, object]:
    """Validate and evaluate one fixed classical/QAOA corpus."""

    corpus_sha256 = canonical_sha256(corpus)
    hold_reasons: list[str] = []
    case_results: list[dict[str, object]] = []
    try:
        _exact_keys(
            corpus,
            {
                "schema_version",
                "corpus_id",
                "policy",
                "cases",
                *set(_REQUIRED_LOCKS),
            },
            "corpus",
        )
        if corpus["schema_version"] != _CORPUS_SCHEMA:
            raise ValueError("corpus.schema_version mismatch")
        _validate_locks(corpus, "corpus")
        expected_corpus_id = (
            "gate1a1-benchmark-corpus:"
            f"{canonical_sha256(_corpus_payload_without_id(corpus))[:24]}"
        )
        if corpus["corpus_id"] != expected_corpus_id:
            raise ValueError("corpus.corpus_id does not match the immutable corpus payload")
        policy = _validate_policy(_mapping(corpus["policy"], "corpus.policy"))
        raw_cases = _sequence(corpus["cases"], "corpus.cases")
        if not raw_cases:
            raise ValueError("corpus.cases cannot be empty")
        seen_case_ids: set[str] = set()
        for index, item in enumerate(raw_cases):
            case = _mapping(item, f"corpus.cases[{index}]")
            case_id = str(case.get("case_id", ""))
            if case_id in seen_case_ids:
                raise ValueError("corpus case identifiers must be unique")
            seen_case_ids.add(case_id)
            try:
                case_results.append(_evaluate_case(case, policy))
            except ValueError as exc:
                hold_reasons.append(f"{case_id or f'case[{index}]'}: {exc}")
    except (TypeError, ValueError) as exc:
        hold_reasons.append(str(exc))

    if hold_reasons:
        overall_outcome = "HOLD"
    else:
        outcomes = {str(result["outcome"]) for result in case_results}
        if outcomes == {"QAOA_CANDIDATE_FOR_FURTHER_TESTING"}:
            overall_outcome = "QAOA_CANDIDATE_FOR_FURTHER_TESTING"
        elif outcomes.issubset({"QAOA_ADDS_NO_MEASURABLE_VALUE"}):
            overall_outcome = "QAOA_ADDS_NO_MEASURABLE_VALUE"
        else:
            overall_outcome = "QAOA_RESEARCH_ONLY"

    report_seed = {
        "schema_version": _REPORT_SCHEMA,
        "corpus_id": str(corpus.get("corpus_id", "UNKNOWN")),
        "corpus_sha256": corpus_sha256,
        "overall_outcome": overall_outcome,
        "hold_reasons": hold_reasons,
        "case_results": case_results,
        **_REQUIRED_LOCKS,
    }
    report_id = f"gate1a1-benchmark-report:{canonical_sha256(report_seed)[:24]}"
    return {"report_id": report_id, **report_seed}


def load_corpus(path: str | Path) -> Mapping[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return _mapping(payload, "corpus")


def render_summary(report: Mapping[str, object]) -> str:
    lines = [
        f"GATE1A1_BENCHMARK={report['overall_outcome']}",
        f"CORPUS={report['corpus_id']}",
        f"CASES={len(report['case_results'])}",
        f"HOLDS={len(report['hold_reasons'])}",
        "AUTHORITY=false",
        "GATE1B_ACTIVATED=false",
        "HUMAN_PROMOTION_REQUIRED=true",
    ]
    for result in report["case_results"]:
        lines.append(f"CASE {result['case_id']} -> {result['outcome']}")
    for reason in report["hold_reasons"]:
        lines.append(f"HOLD_REASON={reason}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the fixed Gate 1A.1 classical/QAOA corpus"
    )
    parser.add_argument("corpus", help="Path to the immutable benchmark corpus JSON")
    parser.add_argument("--output", help="Optional JSON report path")
    parser.add_argument("--summary", action="store_true", help="Emit compact operator summary")
    args = parser.parse_args(argv)

    report = evaluate_corpus(load_corpus(args.corpus))
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if args.summary:
        print(render_summary(report))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["overall_outcome"] == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
