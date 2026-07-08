import argparse
import json
from pathlib import Path
from typing import Any

from eve_q.immutable_receipts import JsonlReceiptLedger

AUDIT_SCHEMA = "eve_q.receipt_ledger_audit.v0.1"
AUDIT_VERSION = "0.1.0"


def audit_receipt_ledger(ledger_path: Path) -> dict[str, Any]:
    ledger = JsonlReceiptLedger(ledger_path)
    events = ledger.read_events()
    errors = []

    expected_previous_cid = None

    for index, event in enumerate(events, start=1):
        if event.get("sequence") != index:
            errors.append(
                {
                    "sequence": event.get("sequence"),
                    "error": "sequence_gap_or_mismatch",
                    "expected_sequence": index,
                }
            )

        cid = event.get("cid")
        if not cid:
            errors.append(
                {
                    "sequence": event.get("sequence"),
                    "error": "missing_cid",
                }
            )

        if not event.get("local_sha256"):
            errors.append(
                {
                    "sequence": event.get("sequence"),
                    "error": "missing_local_sha256",
                }
            )

        if event.get("execution_authority") != "none":
            errors.append(
                {
                    "sequence": event.get("sequence"),
                    "error": "execution_authority_not_none",
                }
            )

        if event.get("artifact_is_command") is not False:
            errors.append(
                {
                    "sequence": event.get("sequence"),
                    "error": "artifact_is_command_not_false",
                }
            )

        if event.get("may_execute") is not False:
            errors.append(
                {
                    "sequence": event.get("sequence"),
                    "error": "may_execute_not_false",
                }
            )

        if event.get("may_move_capital") is not False:
            errors.append(
                {
                    "sequence": event.get("sequence"),
                    "error": "may_move_capital_not_false",
                }
            )

        actual_previous_cid = event.get("previous_cid")

        if actual_previous_cid != expected_previous_cid:
            errors.append(
                {
                    "sequence": event.get("sequence"),
                    "error": "previous_cid_chain_mismatch",
                    "expected_previous_cid": expected_previous_cid,
                    "actual_previous_cid": actual_previous_cid,
                }
            )

        expected_previous_cid = cid

    receipt_events = [
        {
            "sequence": event.get("sequence"),
            "cid": event.get("cid"),
            "receipt_type": event.get("receipt_type"),
            "previous_cid": event.get("previous_cid"),
        }
        for event in events
    ]
    receipt_cids = [event["cid"] for event in receipt_events if event.get("cid")]

    return {
        "schema": AUDIT_SCHEMA,
        "version": AUDIT_VERSION,
        "ledger_path": str(ledger_path),
        "event_count": len(events),
        "valid": not errors,
        "errors": errors,
        "receipt_cids": receipt_cids,
        "receipt_events": receipt_events,
        "latest_cid": expected_previous_cid,
        "execution_authority": "none",
        "artifact_is_command": False,
        "may_execute": False,
        "may_move_capital": False,
        "boundary_law": [
            "No receipt CID, no completion.",
            "No pin verification, no completion.",
            "No receipt chain, no next action.",
            "The audit observes.",
            "The artifact records.",
            "The human promotes.",
            "The chain remembers.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit an append-only receipt ledger.")
    parser.add_argument(
        "--ledger",
        required=True,
        help="Path to append-only receipt ledger JSONL file.",
    )

    args = parser.parse_args()
    audit = audit_receipt_ledger(Path(args.ledger))

    print(json.dumps(audit, sort_keys=True))
    return 0 if audit["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
