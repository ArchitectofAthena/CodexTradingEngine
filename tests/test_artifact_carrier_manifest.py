import copy

from eve_q.artifact_carrier import (
    create_artifact_carrier_manifest,
    load_artifact_carrier_contract,
    validate_artifact_carrier_contract_shape,
    validate_artifact_carrier_manifest,
)

CID_V1 = "bafybeigdyrzt5sfp7udm7hu76qpq7ka7gskp5b4rq6x2zqexample"
CID_V0 = "Qm11111111111111111111111111111111111111111111"


def valid_manifest(**updates):
    manifest = create_artifact_carrier_manifest(CID_V1)
    manifest.update(updates)
    return manifest


def test_artifact_carrier_contract_shape_is_valid():
    assert validate_artifact_carrier_contract_shape(load_artifact_carrier_contract()) == []


def test_default_encrypted_manifest_is_valid():
    assert validate_artifact_carrier_manifest(valid_manifest()) == []


def test_cid_v0_shape_is_allowed():
    manifest = valid_manifest(cid=CID_V0)

    assert validate_artifact_carrier_manifest(manifest) == []


def test_missing_cid_is_rejected():
    manifest = valid_manifest()
    del manifest["cid"]

    assert validate_artifact_carrier_manifest(manifest) == ["missing carrier manifest field: cid"]


def test_public_payload_does_not_require_encryption_block():
    manifest = create_artifact_carrier_manifest(
        CID_V1,
        payload_class="public",
        payload_type="public_receipt",
    )

    assert "encryption" not in manifest
    assert validate_artifact_carrier_manifest(manifest) == []


def test_private_payload_requires_encryption_block():
    manifest = valid_manifest(payload_class="private")
    del manifest["encryption"]

    assert validate_artifact_carrier_manifest(manifest) == [
        "encrypted/private carrier payload requires encryption block"
    ]


def test_non_human_key_custody_is_rejected():
    manifest = valid_manifest()
    manifest["encryption"]["key_custody"] = "stored_in_metadata"

    assert validate_artifact_carrier_manifest(manifest) == ["key custody is not allowed"]


def test_forbidden_secret_marker_is_rejected():
    manifest = valid_manifest(description="leaked sk-this-is-not-a-real-key")

    assert validate_artifact_carrier_manifest(manifest) == [
        "forbidden secret marker in carrier manifest: description"
    ]


def test_forbidden_execution_field_is_rejected_even_when_nested():
    manifest = valid_manifest()
    manifest["metadata"] = {"command": "echo no"}

    assert validate_artifact_carrier_manifest(manifest) == [
        "forbidden carrier manifest field: command"
    ]


def test_human_promotion_false_is_rejected():
    manifest = valid_manifest(human_promotion_required=False)

    assert validate_artifact_carrier_manifest(manifest) == [
        "carrier manifest requires human_promotion_required=true"
    ]


def test_unsafe_ttl_mode_is_rejected():
    manifest = valid_manifest(ttl_mode="ttl_bounded_autonomy")

    assert validate_artifact_carrier_manifest(manifest) == [
        "ttl_mode is not allowed for carrier manifest"
    ]


def test_reverse_execution_channel_is_rejected():
    manifest = valid_manifest(reverse_execution_channel_opened=True)

    assert validate_artifact_carrier_manifest(manifest) == [
        "carrier manifest must not open reverse execution channel"
    ]


def test_execution_authority_must_be_none():
    manifest = valid_manifest(execution_authority="scheduler")

    assert validate_artifact_carrier_manifest(manifest) == [
        "carrier manifest execution_authority must be none"
    ]


def test_contract_shape_detects_default_ttl_drift():
    contract = copy.deepcopy(load_artifact_carrier_contract())
    contract["default_ttl_mode"] = "ttl_bounded_autonomy"

    assert validate_artifact_carrier_contract_shape(contract) == [
        "default_ttl_mode must be allowed"
    ]
