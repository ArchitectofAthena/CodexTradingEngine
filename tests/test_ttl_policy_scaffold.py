import json
from pathlib import Path

TTL_POLICY_PATH = Path("contracts/ttl_policy.json")
TTL_DOC_PATH = Path("docs/ttl_graceful_degradation_policy.md")
ORGAN_CONTRACT_PATH = Path("contracts/organ_contract.json")


def load_ttl_policy():
    return json.loads(TTL_POLICY_PATH.read_text())


def load_organ_contract():
    return json.loads(ORGAN_CONTRACT_PATH.read_text())


def test_ttl_policy_files_exist():
    assert TTL_POLICY_PATH.exists()
    assert TTL_DOC_PATH.exists()


def test_ttl_policy_declares_expiring_authority_posture():
    posture = load_ttl_policy()["posture"]

    assert posture["authority_expires"] is True
    assert posture["uncertainty_degrades_permission"] is True
    assert posture["graceful_degradation_preferred"] is True
    assert posture["hard_stop_on_forbidden_capability"] is True
    assert posture["human_approval_required_for_renewal"] is True


def test_ttl_policy_covers_all_organ_contract_modes():
    ttl_modes = set(load_ttl_policy()["modes"])
    organ_modes = set(load_organ_contract()["allowed_modes"])

    assert ttl_modes == organ_modes


def test_higher_authority_modes_require_ttl():
    modes = load_ttl_policy()["modes"]

    assert modes["artifact_only"]["ttl_required"] is False
    assert modes["simulation"]["ttl_required"] is False
    assert modes["historical_replay"]["ttl_required"] is False
    assert modes["testnet"]["ttl_required"] is True
    assert modes["shadow_live_market_data"]["ttl_required"] is True
    assert modes["human_gated_execution"]["ttl_required"] is True
    assert modes["ttl_bounded_autonomy"]["ttl_required"] is True


def test_degradation_never_increases_authority():
    policy = load_ttl_policy()
    ranks = policy["authority_rank"]

    for mode, mode_policy in policy["modes"].items():
        target = mode_policy["degradation_target"]
        assert target in ranks
        assert ranks[target] <= ranks[mode]


def test_hard_stop_triggers_cover_forbidden_capabilities():
    policy = load_ttl_policy()
    organ_contract = load_organ_contract()

    assert set(organ_contract["forbidden_capabilities"]).issubset(set(policy["hard_stop_triggers"]))


def test_human_approval_is_required_for_renewal_and_promotion():
    required = set(load_ttl_policy()["human_approval_required_for"])

    assert "ttl_renewal_after_expiry" in required
    assert "simulation_to_testnet_promotion" in required
    assert "testnet_to_human_gated_execution_promotion" in required
    assert "human_gated_execution_to_ttl_bounded_autonomy_promotion" in required
    assert "hard_stop_recovery" in required


def test_policy_doc_preserves_core_law():
    doc = TTL_DOC_PATH.read_text()

    assert "Authority expires." in doc
    assert "Uncertainty degrades permission." in doc
    assert "Graceful degradation is preferred" in doc
    assert "Agent proposes. Artifact records." in doc


EXPECTED_HARD_STOP_TRIGGERS = {
    "wallet_signing",
    "autonomous_capital_movement",
    "governance_mutation",
    "webhook_triggered_execution",
    "scheduler_triggered_execution",
    "silent_remote_command_execution",
    "self_promotion",
    "receipt_mutation_after_emission",
}


def normalize_hard_stop_bullet(text):
    return text.strip().lower().replace("-", "_").replace(" ", "_")


def hard_stop_bullets_from_doc():
    doc = TTL_DOC_PATH.read_text()
    section = doc.split("## Hard Stop Triggers", 1)[1]
    section = section.split("## Human Approval Required", 1)[0]

    bullets = []
    for line in section.splitlines():
        if line.startswith("- "):
            bullets.append(normalize_hard_stop_bullet(line[2:]))

    return set(bullets)


def test_hard_stop_triggers_match_single_declared_canon():
    policy = load_ttl_policy()
    organ_contract = load_organ_contract()

    assert set(policy["hard_stop_triggers"]) == EXPECTED_HARD_STOP_TRIGGERS
    assert set(organ_contract["forbidden_capabilities"]) == EXPECTED_HARD_STOP_TRIGGERS
    assert hard_stop_bullets_from_doc() == EXPECTED_HARD_STOP_TRIGGERS


def test_policy_doc_declares_structural_verification_boundary():
    doc = TTL_DOC_PATH.read_text()

    assert "Version: 0.1.0" in doc
    assert "v0.1.0 is a structural policy scaffold." in doc
    assert "It does not yet implement or prove runtime TTL behavior." in doc
    assert "Membrane before motion." in doc
