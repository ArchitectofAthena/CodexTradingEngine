from pathlib import Path

README = Path("README.md")


def test_readme_names_current_constitutional_surfaces():
    text = README.read_text()

    required = [
        "Constitutional Surfaces Index",
        "eve_q/artifact_carrier.py",
        "examples/artifact_carrier_manifest.example.json",
        "docs/artifact_carrier_manifest_example.md",
        "eve_q/receipt_carrier_attestation.py",
        "examples/receipt_carrier_attestation.example.json",
        "docs/receipt_carrier_attestation_example.md",
        "eve_q/membrane_tool.py",
    ]

    for item in required:
        assert item in text


def test_readme_preserves_non_execution_boundary():
    text = README.read_text()

    required = [
        "no autonomous capital movement",
        "no wallet signing",
        "no scheduler authority",
        "no reverse execution channel",
        "no metadata writing",
        "Human promotes.",
        "Image carries acorn.",
    ]

    for item in required:
        assert item in text
