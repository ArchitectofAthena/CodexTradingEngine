import copy
import json
from pathlib import Path

from eve_q.receipt_carrier_attestation import (
    create_receipt_carrier_attestation,
    sha256_manifest,
    validate_receipt_carrier_attestation,
)

EXAMPLE_PATH = Path("examples/artifact_carrier_manifest.example.json")


def load_example_manifest():
    return json.loads(EXAMPLE_PATH.read_text())


def test_receipt_carrier_attestation_validates_example_manifest():
    manifest = load_example_manifest()
    attestation = create_receipt_carrier_attestation(
        receipt_id="receipt_example_001",
        carrier_manifest=manifest,
    )

    assert validate_receipt_carrier_attestation(attestation, manifest) == []


def test_attestation_binds_to_carrier_manifest_hash():
    manifest = load_example_manifest()
    attestation = create_receipt_carrier_attestation(
        receipt_id="receipt_example_001",
        carrier_manifest=manifest,
    )

    assert attestation["carrier_manifest_sha256"] == sha256_manifest(manifest)


def test_attestation_detects_manifest_drift():
    manifest = load_example_manifest()
    attestation = create_receipt_carrier_attestation(
        receipt_id="receipt_example_001",
        carrier_manifest=manifest,
    )

    drifted = copy.deepcopy(manifest)
    drifted["payload_type"] = "changed_payload"

    assert validate_receipt_carrier_attestation(attestation, drifted) == [
        "carrier_manifest_sha256 mismatch"
    ]


def test_attestation_detects_carrier_cid_mismatch():
    manifest = load_example_manifest()
    attestation = create_receipt_carrier_attestation(
        receipt_id="receipt_example_001",
        carrier_manifest=manifest,
    )
    attestation["carrier_cid"] = "bafybeigdyrzt5sfp7udm7hu76qpq7ka7gskp5b4rq6x2zqwrong"

    assert validate_receipt_carrier_attestation(attestation, manifest) == ["carrier_cid mismatch"]


def test_attestation_rejects_execution_authority():
    manifest = load_example_manifest()
    attestation = create_receipt_carrier_attestation(
        receipt_id="receipt_example_001",
        carrier_manifest=manifest,
    )
    attestation["execution_authority"] = "scheduler"

    assert validate_receipt_carrier_attestation(attestation, manifest) == [
        "attestation execution_authority must be none"
    ]


def test_attestation_rejects_reverse_execution_channel():
    manifest = load_example_manifest()
    attestation = create_receipt_carrier_attestation(
        receipt_id="receipt_example_001",
        carrier_manifest=manifest,
    )
    attestation["reverse_execution_channel_opened"] = True

    assert validate_receipt_carrier_attestation(attestation, manifest) == [
        "attestation must not open reverse execution channel"
    ]


def test_attestation_rejects_non_artifact_ttl_mode():
    manifest = load_example_manifest()
    attestation = create_receipt_carrier_attestation(
        receipt_id="receipt_example_001",
        carrier_manifest=manifest,
        ttl_mode="ttl_bounded_autonomy",
    )

    assert validate_receipt_carrier_attestation(attestation, manifest) == [
        "attestation ttl_mode must be artifact_only"
    ]


def test_attestation_rejects_forbidden_nested_command_field():
    manifest = load_example_manifest()
    attestation = create_receipt_carrier_attestation(
        receipt_id="receipt_example_001",
        carrier_manifest=manifest,
    )
    attestation["metadata"] = {"command": "echo no"}

    assert validate_receipt_carrier_attestation(attestation, manifest) == [
        "forbidden attestation field: command"
    ]
