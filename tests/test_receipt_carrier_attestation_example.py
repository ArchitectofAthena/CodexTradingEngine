import json
from pathlib import Path

from eve_q.receipt_carrier_attestation import (
    sha256_manifest,
    validate_receipt_carrier_attestation,
)

CARRIER_PATH = Path("examples/artifact_carrier_manifest.example.json")
ATTESTATION_PATH = Path("examples/receipt_carrier_attestation.example.json")
DOC_PATH = Path("docs/receipt_carrier_attestation_example.md")


def load_carrier_manifest():
    return json.loads(CARRIER_PATH.read_text())


def load_attestation():
    return json.loads(ATTESTATION_PATH.read_text())


def test_receipt_carrier_attestation_example_validates():
    manifest = load_carrier_manifest()
    attestation = load_attestation()

    assert validate_receipt_carrier_attestation(attestation, manifest) == []


def test_receipt_carrier_attestation_example_binds_manifest_hash():
    manifest = load_carrier_manifest()
    attestation = load_attestation()

    assert attestation["carrier_manifest_sha256"] == sha256_manifest(manifest)


def test_receipt_carrier_attestation_example_binds_carrier_cid():
    manifest = load_carrier_manifest()
    attestation = load_attestation()

    assert attestation["carrier_cid"] == manifest["cid"]


def test_receipt_carrier_attestation_example_is_review_artifact_only():
    attestation = load_attestation()

    assert attestation["ttl_mode"] == "artifact_only"
    assert attestation["human_promotion_required"] is True
    assert attestation["execution_authority"] == "none"
    assert attestation["reverse_execution_channel_opened"] is False


def test_receipt_carrier_attestation_example_doc_preserves_law():
    doc = DOC_PATH.read_text()

    assert "Receipt remembers." in doc
    assert "Carrier points." in doc
    assert "TTL expires." in doc
    assert "Human promotes." in doc
    assert "The carrier still does not command." in doc
