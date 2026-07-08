"""Artifact carrier manifest validator.

Artifact carriers may point to memory, receipts, or encrypted spores. They do
not grant authority, execute commands, hold secrets, or move capital.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CARRIER_CONTRACT_PATH = REPO_ROOT / "contracts" / "artifact_carrier_manifest.json"

CIDV0_PATTERN = re.compile(r"^Qm[1-9A-HJ-NP-Za-km-z]{44,}$")
CIDV1_PATTERN = re.compile(r"^ba[a-z0-9]{8,}$")


def load_artifact_carrier_contract(
    path: Path | str = DEFAULT_CARRIER_CONTRACT_PATH,
) -> dict[str, Any]:
    """Load the machine-readable artifact carrier contract."""
    return json.loads(Path(path).read_text())


def _as_string_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, Iterable):
        return {str(item) for item in value}
    return {str(value)}


def _walk_mapping_values(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, inner in value.items():
            yield str(key), inner
            yield from _walk_mapping_values(inner)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_mapping_values(item)


def _cid_shape_is_plausible(cid: Any) -> bool:
    if not isinstance(cid, str):
        return False
    return bool(CIDV0_PATTERN.match(cid) or CIDV1_PATTERN.match(cid))


def validate_artifact_carrier_contract_shape(
    contract: dict[str, Any],
) -> list[str]:
    """Return structural errors for the carrier contract."""
    errors: list[str] = []

    required_fields = {
        "contract_id",
        "version",
        "manifest_schema",
        "default_ttl_mode",
        "allowed_artifact_types",
        "allowed_payload_classes",
        "allowed_ttl_modes",
        "required_manifest_fields",
        "encrypted_payload_classes",
        "required_encryption_fields",
        "allowed_encryption_statuses",
        "allowed_key_custody",
        "forbidden_manifest_fields",
        "forbidden_secret_markers",
        "hard_invariants",
    }

    missing = sorted(required_fields - set(contract))
    errors.extend(f"missing carrier contract field: {field}" for field in missing)

    if errors:
        return errors

    list_fields = {
        "allowed_artifact_types",
        "allowed_payload_classes",
        "allowed_ttl_modes",
        "required_manifest_fields",
        "encrypted_payload_classes",
        "required_encryption_fields",
        "allowed_encryption_statuses",
        "allowed_key_custody",
        "forbidden_manifest_fields",
        "forbidden_secret_markers",
        "hard_invariants",
    }

    for field in sorted(list_fields):
        if not isinstance(contract[field], list):
            errors.append(f"carrier contract field must be a list: {field}")

    if contract["default_ttl_mode"] not in contract["allowed_ttl_modes"]:
        errors.append("default_ttl_mode must be allowed")

    return errors


def create_artifact_carrier_manifest(
    cid: str,
    payload_class: str = "encrypted",
    artifact_type: str = "image_metadata_pointer",
    payload_type: str = "encrypted_spore",
    ttl_mode: str = "artifact_only",
    description: str | None = None,
) -> dict[str, Any]:
    """Create a safe default artifact carrier manifest."""
    manifest: dict[str, Any] = {
        "schema": "spiralbloom.artifact_carrier.v0.1",
        "version": "0.1.0",
        "artifact_type": artifact_type,
        "cid": cid,
        "payload_class": payload_class,
        "payload_type": payload_type,
        "ttl_mode": ttl_mode,
        "human_promotion_required": True,
        "execution_authority": "none",
        "reverse_execution_channel_opened": False,
    }

    if description:
        manifest["description"] = description

    if payload_class in {"encrypted", "private"}:
        manifest["encryption"] = {
            "status": "encrypted",
            "key_custody": "human_held",
        }

    return manifest


def _validate_no_forbidden_fields(
    manifest: Mapping[str, Any],
    forbidden_fields: set[str],
) -> list[str]:
    errors: list[str] = []

    for key, _ in _walk_mapping_values(manifest):
        if key in forbidden_fields:
            errors.append(f"forbidden carrier manifest field: {key}")

    return errors


def _validate_no_secret_markers(
    manifest: Mapping[str, Any],
    forbidden_secret_markers: list[str],
) -> list[str]:
    errors: list[str] = []
    lowered_markers = [marker.lower() for marker in forbidden_secret_markers]

    for key, value in _walk_mapping_values(manifest):
        searchable = [key]
        if isinstance(value, str):
            searchable.append(value)

        for item in searchable:
            item_lower = item.lower()
            for marker in lowered_markers:
                if marker in item_lower:
                    errors.append(f"forbidden secret marker in carrier manifest: {key}")

    return sorted(set(errors))


def _validate_encryption_block(
    manifest: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    payload_class = manifest.get("payload_class")

    if payload_class not in contract["encrypted_payload_classes"]:
        return errors

    encryption = manifest.get("encryption")
    if not isinstance(encryption, Mapping):
        return ["encrypted/private carrier payload requires encryption block"]

    for field in contract["required_encryption_fields"]:
        if field not in encryption:
            errors.append(f"missing encryption field: {field}")

    if encryption.get("status") not in contract["allowed_encryption_statuses"]:
        errors.append("encryption status is not allowed")

    if encryption.get("key_custody") not in contract["allowed_key_custody"]:
        errors.append("key custody is not allowed")

    return errors


def validate_artifact_carrier_manifest(
    manifest: dict[str, Any],
    contract: dict[str, Any] | None = None,
    contract_path: Path | str = DEFAULT_CARRIER_CONTRACT_PATH,
) -> list[str]:
    """Validate a carrier manifest as a pointer, not an authority source."""
    if contract is None:
        contract = load_artifact_carrier_contract(contract_path)

    errors = validate_artifact_carrier_contract_shape(contract)
    if errors:
        return errors

    required_fields = set(contract["required_manifest_fields"])
    missing = sorted(required_fields - set(manifest))
    errors.extend(f"missing carrier manifest field: {field}" for field in missing)

    if errors:
        return errors

    if manifest["schema"] != contract["manifest_schema"]:
        errors.append("carrier manifest schema mismatch")

    if manifest["artifact_type"] not in contract["allowed_artifact_types"]:
        errors.append("artifact_type is not allowed")

    if manifest["payload_class"] not in contract["allowed_payload_classes"]:
        errors.append("payload_class is not allowed")

    if manifest["ttl_mode"] not in contract["allowed_ttl_modes"]:
        errors.append("ttl_mode is not allowed for carrier manifest")

    if manifest["human_promotion_required"] is not True:
        errors.append("carrier manifest requires human_promotion_required=true")

    if manifest["execution_authority"] != "none":
        errors.append("carrier manifest execution_authority must be none")

    if manifest["reverse_execution_channel_opened"] is not False:
        errors.append("carrier manifest must not open reverse execution channel")

    if not _cid_shape_is_plausible(manifest["cid"]):
        errors.append("carrier manifest CID shape is invalid")

    errors.extend(
        _validate_no_forbidden_fields(
            manifest,
            _as_string_set(contract["forbidden_manifest_fields"]),
        )
    )
    errors.extend(
        _validate_no_secret_markers(
            manifest,
            list(contract["forbidden_secret_markers"]),
        )
    )
    errors.extend(_validate_encryption_block(manifest, contract))

    return sorted(set(errors))
