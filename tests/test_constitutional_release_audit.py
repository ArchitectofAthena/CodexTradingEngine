import json
import subprocess
import sys
import zlib
from pathlib import Path

DOC = Path("docs/constitutional_release_audit.md")
README = Path("README.md")
CHECKPOINT = Path("docs/constitutional_membrane_checkpoint.md")
CARRIER = Path("examples/artifact_carrier_manifest.example.json")
ATTESTATION = Path("examples/receipt_carrier_attestation.example.json")

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_chunk(chunk_type, data):
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return len(data).to_bytes(4, "big") + chunk_type + data + crc.to_bytes(4, "big")


def write_png_with_comment(path, comment):
    ihdr = (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, 2, 0, 0, 0])
    text = b"Comment\x00" + comment.encode("latin-1")
    path.write_bytes(
        PNG_SIGNATURE
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"tEXt", text)
        + png_chunk(b"IEND", b"")
    )


def run_command(args):
    return subprocess.run(
        [sys.executable, "-m", *args],
        capture_output=True,
        check=False,
        text=True,
    )


def test_release_audit_doc_names_current_surfaces():
    text = DOC.read_text()

    required = [
        "eve_q/artifact_carrier.py",
        "examples/artifact_carrier_manifest.example.json",
        "eve_q/receipt_carrier_attestation.py",
        "examples/receipt_carrier_attestation.example.json",
        "eve_q/membrane_tool.py",
        "docs/membrane_tool_usage.md",
        "docs/constitutional_membrane_checkpoint.md",
        "README.md",
    ]

    for item in required:
        assert item in text


def test_release_audit_preserves_boundary_language():
    text = "\n".join(
        [
            DOC.read_text(),
            README.read_text(),
            CHECKPOINT.read_text(),
        ]
    )

    required = [
        "no autonomous capital movement",
        "no wallet signing",
        "no scheduler authority",
        "no reverse execution channel",
        "no metadata writing",
        "no IPFS daemon dependency",
        "no network access",
        "no command execution from metadata",
    ]

    for item in required:
        assert item in text


def test_release_examples_preserve_non_authority_flags():
    carrier = json.loads(CARRIER.read_text())
    attestation = json.loads(ATTESTATION.read_text())

    for artifact in [carrier, attestation]:
        assert artifact["execution_authority"] == "none"
        assert artifact["human_promotion_required"] is True
        assert artifact["reverse_execution_channel_opened"] is False
        assert artifact["ttl_mode"] == "artifact_only"


def test_release_artifact_carrier_cli_smoke():
    result = run_command(
        [
            "eve_q.artifact_carrier",
            "--manifest",
            str(CARRIER),
        ]
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"errors": [], "valid": True}
    assert result.stderr == ""


def test_release_receipt_attestation_cli_smoke():
    result = run_command(
        [
            "eve_q.receipt_carrier_attestation",
            "--carrier",
            str(CARRIER),
            "--attestation",
            str(ATTESTATION),
        ]
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"errors": [], "valid": True}
    assert result.stderr == ""


def test_release_membrane_bridge_cli_smoke(tmp_path):
    carrier = json.loads(CARRIER.read_text())
    image = tmp_path / "membrane.png"
    write_png_with_comment(image, json.dumps(carrier))

    result = run_command(
        [
            "eve_q.membrane_tool",
            "--image",
            str(image),
            "--attestation",
            str(ATTESTATION),
        ]
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["valid"] is True
    assert payload["errors"] == []
    assert payload["attestation"] == {"errors": [], "valid": True}
    assert result.stderr == ""


def test_release_audit_preserves_self_cid_trap():
    text = DOC.read_text()

    required = [
        "Self-CID Trap",
        "An image cannot safely contain its own final CID",
        "Embedding the CID changes the image bytes",
        "changes the CID again",
        "image metadata -> carrier manifest",
    ]

    for item in required:
        assert item in text


def test_release_audit_preserves_law():
    text = DOC.read_text()

    required = [
        "The validators answer.",
        "The CLIs report.",
        "The docs remember.",
        "The release audit seals the membrane.",
        "The artifact still does not command.",
    ]

    for item in required:
        assert item in text
