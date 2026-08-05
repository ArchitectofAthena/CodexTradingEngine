"""Deterministic offline Gate 1 source-consensus evaluator.

The evaluator preserves conflict, freshness, units, review state, and provenance
independence. It never averages disagreement, never treats shared lineage as
independent corroboration, and never grants proposal, signing, transaction,
execution, or capital authority.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

CONTRACT_VERSION = "codex-gate1-source-consensus-v0.1"
ARTIFACT_TYPE = "Gate1SourceConsensusDecision"
DECISION_CODES = frozenset(
    {
        "ACCEPT_OBSERVATION_ONLY",
        "HOLD_CONFLICT",
        "HOLD_CONCENTRATION",
        "HOLD_STALE",
        "HOLD_UNIT_AMBIGUITY",
        "HOLD_REVIEW_EXPIRED",
        "HOLD_SOURCE_REVIEW",
    }
)
GATE_POSTURE = {
    "gate_0": "ACTIVE",
    "gate_1a": "ACTIVE_FOR_APPROVED_ALPHA_RUNS",
    "gate_1b": "LOCKED",
    "gate_2": "LOCKED",
    "gate_3": "LOCKED",
    "gate_4_through_6": "LOCKED",
}
AUTHORITY_BOUNDARY = {
    "authority": False,
    "artifact_is_command": False,
    "network_access_allowed": False,
    "may_generate_live_proposal": False,
    "may_execute": False,
    "may_sign": False,
    "may_submit_transaction": False,
    "may_move_capital": False,
}
ZERO_COUNTS = {
    "live_proposals_generated": 0,
    "signatures_created": 0,
    "transactions_submitted": 0,
    "executions_performed": 0,
    "capital_movements": 0,
}

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_PACKET_SCHEMA = _ROOT / "schemas" / "gate1_source_consensus_packet_v0_1.schema.json"
_DEFAULT_DECISION_SCHEMA = _ROOT / "schemas" / "gate1_source_consensus_decision_v0_1.schema.json"


class SourceConsensusError(RuntimeError):
    """Raised when an evidence packet cannot be evaluated deterministically."""


@dataclass(frozen=True, slots=True)
class NormalizedObservation:
    source_id: str
    registry_sha256: str
    provenance_group: str
    operator: str
    original_value: str
    original_unit: str
    decimals: int
    conversion_kind: str
    conversion_factor: str
    normalized_value: Decimal
    comparison_unit: str
    observed_at: str
    expires_at: str
    review_status: str
    review_expires_at: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "registry_sha256": self.registry_sha256,
            "provenance_group": self.provenance_group,
            "operator": self.operator,
            "original_value": self.original_value,
            "original_unit": self.original_unit,
            "decimals": self.decimals,
            "conversion": {
                "kind": self.conversion_kind,
                "factor": self.conversion_factor,
                "comparison_unit": self.comparison_unit,
            },
            "normalized_value": decimal_string(self.normalized_value),
            "comparison_unit": self.comparison_unit,
            "observed_at": self.observed_at,
            "expires_at": self.expires_at,
            "review_status": self.review_status,
            "review_expires_at": self.review_expires_at,
        }


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def parse_utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise SourceConsensusError(f"invalid date-time at {field}") from exc
    if parsed.tzinfo is None:
        raise SourceConsensusError(f"date-time must include timezone at {field}")
    return parsed.astimezone(UTC)


def decimal_value(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise SourceConsensusError(f"boolean is not a decimal at {field}")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SourceConsensusError(f"invalid decimal at {field}") from exc
    if not parsed.is_finite():
        raise SourceConsensusError(f"non-finite decimal at {field}")
    return parsed


def decimal_string(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


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


def require_schema(document: Any, schema: Mapping[str, Any], label: str) -> None:
    errors = _schema_errors(document, schema)
    if errors:
        raise SourceConsensusError(f"{label} schema validation failed: " + "; ".join(errors[:8]))


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceConsensusError(
            f"unable to load JSON {path}: {type(exc).__name__}: {exc}"
        ) from exc


def normalize_observation(
    observation: Mapping[str, Any],
) -> NormalizedObservation:
    source_id = str(observation["source_id"])
    value = decimal_value(observation["value"], f"{source_id}.value")
    decimals = observation.get("decimals")
    unit = str(observation.get("unit", "")).strip()
    comparison_unit = str(observation.get("comparison_unit", "")).strip()
    conversion = observation.get("conversion", {})

    if not isinstance(decimals, int) or isinstance(decimals, bool):
        raise SourceConsensusError(f"{source_id} has unknown decimal convention")
    if decimals < 0 or decimals > 36:
        raise SourceConsensusError(f"{source_id} decimal convention is out of range")
    if not unit or not comparison_unit:
        raise SourceConsensusError(f"{source_id} has unknown unit")
    kind = str(conversion.get("kind", ""))
    factor_text = str(conversion.get("factor", ""))
    if kind == "identity":
        factor = Decimal("1")
        factor_text = "1"
        if unit != comparison_unit:
            raise SourceConsensusError(f"{source_id} identity conversion cannot change units")
    elif kind == "decimal_scale":
        factor = decimal_value(factor_text, f"{source_id}.conversion.factor")
    else:
        raise SourceConsensusError(f"{source_id} has unsupported conversion")

    normalized = value * factor
    if not normalized.is_finite():
        raise SourceConsensusError(f"{source_id} conversion produced non-finite value")
    return NormalizedObservation(
        source_id=source_id,
        registry_sha256=str(observation["registry_sha256"]),
        provenance_group=str(observation["provenance_group"]),
        operator=str(observation["operator"]),
        original_value=str(observation["value"]),
        original_unit=unit,
        decimals=decimals,
        conversion_kind=kind,
        conversion_factor=decimal_string(factor),
        normalized_value=normalized,
        comparison_unit=comparison_unit,
        observed_at=str(observation["observed_at"]),
        expires_at=str(observation["expires_at"]),
        review_status=str(observation["review_status"]),
        review_expires_at=(
            str(observation["review_expires_at"])
            if observation.get("review_expires_at") is not None
            else None
        ),
    )


def _receipt_material(decision: Mapping[str, Any]) -> dict[str, Any]:
    material = copy.deepcopy(dict(decision))
    material.pop("receipt_sha256", None)
    return material


def _decision(
    *,
    packet: Mapping[str, Any],
    observations: Sequence[NormalizedObservation],
    code: str,
    reasons: Sequence[str],
    conflict_magnitude: Decimal | None,
    tolerance: Decimal,
    independence: bool,
    unresolved_questions: Sequence[str],
) -> dict[str, Any]:
    normalized = [item.as_dict() for item in sorted(observations, key=lambda item: item.source_id)]
    groups = sorted({item.provenance_group for item in observations})
    operators = sorted({item.operator for item in observations})
    values = sorted(item.normalized_value for item in observations)
    decision: dict[str, Any] = {
        "artifact_type": ARTIFACT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "evaluation_id": packet["evaluation_id"],
        "evaluated_at": packet["evaluated_at"],
        "receipt_sha256": "0" * 64,
        "comparison": {
            "comparison_unit": packet["comparison_unit"],
            "absolute_tolerance": decimal_string(tolerance),
            "source_count": len(observations),
            "provenance_group_count": len(groups),
            "operator_count": len(operators),
            "independent_provenance": independence,
            "observed_min": decimal_string(values[0]) if values else None,
            "observed_max": decimal_string(values[-1]) if values else None,
            "conflict_magnitude": (
                decimal_string(conflict_magnitude) if conflict_magnitude is not None else None
            ),
            "aggregate_value": None,
            "aggregation_performed": False,
        },
        "observations": normalized,
        "decision": {
            "code": code,
            "reasons": sorted(set(reasons)),
            "observation_only": code == "ACCEPT_OBSERVATION_ONLY",
            "human_review_required": True,
        },
        "unresolved_questions": sorted(set(unresolved_questions)),
        "counts": dict(ZERO_COUNTS),
        "gate_posture": dict(GATE_POSTURE),
        "authority": dict(AUTHORITY_BOUNDARY),
    }
    decision["receipt_sha256"] = sha256_hex(_receipt_material(decision))
    return decision


def evaluate_packet(
    packet: Mapping[str, Any],
    *,
    packet_schema: Mapping[str, Any],
    decision_schema: Mapping[str, Any],
) -> dict[str, Any]:
    require_schema(packet, packet_schema, "source-consensus packet")
    evaluated_at = parse_utc(str(packet["evaluated_at"]), "evaluated_at")
    tolerance = decimal_value(packet["absolute_tolerance"], "absolute_tolerance")
    if tolerance < 0:
        raise SourceConsensusError("absolute tolerance may not be negative")

    raw_observations = packet["observations"]
    source_ids = [str(item["source_id"]) for item in raw_observations]
    if len(source_ids) != len(set(source_ids)):
        raise SourceConsensusError("source IDs must be unique")

    normalized: list[NormalizedObservation] = []
    unit_errors: list[str] = []
    for observation in raw_observations:
        try:
            item = normalize_observation(observation)
        except SourceConsensusError as exc:
            unit_errors.append(str(exc))
            continue
        normalized.append(item)

    unresolved = list(packet.get("unresolved_questions", []))
    if unit_errors:
        decision = _decision(
            packet=packet,
            observations=normalized,
            code="HOLD_UNIT_AMBIGUITY",
            reasons=unit_errors,
            conflict_magnitude=None,
            tolerance=tolerance,
            independence=False,
            unresolved_questions=unresolved,
        )
        require_schema(decision, decision_schema, "source-consensus decision")
        return decision

    comparison_units = {item.comparison_unit for item in normalized}
    if comparison_units != {str(packet["comparison_unit"])}:
        decision = _decision(
            packet=packet,
            observations=normalized,
            code="HOLD_UNIT_AMBIGUITY",
            reasons=["normalized observations do not share the declared comparison unit"],
            conflict_magnitude=None,
            tolerance=tolerance,
            independence=False,
            unresolved_questions=unresolved,
        )
        require_schema(decision, decision_schema, "source-consensus decision")
        return decision

    review_failures = [
        item.source_id
        for item in normalized
        if item.review_status != "ELIGIBLE" or item.review_expires_at is None
    ]
    if review_failures:
        decision = _decision(
            packet=packet,
            observations=normalized,
            code="HOLD_SOURCE_REVIEW",
            reasons=[
                "missing or non-eligible source review: " + ", ".join(sorted(review_failures))
            ],
            conflict_magnitude=None,
            tolerance=tolerance,
            independence=False,
            unresolved_questions=unresolved,
        )
        require_schema(decision, decision_schema, "source-consensus decision")
        return decision

    expired_reviews = [
        item.source_id
        for item in normalized
        if parse_utc(str(item.review_expires_at), f"{item.source_id}.review_expires_at")
        <= evaluated_at
    ]
    if expired_reviews:
        decision = _decision(
            packet=packet,
            observations=normalized,
            code="HOLD_REVIEW_EXPIRED",
            reasons=["expired source review: " + ", ".join(sorted(expired_reviews))],
            conflict_magnitude=None,
            tolerance=tolerance,
            independence=False,
            unresolved_questions=unresolved,
        )
        require_schema(decision, decision_schema, "source-consensus decision")
        return decision

    stale_sources = [
        item.source_id
        for item in normalized
        if parse_utc(item.expires_at, f"{item.source_id}.expires_at") <= evaluated_at
    ]
    if stale_sources:
        decision = _decision(
            packet=packet,
            observations=normalized,
            code="HOLD_STALE",
            reasons=["stale observations: " + ", ".join(sorted(stale_sources))],
            conflict_magnitude=None,
            tolerance=tolerance,
            independence=False,
            unresolved_questions=unresolved,
        )
        require_schema(decision, decision_schema, "source-consensus decision")
        return decision

    values = sorted(item.normalized_value for item in normalized)
    conflict = values[-1] - values[0]
    provenance_counts = Counter(item.provenance_group for item in normalized)
    independent = all(count == 1 for count in provenance_counts.values())

    if conflict > tolerance:
        code = "HOLD_CONFLICT"
        reasons = [
            "material disagreement exceeds declared absolute tolerance",
            "conflicting observations were preserved and not averaged",
        ]
    elif not independent:
        code = "HOLD_CONCENTRATION"
        repeated = sorted(group for group, count in provenance_counts.items() if count > 1)
        reasons = [
            "agreement does not establish independence",
            "shared provenance groups: " + ", ".join(repeated),
        ]
    else:
        code = "ACCEPT_OBSERVATION_ONLY"
        reasons = [
            "reviewed fresh observations agree within tolerance",
            "provenance groups are distinct",
            "acceptance is observation-only and grants no authority",
        ]

    decision = _decision(
        packet=packet,
        observations=normalized,
        code=code,
        reasons=reasons,
        conflict_magnitude=conflict,
        tolerance=tolerance,
        independence=independent,
        unresolved_questions=unresolved,
    )
    require_schema(decision, decision_schema, "source-consensus decision")
    return decision


def verify_decision(
    decision: Mapping[str, Any],
    decision_schema: Mapping[str, Any],
) -> tuple[str, ...]:
    findings = list(_schema_errors(decision, decision_schema))
    if decision.get("receipt_sha256") != sha256_hex(_receipt_material(decision)):
        findings.append("receipt hash does not match canonical decision evidence")
    comparison = decision.get("comparison", {})
    if comparison.get("aggregate_value") is not None:
        findings.append("aggregate value must remain null")
    if comparison.get("aggregation_performed") is not False:
        findings.append("aggregation_performed must remain false")
    counts = decision.get("counts", {})
    if any(counts.get(key) != 0 for key in ZERO_COUNTS):
        findings.append(
            "all proposal, signing, transaction, execution, and capital counts must be zero"
        )
    authority = decision.get("authority", {})
    for key, expected in AUTHORITY_BOUNDARY.items():
        if authority.get(key) is not expected:
            findings.append(f"authority.{key} must be {str(expected).lower()}")
    return tuple(sorted(set(findings)))


def render_summary(decision: Mapping[str, Any]) -> str:
    comparison = decision["comparison"]
    return "\n".join(
        (
            "CODEX GATE 1 SOURCE CONSENSUS v0.1",
            f"EVALUATION: {decision['evaluation_id']}",
            f"SOURCES: {comparison['source_count']}",
            f"PROVENANCE GROUPS: {comparison['provenance_group_count']}",
            f"INDEPENDENT: {str(comparison['independent_provenance']).lower()}",
            f"UNIT: {comparison['comparison_unit']}",
            f"TOLERANCE: {comparison['absolute_tolerance']}",
            f"CONFLICT MAGNITUDE: {comparison['conflict_magnitude'] or 'not-computed'}",
            f"DECISION: {decision['decision']['code']}",
            "AGGREGATION: none",
            f"RECEIPT: {decision['receipt_sha256']}",
            "LIVE PROPOSALS: 0",
            "EXECUTION: LOCKED",
            "CAPITAL: LOCKED",
            "AUTHORITY: false",
        )
    )


def write_decision(output_dir: Path, decision: Mapping[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "source-consensus-decision.json"
    text_path = output_dir / "source-consensus-summary.txt"
    json_path.write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    text_path.write_text(render_summary(decision) + "\n", encoding="utf-8")
    return json_path, text_path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="codex-gate1-consensus",
        description="Evaluate offline Gate 1 source diversity without aggregation or authority.",
    )
    subparsers = result.add_subparsers(dest="command", required=True)

    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--packet", type=Path, required=True)
    evaluate.add_argument("--packet-schema", type=Path, default=_DEFAULT_PACKET_SCHEMA)
    evaluate.add_argument("--decision-schema", type=Path, default=_DEFAULT_DECISION_SCHEMA)
    evaluate.add_argument("--output-dir", type=Path, required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--decision", type=Path, required=True)
    verify.add_argument("--decision-schema", type=Path, default=_DEFAULT_DECISION_SCHEMA)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        decision_schema = _load_json(args.decision_schema)
        if args.command == "verify":
            findings = verify_decision(_load_json(args.decision), decision_schema)
            print(json.dumps({"valid": not findings, "findings": findings}, indent=2))
            return 0 if not findings else 1

        packet = _load_json(args.packet)
        packet_schema = _load_json(args.packet_schema)
        decision = evaluate_packet(
            packet,
            packet_schema=packet_schema,
            decision_schema=decision_schema,
        )
        findings = verify_decision(decision, decision_schema)
        if findings:
            raise SourceConsensusError("; ".join(findings))
        paths = write_decision(args.output_dir, decision)
    except (SourceConsensusError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"HOLD: {exc}")
        return 2

    print(render_summary(decision))
    print(f"Decision JSON: {paths[0]}")
    print(f"Summary text: {paths[1]}")
    return 0 if decision["decision"]["code"] == "ACCEPT_OBSERVATION_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
