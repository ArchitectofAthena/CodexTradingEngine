"""Membrane metadata extractor.

Extracts a carrier manifest from PNG metadata and validates it without creating
execution authority.

Safety boundary:
- no IPFS daemon dependency
- no metadata writing
- no network access
- no wallet access
- no scheduler
- no capital movement
"""

from __future__ import annotations

import argparse
import json
import zlib
from pathlib import Path
from typing import Any

from eve_q.artifact_carrier import validate_artifact_carrier_manifest
from eve_q.receipt_carrier_attestation import (
    load_json,
    validate_receipt_carrier_attestation,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _read_png_chunks(image_bytes: bytes) -> list[tuple[bytes, bytes]]:
    """Read PNG chunks as ``(chunk_type, chunk_data)`` tuples."""
    if not image_bytes.startswith(PNG_SIGNATURE):
        raise ValueError("unsupported image format: expected PNG")

    chunks: list[tuple[bytes, bytes]] = []
    offset = len(PNG_SIGNATURE)

    while offset + 12 <= len(image_bytes):
        length = int.from_bytes(image_bytes[offset : offset + 4], "big")
        chunk_type = image_bytes[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4

        if crc_end > len(image_bytes):
            raise ValueError("truncated PNG chunk")

        chunk_data = image_bytes[data_start:data_end]
        chunks.append((chunk_type, chunk_data))
        offset = crc_end

        if chunk_type == b"IEND":
            break

    return chunks


def _decode_png_text_chunk(chunk_type: bytes, data: bytes) -> tuple[str, str] | None:
    """Decode PNG text metadata chunks."""
    if chunk_type == b"tEXt":
        if b"\x00" not in data:
            return None
        keyword, text = data.split(b"\x00", 1)
        return keyword.decode("latin-1"), text.decode("latin-1")

    if chunk_type == b"zTXt":
        parts = data.split(b"\x00", 1)
        if len(parts) != 2 or not parts[1]:
            return None
        keyword = parts[0].decode("latin-1")
        compression_method = parts[1][0]
        compressed_text = parts[1][1:]
        if compression_method != 0:
            return None
        return keyword, zlib.decompress(compressed_text).decode("latin-1")

    if chunk_type == b"iTXt":
        parts = data.split(b"\x00", 5)
        if len(parts) != 6:
            return None
        keyword = parts[0].decode("latin-1")
        compression_flag = parts[1]
        compression_method = parts[2]
        text = parts[5]

        if compression_flag == b"\x01":
            if compression_method != b"\x00":
                return None
            text = zlib.decompress(text)

        return keyword, text.decode("utf-8")

    return None


def extract_png_text_fields(image_path: Path | str) -> dict[str, str]:
    """Extract PNG text metadata fields."""
    image_bytes = Path(image_path).read_bytes()
    fields: dict[str, str] = {}

    for chunk_type, chunk_data in _read_png_chunks(image_bytes):
        decoded = _decode_png_text_chunk(chunk_type, chunk_data)
        if decoded is None:
            continue

        keyword, text = decoded
        fields[keyword] = text

    return fields


def extract_carrier_manifest_from_image(
    image_path: Path | str,
    field_name: str = "Comment",
) -> dict[str, Any]:
    """Extract and parse a carrier manifest JSON object from PNG metadata."""
    fields = extract_png_text_fields(image_path)

    if field_name not in fields:
        raise ValueError(f"metadata field not found: {field_name}")

    manifest = json.loads(fields[field_name])
    if not isinstance(manifest, dict):
        raise ValueError("metadata field did not contain a JSON object")

    return manifest


def validate_membrane_image(
    image_path: Path | str,
    field_name: str = "Comment",
    attestation_path: Path | str | None = None,
) -> dict[str, Any]:
    """Extract and validate an image-carried artifact carrier manifest."""
    manifest = extract_carrier_manifest_from_image(image_path, field_name)
    carrier_errors = validate_artifact_carrier_manifest(manifest)

    result: dict[str, Any] = {
        "valid": carrier_errors == [],
        "errors": carrier_errors,
        "metadata_field": field_name,
        "manifest": manifest,
    }

    if attestation_path is not None:
        attestation = load_json(attestation_path)
        attestation_errors = validate_receipt_carrier_attestation(
            attestation,
            manifest,
        )
        result["attestation"] = {
            "valid": attestation_errors == [],
            "errors": attestation_errors,
        }
        result["valid"] = result["valid"] and attestation_errors == []
        result["errors"] = carrier_errors + [
            f"attestation: {error}" for error in attestation_errors
        ]

    return result


def main(argv: list[str] | None = None) -> int:
    """Run the local membrane metadata extractor CLI."""
    parser = argparse.ArgumentParser(
        description="Extract and validate a carrier manifest from PNG metadata."
    )
    parser.add_argument("--image", required=True)
    parser.add_argument("--field", default="Comment")
    parser.add_argument("--attestation")
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Print only the extracted manifest JSON.",
    )
    args = parser.parse_args(argv)

    try:
        if args.manifest_only:
            manifest = extract_carrier_manifest_from_image(args.image, args.field)
            print(json.dumps(manifest, sort_keys=True))
            return 0

        result = validate_membrane_image(
            args.image,
            args.field,
            args.attestation,
        )
    except (OSError, ValueError, json.JSONDecodeError, zlib.error) as exc:
        result = {"valid": False, "errors": [f"failed to validate membrane: {exc}"]}

    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
