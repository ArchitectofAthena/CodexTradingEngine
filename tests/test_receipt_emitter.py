import json
import subprocess
import sys
import pytest

from eve_q.receipt_emitter import (
    ACTION_INTENT_FIELDS,
    SPIRALBLOOM_REQUIRED_FIELDS,
    build_receipt,
    sha256_file,
    validate_emitted_receipt,
    write_receipt,
)


def test_build_receipt_matches_spiralbloom_contract(tmp_path):
    artifact = tmp_path / "CROSS_REPO_INTEGRATION.md"
    artifact.write_text("artifact bridge contract\n", encoding="utf-8")

    receipt = build_receipt(
        artifact_path=artifact,
        source_repo="ArchitectofAthena/CodexTradingEngine",
        source_commit="abc123",
        source_pr=8,
        root=tmp_path,
    )

    assert SPIRALBLOOM_REQUIRED_FIELDS <= set(receipt)
    assert receipt["mode"] == "artifact_only"
    assert receipt["human_promotion_required"] is True
    assert receipt["artifact_path"] == "CROSS_REPO_INTEGRATION.md"
    assert receipt["artifact_sha256"] == sha256_file(artifact)
    assert receipt["source_pr"] == 8
    assert not (ACTION_INTENT_FIELDS & set(receipt))
    assert validate_emitted_receipt(receipt) == []


def test_write_receipt_round_trip(tmp_path):
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("hello receipt\n", encoding="utf-8")
    out = tmp_path / "receipts" / "receipt.json"

    receipt = build_receipt(
        artifact_path=artifact,
        source_repo="ArchitectofAthena/CodexTradingEngine",
        source_commit="def456",
        root=tmp_path,
    )
    write_receipt(receipt, out)

    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == receipt
    assert validate_emitted_receipt(loaded) == []


def test_missing_artifact_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_receipt(
            artifact_path=tmp_path / "missing.md",
            source_repo="ArchitectofAthena/CodexTradingEngine",
            source_commit="abc123",
            root=tmp_path,
        )


def test_action_intent_fields_are_rejected(tmp_path):
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("safe artifact\n", encoding="utf-8")

    receipt = build_receipt(
        artifact_path=artifact,
        source_repo="ArchitectofAthena/CodexTradingEngine",
        source_commit="abc123",
        root=tmp_path,
    )
    receipt["requested_action"] = "execute live trade"

    errors = validate_emitted_receipt(receipt)

    assert any("action/intent fields" in error for error in errors)


def test_cli_emits_receipt(tmp_path):
    artifact = tmp_path / "artifact.md"
    artifact.write_text("cli artifact\n", encoding="utf-8")
    out = tmp_path / "out" / "receipt.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.receipt_emitter",
            "--artifact",
            str(artifact),
            "--out",
            str(out),
            "--source-commit",
            "abc123",
            "--source-pr",
            "8",
            "--root",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(result.stdout)
    receipt = json.loads(out.read_text(encoding="utf-8"))

    assert summary["ok"] is True
    assert receipt["artifact_sha256"] == sha256_file(artifact)
    assert receipt["mode"] == "artifact_only"
    assert receipt["source_pr"] == 8
    assert validate_emitted_receipt(receipt) == []
