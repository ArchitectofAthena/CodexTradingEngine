import json
from decimal import Decimal
from pathlib import Path

import pytest

from eve_q.cross_repo_ingestor import (
    CrossRepoReceiptIngestor,
    ReceiptIngestionConfig,
)


def make_receipt(**overrides):
    receipt = {
        "cycle_id": "cycle-test-001",
        "mode": "shadow",
        "chain": "base",
        "optimizer_used": "simulated_optimizer",
        "proof_type": "local_file",
        "actual_profit_eth": "0.0500",
        "charity_due_eth": "0.0075",
        "execution_success": True,
        "charity_success": True,
        "ipfs_success": False,
    }
    receipt.update(overrides)
    return receipt


class GuardedIngestor(CrossRepoReceiptIngestor):
    def __init__(self, config):
        super().__init__(config)
        self.governance_calls = 0

    def _query_governance_gate(self, receipt_dict):
        self.governance_calls += 1
        raise AssertionError("shadow ingestion must not query governance")


def write_receipt(path: Path, **overrides) -> Path:
    path.write_text(json.dumps(make_receipt(**overrides), indent=2), encoding="utf-8")
    return path


def valid_merkle_envelope() -> dict:
    return {
        "merkle_root": "root-abc",
        "merkle_proof": {
            "leaf_hash": "leaf-abc",
            "path": ["sibling-one", "sibling-two"],
            "indices": [0, 1],
            "root_hash": "root-abc",
        },
    }


def test_shadow_ingestion_does_not_query_governance(tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    receipt_path = write_receipt(source_dir / "receipt.json")

    config = ReceiptIngestionConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        governance_gate_url="http://127.0.0.1:9999/policy",
        shadow_mode=True,
    )
    ingestor = GuardedIngestor(config)

    result = ingestor.ingest_receipt_file(receipt_path)

    assert result.success is True
    assert result.governance_gate_queried is False
    assert result.governance_gate_approved is None
    assert ingestor.governance_calls == 0
    assert result.target_path is not None
    assert Path(result.target_path).exists()


def test_missing_governance_url_remains_file_only(tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    receipt_path = write_receipt(source_dir / "receipt.json")

    config = ReceiptIngestionConfig(
        source_dir=source_dir,
        target_dir=target_dir,
        governance_gate_url=None,
        shadow_mode=False,
    )
    ingestor = CrossRepoReceiptIngestor(config)

    result = ingestor.ingest_receipt_file(receipt_path)

    assert result.success is True
    assert result.governance_gate_queried is False
    assert result.target_path is not None
    stored = json.loads(Path(result.target_path).read_text(encoding="utf-8"))
    assert stored["cycle_id"] == "cycle-test-001"
    assert stored["spiralbloom_source_path"] == str(receipt_path)


def test_invalid_receipt_is_rejected_and_not_written(tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    receipt_path = source_dir / "bad.json"
    receipt_path.write_text(json.dumps({"cycle_id": "bad"}), encoding="utf-8")

    config = ReceiptIngestionConfig(source_dir=source_dir, target_dir=target_dir)
    ingestor = CrossRepoReceiptIngestor(config)

    result = ingestor.ingest_receipt_file(receipt_path)

    assert result.success is False
    assert result.target_path is None
    assert result.validation_errors
    assert not list(target_dir.glob("*_ingested.json"))


def test_charity_mismatch_is_rejected(tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    receipt_path = write_receipt(
        source_dir / "receipt.json",
        actual_profit_eth=str(Decimal("1.0")),
        charity_due_eth=str(Decimal("0.01")),
    )

    config = ReceiptIngestionConfig(source_dir=source_dir, target_dir=target_dir)
    ingestor = CrossRepoReceiptIngestor(config)

    result = ingestor.ingest_receipt_file(receipt_path)

    assert result.success is False
    assert any("Charity mismatch" in error for error in result.validation_errors)
    assert result.target_path is None


def test_valid_merkle_proof_is_checked_and_ingested(tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    receipt_path = write_receipt(source_dir / "receipt.json", **valid_merkle_envelope())

    result = CrossRepoReceiptIngestor(
        ReceiptIngestionConfig(source_dir=source_dir, target_dir=target_dir)
    ).ingest_receipt_file(receipt_path)

    assert result.success is True
    assert result.validation_errors == []


def test_merkle_root_mismatch_fails_closed(tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    envelope = valid_merkle_envelope()
    envelope["merkle_proof"]["root_hash"] = "different-root"
    receipt_path = write_receipt(source_dir / "receipt.json", **envelope)

    result = CrossRepoReceiptIngestor(
        ReceiptIngestionConfig(source_dir=source_dir, target_dir=target_dir)
    ).ingest_receipt_file(receipt_path)

    assert result.success is False
    assert any("Merkle root mismatch" in error for error in result.validation_errors)
    assert result.target_path is None


def test_misspelled_merkle_proof_field_is_rejected(tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    receipt_path = write_receipt(
        source_dir / "receipt.json",
        merkle_root="root-abc",
        merkle_proo=valid_merkle_envelope()["merkle_proof"],
    )

    result = CrossRepoReceiptIngestor(
        ReceiptIngestionConfig(source_dir=source_dir, target_dir=target_dir)
    ).ingest_receipt_file(receipt_path)

    assert result.success is False
    assert any("merkle_proo" in error for error in result.validation_errors)
    assert any("without merkle_proof" in error for error in result.validation_errors)


def test_merkle_skip_verification_sentinel_is_rejected(tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    envelope = valid_merkle_envelope()
    envelope["merkle_root"] = "skip_verification"
    envelope["merkle_proof"]["root_hash"] = "skip_verification"
    receipt_path = write_receipt(source_dir / "receipt.json", **envelope)

    result = CrossRepoReceiptIngestor(
        ReceiptIngestionConfig(source_dir=source_dir, target_dir=target_dir)
    ).ingest_receipt_file(receipt_path)

    assert result.success is False
    assert any("bypass sentinel" in error for error in result.validation_errors)


@pytest.mark.parametrize("cycle_id", ["../escape", "/absolute", "has space", ""])
def test_unsafe_cycle_ids_are_rejected(tmp_path, cycle_id):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    receipt_path = write_receipt(source_dir / "receipt.json", cycle_id=cycle_id)

    result = CrossRepoReceiptIngestor(
        ReceiptIngestionConfig(source_dir=source_dir, target_dir=target_dir)
    ).ingest_receipt_file(receipt_path)

    assert result.success is False
    assert any("cycle_id must match" in error for error in result.validation_errors)
    assert not list(target_dir.glob("*_ingested.json"))


def test_governance_gate_must_be_loopback(tmp_path):
    with pytest.raises(ValueError, match="loopback"):
        ReceiptIngestionConfig(
            source_dir=tmp_path / "source",
            target_dir=tmp_path / "target",
            governance_gate_url="https://example.com/policy",
        )


def test_symlink_receipt_is_rejected(tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    actual = write_receipt(source_dir / "actual.json")
    link = source_dir / "linked.json"
    link.symlink_to(actual)

    result = CrossRepoReceiptIngestor(
        ReceiptIngestionConfig(source_dir=source_dir, target_dir=target_dir)
    ).ingest_receipt_file(link)

    assert result.success is False
    assert any("non-symlink" in error for error in result.validation_errors)
