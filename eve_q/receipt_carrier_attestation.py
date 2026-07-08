"""Receipt-to-carrier attestation validator.

This module binds a receipt-like artifact to a carrier manifest without creating
execution authority. The attestation is a review artifact only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from eve_q.artifact_carrier import validate_artifact_carrier_manifest

REQUIRED_ATTESTATION_FIELDS = {
    "schema",
    "version",
    "attestation_type",
    "receipt_id",
    "carrier_manifest_sha256",
    "carrier_cid",
    "ttl_mode",
    "human_promotion_required",
    "execution_authority",
    "reverse_execution_channel_opened",
}

FORBIDDEN_ATTESTATION_FIELDS = {
    "api_key",
    "command",
    "commands",
    "execute",
    "execution",
    "private_key",
    "scheduler",
    "seed_phrase",
    "shell",
    "subprocess",
    "wallet_private_key",
    "webhook_url",
}


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Return deterministic JSON bytes for hashing review artifacts."""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_manifest(manifest: Mapping[str, Any]) -> str:
    """Compute a deterministic SHA-256 digest for a carrier manifest."""
    return hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()


def create_receipt_carrier_attestation(
    receipt_id: str,
    carrier_manifest: dict[str, Any],
    ttl_mode: str = "artifact_only",
) -> dict[str, Any]:
    """Create a safe receipt-to-carrier attestation artifact."""
    return {
        "schema": "spiralbloom.receipt_carrier_attestation.v0.1",
        "version": "0.1.0",
        "attestation_type": "receipt_carrier_binding",
        "receipt_id": receipt_id,
        "carrier_manifest_sha256": sha256_manifest(carrier_manifest),
        "carrier_cid": carrier_manifest.get("cid"),
        "ttl_mode": ttl_mode,
        "human_promotion_required": True,
        "execution_authority": "none",
        "reverse_execution_channel_opened": False,
    }


def load_json(path: Path | str) -> dict[str, Any]:
    """Load a JSON object from disk."""
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _nested_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        keys: set[str] = set()
        for key, inner in value.items():
            keys.add(str(key))
            keys.update(_nested_keys(inner))
        return keys
    if isinstance(value, list):
        keys = set()
        for item in value:
            keys.update(_nested_keys(item))
        return keys
    return set()


def validate_receipt_carrier_attestation(
    attestation: dict[str, Any],
    carrier_manifest: dict[str, Any],
) -> list[str]:
    """Validate an attestation as a safe review artifact."""
    errors: list[str] = []

    carrier_errors = validate_artifact_carrier_manifest(carrier_manifest)
    errors.extend(f"carrier manifest invalid: {error}" for error in carrier_errors)

    missing = sorted(REQUIRED_ATTESTATION_FIELDS - set(attestation))
    errors.extend(f"missing attestation field: {field}" for field in missing)

    forbidden = sorted(_nested_keys(attestation) & FORBIDDEN_ATTESTATION_FIELDS)
    errors.extend(f"forbidden attestation field: {field}" for field in forbidden)

    if errors:
        return sorted(set(errors))

    if attestation["schema"] != "spiralbloom.receipt_carrier_attestation.v0.1":
        errors.append("attestation schema mismatch")

    if attestation["attestation_type"] != "receipt_carrier_binding":
        errors.append("attestation_type must be receipt_carrier_binding")

    if not isinstance(attestation["receipt_id"], str) or not attestation["receipt_id"]:
        errors.append("receipt_id must be a non-empty string")

    if attestation["carrier_manifest_sha256"] != sha256_manifest(carrier_manifest):
        errors.append("carrier_manifest_sha256 mismatch")

    if attestation["carrier_cid"] != carrier_manifest.get("cid"):
        errors.append("carrier_cid mismatch")

    if attestation["ttl_mode"] != "artifact_only":
        errors.append("attestation ttl_mode must be artifact_only")

    if attestation["human_promotion_required"] is not True:
        errors.append("attestation requires human_promotion_required=true")

    if attestation["execution_authority"] != "none":
        errors.append("attestation execution_authority must be none")

    if attestation["reverse_execution_channel_opened"] is not False:
        errors.append("attestation must not open reverse execution channel")

    return sorted(set(errors))


def validate_receipt_carrier_attestation_files(
    carrier_path: Path | str,
    attestation_path: Path | str,
) -> dict[str, Any]:
    """Validate carrier and attestation JSON files."""
    carrier_manifest = load_json(carrier_path)
    attestation = load_json(attestation_path)
    errors = validate_receipt_carrier_attestation(attestation, carrier_manifest)
    return {"valid": errors == [], "errors": errors}


def main(argv: list[str] | None = None) -> int:
    """Run the local attestation validator CLI."""
    parser = argparse.ArgumentParser(description="Validate a receipt carrier attestation.")
    parser.add_argument("--carrier", required=True)
    parser.add_argument("--attestation", required=True)
    args = parser.parse_args(argv)

    try:
        result = validate_receipt_carrier_attestation_files(
            carrier_path=args.carrier,
            attestation_path=args.attestation,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"valid": False, "errors": [f"failed to load input: {exc}"]}

    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
