import argparse
import json
from pathlib import Path
from typing import Any

from eve_q.immutable_receipts import (
    JsonlReceiptLedger,
    canonical_json_bytes,
    sha256_hex,
)
from eve_q.receipt_ledger_audit import audit_receipt_ledger

MERKLE_SCHEMA = "eve_q.receipt_merkle_audit.v0.1"
MERKLE_VERSION = "0.1.0"


def event_leaf_hash(event: dict[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(event))


def merkle_parent(left_hash: str, right_hash: str) -> str:
    combined = bytes.fromhex(left_hash) + bytes.fromhex(right_hash)
    return sha256_hex(combined)


def merkle_root(leaf_hashes: list[str]) -> str | None:
    if not leaf_hashes:
        return None

    level = list(leaf_hashes)

    while len(level) > 1:
        next_level = []

        for index in range(0, len(level), 2):
            left = level[index]
            right = level[index + 1] if index + 1 < len(level) else left
            next_level.append(merkle_parent(left, right))

        level = next_level

    return level[0]


def build_receipt_merkle_audit(
    ledger_path: Path,
    period: str | None = None,
) -> dict[str, Any]:
    ledger = JsonlReceiptLedger(ledger_path)
    events = ledger.read_events()
    ledger_audit = audit_receipt_ledger(ledger_path)

    leaves = [
        {
            "sequence": event.get("sequence"),
            "cid": event.get("cid"),
            "leaf_sha256": event_leaf_hash(event),
        }
        for event in events
    ]

    root = merkle_root([leaf["leaf_sha256"] for leaf in leaves])
    errors = []

    if not events:
        errors.append(
            {
                "error": "empty_ledger",
            }
        )

    if not ledger_audit["valid"]:
        errors.append(
            {
                "error": "ledger_audit_invalid",
            }
        )

    return {
        "schema": MERKLE_SCHEMA,
        "version": MERKLE_VERSION,
        "period": period,
        "ledger_path": str(ledger_path),
        "event_count": len(events),
        "ledger_valid": ledger_audit["valid"],
        "valid": not errors,
        "errors": errors,
        "merkle_root": root,
        "latest_cid": ledger_audit["latest_cid"],
        "leaves": leaves,
        "ledger_audit": ledger_audit,
        "execution_authority": "none",
        "artifact_is_command": False,
        "may_execute": False,
        "may_move_capital": False,
        "boundary_law": [
            "No receipt CID, no completion.",
            "No pin verification, no completion.",
            "No receipt chain, no next action.",
            "The Merkle root compresses continuity.",
            "The artifact records.",
            "The human promotes.",
            "The chain remembers.",
        ],
    }


def write_merkle_audit(packet: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Merkle audit root for a receipt ledger.")
    parser.add_argument(
        "--ledger",
        required=True,
        help="Path to append-only receipt ledger JSONL file.",
    )
    parser.add_argument(
        "--period",
        default=None,
        help="Optional period label, such as 2026-07-08.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional JSON output path for the Merkle audit packet.",
    )

    args = parser.parse_args()

    packet = build_receipt_merkle_audit(
        Path(args.ledger),
        period=args.period,
    )

    if args.output:
        write_merkle_audit(packet, Path(args.output))

    print(json.dumps(packet, sort_keys=True))
    return 0 if packet["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
