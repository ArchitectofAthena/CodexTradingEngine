import argparse
import json
from pathlib import Path
from typing import Any

from eve_q.immutable_receipts import (
    JsonlReceiptLedger,
    ReceiptSealError,
    canonical_json_bytes,
    seal_receipt,
    sha256_hex,
)
from eve_q.ipfs_adapters import DEFAULT_KUBO_API_URL
from eve_q.receipt_merkle_audit import build_receipt_merkle_audit
from eve_q.receipt_sealer import (
    BACKEND_MOCK,
    BACKENDS,
    build_ipfs_writer,
)

ANCHOR_RECEIPT_TYPE = "ReceiptMerkleAnchorReceipt"
ANCHOR_RECEIPT_VERSION = "0.1.0"


def merkle_packet_digest(packet: dict[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(packet))


def build_merkle_anchor_receipt(
    merkle_packet: dict[str, Any],
) -> dict[str, Any]:
    if not merkle_packet.get("valid"):
        raise ReceiptSealError("cannot anchor invalid Merkle audit packet")

    merkle_root = merkle_packet.get("merkle_root")

    if not merkle_root:
        raise ReceiptSealError("cannot anchor Merkle audit packet without root")

    return {
        "receipt_type": ANCHOR_RECEIPT_TYPE,
        "receipt_version": ANCHOR_RECEIPT_VERSION,
        "period": merkle_packet.get("period"),
        "source_ledger_path": merkle_packet.get("ledger_path"),
        "event_count": merkle_packet.get("event_count"),
        "ledger_valid": merkle_packet.get("ledger_valid"),
        "latest_cid": merkle_packet.get("latest_cid"),
        "merkle_root": merkle_root,
        "merkle_packet_schema": merkle_packet.get("schema"),
        "merkle_packet_sha256": merkle_packet_digest(merkle_packet),
        "anchor_scope": "audit_root_only",
        "execution_authority": "none",
        "artifact_is_command": False,
        "may_execute": False,
        "may_move_capital": False,
    }


def seal_merkle_anchor(
    source_ledger_path: Path,
    anchor_ledger_path: Path,
    backend: str = BACKEND_MOCK,
    period: str | None = None,
    previous_anchor_cid: str | None = None,
    kubo_api_url: str = DEFAULT_KUBO_API_URL,
) -> dict[str, Any]:
    merkle_packet = build_receipt_merkle_audit(
        source_ledger_path,
        period=period,
    )
    anchor_receipt = build_merkle_anchor_receipt(merkle_packet)
    ipfs = build_ipfs_writer(backend, kubo_api_url)
    anchor_ledger = JsonlReceiptLedger(anchor_ledger_path)

    seal_result = seal_receipt(
        receipt=anchor_receipt,
        previous_cid=previous_anchor_cid,
        ipfs=ipfs,
        ledger=anchor_ledger,
    )

    return {
        "backend": backend,
        "source_ledger_path": str(source_ledger_path),
        "anchor_ledger_path": str(anchor_ledger_path),
        "merkle_packet": merkle_packet,
        "anchor_receipt": anchor_receipt,
        "result": seal_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seal a Merkle audit root as an anchor receipt.")
    parser.add_argument(
        "--ledger",
        required=True,
        help="Source receipt ledger JSONL file.",
    )
    parser.add_argument(
        "--anchor-ledger",
        required=True,
        help="Separate append-only anchor ledger JSONL file.",
    )
    parser.add_argument(
        "--backend",
        default=BACKEND_MOCK,
        choices=sorted(BACKENDS),
        help="Receipt sealing backend.",
    )
    parser.add_argument(
        "--period",
        default=None,
        help="Optional period label, such as 2026-07-08.",
    )
    parser.add_argument(
        "--previous-anchor-cid",
        default=None,
        help="Previous Merkle anchor CID for anchor chaining.",
    )
    parser.add_argument(
        "--kubo-api-url",
        default=DEFAULT_KUBO_API_URL,
        help="Local Kubo API URL for kubo backend.",
    )

    args = parser.parse_args()

    try:
        anchored = seal_merkle_anchor(
            source_ledger_path=Path(args.ledger),
            anchor_ledger_path=Path(args.anchor_ledger),
            backend=args.backend,
            period=args.period,
            previous_anchor_cid=args.previous_anchor_cid,
            kubo_api_url=args.kubo_api_url,
        )
    except (ReceiptSealError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                **anchored,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
