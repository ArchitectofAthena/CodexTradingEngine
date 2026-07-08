import json
from pathlib import Path

from eve_q.artifact_carrier import validate_artifact_carrier_manifest

EXAMPLE_PATH = Path("examples/artifact_carrier_manifest.example.json")
DOC_PATH = Path("docs/artifact_carrier_manifest_example.md")


def test_artifact_carrier_example_manifest_validates():
    manifest = json.loads(EXAMPLE_PATH.read_text())

    assert validate_artifact_carrier_manifest(manifest) == []


def test_artifact_carrier_example_is_pointer_not_authority():
    manifest = json.loads(EXAMPLE_PATH.read_text())

    assert manifest["ttl_mode"] == "artifact_only"
    assert manifest["human_promotion_required"] is True
    assert manifest["execution_authority"] == "none"
    assert manifest["reverse_execution_channel_opened"] is False


def test_artifact_carrier_example_keeps_key_with_human():
    manifest = json.loads(EXAMPLE_PATH.read_text())

    assert manifest["payload_class"] == "encrypted"
    assert manifest["encryption"]["status"] == "encrypted"
    assert manifest["encryption"]["key_custody"] == "human_held"


def test_artifact_carrier_example_doc_preserves_carrier_law():
    doc = DOC_PATH.read_text()

    assert "The CID points to the memory." in doc
    assert "The key is consent." in doc
    assert "The artifact never commands." in doc
    assert "It must not say what must execute." in doc
