from __future__ import annotations

import json
from pathlib import Path

from eve_q.rust_verifier_provenance import build_manifest, file_sha256, verify_binary

REQUEST = Path(__file__).parent / "fixtures" / "gate1a1_rust_repricing_request_v0_1.json"


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
        'asset_path': ['USD', 'ETH', 'BTC', 'USD'],
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


def _manifest(executable: Path) -> dict[str, object]:
    return build_manifest(
        source_commit="a" * 40,
        source_tree_sha256="b" * 64,
        cargo_manifest_sha256="c" * 64,
        cargo_lock_sha256="d" * 64,
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


def test_reviewed_binary_replays_deterministically(tmp_path: Path) -> None:
    executable = _fake_verifier(tmp_path)
    request = json.loads(REQUEST.read_text(encoding="utf-8"))

    report = verify_binary(_manifest(executable), executable=executable.resolve(), request=request)

    assert report["outcome"] == "VERIFIED_RESEARCH_BINARY"
    assert report["hold_reasons"] == []
    assert report["deterministic_replay"] is True
    assert report["output_sha256"] == report["replay_sha256"]
    assert report["authority"] is False
    assert report["gate1b_activated"] is False
    assert report["may_execute"] is False


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
