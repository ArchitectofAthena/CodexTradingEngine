from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from eve_q.proposal_artifact import (
    build_proposal_artifact,
    validate_proposal_semantics,
)
from shadow_cycle_runner import build_shadow_receipt, run_shadow_cycle


SCHEMA_ROOT = Path("schemas")
EXAMPLE_ROOT = Path("examples/contracts")
COMMIT = "a" * 40
FIXED_NOW = datetime(2026, 7, 11, 19, 0, 1, tzinfo=timezone.utc)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def apply_mutations(document: dict, mutations: list[dict]) -> dict:
    result = copy.deepcopy(document)
    for mutation in mutations:
        parts = [part for part in mutation["path"].split("/") if part]
        target = result
        for part in parts[:-1]:
            target = target[part]
        leaf = parts[-1]
        if mutation["op"] == "replace":
            target[leaf] = mutation["value"]
        elif mutation["op"] == "remove":
            target.pop(leaf)
        else:
            raise AssertionError(f"unsupported fixture mutation: {mutation['op']}")
    return result


def test_builder_emits_schema_valid_non_authoritative_proposal():
    receipt = build_shadow_receipt(cycle_id="proposal-builder-test")
    receipt.created_at = "2026-07-11T19:00:00Z"
    artifact = build_proposal_artifact(receipt, producer_commit=COMMIT)

    schema = load_json(SCHEMA_ROOT / "proposal_artifact_v0_1.schema.json")
    validator = Draft202012Validator(schema)

    assert list(validator.iter_errors(artifact)) == []
    assert validate_proposal_semantics(artifact, now=FIXED_NOW) == []
    assert artifact["scope"]["environment"] == "shadow"
    assert artifact["risk_envelope"]["max_notional_usd"] == 0.0
    assert artifact["authority"] is False
    assert artifact["human_promotion_required"] is True
    assert artifact["autonomous_capital_movement"] is False
    assert "capital_movement" in artifact["prohibited_actions"]
    assert "self_promotion" in artifact["prohibited_actions"]


def test_canonical_fixture_is_schema_and_semantically_valid():
    fixture = load_json(EXAMPLE_ROOT / "proposal_artifact_valid_v0_1.json")
    schema = load_json(SCHEMA_ROOT / "proposal_artifact_v0_1.schema.json")

    assert list(Draft202012Validator(schema).iter_errors(fixture)) == []
    assert validate_proposal_semantics(fixture, now=FIXED_NOW) == []


def test_invalid_proposal_fixture_mutations_fail_closed():
    fixture_set = load_json(
        EXAMPLE_ROOT / "proposal_artifact_invalid_cases_v0_1.json"
    )
    base = load_json(Path(fixture_set["base_fixture"]))

    for case in fixture_set["cases"]:
        mutated = apply_mutations(base, case["mutations"])
        findings = validate_proposal_semantics(mutated, now=FIXED_NOW)
        assert case["expected_finding"] in findings, case["name"]


def test_inferred_execution_fixture_is_rejected_by_schema():
    fixture = load_json(
        EXAMPLE_ROOT / "execution_receipt_invalid_inferred_v0_1.json"
    )
    schema = load_json(SCHEMA_ROOT / "execution_receipt_v0_1.schema.json")
    errors = list(Draft202012Validator(schema).iter_errors(fixture))

    assert errors
    messages = "\n".join(error.message for error in errors)
    assert "True was expected" in messages or "False was expected" in messages


def test_shadow_cycle_emits_receipt_and_proposal_artifact(tmp_path: Path):
    run = run_shadow_cycle(
        output_dir=tmp_path,
        cycle_id="shadow-proposal-adapter-test",
        producer_commit=COMMIT,
        impact_category="medical_access",
    )

    assert run.receipt_path.exists()
    assert run.proposal_path.exists()
    assert run.validation.valid is True
    assert run.validation.trust_increment_allowed is False

    proposal = load_json(run.proposal_path)
    schema = load_json(SCHEMA_ROOT / "proposal_artifact_v0_1.schema.json")

    assert list(Draft202012Validator(schema).iter_errors(proposal)) == []
    assert proposal == run.proposal_artifact
    assert proposal["proposal_id"] == "proposal:shadow-proposal-adapter-test"
    assert proposal["producer"]["commit_sha"] == COMMIT
    assert proposal["charity_allocation_candidate"]["fraction"] == 0.15
    assert proposal["charity_allocation_candidate"]["impact_category"] == "medical_access"
    assert proposal["authority"] is False
    assert proposal["autonomous_capital_movement"] is False
