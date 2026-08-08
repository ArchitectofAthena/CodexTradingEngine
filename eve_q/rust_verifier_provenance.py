"""Fail-closed provenance membrane for local Rust verifier binaries.

A binary is trusted only when an explicit build manifest binds its source,
toolchain, package origin, target, schemas, binary digest, and deterministic
replay. Matching output alone never grants provenance or execution authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

_MANIFEST_SCHEMA = "gate1a1-rust-verifier-manifest-v0.1"
_REPORT_SCHEMA = "gate1a1-rust-verifier-report-v0.1"
_HOLD = "HOLD_UNVERIFIED_BINARY"
_VERIFIED = "VERIFIED_RESEARCH_BINARY"
_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_RESPONSE_SCHEMA = _ROOT / "schemas" / "delta_repricing_response.schema.json"
_REQUIRED_LOCKS = {
    "authority": False,
    "artifact_is_command": False,
    "may_execute": False,
    "may_sign": False,
    "may_submit_transaction": False,
    "may_access_wallet": False,
    "may_move_capital": False,
    "gate1b_activated": False,
    "human_promotion_required": True,
}


def stable_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(
            f"{context} keys mismatch; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _sha(value: object, context: str) -> str:
    digest = str(value)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError(f"{context} must be 64 lowercase hexadecimal characters")
    return digest


def _validate_locks(payload: Mapping[str, object], context: str) -> None:
    for key, expected in _REQUIRED_LOCKS.items():
        if payload.get(key) is not expected:
            raise ValueError(f"{context}.{key} must be {expected!r}")


def manifest_seed(manifest: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in manifest.items() if key != "manifest_id"}


def build_manifest(
    *,
    source_commit: str,
    source_tree_sha256: str,
    cargo_manifest_sha256: str,
    cargo_lock_sha256: str,
    build_command: str,
    rustc_version: str,
    cargo_version: str,
    package_origin: str,
    binary_path: str | Path,
    target_triple: str,
    tree_posture: str,
    input_schema_version: str,
    output_schema_version: str,
) -> dict[str, object]:
    binary = Path(binary_path)
    if not binary.is_absolute() or not binary.is_file():
        raise ValueError("binary_path must be an existing absolute file")
    for digest, context in (
        (source_tree_sha256, "source_tree_sha256"),
        (cargo_manifest_sha256, "cargo_manifest_sha256"),
        (cargo_lock_sha256, "cargo_lock_sha256"),
    ):
        _sha(digest, context)
    if len(source_commit) != 40 or any(ch not in "0123456789abcdef" for ch in source_commit):
        raise ValueError("source_commit must be a 40-character lowercase Git commit SHA")
    if tree_posture not in {"CLEAN", "REVIEWED_DIGEST"}:
        raise ValueError("tree_posture must be CLEAN or REVIEWED_DIGEST")
    required_strings = {
        "build_command": build_command,
        "rustc_version": rustc_version,
        "cargo_version": cargo_version,
        "package_origin": package_origin,
        "target_triple": target_triple,
        "input_schema_version": input_schema_version,
        "output_schema_version": output_schema_version,
    }
    if any(not value.strip() for value in required_strings.values()):
        raise ValueError("all provenance string fields are required")

    seed = {
        "schema_version": _MANIFEST_SCHEMA,
        "source_commit": source_commit,
        "source_tree_sha256": source_tree_sha256,
        "cargo_manifest_sha256": cargo_manifest_sha256,
        "cargo_lock_sha256": cargo_lock_sha256,
        "build_command": build_command,
        "rustc_version": rustc_version,
        "cargo_version": cargo_version,
        "package_origin": package_origin,
        "binary_sha256": file_sha256(binary),
        "target_triple": target_triple,
        "tree_posture": tree_posture,
        "input_schema_version": input_schema_version,
        "output_schema_version": output_schema_version,
        **_REQUIRED_LOCKS,
    }
    return {"manifest_id": f"rust-verifier-manifest:{stable_sha256(seed)[:24]}", **seed}


def validate_manifest(manifest: Mapping[str, object]) -> None:
    _exact_keys(
        manifest,
        {
            "manifest_id",
            "schema_version",
            "source_commit",
            "source_tree_sha256",
            "cargo_manifest_sha256",
            "cargo_lock_sha256",
            "build_command",
            "rustc_version",
            "cargo_version",
            "package_origin",
            "binary_sha256",
            "target_triple",
            "tree_posture",
            "input_schema_version",
            "output_schema_version",
            *set(_REQUIRED_LOCKS),
        },
        "manifest",
    )
    if manifest["schema_version"] != _MANIFEST_SCHEMA:
        raise ValueError("manifest schema_version mismatch")
    _validate_locks(manifest, "manifest")
    for key in (
        "source_tree_sha256",
        "cargo_manifest_sha256",
        "cargo_lock_sha256",
        "binary_sha256",
    ):
        _sha(manifest[key], f"manifest.{key}")
    source_commit = str(manifest["source_commit"])
    if len(source_commit) != 40 or any(ch not in "0123456789abcdef" for ch in source_commit):
        raise ValueError("manifest.source_commit is invalid")
    if manifest["tree_posture"] not in {"CLEAN", "REVIEWED_DIGEST"}:
        raise ValueError("manifest.tree_posture is invalid")
    for key in (
        "build_command",
        "rustc_version",
        "cargo_version",
        "package_origin",
        "target_triple",
        "input_schema_version",
        "output_schema_version",
    ):
        if not str(manifest[key]).strip():
            raise ValueError(f"manifest.{key} is required")
    expected = f"rust-verifier-manifest:{stable_sha256(manifest_seed(manifest))[:24]}"
    if manifest["manifest_id"] != expected:
        raise ValueError("manifest_id does not match the provenance payload")


def _run_binary(executable: Path, request_bytes: bytes, timeout_seconds: float) -> bytes:
    completed = subprocess.run(
        [str(executable)],
        input=request_bytes,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
        shell=False,
        close_fds=True,
        cwd=executable.parent,
        env={"PATH": os.environ.get("PATH", "")},
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"verifier rejected deterministic replay: {message[:1000]}")
    if len(completed.stdout) > 64 * 1024:
        raise RuntimeError("verifier output exceeded 65536 bytes")
    return completed.stdout


def _validate_replay_response(
    response: Mapping[str, object],
    *,
    request: Mapping[str, object],
    response_schema: Mapping[str, object],
) -> None:
    Draft202012Validator.check_schema(response_schema)
    validator = Draft202012Validator(response_schema)
    errors = sorted(
        validator.iter_errors(response),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if errors:
        rendered = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:8]
        )
        raise ValueError(f"verifier response schema validation failed: {rendered}")

    for field in (
        "request_id",
        "snapshot_sha256",
        "model_sha256",
        "confidence_receipt_id",
        "candidate_id",
    ):
        if response.get(field) != request.get(field):
            raise ValueError(f"verifier response changed {field}")

    request_edges = request.get("edges")
    if not isinstance(request_edges, list) or len(request_edges) != 3:
        raise ValueError("request edges must contain exactly three entries")
    edge_rows = [_mapping(edge, "request edge") for edge in request_edges]
    expected_edge_ids = [str(edge["edge_id"]) for edge in edge_rows]
    expected_asset_path = [str(edge_rows[0]["source_asset"])] + [
        str(edge["target_asset"]) for edge in edge_rows
    ]

    verification = _mapping(response.get("verification"), "verifier response verification")
    if verification.get("edge_ids") != expected_edge_ids:
        raise ValueError("verifier response changed edge_ids")
    if verification.get("asset_path") != expected_asset_path:
        raise ValueError("verifier response changed asset_path")
    if verification.get("minimum_log_delta") != request.get("minimum_log_delta"):
        raise ValueError("verifier response changed minimum_log_delta")


def verify_binary(
    manifest: Mapping[str, object],
    *,
    executable: str | Path,
    request: Mapping[str, object],
    response_schema: Mapping[str, object] | None = None,
    timeout_seconds: float = 3.0,
) -> dict[str, object]:
    """Validate provenance and replay a binary twice, returning a fail-closed report."""

    executable_path = Path(executable)
    reasons: list[str] = []
    output_sha256 = ""
    replay_sha256 = ""
    output_schema_version = ""
    try:
        validate_manifest(manifest)
        if not executable_path.is_absolute() or not executable_path.is_file():
            raise ValueError("verifier executable must be an existing absolute file")
        if file_sha256(executable_path) != manifest["binary_sha256"]:
            raise ValueError("binary digest does not match the reviewed manifest")
        if timeout_seconds <= 0.0 or not math.isfinite(timeout_seconds):
            raise ValueError("timeout_seconds must be finite and positive")
        if request.get("schema_version") != manifest["input_schema_version"]:
            raise ValueError("request schema does not match the manifest")
        if request.get("authority") is not False:
            raise ValueError("request authority must be false")
        request_bytes = json.dumps(
            request, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        first = _run_binary(executable_path, request_bytes, timeout_seconds)
        second = _run_binary(executable_path, request_bytes, timeout_seconds)
        output_sha256 = hashlib.sha256(first).hexdigest()
        replay_sha256 = hashlib.sha256(second).hexdigest()
        if first != second:
            raise ValueError("deterministic replay output diverged")
        response = json.loads(first.decode("utf-8"))
        response = _mapping(response, "verifier response")
        output_schema_version = str(response.get("schema_version", ""))
        if output_schema_version != manifest["output_schema_version"]:
            raise ValueError("response schema does not match the manifest")
        active_response_schema = (
            response_schema if response_schema is not None else load_json(_DEFAULT_RESPONSE_SCHEMA)
        )
        _validate_replay_response(
            response,
            request=request,
            response_schema=active_response_schema,
        )
        outcome = _VERIFIED
    except (
        json.JSONDecodeError,
        KeyError,
        OSError,
        RuntimeError,
        SchemaError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ) as exc:
        reasons.append(str(exc))
        outcome = _HOLD

    report_seed = {
        "schema_version": _REPORT_SCHEMA,
        "manifest_id": str(manifest.get("manifest_id", "UNKNOWN")),
        "binary_path": str(executable_path),
        "binary_sha256": file_sha256(executable_path) if executable_path.is_file() else "",
        "output_sha256": output_sha256,
        "replay_sha256": replay_sha256,
        "input_schema_version": str(request.get("schema_version", "")),
        "output_schema_version": output_schema_version,
        "deterministic_replay": bool(output_sha256 and output_sha256 == replay_sha256),
        "outcome": outcome,
        "hold_reasons": reasons,
        **_REQUIRED_LOCKS,
    }
    return {"report_id": f"rust-verifier-report:{stable_sha256(report_seed)[:24]}", **report_seed}


def load_json(path: str | Path) -> Mapping[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return _mapping(payload, str(path))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or verify Rust verifier provenance")
    subparsers = parser.add_subparsers(dest="command", required=True)

    emit = subparsers.add_parser("emit-manifest")
    emit.add_argument("--source-commit", required=True)
    emit.add_argument("--source-tree-sha256", required=True)
    emit.add_argument("--cargo-manifest-sha256", required=True)
    emit.add_argument("--cargo-lock-sha256", required=True)
    emit.add_argument("--build-command", required=True)
    emit.add_argument("--rustc-version", required=True)
    emit.add_argument("--cargo-version", required=True)
    emit.add_argument("--package-origin", required=True)
    emit.add_argument("--binary", required=True)
    emit.add_argument("--target-triple", required=True)
    emit.add_argument("--tree-posture", required=True)
    emit.add_argument("--input-schema-version", required=True)
    emit.add_argument("--output-schema-version", required=True)
    emit.add_argument("--output", required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--binary", required=True)
    verify.add_argument("--request", required=True)
    verify.add_argument("--response-schema", default=str(_DEFAULT_RESPONSE_SCHEMA))
    verify.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.command == "emit-manifest":
        payload = build_manifest(
            source_commit=args.source_commit,
            source_tree_sha256=args.source_tree_sha256,
            cargo_manifest_sha256=args.cargo_manifest_sha256,
            cargo_lock_sha256=args.cargo_lock_sha256,
            build_command=args.build_command,
            rustc_version=args.rustc_version,
            cargo_version=args.cargo_version,
            package_origin=args.package_origin,
            binary_path=Path(args.binary).resolve(),
            target_triple=args.target_triple,
            tree_posture=args.tree_posture,
            input_schema_version=args.input_schema_version,
            output_schema_version=args.output_schema_version,
        )
        exit_code = 0
    else:
        payload = verify_binary(
            load_json(args.manifest),
            executable=Path(args.binary).resolve(),
            request=load_json(args.request),
            response_schema=load_json(args.response_schema),
        )
        exit_code = 2 if payload["outcome"] == _HOLD else 0
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
