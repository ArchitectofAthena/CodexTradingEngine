import json
import subprocess
import sys
import zlib
from pathlib import Path

from eve_q.membrane_tool import (
    extract_carrier_manifest_from_image,
    validate_membrane_image,
)

MANIFEST_PATH = Path("examples/artifact_carrier_manifest.example.json")


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


def run_cli(image_path, *extra_args):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.membrane_tool",
            "--image",
            str(image_path),
            *extra_args,
        ],
        capture_output=True,
        check=False,
        text=True,
    )


def test_extract_carrier_manifest_from_png_comment(tmp_path):
    manifest = json.loads(MANIFEST_PATH.read_text())
    image = tmp_path / "membrane.png"
    write_png_with_comment(image, json.dumps(manifest))

    extracted = extract_carrier_manifest_from_image(image)

    assert extracted == manifest


def test_validate_membrane_image_accepts_valid_manifest(tmp_path):
    manifest = json.loads(MANIFEST_PATH.read_text())
    image = tmp_path / "membrane.png"
    write_png_with_comment(image, json.dumps(manifest))

    result = validate_membrane_image(image)

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["metadata_field"] == "Comment"
    assert result["manifest"] == manifest


def test_membrane_tool_cli_validates_png_comment_manifest(tmp_path):
    manifest = json.loads(MANIFEST_PATH.read_text())
    image = tmp_path / "membrane.png"
    write_png_with_comment(image, json.dumps(manifest))

    result = run_cli(image)
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["valid"] is True
    assert payload["errors"] == []
    assert payload["manifest"] == manifest
    assert result.stderr == ""


def test_membrane_tool_cli_manifest_only(tmp_path):
    manifest = json.loads(MANIFEST_PATH.read_text())
    image = tmp_path / "membrane.png"
    write_png_with_comment(image, json.dumps(manifest))

    result = run_cli(image, "--manifest-only")

    assert result.returncode == 0
    assert json.loads(result.stdout) == manifest


def test_membrane_tool_cli_rejects_invalid_manifest(tmp_path):
    manifest = json.loads(MANIFEST_PATH.read_text())
    manifest["execution_authority"] = "scheduler"

    image = tmp_path / "membrane.png"
    write_png_with_comment(image, json.dumps(manifest))

    result = run_cli(image)
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["valid"] is False
    assert any("execution_authority must be none" in error for error in payload["errors"])


def test_membrane_tool_cli_reports_missing_comment(tmp_path):
    image = tmp_path / "membrane.png"
    write_png_with_comment(image, "{}")

    result = run_cli(image, "--field", "Missing")
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["valid"] is False
    assert payload["errors"][0].startswith("failed to extract manifest:")
