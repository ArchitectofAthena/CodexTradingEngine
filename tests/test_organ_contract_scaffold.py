import json
from pathlib import Path

CONTRACT_PATH = Path("contracts/organ_contract.json")
DOC_PATH = Path("contracts/ORGAN_CONTRACT.md")


def load_contract():
    return json.loads(CONTRACT_PATH.read_text())


def test_organ_contract_files_exist():
    assert CONTRACT_PATH.exists()
    assert DOC_PATH.exists()


def test_organ_contract_declares_codex_identity():
    contract = load_contract()

    assert contract["organ_id"] == "codex_trading_engine"
    assert contract["organ_type"] == "market_facing_metabolic_organ"
    assert contract["version"] == "0.1.0"
    assert contract["default_mode"] == "simulation"


def test_organ_contract_requires_proposal_only_human_promotion():
    posture = load_contract()["constitutional_posture"]

    assert posture["proposal_only"] is True
    assert posture["human_promotion_required"] is True
    assert posture["ttl_required_for_autonomy"] is True
    assert posture["no_reverse_execution_channel"] is True


def test_organ_contract_allows_only_artifact_style_outputs():
    contract = load_contract()

    expected_outputs = {
        "artifact_receipt",
        "safety_bridge_receipt",
        "risk_report",
        "charity_allocation_proposal",
        "simulation_summary",
        "drift_audit",
        "testnet_result",
    }

    assert set(contract["allowed_outputs"]) == expected_outputs


def test_organ_contract_declares_forbidden_capabilities():
    contract = load_contract()

    forbidden = set(contract["forbidden_capabilities"])

    assert "wallet_signing" in forbidden
    assert "autonomous_capital_movement" in forbidden
    assert "governance_mutation" in forbidden
    assert "webhook_triggered_execution" in forbidden
    assert "scheduler_triggered_execution" in forbidden
    assert "silent_remote_command_execution" in forbidden
    assert "self_promotion" in forbidden
    assert "receipt_mutation_after_emission" in forbidden


def test_organ_contract_declares_valid_promotion_path():
    contract = load_contract()

    assert contract["promotion_path"] == [
        "simulate",
        "validate",
        "emit_receipt",
        "ingest_receipt",
        "verify",
        "human_review",
        "human_promotion",
    ]


def test_organ_contract_preserves_hard_invariants():
    invariants = set(load_contract()["hard_invariants"])

    assert "Codex proposes." in invariants
    assert "Artifacts record." in invariants
    assert "Verifiers gate." in invariants
    assert "Registry remembers." in invariants
    assert "Human promotes." in invariants
    assert "No single charity may become the whole definition of good." in invariants
    assert "Graceful degradation over chaotic stop." in invariants


def test_human_readable_contract_contains_bridge_rule():
    doc = DOC_PATH.read_text()

    assert "SpiralBloom may review Codex artifacts." in doc
    assert "SpiralBloom may not silently command Codex execution." in doc
    assert "Codex may not mutate SpiralBloom governance state." in doc
