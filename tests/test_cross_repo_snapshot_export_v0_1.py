from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from eve_q.cross_repo_snapshot_export import (
    CrossRepoExportError,
    build_cross_repo_envelope,
    compute_envelope_id,
    export_snapshot_bundle,
    snapshot_document_sha256,
)
from eve_q.live_read_only_telemetry import (
    SourceSpec,
    TransportResult,
    build_snapshot,
    compute_artifact_id,
    write_snapshot_bundle,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas" / "cross_repo_snapshot_envelope_v0_1.schema.json").read_text(
        encoding="utf-8"
    )
)


def snapshot_fixture() -> tuple[dict, bytes, bytes]:
    spec = SourceSpec(
        source_id="fixture-market",
        source_kind="market_snapshot",
        url="https://data.example.org/market",
        allowed_hosts=("data.example.org",),
        freshness_ttl_seconds=300,
    )
    result = TransportResult(
        status=200,
        headers={"content-type": "application/json"},
        body=b'{"price":100,"symbol":"TEST"}',
        final_url="https://data.example.org/market",
        retrieved_at="2026-08-02T00:00:00Z",
    )
    return build_snapshot(
        spec,
        result,
        producer_commit="b" * 40,
    )


def test_exported_envelope_matches_spiralbloom_contract(tmp_path: Path) -> None:
    snapshot, raw_bytes, normalized_bytes = snapshot_fixture()
    bundle = tmp_path / "bundle"
    write_snapshot_bundle(bundle, snapshot, raw_bytes, normalized_bytes)

    envelope = export_snapshot_bundle(bundle)
    Draft202012Validator(SCHEMA).validate(envelope)

    assert envelope["envelope_id"] == compute_envelope_id(envelope)
    assert envelope["snapshot"]["document_sha256"] == snapshot_document_sha256(snapshot)
    assert envelope["snapshot"]["artifact_id"] == snapshot["artifact_id"]
    assert envelope["producer"]["commit_sha"] == "b" * 40
    assert envelope["gate_posture"]["gate_2_through_6"] == "LOCKED"
    assert envelope["authority"] is False
    assert envelope["may_generate_live_proposal"] is False
    assert envelope["may_execute"] is False
    assert envelope["may_move_capital"] is False


def test_export_is_deterministic() -> None:
    snapshot, raw_bytes, normalized_bytes = snapshot_fixture()
    first = build_cross_repo_envelope(snapshot, raw_bytes, normalized_bytes)
    second = build_cross_repo_envelope(snapshot, raw_bytes, normalized_bytes)
    assert first == second
    assert first["envelope_id"] == second["envelope_id"]


def test_tampered_bundle_fails_closed(tmp_path: Path) -> None:
    snapshot, raw_bytes, normalized_bytes = snapshot_fixture()
    bundle = tmp_path / "bundle"
    write_snapshot_bundle(bundle, snapshot, raw_bytes, normalized_bytes)
    (bundle / "raw.bin").write_bytes(raw_bytes + b"tamper")
    with pytest.raises(CrossRepoExportError, match="replay failed"):
        export_snapshot_bundle(bundle)


def test_gate_leakage_fails_closed() -> None:
    snapshot, raw_bytes, normalized_bytes = snapshot_fixture()
    unsafe = deepcopy(snapshot)
    unsafe["gate_posture"]["gate_2_through_6"] = "OPEN"
    unsafe["artifact_id"] = compute_artifact_id(unsafe)
    with pytest.raises(CrossRepoExportError, match="gate posture"):
        build_cross_repo_envelope(unsafe, raw_bytes, normalized_bytes)


def test_authority_escalation_fails_closed() -> None:
    snapshot, raw_bytes, normalized_bytes = snapshot_fixture()
    unsafe = deepcopy(snapshot)
    unsafe["authority"] = True
    unsafe["artifact_id"] = compute_artifact_id(unsafe)
    with pytest.raises(CrossRepoExportError, match="authority"):
        build_cross_repo_envelope(unsafe, raw_bytes, normalized_bytes)


def test_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(SCHEMA)
