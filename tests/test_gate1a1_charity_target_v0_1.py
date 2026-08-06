from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from eve_q.gate1a1_charity_target import (
    CharityTargetError,
    build_receipt,
    validate_contract,
)

CONTRACT = Path(__file__).parents[1] / "contracts" / "gate1a1_charity_target_contract_v0_1.json"


def load_contract() -> dict[str, object]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_baseline_contract_is_complete_and_transfer_free() -> None:
    contract = load_contract()
    validate_contract(contract)

    receipt = build_receipt(contract)

    assert receipt["status"] == "SIMULATION_ONLY_CONTRACT_COMPLETE"
    assert receipt["hold_reasons"] == []
    assert receipt["transfer_evidence_status"] == "ABSENT"
    assert receipt["outcome_evidence_status"] == "NO_DATA"
    assert receipt["modeled_contribution_status"] == "MODEL_ONLY"
    assert receipt["no_data_means_zero"] is False
    assert receipt["transfer_enabled"] is False
    assert receipt["reward_update_enabled"] is False
    assert receipt["authority"] is False
    assert receipt["gate1b_activated"] is False
    assert receipt["may_access_wallet"] is False
    assert receipt["may_move_capital"] is False


def test_no_data_cannot_be_rewritten_as_zero_impact() -> None:
    contract = load_contract()
    contract["no_data_semantics"]["meaning"] = "ZERO_IMPACT"

    receipt = build_receipt(contract)

    assert receipt["status"] == "HOLD_CHARITY_TARGET_CONTRACT"
    assert receipt["no_data_means_zero"] is False


def test_unsupported_causal_claim_holds() -> None:
    contract = load_contract()
    contract["unsupported_causal_claim"] = {
        "present": True,
        "claim": "This modeled contribution caused the observed outcome.",
    }

    receipt = build_receipt(contract)

    assert receipt["status"] == "HOLD_CHARITY_TARGET_CONTRACT"
    assert any("causal" in reason for reason in receipt["hold_reasons"])


def test_transfer_or_wallet_activation_holds() -> None:
    contract = load_contract()
    contract["transfer_posture"]["enabled"] = True
    contract["transfer_posture"]["wallet_access"] = True

    receipt = build_receipt(contract)

    assert receipt["status"] == "HOLD_CHARITY_TARGET_CONTRACT"
    assert receipt["transfer_enabled"] is False
    assert receipt["may_access_wallet"] is False


def test_automatic_reward_rewrite_holds() -> None:
    contract = load_contract()
    contract["reward_posture"]["automatic_update"] = True
    contract["reward_posture"]["may_rewrite_reward_function"] = True

    receipt = build_receipt(contract)

    assert receipt["status"] == "HOLD_CHARITY_TARGET_CONTRACT"
    assert receipt["reward_update_enabled"] is False


def test_pipeline_order_is_load_bearing() -> None:
    contract = load_contract()
    contract["pipeline"] = list(reversed(contract["pipeline"]))

    with pytest.raises(CharityTargetError, match="pipeline"):
        validate_contract(contract)


def test_contract_id_rejects_resealed_semantic_drift() -> None:
    contract = load_contract()
    contract["modeled_contribution"]["estimate"] = 0.5

    receipt = build_receipt(contract)

    assert receipt["status"] == "HOLD_CHARITY_TARGET_CONTRACT"
    assert any("contract_id" in reason for reason in receipt["hold_reasons"])


def test_malformed_evidence_returns_hold_not_exception() -> None:
    contract = load_contract()
    contract["observed_outcome_evidence"] = ["invented"]

    receipt = build_receipt(copy.deepcopy(contract))

    assert receipt["status"] == "HOLD_CHARITY_TARGET_CONTRACT"
    assert receipt["authority"] is False
    assert receipt["transfer_enabled"] is False
