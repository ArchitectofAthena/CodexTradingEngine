from pathlib import Path

README = Path("README.md")


def test_readme_names_current_constitutional_surfaces():
    text = README.read_text(encoding="utf-8")

    required = [
        "## Current Surface Index",
        "contracts/organ_contract.json",
        "eve_q/artifact_carrier.py",
        "eve_q/receipt_carrier_attestation.py",
        "eve_q/membrane_tool.py",
        "Carrier validator",
        "Membrane tool",
    ]

    for item in required:
        assert item in text


def test_readme_preserves_non_execution_boundary():
    text = README.read_text(encoding="utf-8")

    required = [
        "autonomous capital movement",
        "wallet or transaction signing",
        "scheduler- or webhook-triggered execution",
        "reverse execution channel",
        "without writing metadata",
        "Human promotes.",
        "The image carries the acorn.",
        "The artifact never commands.",
        "receipt attestation",
        "human promotion",
    ]

    for item in required:
        assert item in text
