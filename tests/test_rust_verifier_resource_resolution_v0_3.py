from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import eve_q
import eve_q.rust_verifier_provenance as provenance
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SCHEMA = ROOT / "schemas" / "delta_repricing_response.schema.json"
EXPECTED_PATTERN = r"^triangle:[0-9a-f]{20}$"


def _candidate_pattern(schema: dict[str, object]) -> object:
    properties = schema["properties"]
    assert isinstance(properties, dict)
    candidate = properties["candidate_id"]
    assert isinstance(candidate, dict)
    return candidate["pattern"]


def test_runtime_canonical_schema_resolves_to_current_eve_q_resource() -> None:
    resource = files("eve_q").joinpath("delta_repricing_response.schema.json")
    packaged_schema = json.loads(resource.read_text(encoding="utf-8"))
    source_schema = json.loads(SOURCE_SCHEMA.read_text(encoding="utf-8"))
    helper_schema = dict(provenance._canonical_response_schema())

    debug = {
        "eve_q_file": eve_q.__file__,
        "provenance_file": provenance.__file__,
        "resource": str(resource),
        "packaged_pattern": _candidate_pattern(packaged_schema),
        "source_pattern": _candidate_pattern(source_schema),
        "helper_pattern": _candidate_pattern(helper_schema),
        "packaged_sha": provenance.canonical_response_schema_sha256(),
    }

    assert packaged_schema == source_schema, debug
    assert _candidate_pattern(packaged_schema) == EXPECTED_PATTERN, debug
    assert _candidate_pattern(helper_schema) == EXPECTED_PATTERN, debug


def test_runtime_schema_accepts_current_twenty_hex_candidate_contract() -> None:
    schema = dict(provenance._canonical_response_schema())
    response = {
        "schema_version": "delta-repricing-response-v0.1",
        "request_id": "delta-reprice:" + "0" * 24,
        "snapshot_sha256": "1" * 64,
        "model_sha256": "2" * 64,
        "confidence_receipt_id": "qaoa-confidence:" + "3" * 24,
        "candidate_id": "triangle:" + "4" * 20,
        "verifier": "codex-delta-verifier/test",
        "status": "verified",
        "verification": {
            "edge_ids": ["a", "b", "c"],
            "asset_path": ["USD", "ETH", "BTC", "USD"],
            "net_multiplier": 1.0,
            "net_log_delta": 0.0,
            "minimum_log_delta": 0.0,
            "profitable": False,
            "passes_margin": True,
            "authority": False,
        },
        "authority": False,
    }

    errors = list(Draft202012Validator(schema).iter_errors(response))
    assert not errors, [error.message for error in errors]
