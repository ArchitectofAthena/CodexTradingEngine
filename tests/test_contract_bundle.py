from __future__ import annotations

import json
from pathlib import Path

import pytest

from eve_q.contract_bundle import (
    CONTRACT_VERSION,
    SCHEMA_FILENAMES,
    ContractBundleError,
    build_contract_bundle_receipt,
    pin_contract_bundle,
)


PRODUCER_COMMIT = "a" * 40
CONTROL_PLANE_COMMIT = "b" * 40


def seed_schemas(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for index, filename in enumerate(SCHEMA_FILENAMES):
        document = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://example.invalid/{filename}",
            "title": f"contract schema {index}",
            "type": "object",
        }
        (root / filename).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def test_build_contract_bundle_is_non_authoritative_and_complete(tmp_path: Path):
    schema_root = tmp_path / "schemas"
    seed_schemas(schema_root)

    receipt = build_contract_bundle_receipt(
        schema_root=schema_root,
        producer_commit=PRODUCER_COMMIT,
        control_plane_commit=CONTROL_PLANE_COMMIT,
    )

    assert receipt["contract_version"] == CONTRACT_VERSION
    assert receipt["schema_count"] == 6
    assert len(receipt["schemas"]) == 6
    assert receipt["authority"] is False
    assert receipt["artifact_is_command"] is False
    assert receipt["may_execute"] is False
    assert receipt["may_move_capital"] is False
    assert receipt["human_promotion_required"] is True

    for schema in receipt["schemas"]:
        assert len(schema["file_sha256"]) == 64
        assert len(schema["canonical_json_sha256"]) == 64
        assert schema["path"].startswith("schemas/")


def test_mock_pin_is_verified_and_appends_ledger(tmp_path: Path):
    schema_root = tmp_path / "schemas"
    ledger_path = tmp_path / "artifacts" / "contracts" / "ipfs_ledger.jsonl"
    seed_schemas(schema_root)

    result = pin_contract_bundle(
        schema_root=schema_root,
        ledger_path=ledger_path,
        producer_commit=PRODUCER_COMMIT,
        control_plane_commit=CONTROL_PLANE_COMMIT,
        backend="mock",
    )

    assert result["ok"] is True
    assert result["result"]["status"] == "IPFS_PINNED_VERIFIED"
    assert result["result"]["cid"].startswith("mock-ipfs-")
    assert ledger_path.exists()

    event = json.loads(ledger_path.read_text(encoding="utf-8").splitlines()[-1])
    assert event["event_type"] == "receipt_pinned"
    assert event["receipt_type"] == "eve_q.cross_repo_contract_bundle.v0.1"
    assert event["may_execute"] is False
    assert event["may_move_capital"] is False


def test_missing_schema_fails_closed(tmp_path: Path):
    schema_root = tmp_path / "schemas"
    schema_root.mkdir()

    with pytest.raises(ContractBundleError, match="missing contract schema"):
        build_contract_bundle_receipt(
            schema_root=schema_root,
            producer_commit=PRODUCER_COMMIT,
            control_plane_commit=CONTROL_PLANE_COMMIT,
        )
