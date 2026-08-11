from __future__ import annotations

import hashlib
import json
from pathlib import Path

from eve_q.pinning_registry import (
    REGISTRY_VERSION,
    git_blob_sha1,
    validate_registry,
)


def write_json(path: Path, value: object) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def seed_registry(root: Path, *, authority: bool = False) -> tuple[Path, Path]:
    schema_paths = []
    for name in ("proposal.schema.json", "evidence.schema.json"):
        path = root / "schemas" / name
        raw = write_json(
            path,
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "title": name,
            },
        )
        schema_paths.append(
            {
                "path": path.relative_to(root).as_posix(),
                "source_git_blob_sha": git_blob_sha1(raw),
            }
        )

    manifest = {
        "contract_version": "eve_q_cross_repo_v0.1",
        "source_repository": "ArchitectofAthena/spiralbloom-os",
        "source_commit": "a" * 40,
        "producer_repository": "ArchitectofAthena/CodexTradingEngine",
        "schemas": schema_paths,
        "schema_count": len(schema_paths),
        "authority": authority,
        "artifact_is_command": False,
        "may_execute": False,
        "may_move_capital": False,
        "human_promotion_required": True,
    }
    manifest_path = root / "contracts" / "eve_q_cross_repo_contract_v0_1.manifest.json"
    manifest_raw = write_json(manifest_path, manifest)

    registry = {
        "registry_version": REGISTRY_VERSION,
        "drift_policy": "fail_closed",
        "watched_globs": ["contracts/*cross_repo*.manifest.json"],
        "pins": [
            {
                "pin_id": "eve_q_cross_repo_contract_v0_1",
                "path": manifest_path.relative_to(root).as_posix(),
                "raw_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                "expected_json": {
                    "contract_version": "eve_q_cross_repo_v0.1",
                    "source_repository": "ArchitectofAthena/spiralbloom-os",
                    "source_commit": "a" * 40,
                    "producer_repository": "ArchitectofAthena/CodexTradingEngine",
                },
                "verify_manifest_schema_git_blobs": True,
                "drift_policy": "fail_closed",
                "authority": False,
            }
        ],
        "artifact_is_command": False,
        "authority": False,
        "may_execute": False,
        "may_move_capital": False,
        "human_promotion_required": True,
    }
    registry_path = root / "contracts" / "PINNING.json"
    write_json(registry_path, registry)
    return registry_path, manifest_path


def test_registry_accepts_exact_non_authoritative_pin(tmp_path: Path) -> None:
    registry_path, _ = seed_registry(tmp_path)

    receipt = validate_registry(root=tmp_path, registry_path=registry_path)

    assert receipt["ok"] is True
    assert receipt["drift_count"] == 0
    assert receipt["authority"] is False
    assert receipt["artifact_is_command"] is False
    assert receipt["may_execute"] is False
    assert receipt["may_move_capital"] is False
    assert receipt["human_promotion_required"] is True


def test_manifest_byte_drift_fails_closed(tmp_path: Path) -> None:
    registry_path, manifest_path = seed_registry(tmp_path)
    manifest_path.write_bytes(manifest_path.read_bytes() + b"\n")

    receipt = validate_registry(root=tmp_path, registry_path=registry_path)

    assert receipt["ok"] is False
    assert "pinned_artifact_sha256_mismatch" in {
        item["kind"] for item in receipt["drifts"]
    }


def test_schema_drift_fails_closed_even_when_manifest_is_unchanged(tmp_path: Path) -> None:
    registry_path, _ = seed_registry(tmp_path)
    schema_path = tmp_path / "schemas" / "proposal.schema.json"
    schema_path.write_text('{"type":"array"}\n', encoding="utf-8")

    receipt = validate_registry(root=tmp_path, registry_path=registry_path)

    assert receipt["ok"] is False
    assert "manifest_schema_git_blob_mismatch" in {
        item["kind"] for item in receipt["drifts"]
    }


def test_unregistered_cross_repo_manifest_fails_closed(tmp_path: Path) -> None:
    registry_path, _ = seed_registry(tmp_path)
    write_json(
        tmp_path / "contracts" / "new_cross_repo_contract_v0_2.manifest.json",
        {"authority": False},
    )

    receipt = validate_registry(root=tmp_path, registry_path=registry_path)

    assert receipt["ok"] is False
    assert "unregistered_pinning_surface" in {
        item["kind"] for item in receipt["drifts"]
    }


def test_matching_hash_cannot_hide_authority_escalation(tmp_path: Path) -> None:
    registry_path, _ = seed_registry(tmp_path, authority=True)

    receipt = validate_registry(root=tmp_path, registry_path=registry_path)

    assert receipt["ok"] is False
    assert "authority_posture_mismatch" in {
        item["kind"] for item in receipt["drifts"]
    }
