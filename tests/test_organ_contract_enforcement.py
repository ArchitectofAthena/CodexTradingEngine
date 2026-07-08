from copy import deepcopy

from eve_q.organ_contract import (
    load_organ_contract,
    validate_contract_shape,
    validate_receipt_against_contract,
)
from eve_q.receipt_emitter import build_receipt, validate_emitted_receipt

VALID_SHA = "a" * 64


def minimal_receipt(**overrides):
    receipt = {
        "source_repo": "ArchitectofAthena/CodexTradingEngine",
        "source_commit": "abc123",
        "artifact_type": "safety_bridge_receipt",
        "artifact_path": "artifacts/example.json",
        "artifact_sha256": VALID_SHA,
        "mode": "artifact_only",
        "summary": "Artifact-only receipt.",
        "boundary": ["human promotion required"],
        "human_promotion_required": True,
    }
    receipt.update(overrides)
    return receipt


def test_organ_contract_shape_is_valid():
    contract = load_organ_contract()

    assert validate_contract_shape(contract) == []


def test_default_receipt_shape_is_allowed_by_organ_contract(tmp_path):
    artifact = tmp_path / "artifact.json"
    artifact.write_text('{"ok": true}\n')

    receipt = build_receipt(
        artifact_path=artifact,
        source_repo="ArchitectofAthena/CodexTradingEngine",
        source_commit="abc123",
        root=tmp_path,
    )

    assert validate_receipt_against_contract(receipt) == []
    assert validate_emitted_receipt(receipt) == []


def test_undeclared_artifact_type_is_rejected():
    receipt = minimal_receipt(artifact_type="undeclared_output")

    errors = validate_receipt_against_contract(receipt)

    assert any("artifact_type is not allowed" in error for error in errors)


def test_mode_outside_contract_is_rejected():
    receipt = minimal_receipt(mode="rogue_mode")

    errors = validate_receipt_against_contract(receipt)

    assert any("mode is not allowed" in error for error in errors)


def test_human_promotion_required_by_contract():
    receipt = minimal_receipt(human_promotion_required=False)

    errors = validate_receipt_against_contract(receipt)

    assert any("human_promotion_required must be true" in error for error in errors)


def test_action_execution_fields_are_rejected():
    receipt = minimal_receipt(webhook="https://example.invalid/hook")

    errors = validate_receipt_against_contract(receipt)

    assert any("action/execution fields" in error for error in errors)


def test_forbidden_capability_direct_field_is_rejected():
    receipt = minimal_receipt(wallet_signing=True)

    errors = validate_receipt_against_contract(receipt)

    assert any("forbidden capabilities as fields" in error for error in errors)


def test_forbidden_capability_claim_is_rejected():
    receipt = minimal_receipt(claimed_capabilities=["wallet_signing"])

    errors = validate_receipt_against_contract(receipt)

    assert any("forbidden capabilities" in error for error in errors)


def test_contract_can_detect_contract_shape_drift():
    contract = deepcopy(load_organ_contract())
    contract["constitutional_posture"]["human_promotion_required"] = False

    errors = validate_receipt_against_contract(
        minimal_receipt(),
        contract=contract,
    )

    assert any(
        "constitutional_posture.human_promotion_required must be true" in error for error in errors
    )
