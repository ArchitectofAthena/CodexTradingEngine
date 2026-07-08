from pathlib import Path

DOC = Path("docs/constitutional_membrane_checkpoint.md")


def test_checkpoint_names_sealed_surface_stack():
    text = DOC.read_text()

    required = [
        "#20",
        "#21",
        "#22",
        "#23",
        "#24",
        "#25",
        "#26",
        "#27",
        "#28",
        "#29",
        "#30",
        "#31",
        "#32",
        "#33",
        "Artifact carrier validator",
        "Receipt carrier attestation validator",
        "Membrane metadata extractor",
        "Membrane attestation bridge",
    ]

    for item in required:
        assert item in text


def test_checkpoint_preserves_verified_chain():
    text = DOC.read_text()

    required = [
        "image metadata",
        "carrier manifest",
        "carrier law validation",
        "receipt attestation validation",
        "combined CLI result",
        "human review",
    ]

    for item in required:
        assert item in text


def test_checkpoint_names_live_smoke_test_commands():
    text = DOC.read_text()

    required = [
        "python -m eve_q.artifact_carrier",
        "python -m eve_q.receipt_carrier_attestation",
        "python -m eve_q.membrane_tool",
        "--attestation examples/receipt_carrier_attestation.example.json",
    ]

    for item in required:
        assert item in text


def test_checkpoint_preserves_self_cid_trap():
    text = DOC.read_text()

    required = [
        "Self-CID Trap",
        "An IPFS CID is derived from the full file contents.",
        "embedding the CID changes the image bytes",
        "changes the CID again",
        "should not try to self-seal the image",
    ]

    for item in required:
        assert item in text


def test_checkpoint_preserves_non_authority_boundary():
    text = DOC.read_text()

    required = [
        "no autonomous capital movement",
        "no wallet signing",
        "no scheduler authority",
        "no reverse execution channel",
        "no metadata writing",
        "no IPFS daemon dependency",
        "no network access",
        "no shell execution from metadata",
        "no subprocess execution from metadata",
        "no command execution from metadata",
    ]

    for item in required:
        assert item in text


def test_checkpoint_preserves_law():
    text = DOC.read_text()

    required = [
        "The bridge is built.",
        "The map is guarded.",
        "The checkpoint remembers what changed.",
        "The artifact still does not command.",
    ]

    for item in required:
        assert item in text
