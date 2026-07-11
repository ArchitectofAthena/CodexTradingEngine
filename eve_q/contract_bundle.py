from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from eve_q.immutable_receipts import (
    InMemoryIpfsWriter,
    JsonlReceiptLedger,
    ReceiptSealError,
    canonical_json_bytes,
    seal_receipt,
)
from eve_q.ipfs_adapters import DEFAULT_KUBO_API_URL, KuboHttpIpfsWriter


CONTRACT_VERSION = "eve_q_cross_repo_v0.1"
RECEIPT_TYPE = "eve_q.cross_repo_contract_bundle.v0.1"
SCHEMA_FILENAMES = (
    "proposal_artifact_v0_1.schema.json",
    "evidence_bundle_v0_1.schema.json",
    "gate_decision_v0_1.schema.json",
    "human_promotion_receipt_v0_1.schema.json",
    "registry_entry_v0_1.schema.json",
    "execution_receipt_v0_1.schema.json",
)


class ContractBundleError(RuntimeError):
    pass


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_schema_record(schema_root: Path, filename: str) -> dict[str, Any]:
    path = schema_root / filename
    if not path.is_file():
        raise ContractBundleError(f"missing contract schema: {path}")

    raw = path.read_bytes()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractBundleError(f"invalid UTF-8 JSON schema: {path}") from exc

    if not isinstance(document, dict):
        raise ContractBundleError(f"schema must be a JSON object: {path}")

    return {
        "path": f"schemas/{filename}",
        "file_sha256": sha256_hex(raw),
        "canonical_json_sha256": sha256_hex(canonical_json_bytes(document)),
        "document": document,
    }


def build_contract_bundle_receipt(
    schema_root: Path,
    producer_commit: str,
    control_plane_commit: str,
    previous_cid: str | None = None,
) -> dict[str, Any]:
    if len(producer_commit) != 40:
        raise ContractBundleError("producer_commit must be a 40-character commit SHA")
    if len(control_plane_commit) != 40:
        raise ContractBundleError("control_plane_commit must be a 40-character commit SHA")

    schemas = [load_schema_record(schema_root, name) for name in SCHEMA_FILENAMES]

    return {
        "receipt_type": RECEIPT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "producer_repository": "ArchitectofAthena/CodexTradingEngine",
        "producer_commit": producer_commit,
        "control_plane_repository": "ArchitectofAthena/spiralbloom-os",
        "control_plane_commit": control_plane_commit,
        "contract_issue": "ArchitectofAthena/spiralbloom-os#102",
        "control_plane_pr": "ArchitectofAthena/spiralbloom-os#103",
        "canonical_serialization": "utf8-json-sorted-keys-compact-separators",
        "schema_count": len(schemas),
        "schemas": schemas,
        "previous_contract_bundle_cid": previous_cid,
        "artifact_is_command": False,
        "authority": False,
        "execution_authority": "none",
        "may_execute": False,
        "may_move_capital": False,
        "human_promotion_required": True,
    }


def pin_contract_bundle(
    schema_root: Path,
    ledger_path: Path,
    producer_commit: str,
    control_plane_commit: str,
    backend: str = "mock",
    previous_cid: str | None = None,
    kubo_api_url: str = DEFAULT_KUBO_API_URL,
) -> dict[str, Any]:
    receipt = build_contract_bundle_receipt(
        schema_root=schema_root,
        producer_commit=producer_commit,
        control_plane_commit=control_plane_commit,
        previous_cid=previous_cid,
    )

    if backend == "mock":
        writer = InMemoryIpfsWriter()
    elif backend == "kubo":
        writer = KuboHttpIpfsWriter(api_url=kubo_api_url)
    else:
        raise ContractBundleError(f"unsupported backend: {backend}")

    result = seal_receipt(
        receipt=receipt,
        previous_cid=previous_cid,
        ipfs=writer,
        ledger=JsonlReceiptLedger(ledger_path),
    )

    return {
        "ok": True,
        "backend": backend,
        "contract_version": CONTRACT_VERSION,
        "schema_count": len(SCHEMA_FILENAMES),
        "ledger_path": str(ledger_path),
        "result": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build, pin, verify, and ledger the EVE_Q++ cross-repository contract bundle."
    )
    parser.add_argument("--schema-root", default="schemas", type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--producer-commit", required=True)
    parser.add_argument("--control-plane-commit", required=True)
    parser.add_argument("--previous-cid", default=None)
    parser.add_argument("--backend", choices=("mock", "kubo"), default="mock")
    parser.add_argument("--kubo-api-url", default=DEFAULT_KUBO_API_URL)
    args = parser.parse_args()

    try:
        result = pin_contract_bundle(
            schema_root=args.schema_root,
            ledger_path=args.ledger,
            producer_commit=args.producer_commit,
            control_plane_commit=args.control_plane_commit,
            backend=args.backend,
            previous_cid=args.previous_cid,
            kubo_api_url=args.kubo_api_url,
        )
    except (ContractBundleError, ReceiptSealError, OSError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
