from pathlib import Path

DOC = Path("docs/membrane_tool_usage.md")


def test_membrane_tool_usage_doc_names_cli_surfaces():
    text = DOC.read_text()

    required = [
        "python -m eve_q.membrane_tool",
        "python -m eve_q.artifact_carrier",
        "python -m eve_q.receipt_carrier_attestation",
        "--manifest-only",
    ]

    for item in required:
        assert item in text


def test_membrane_tool_usage_doc_preserves_safety_boundary():
    text = DOC.read_text()

    required = [
        "extract only",
        "parse only",
        "validate only",
        "no metadata writing",
        "no IPFS daemon dependency",
        "no network access",
        "no wallet access",
        "no scheduler",
        "no capital movement",
    ]

    for item in required:
        assert item in text


def test_membrane_tool_usage_doc_explains_self_cid_trap():
    text = DOC.read_text()

    required = [
        "The Self-CID Trap",
        "An IPFS CID is derived from the full file contents.",
        "the image bytes change",
        "changes the CID again",
        "should not try to self-seal the image",
    ]

    for item in required:
        assert item in text


def test_membrane_tool_usage_doc_preserves_law():
    text = DOC.read_text()

    required = [
        "The image carries the acorn.",
        "The extractor reads.",
        "The validator judges.",
        "The operator remembers the self-CID trap.",
        "The artifact still does not command.",
    ]

    for item in required:
        assert item in text
