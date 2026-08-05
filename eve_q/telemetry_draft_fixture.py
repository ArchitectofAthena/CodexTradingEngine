"""Deterministic Gate 1A telemetry-to-draft-fixture adapter.

The adapter translates one already captured and validated public-testnet snapshot
into a local modeling draft. Observation, transformation, assumption, review,
and authority remain separate. No network request, proposal generation, wallet,
signing, transaction, execution, or capital movement is available here.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from eve_q.alpha_doctor import validate_registry
from eve_q.gate1_readonly_runtime import parse_utc, validate_snapshot_v2


ADAPTER_VERSION = "codex-telemetry-draft-v0.1"
DRAFT_ARTIFACT_TYPE = "TelemetryDraftFixture"
MAPPING_SCHEMA_VERSION = "0.1"
DRAFT_SCHEMA_VERSION = "0.1"
REVIEW_STATES = frozenset(
    {
        "DRAFT_UNREVIEWED",
        "RETURN_FOR_EVIDENCE",
        "REVIEWED_FOR_LOCAL_SIMULATION",
        "REJECTED",
    }
)
REQUIRED_ECONOMIC_ASSUMPTIONS = (
    "gas_cost_eth",
    "fee_cost_eth",
    "liquidity_eth",
    "latency_ms",
    "slippage_eth",
    "bridge_cost_eth",
    "safety_margin_eth",
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
_DEFAULT_REGISTRY_SCHEMA = (
    _ROOT / "schemas" / "alpha_testnet_source_registry_v0_1.schema.json"
)
_DEFAULT_SNAPSHOT_SCHEMA = (
    _ROOT / "schemas" / "live_read_only_telemetry_snapshot_v0_2.schema.json"
)
_DEFAULT_MAPPING_SCHEMA = _ROOT / "schemas" / "telemetry_fixture_mapping_v0_1.schema.json"
_DEFAULT_DRAFT_SCHEMA = _ROOT / "schemas" / "telemetry_draft_fixture_v0_1.schema.json"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DraftFixtureError(RuntimeError):
    """Raised when a draft cannot be produced without widening authority."""


@dataclass(frozen=True, slots=True)
class DraftResult:
    draft: Mapping[str, Any]
    summary: Mapping[str, Any]
    summary_text: str


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


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DraftFixtureError(
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
        raise DraftFixtureError(
            f"{label} schema validation failed: " + "; ".join(errors[:8])
        )


def _json_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise DraftFixtureError(f"JSON pointer must start with '/': {pointer}")
    current = document
    for token in pointer[1:].split("/"):
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if key not in current:
                raise DraftFixtureError(f"JSON pointer does not exist: {pointer}")
            current = current[key]
        elif isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            try:
                index = int(key)
                current = current[index]
            except (ValueError, IndexError) as exc:
                raise DraftFixtureError(f"JSON pointer does not exist: {pointer}") from exc
        else:
            raise DraftFixtureError(f"JSON pointer crosses a scalar value: {pointer}")
    return copy.deepcopy(current)


def _normalize_decimal(value: Any) -> str:
    if isinstance(value, bool):
        raise DraftFixtureError("boolean values cannot be converted to decimal strings")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DraftFixtureError(f"value is not a finite decimal: {value!r}") from exc
    if not decimal_value.is_finite():
        raise DraftFixtureError(f"value is not a finite decimal: {value!r}")
    normalized = format(decimal_value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _transform_value(value: Any, transform: Mapping[str, Any]) -> tuple[Any, str]:
    kind = str(transform["kind"])
    if kind == "identity":
        return copy.deepcopy(value), "identity"
    if kind == "decimal_scale":
        try:
            factor = Decimal(str(transform["factor"]))
            converted = Decimal(str(value)) * factor
        except (InvalidOperation, ValueError) as exc:
            raise DraftFixtureError(
                "decimal_scale requires finite decimal value and factor"
            ) from exc
        if not factor.is_finite() or not converted.is_finite():
            raise DraftFixtureError(
                "decimal_scale requires finite decimal value and factor"
            )
        result = _normalize_decimal(converted)
        return result, f"decimal_scale factor={_normalize_decimal(factor)}"
    raise DraftFixtureError(f"unsupported transform kind: {kind}")


def _normalize_host(value: str) -> str:
    return value.strip().rstrip(".").lower()


def _find_source(registry: Mapping[str, Any], source_id: str) -> Mapping[str, Any]:
    matches = [
        item for item in registry.get("sources", []) if item.get("source_id") == source_id
    ]
    if len(matches) != 1:
        raise DraftFixtureError(
            f"registry must contain exactly one source entry for {source_id}"
        )
    source = matches[0]
    if source.get("disposition") != "ELIGIBLE":
        raise DraftFixtureError(f"source {source_id} has not earned ELIGIBLE status")
    return source


def _validate_source_boundary(
    snapshot: Mapping[str, Any],
    mapping: Mapping[str, Any],
    source: Mapping[str, Any],
) -> None:
    snapshot_source = snapshot["source"]
    source_id = str(source["source_id"])
    if (
        snapshot_source.get("source_id") != source_id
        or mapping.get("source_id") != source_id
    ):
        raise DraftFixtureError("snapshot, mapping, and registry source IDs must match")
    if source.get("network_class") != "testnet" or source.get("mainnet") is not False:
        raise DraftFixtureError("only reviewed public testnet sources are permitted")
    mainnet_identifiers = (
        str(source.get("source_id", "")),
        str(source.get("network_name", "")),
        str(source.get("url", "")),
        str(mapping.get("network_name", "")),
        str(mapping.get("chain_id", "")),
        str(mapping.get("route_id", "")),
    )
    if any("mainnet" in value.lower() for value in mainnet_identifiers):
        raise DraftFixtureError("mainnet identifiers are forbidden in Gate 1A drafts")
    expected_host = _normalize_host(str(source["host"]))
    for key in ("requested_uri", "final_uri"):
        host = urllib.parse.urlparse(str(snapshot_source[key])).hostname
        if not host or _normalize_host(host) != expected_host:
            raise DraftFixtureError(
                f"snapshot {key} does not match the reviewed exact host"
            )
    if _normalize_host(str(snapshot_source["allowlisted_host"])) != expected_host:
        raise DraftFixtureError(
            "snapshot allowlisted host does not match the reviewed source"
        )
    method = str(snapshot_source["method"])
    if method not in source.get("allowed_methods", []):
        raise DraftFixtureError(
            "snapshot method is not approved by the source registry"
        )
    for field in (
        "authority",
        "mainnet",
        "wallet_required",
        "signing_required",
        "transaction_submission",
        "capital_movement",
    ):
        if source.get(field) is not False:
            raise DraftFixtureError(f"reviewed source boundary requires {field}=false")
    if mapping.get("authority") is not False:
        raise DraftFixtureError("mapping authority must remain false")


def _validate_normalized_payload(
    snapshot: Mapping[str, Any], normalized_bytes: bytes
) -> None:
    format_name = snapshot["normalization"]["format"]
    if format_name in {"canonical_json", "head_metadata"}:
        try:
            decoded = json.loads(normalized_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DraftFixtureError(
                "normalized payload is not valid canonical JSON"
            ) from exc
    elif format_name == "utf8_text_lf":
        try:
            decoded = normalized_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DraftFixtureError("normalized payload is not valid UTF-8") from exc
    else:
        raise DraftFixtureError(f"unsupported normalization format: {format_name}")
    if decoded != snapshot["normalized_payload"]:
        raise DraftFixtureError(
            "normalized bytes do not match snapshot normalized_payload"
        )


def _assumption_map(document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    entries = document.get("assumptions", [])
    if not isinstance(entries, list):
        raise DraftFixtureError("assumptions must be an array")
    result: dict[str, Mapping[str, Any]] = {}
    for item in entries:
        if not isinstance(item, Mapping):
            raise DraftFixtureError("each assumption must be an object")
        field = str(item.get("field", ""))
        if not field or field in result:
            raise DraftFixtureError("assumption fields must be non-empty and unique")
        if (
            "value" not in item
            or not str(item.get("unit", ""))
            or not str(item.get("basis", ""))
        ):
            raise DraftFixtureError(
                f"assumption {field} requires value, unit, and basis"
            )
        result[field] = copy.deepcopy(item)
    return result


def _draft_material(
    snapshot: Mapping[str, Any],
    registry: Mapping[str, Any],
    source: Mapping[str, Any],
    mapping: Mapping[str, Any],
    assumptions_document: Mapping[str, Any],
) -> dict[str, Any]:
    observed_fields: list[dict[str, Any]] = []
    transformed_fields: list[dict[str, Any]] = []
    route_values: dict[str, Any] = {
        "route": mapping["route_id"],
        "chain": mapping["network_name"],
    }
    occupied: set[str] = {"route", "chain"}

    for entry in mapping["observations"]:
        target = str(entry["target_field"])
        if target in occupied:
            raise DraftFixtureError(f"duplicate or reserved target field: {target}")
        occupied.add(target)
        original = _json_pointer(snapshot, str(entry["source_pointer"]))
        transformed, description = _transform_value(original, entry["transform"])
        observed_fields.append(
            {
                "target_field": target,
                "source_pointer": entry["source_pointer"],
                "original_value": original,
                "unit": entry["source_unit"],
                "observed_at": snapshot["retrieval"]["observed_at"],
            }
        )
        route_values[target] = transformed
        if entry["transform"]["kind"] != "identity":
            transformed_fields.append(
                {
                    "target_field": target,
                    "input_value": original,
                    "output_value": transformed,
                    "input_unit": entry["source_unit"],
                    "output_unit": entry["target_unit"],
                    "conversion": description,
                }
            )

    assumptions = _assumption_map(assumptions_document)
    overlap = occupied.intersection(assumptions)
    if overlap:
        raise DraftFixtureError(
            "operator assumptions may not overwrite observed fields: "
            + ", ".join(sorted(overlap))
        )
    inferred_assumptions: list[dict[str, Any]] = []
    for field in sorted(assumptions):
        item = assumptions[field]
        inferred_assumptions.append(
            {
                "field": field,
                "value": copy.deepcopy(item["value"]),
                "unit": item["unit"],
                "basis": item["basis"],
                "operator_supplied": True,
            }
        )
        route_values[field] = copy.deepcopy(item["value"])

    available = occupied.union(assumptions)
    missing = [
        field for field in REQUIRED_ECONOMIC_ASSUMPTIONS if field not in available
    ]
    source_review = {
        "registry_id": registry["registry_id"],
        "registry_sha256": sha256_hex(registry),
        "source_id": source["source_id"],
        "source_review_evidence": copy.deepcopy(source["review_evidence"]),
        "source_reviewed_at": source["reviewed_at"],
    }
    return {
        "snapshot": {
            "artifact_id": snapshot["artifact_id"],
            "raw_sha256": snapshot["hashes"]["raw_sha256"],
            "normalized_sha256": snapshot["hashes"]["normalized_sha256"],
            "observed_at": snapshot["retrieval"]["observed_at"],
            "expires_at": snapshot["retrieval"]["expires_at"],
        },
        "source_review": source_review,
        "mapping": {
            "mapping_id": mapping["mapping_id"],
            "mapping_sha256": sha256_hex(mapping),
        },
        "network": {
            "network_name": source["network_name"],
            "chain_id": source["chain_id"],
            "network_class": "testnet",
        },
        "observed_fields": observed_fields,
        "transformed_fields": transformed_fields,
        "inferred_assumptions": inferred_assumptions,
        "missing_assumptions": missing,
        "local_route_fixture": route_values,
        "authority": dict(AUTHORITY_BOUNDARY),
    }


def build_draft(
    *,
    snapshot: Mapping[str, Any],
    raw_bytes: bytes,
    normalized_bytes: bytes,
    registry: Mapping[str, Any],
    registry_schema: Mapping[str, Any],
    snapshot_schema: Mapping[str, Any],
    mapping: Mapping[str, Any],
    mapping_schema: Mapping[str, Any],
    assumptions: Mapping[str, Any],
    draft_schema: Mapping[str, Any],
    now: datetime | None = None,
) -> DraftResult:
    _require_schema(snapshot, snapshot_schema, "snapshot")
    _require_schema(mapping, mapping_schema, "mapping")
    registry_result = validate_registry(registry, registry_schema)
    if not registry_result.valid:
        raise DraftFixtureError(
            "source registry is invalid: " + "; ".join(registry_result.errors[:8])
        )
    findings = validate_snapshot_v2(
        snapshot,
        raw_bytes,
        normalized_bytes,
        now=now,
        require_fresh=True,
    )
    if findings:
        raise DraftFixtureError(
            "snapshot validation failed: " + "; ".join(findings)
        )
    _validate_normalized_payload(snapshot, normalized_bytes)
    source = _find_source(registry, str(mapping["source_id"]))
    _validate_source_boundary(snapshot, mapping, source)
    if (
        mapping["network_name"] != source["network_name"]
        or mapping["chain_id"] != source["chain_id"]
    ):
        raise DraftFixtureError(
            "mapping network name and chain ID must match the registry"
        )

    material = _draft_material(snapshot, registry, source, mapping, assumptions)
    draft_hash = sha256_hex(material)
    draft = {
        "artifact_type": DRAFT_ARTIFACT_TYPE,
        "adapter_version": ADAPTER_VERSION,
        "schema_version": DRAFT_SCHEMA_VERSION,
        "draft_id": f"draft-{draft_hash[:24]}",
        "draft_hash": draft_hash,
        "draft_material": material,
        "freshness": {
            "state": "fresh",
            "evaluated_at": (now or datetime.now(timezone.utc))
            .astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "expires_at": snapshot["retrieval"]["expires_at"],
        },
        "operator_review": {
            "state": "DRAFT_UNREVIEWED",
            "reviewed_draft_hash": None,
            "reviewer": None,
            "reviewed_at": None,
            "note": None,
        },
        "local_simulation_eligible": False,
        "authority": dict(AUTHORITY_BOUNDARY),
    }
    _require_schema(draft, draft_schema, "draft")
    summary = summarize(draft)
    return DraftResult(
        draft=draft,
        summary=summary,
        summary_text=render_summary(summary),
    )


def verify_draft_hash(draft: Mapping[str, Any]) -> None:
    actual = sha256_hex(draft["draft_material"])
    if draft.get("draft_hash") != actual or not _SHA256_RE.fullmatch(actual):
        raise DraftFixtureError(
            "draft hash does not match the immutable draft material"
        )
    expected_id = f"draft-{actual[:24]}"
    if draft.get("draft_id") != expected_id:
        raise DraftFixtureError("draft ID does not match the draft hash")


def review_draft(
    draft: Mapping[str, Any],
    *,
    expected_draft_hash: str,
    decision: str,
    reviewer: str,
    reviewed_at: str,
    note: str,
    draft_schema: Mapping[str, Any],
) -> DraftResult:
    _require_schema(draft, draft_schema, "draft")
    verify_draft_hash(draft)
    if decision not in REVIEW_STATES - {"DRAFT_UNREVIEWED"}:
        raise DraftFixtureError(f"unsupported review decision: {decision}")
    if expected_draft_hash != draft["draft_hash"]:
        raise DraftFixtureError(
            "operator review hash does not match the exact draft hash"
        )
    try:
        parsed = parse_utc(reviewed_at)
    except (TypeError, ValueError) as exc:
        raise DraftFixtureError(
            "reviewed_at must be a timezone-aware date-time"
        ) from exc
    if not reviewer.strip() or not note.strip():
        raise DraftFixtureError("reviewer and review note are required")
    if (
        decision == "REVIEWED_FOR_LOCAL_SIMULATION"
        and draft["draft_material"]["missing_assumptions"]
    ):
        raise DraftFixtureError(
            "missing economic assumptions block local simulation review"
        )

    reviewed = copy.deepcopy(dict(draft))
    reviewed["operator_review"] = {
        "state": decision,
        "reviewed_draft_hash": expected_draft_hash,
        "reviewer": reviewer.strip(),
        "reviewed_at": parsed.isoformat().replace("+00:00", "Z"),
        "note": note.strip(),
    }
    reviewed["local_simulation_eligible"] = (
        decision == "REVIEWED_FOR_LOCAL_SIMULATION"
    )
    reviewed["authority"] = dict(AUTHORITY_BOUNDARY)
    _require_schema(reviewed, draft_schema, "reviewed draft")
    verify_draft_hash(reviewed)
    summary = summarize(reviewed)
    return DraftResult(
        draft=reviewed,
        summary=summary,
        summary_text=render_summary(summary),
    )


def summarize(draft: Mapping[str, Any]) -> dict[str, Any]:
    material = draft["draft_material"]
    review = draft["operator_review"]
    return {
        "draft_id": draft["draft_id"],
        "draft_hash": draft["draft_hash"],
        "source_id": material["source_review"]["source_id"],
        "network_name": material["network"]["network_name"],
        "chain_id": material["network"]["chain_id"],
        "observed_field_count": len(material["observed_fields"]),
        "transformed_field_count": len(material["transformed_fields"]),
        "assumption_count": len(material["inferred_assumptions"]),
        "missing_assumptions": list(material["missing_assumptions"]),
        "freshness_state": draft["freshness"]["state"],
        "review_state": review["state"],
        "local_simulation_eligible": draft["local_simulation_eligible"],
        "authority": False,
        "execution": "LOCKED",
    }


def render_summary(summary: Mapping[str, Any]) -> str:
    missing = ", ".join(summary["missing_assumptions"]) or "none"
    return "\n".join(
        (
            "CODEX TELEMETRY DRAFT FIXTURE v0.1",
            f"DRAFT: {summary['draft_id']}",
            f"HASH: {summary['draft_hash']}",
            f"SOURCE: {summary['source_id']}",
            f"NETWORK: {summary['network_name']} ({summary['chain_id']})",
            f"OBSERVED FIELDS: {summary['observed_field_count']}",
            f"TRANSFORMED FIELDS: {summary['transformed_field_count']}",
            f"OPERATOR ASSUMPTIONS: {summary['assumption_count']}",
            f"MISSING ASSUMPTIONS: {missing}",
            f"FRESHNESS: {summary['freshness_state']}",
            f"REVIEW: {summary['review_state']}",
            "LOCAL SIMULATION ELIGIBLE: "
            + str(summary["local_simulation_eligible"]).lower(),
            "AUTHORITY: false",
            "EXECUTION: LOCKED",
        )
    )


def _write_result(
    output_dir: Path,
    result: DraftResult,
    *,
    filename: str = "draft.json",
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / filename).write_text(
        json.dumps(result.draft, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "draft-summary.json").write_text(
        json.dumps(result.summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "draft-summary.txt").write_text(
        result.summary_text + "\n",
        encoding="utf-8",
    )


def _build_from_args(args: argparse.Namespace) -> DraftResult:
    bundle = args.bundle.expanduser().resolve()
    snapshot = _load_json(bundle / "snapshot.json")
    raw_bytes = (bundle / "raw.bin").read_bytes()
    normalized_bytes = (bundle / "normalized.json").read_bytes().rstrip(b"\n")
    now = parse_utc(args.now) if args.now else None
    return build_draft(
        snapshot=snapshot,
        raw_bytes=raw_bytes,
        normalized_bytes=normalized_bytes,
        registry=_load_json(args.registry),
        registry_schema=_load_json(args.registry_schema),
        snapshot_schema=_load_json(args.snapshot_schema),
        mapping=_load_json(args.mapping),
        mapping_schema=_load_json(args.mapping_schema),
        assumptions=_load_json(args.assumptions),
        draft_schema=_load_json(args.draft_schema),
        now=now,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or review one Gate 1A telemetry draft"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build", help="build a deterministic unreviewed draft"
    )
    build.add_argument("--bundle", type=Path, required=True)
    build.add_argument("--mapping", type=Path, required=True)
    build.add_argument("--assumptions", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--registry", type=Path, default=_DEFAULT_REGISTRY)
    build.add_argument(
        "--registry-schema", type=Path, default=_DEFAULT_REGISTRY_SCHEMA
    )
    build.add_argument(
        "--snapshot-schema", type=Path, default=_DEFAULT_SNAPSHOT_SCHEMA
    )
    build.add_argument(
        "--mapping-schema", type=Path, default=_DEFAULT_MAPPING_SCHEMA
    )
    build.add_argument("--draft-schema", type=Path, default=_DEFAULT_DRAFT_SCHEMA)
    build.add_argument("--now")

    review = subparsers.add_parser(
        "review", help="record exact-hash operator review"
    )
    review.add_argument("--draft", type=Path, required=True)
    review.add_argument("--expected-draft-hash", required=True)
    review.add_argument(
        "--decision",
        required=True,
        choices=sorted(REVIEW_STATES - {"DRAFT_UNREVIEWED"}),
    )
    review.add_argument("--reviewer", required=True)
    review.add_argument("--reviewed-at", required=True)
    review.add_argument("--note", required=True)
    review.add_argument("--output-dir", type=Path, required=True)
    review.add_argument("--draft-schema", type=Path, default=_DEFAULT_DRAFT_SCHEMA)

    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = _build_from_args(args)
            _write_result(args.output_dir, result)
        else:
            result = review_draft(
                _load_json(args.draft),
                expected_draft_hash=args.expected_draft_hash,
                decision=args.decision,
                reviewer=args.reviewer,
                reviewed_at=args.reviewed_at,
                note=args.note,
                draft_schema=_load_json(args.draft_schema),
            )
            _write_result(
                args.output_dir,
                result,
                filename="reviewed-draft.json",
            )
    except (DraftFixtureError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"HOLD: {exc}")
        return 2
    print(result.summary_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
