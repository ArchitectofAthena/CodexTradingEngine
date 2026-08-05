from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import eve_q.organ_contract as organ_contract
from eve_q.organ_contract import load_organ_contract, validate_receipt_against_contract


REPOSITORY_CONTRACT = Path("contracts/organ_contract.json")


def test_default_contract_is_packaged_inside_eve_q() -> None:
    resource = files("eve_q").joinpath("organ_contract.json")

    assert resource.is_file()
    assert organ_contract.DEFAULT_CONTRACT_PATH.read_text(encoding="utf-8") == resource.read_text(
        encoding="utf-8"
    )
    assert load_organ_contract()["organ_id"] == "codex_trading_engine"


def test_default_load_does_not_depend_on_repository_contract_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        organ_contract,
        "SOURCE_CONTRACT_PATH",
        tmp_path / "missing" / "contracts" / "organ_contract.json",
    )

    contract = load_organ_contract()

    assert contract["version"] == "0.1.0"
    assert contract["constitutional_posture"]["human_promotion_required"] is True


def test_packaged_contract_matches_repository_mirror() -> None:
    packaged = load_organ_contract()
    repository = json.loads(REPOSITORY_CONTRACT.read_text(encoding="utf-8"))

    assert packaged == repository


def test_explicit_path_override_remains_supported(tmp_path: Path) -> None:
    override = load_organ_contract()
    override["allowed_outputs"] = ["artifact_receipt"]
    path = tmp_path / "bounded-contract.json"
    path.write_text(json.dumps(override), encoding="utf-8")

    receipt = {
        "artifact_type": "simulation_summary",
        "mode": "simulation",
        "human_promotion_required": True,
    }
    errors = validate_receipt_against_contract(receipt, contract_path=path)

    assert errors == [
        "artifact_type is not allowed by organ contract: 'simulation_summary'"
    ]
