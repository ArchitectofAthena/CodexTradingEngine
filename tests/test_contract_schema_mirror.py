from __future__ import annotations

import hashlib
import json
from pathlib import Path


MANIFEST_PATH = Path("contracts/eve_q_cross_repo_contract_v0_1.manifest.json")


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


def test_manifest_pins_exact_control_plane_schema_blobs():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["contract_version"] == "eve_q_cross_repo_v0.1"
    assert manifest["source_repository"] == "ArchitectofAthena/spiralbloom-os"
    assert len(manifest["source_commit"]) == 40
    assert manifest["schema_count"] == 6
    assert len(manifest["schemas"]) == 6

    for entry in manifest["schemas"]:
        path = Path(entry["path"])
        assert path.is_file(), path

        raw = path.read_bytes()
        assert git_blob_sha(raw) == entry["source_git_blob_sha"], path

        schema = json.loads(raw.decode("utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["properties"]["contract_version"]["const"] == manifest["contract_version"]


def test_manifest_and_schemas_carry_no_execution_authority():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["authority"] is False
    assert manifest["execution_authority"] == "none"
    assert manifest["artifact_is_command"] is False
    assert manifest["may_execute"] is False
    assert manifest["may_move_capital"] is False
    assert manifest["human_promotion_required"] is True

    proposal = json.loads(
        Path("schemas/proposal_artifact_v0_1.schema.json").read_text(encoding="utf-8")
    )
    gate = json.loads(
        Path("schemas/gate_decision_v0_1.schema.json").read_text(encoding="utf-8")
    )
    execution = json.loads(
        Path("schemas/execution_receipt_v0_1.schema.json").read_text(encoding="utf-8")
    )

    assert proposal["properties"]["authority"]["const"] is False
    assert proposal["properties"]["autonomous_capital_movement"]["const"] is False
    assert gate["properties"]["execution_authority"]["const"] is False
    assert gate["properties"]["capital_movement_authorized"]["const"] is False
    assert execution["properties"]["observed"]["const"] is True
    assert execution["properties"]["inferred"]["const"] is False
