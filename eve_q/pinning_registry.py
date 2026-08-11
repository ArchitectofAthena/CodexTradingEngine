from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REGISTRY_VERSION = "cross_repo_pinning_registry_v0.1"
RECEIPT_TYPE = "eve_q.cross_repo_pinning_validation.v0.1"


class PinningRegistryError(RuntimeError):
    pass


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    # Git v0.1 blob IDs are SHA-1 by contract; this is identity compatibility,
    # not a security primitive.
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def _load_json_object(path: Path) -> tuple[bytes, dict[str, Any]]:
    if not path.is_file():
        raise PinningRegistryError(f"missing JSON file: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PinningRegistryError(f"invalid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PinningRegistryError(f"JSON root must be an object: {path}")
    return raw, value


def _resolve_inside(root: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise PinningRegistryError("pin path must be a non-empty string")
    root = root.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PinningRegistryError(
            f"pin path escapes repository root: {relative_path}"
        ) from exc
    return candidate


def _drift(
    *,
    kind: str,
    pin_id: str,
    path: str,
    expected: object = None,
    observed: object = None,
) -> dict[str, object]:
    return {
        "kind": kind,
        "pin_id": pin_id,
        "path": path,
        "expected": expected,
        "observed": observed,
    }


def _validate_safe_posture(
    document: dict[str, Any],
    *,
    pin_id: str,
    path: str,
) -> list[dict[str, object]]:
    requirements = {
        "authority": False,
        "artifact_is_command": False,
        "may_execute": False,
        "may_move_capital": False,
        "human_promotion_required": True,
    }
    drifts: list[dict[str, object]] = []
    for field_name, expected in requirements.items():
        observed = document.get(field_name)
        if observed is not expected:
            drifts.append(
                _drift(
                    kind="authority_posture_mismatch",
                    pin_id=pin_id,
                    path=path,
                    expected={field_name: expected},
                    observed={field_name: observed},
                )
            )
    return drifts


def validate_registry(
    *,
    root: Path,
    registry_path: Path,
) -> dict[str, Any]:
    root = root.resolve()
    registry_path = registry_path.resolve()
    raw_registry, registry = _load_json_object(registry_path)

    if registry.get("registry_version") != REGISTRY_VERSION:
        raise PinningRegistryError(
            f"unsupported registry_version: {registry.get('registry_version')!r}"
        )
    if registry.get("drift_policy") != "fail_closed":
        raise PinningRegistryError("registry drift_policy must be fail_closed")

    registry_drifts = _validate_safe_posture(
        registry,
        pin_id="registry",
        path=str(registry_path.relative_to(root)),
    )

    pins = registry.get("pins")
    if not isinstance(pins, list) or not pins:
        raise PinningRegistryError("registry requires at least one pin")

    pin_ids: set[str] = set()
    registered_paths: set[str] = set()
    drifts: list[dict[str, object]] = list(registry_drifts)
    checked_pin_ids: list[str] = []

    for pin in pins:
        if not isinstance(pin, dict):
            raise PinningRegistryError("each pin must be a JSON object")
        pin_id = pin.get("pin_id")
        relative_path = pin.get("path")
        if not isinstance(pin_id, str) or not pin_id.strip():
            raise PinningRegistryError("pin_id must be a non-empty string")
        if pin_id in pin_ids:
            raise PinningRegistryError(f"duplicate pin_id: {pin_id}")
        pin_ids.add(pin_id)

        if not isinstance(relative_path, str) or not relative_path.strip():
            raise PinningRegistryError(f"{pin_id}: path must be a non-empty string")
        if relative_path in registered_paths:
            raise PinningRegistryError(f"duplicate pinned path: {relative_path}")
        registered_paths.add(relative_path)
        checked_pin_ids.append(pin_id)

        if pin.get("drift_policy") != "fail_closed":
            raise PinningRegistryError(f"{pin_id}: drift_policy must be fail_closed")
        if pin.get("authority") is not False:
            raise PinningRegistryError(f"{pin_id}: registry pins cannot grant authority")

        target = _resolve_inside(root, relative_path)
        if not target.is_file():
            drifts.append(
                _drift(
                    kind="missing_pinned_artifact",
                    pin_id=pin_id,
                    path=relative_path,
                    expected="file",
                    observed="missing",
                )
            )
            continue

        raw = target.read_bytes()
        expected_sha256 = pin.get("raw_sha256")
        observed_sha256 = sha256_hex(raw)
        if expected_sha256 != observed_sha256:
            drifts.append(
                _drift(
                    kind="pinned_artifact_sha256_mismatch",
                    pin_id=pin_id,
                    path=relative_path,
                    expected=expected_sha256,
                    observed=observed_sha256,
                )
            )

        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            drifts.append(
                _drift(
                    kind="pinned_artifact_invalid_json",
                    pin_id=pin_id,
                    path=relative_path,
                    expected="UTF-8 JSON object",
                    observed="invalid",
                )
            )
            continue
        if not isinstance(document, dict):
            drifts.append(
                _drift(
                    kind="pinned_artifact_invalid_json_root",
                    pin_id=pin_id,
                    path=relative_path,
                    expected="object",
                    observed=type(document).__name__,
                )
            )
            continue

        expected_json = pin.get("expected_json", {})
        if not isinstance(expected_json, dict):
            raise PinningRegistryError(f"{pin_id}: expected_json must be an object")
        for field_name in sorted(expected_json):
            expected_value = expected_json[field_name]
            observed_value = document.get(field_name)
            if observed_value != expected_value:
                drifts.append(
                    _drift(
                        kind="pinned_metadata_mismatch",
                        pin_id=pin_id,
                        path=relative_path,
                        expected={field_name: expected_value},
                        observed={field_name: observed_value},
                    )
                )

        drifts.extend(
            _validate_safe_posture(
                document,
                pin_id=pin_id,
                path=relative_path,
            )
        )

        if pin.get("verify_manifest_schema_git_blobs") is True:
            schema_records = document.get("schemas")
            if not isinstance(schema_records, list):
                drifts.append(
                    _drift(
                        kind="manifest_schema_records_missing",
                        pin_id=pin_id,
                        path=relative_path,
                        expected="list",
                        observed=type(schema_records).__name__,
                    )
                )
                continue

            declared_count = document.get("schema_count")
            if declared_count != len(schema_records):
                drifts.append(
                    _drift(
                        kind="manifest_schema_count_mismatch",
                        pin_id=pin_id,
                        path=relative_path,
                        expected=declared_count,
                        observed=len(schema_records),
                    )
                )

            for schema_record in schema_records:
                if not isinstance(schema_record, dict):
                    drifts.append(
                        _drift(
                            kind="manifest_schema_record_invalid",
                            pin_id=pin_id,
                            path=relative_path,
                            expected="object",
                            observed=type(schema_record).__name__,
                        )
                    )
                    continue
                schema_path = schema_record.get("path")
                expected_blob = schema_record.get("source_git_blob_sha")
                if not isinstance(schema_path, str) or not schema_path:
                    drifts.append(
                        _drift(
                            kind="manifest_schema_path_invalid",
                            pin_id=pin_id,
                            path=relative_path,
                            expected="non-empty path",
                            observed=schema_path,
                        )
                    )
                    continue
                schema_target = _resolve_inside(root, schema_path)
                if not schema_target.is_file():
                    drifts.append(
                        _drift(
                            kind="manifest_schema_missing",
                            pin_id=pin_id,
                            path=schema_path,
                            expected=expected_blob,
                            observed="missing",
                        )
                    )
                    continue
                observed_blob = git_blob_sha1(schema_target.read_bytes())
                if observed_blob != expected_blob:
                    drifts.append(
                        _drift(
                            kind="manifest_schema_git_blob_mismatch",
                            pin_id=pin_id,
                            path=schema_path,
                            expected=expected_blob,
                            observed=observed_blob,
                        )
                    )

    watched_globs = registry.get("watched_globs", [])
    if not isinstance(watched_globs, list):
        raise PinningRegistryError("watched_globs must be a list")
    for pattern in watched_globs:
        if not isinstance(pattern, str) or not pattern.strip():
            raise PinningRegistryError("watched_globs entries must be non-empty strings")
        for candidate in sorted(root.glob(pattern)):
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(root).as_posix()
            if relative not in registered_paths:
                drifts.append(
                    _drift(
                        kind="unregistered_pinning_surface",
                        pin_id="registry",
                        path=relative,
                        expected="registered pin",
                        observed="unregistered file",
                    )
                )

    ordered_drifts = tuple(
        sorted(
            drifts,
            key=lambda item: (
                str(item["kind"]),
                str(item["pin_id"]),
                str(item["path"]),
                json.dumps(item["expected"], sort_keys=True),
                json.dumps(item["observed"], sort_keys=True),
            ),
        )
    )
    return {
        "receipt_type": RECEIPT_TYPE,
        "registry_version": REGISTRY_VERSION,
        "registry_path": str(registry_path.relative_to(root)),
        "registry_sha256": sha256_hex(raw_registry),
        "checked_pin_ids": sorted(checked_pin_ids),
        "drift_count": len(ordered_drifts),
        "drifts": list(ordered_drifts),
        "ok": not ordered_drifts,
        "artifact_is_command": False,
        "authority": False,
        "may_execute": False,
        "may_move_capital": False,
        "human_promotion_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the fail-closed cross-repository pinning registry."
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("contracts/PINNING.json"),
    )
    args = parser.parse_args()

    root = args.root.resolve()
    registry_path = args.registry
    if not registry_path.is_absolute():
        registry_path = root / registry_path

    try:
        receipt = validate_registry(root=root, registry_path=registry_path)
    except (PinningRegistryError, OSError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "receipt_type": RECEIPT_TYPE,
                    "error": str(exc),
                    "artifact_is_command": False,
                    "authority": False,
                    "may_execute": False,
                    "may_move_capital": False,
                    "human_promotion_required": True,
                },
                sort_keys=True,
            )
        )
        return 1

    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
