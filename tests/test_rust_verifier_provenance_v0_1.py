from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from eve_q.rust_verifier_provenance import (
    build_manifest,
    canonical_response_schema_sha256,
    file_sha256,
    manifest_seed,
    stable_sha256,
    verify_binary,
)

ROOT = Path(__file__).resolve().parents[1]
REQUEST = Path(__file__).parent / "fixtures" / "gate1a1_rust_repricing_request_v0_1.json"
WORKFLOW = ROOT / ".github" / "workflows" / "gate1a1-rust-verifier-provenance-v0-1-ci.yml"
SOURCE_SCHEMA = ROOT / "schemas" / "delta_repricing_response.schema.json"


def _fake_verifier(tmp_path: Path) -> Path:
    executable = tmp_path / "fake-verifier"
    executable.write_text(
        """#!/usr/bin/env python3
import json, sys
request = json.load(sys.stdin)
response = {
    'schema_version': 'delta-repricing-response-v0.1',
    'request_id': request['request_id'],
    'snapshot_sha256': request['snapshot_sha256'],
    'model_sha256': request['model_sha256'],
    'confidence_receipt_id': request['confidence_receipt_id'],
    'candidate_id': request['candidate_id'],
    'verifier': 'codex-delta-verifier/test',
    'status': 'verified',
    'verification': {
        'edge_ids': [edge['edge_id'] for edge in request['edges']],
        'asset_path': [request['edges'][0]['source_asset']] + [
            edge['target_asset'] for edge in request['edges']
        ],
        'net_multiplier': 1.0,
        'net_log_delta': 0.0,
        'minimum_log_delta': request['minimum_log_delta'],
        'profitable': False,
        'passes_margin': True,
        'authority': False,
    },
    'authority': False,
}
print(json.dumps(response, sort_keys=True, separators=(',', ':')))
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _minimal_spoof_verifier(tmp_path: Path) -> Path:
    executable = tmp_path / "minimal-spoof-verifier"
    executable.write_text(
        """#!/usr/bin/env python3
import json, sys
request = json.load(sys.stdin)
print(json.dumps({
    'schema_version': 'delta-repricing-response-v0.1',
    'request_id': request['request_id'],
    'authority': False,
}, sort_keys=True, separators=(',', ':')))
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _manifest(executable: Path) -> dict[str, object]:
    return build_manifest(
        source_commit="a" * 40,
        source_tree_sha256="b" * 64,
        cargo_manifest_sha256="c" * 64,
        cargo_lock_sha256="d" * 64,
        response_schema_sha256=canonical_response_schema_sha256(),
        build_command="cargo build --locked --release --bin codex-delta-verifier",
        rustc_version="rustc 1.85.0",
        cargo_version="cargo 1.85.0",
        package_origin="rust/delta-verifier/Cargo.toml",
        binary_path=executable.resolve(),
        target_triple="x86_64-unknown-linux-gnu",
        tree_posture="CLEAN",
        input_schema_version="delta-repricing-request-v0.1",
        output_schema_version="delta-repricing-response-v0.1",
    )


def _reseal_manifest(manifest: dict[str, object]) -> None:
    manifest["manifest_id"] = f"rust-verifier-manifest:{stable_sha256(manifest_seed(manifest))[:24]}"


def test_packaged_response_schema_matches_repository_canonical() -> None:
    packaged = files("eve_q").joinpath("delta_repricing_response.schema.json").read_bytes()
    source = SOURCE_SCHEMA.read_bytes()

    assert packaged == source
    assert canonical_response_schema_sha256() == file_sha256(SOURCE_SCHEMA)


def test_reviewed_binary_replays_deterministically(tmp_path: Path) -> None:
    executable = _fake_verifier(tmp_path)
    request = json.loads(REQUEST.read_text(encoding="utf-8"))

    report = verify_binary(_manifest(executable), executable=executable.resolve(), request=request)

    assert report["outcome"] == "VERIFIED_RESEARCH_BINARY", report["hold_reasons"]
    assert report["hold_reasons"] == []
    assert report["deterministic_replay"] is True
    assert report["output_sha256"] == report["replay_sha256"]
    assert report["authority"] is False
    assert report["gate1b_activated"] is False
    assert report["may_execute"] is False


def test_schema_digest_tamper_holds_after_manifest_reseal(tmp_path: Path) -> None:
    executable = _fake_verifier(tmp_path)
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    manifest = _manifest(executable)
    manifest["response_schema_sha256"] = "0" * 64
    _reseal_manifest(manifest)

    report = verify_binary(manifest, executable=executable.resolve(), request=request)

    assert report["outcome"] == "HOLD_UNVERIFIED_BINARY"
    assert any("canonical response schema digest" in reason for reason in report["hold_reasons"])


def test_minimal_schema_version_spoof_holds(tmp_path: Path) -> None:
    executable = _minimal_spoof_verifier(tmp_path)
    request = json.loads(REQUEST.read_text(encoding="utf-8"))

    report = verify_binary(_manifest(executable), executable=executable.resolve(), request=request)

    assert report["outcome"] == "HOLD_UNVERIFIED_BINARY"
    assert any("schema validation failed" in reason for reason in report["hold_reasons"])


def test_request_derived_candidate_identity_mismatch_holds(tmp_path: Path) -> None:
    executable = _fake_verifier(tmp_path)
    source = executable.read_text(encoding="utf-8").replace(
        "'candidate_id': request['candidate_id']",
        "'candidate_id': 'triangle:00000000000000000000'",
    )
    executable.write_text(source, encoding="utf-8")
    executable.chmod(0o755)
    request = json.loads(REQUEST.read_text(encoding="utf-8"))

    report = verify_binary(_manifest(executable), executable=executable.resolve(), request=request)

    assert report["outcome"] == "HOLD_UNVERIFIED_BINARY"
    assert any("candidate_id" in reason for reason in report["hold_reasons"])


def test_request_derived_edge_identity_mismatch_holds(tmp_path: Path) -> None:
    executable = _fake_verifier(tmp_path)
    source = executable.read_text(encoding="utf-8").replace(
        "[edge['edge_id'] for edge in request['edges']]",
        "['edge:tamper-a', 'edge:tamper-b', 'edge:tamper-c']",
    )
    executable.write_text(source, encoding="utf-8")
    executable.chmod(0o755)
    request = json.loads(REQUEST.read_text(encoding="utf-8"))

    report = verify_binary(_manifest(executable), executable=executable.resolve(), request=request)

    assert report["outcome"] == "HOLD_UNVERIFIED_BINARY"
    assert any("edge_ids" in reason for reason in report["hold_reasons"])


def test_workflow_executes_recorded_build_and_binds_schema_digest() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    for required in (
        "BUILD_COMMAND: >-",
        "SOURCE_DATE_EPOCH=0 CARGO_INCREMENTAL=0",
        "RUSTFLAGS='-C strip=symbols -C debuginfo=0'",
        "CARGO_TARGET_DIR=/tmp/target-a cargo build",
        "--manifest-path /tmp/build-a/Cargo.toml",
        "--locked --release --bin codex-delta-verifier",
        "--target x86_64-unknown-linux-gnu",
        'bash -c "$BUILD_COMMAND"',
        '--build-command "$BUILD_COMMAND"',
        '--response-schema-sha256 "$RESPONSE_SCHEMA_SHA"',
    ):
        assert required in text, required

    assert "--response-schema " not in text


def test_unexplained_binary_holds(tmp_path: Path) -> None:
    executable = _fake_verifier(tmp_path)
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    manifest = _manifest(executable)
    manifest["binary_sha256"] = "0" * 64

    report = verify_binary(manifest, executable=executable.resolve(), request=request)

    assert report["outcome"] == "HOLD_UNVERIFIED_BINARY"
    assert report["hold_reasons"]


def test_changed_binary_holds_even_when_output_matches(tmp_path: Path) -> None:
    executable = _fake_verifier(tmp_path)
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    manifest = _manifest(executable)
    executable.write_text(executable.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    executable.chmod(0o755)

    report = verify_binary(manifest, executable=executable.resolve(), request=request)

    assert file_sha256(executable) != manifest["binary_sha256"]
    assert report["outcome"] == "HOLD_UNVERIFIED_BINARY"


def test_input_schema_mismatch_holds(tmp_path: Path) -> None:
    executable = _fake_verifier(tmp_path)
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    request["schema_version"] = "wrong-schema"

    report = verify_binary(_manifest(executable), executable=executable.resolve(), request=request)

    assert report["outcome"] == "HOLD_UNVERIFIED_BINARY"
    assert any("request schema" in reason for reason in report["hold_reasons"])


def test_authority_request_holds(tmp_path: Path) -> None:
    executable = _fake_verifier(tmp_path)
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    request["authority"] = True

    report = verify_binary(_manifest(executable), executable=executable.resolve(), request=request)

    assert report["outcome"] == "HOLD_UNVERIFIED_BINARY"
    assert any("authority" in reason for reason in report["hold_reasons"])
