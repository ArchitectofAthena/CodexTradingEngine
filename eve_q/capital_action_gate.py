import argparse
import json
from pathlib import Path
from typing import Any

GATE_SCHEMA = "eve_q.capital_action_completion_gate.v0.1"
GATE_VERSION = "0.1.0"

ACTION_TRADE = "trade"
ACTION_CHARITY_TX = "charity_tx"

CAPITAL_ACTION_KINDS = {
    ACTION_TRADE,
    ACTION_CHARITY_TX,
}

COMPLETE_STATUSES = {
    "SETTLED",
    "COMPLETE",
}


class CapitalActionGateError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def validate_ledger_audit(
    ledger_audit: dict[str, Any],
    receipt_cid: str,
) -> None:
    if ledger_audit.get("valid") is not True:
        raise CapitalActionGateError("cannot complete capital action with invalid ledger audit")

    receipt_cids = ledger_audit.get("receipt_cids")

    if not isinstance(receipt_cids, list):
        raise CapitalActionGateError("ledger audit must include receipt CID membership list")

    if receipt_cid not in receipt_cids:
        raise CapitalActionGateError("receipt CID must be present in audited ledger")

    if ledger_audit.get("execution_authority") != "none":
        raise CapitalActionGateError("ledger audit execution authority must be none")

    if ledger_audit.get("artifact_is_command") is not False:
        raise CapitalActionGateError("ledger audit artifact_is_command must be false")

    if ledger_audit.get("may_execute") is not False:
        raise CapitalActionGateError("ledger audit may_execute must be false")

    if ledger_audit.get("may_move_capital") is not False:
        raise CapitalActionGateError("ledger audit may_move_capital must be false")


def build_completion_certificate(
    action_kind: str,
    target_status: str,
    receipt_cid: str | None,
    ledger_audit: dict[str, Any],
    source_receipt_cid: str | None = None,
    merkle_anchor_cid: str | None = None,
    require_merkle_anchor: bool = False,
) -> dict[str, Any]:
    if action_kind not in CAPITAL_ACTION_KINDS:
        raise CapitalActionGateError(f"unsupported capital action kind: {action_kind}")

    if target_status not in COMPLETE_STATUSES:
        raise CapitalActionGateError(f"unsupported completion status: {target_status}")

    if not receipt_cid:
        raise CapitalActionGateError("capital action cannot complete without receipt CID")

    if action_kind == ACTION_CHARITY_TX and not source_receipt_cid:
        raise CapitalActionGateError("charity transaction requires source trade receipt CID")

    if require_merkle_anchor and not merkle_anchor_cid:
        raise CapitalActionGateError("Merkle anchor CID is required before completion")

    validate_ledger_audit(ledger_audit, receipt_cid)

    return {
        "schema": GATE_SCHEMA,
        "version": GATE_VERSION,
        "action_kind": action_kind,
        "target_status": target_status,
        "completion_status": "ACCOUNTED",
        "receipt_cid": receipt_cid,
        "source_receipt_cid": source_receipt_cid,
        "ledger_path": ledger_audit.get("ledger_path"),
        "ledger_event_count": ledger_audit.get("event_count"),
        "ledger_latest_cid": ledger_audit.get("latest_cid"),
        "merkle_anchor_required": require_merkle_anchor,
        "merkle_anchor_cid": merkle_anchor_cid,
        "execution_authority": "none",
        "artifact_is_command": False,
        "may_execute": False,
        "may_move_capital": False,
        "human_promotion_required": True,
        "boundary_law": [
            "No receipt CID, no completion.",
            "No valid ledger audit, no completion.",
            "No charity completion without source trade receipt.",
            "No required Merkle anchor, no completion.",
            "The completion gate accounts.",
            "The artifact records.",
            "The human promotes.",
            "The chain remembers.",
        ],
    }


def write_completion_certificate(
    certificate: dict[str, Any],
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(certificate, indent=2, sort_keys=True) + "\n")

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate trade or charity completion by receipt audit."
    )
    parser.add_argument(
        "--action-kind",
        required=True,
        choices=sorted(CAPITAL_ACTION_KINDS),
    )
    parser.add_argument(
        "--target-status",
        required=True,
        choices=sorted(COMPLETE_STATUSES),
    )
    parser.add_argument(
        "--receipt-cid",
        required=True,
    )
    parser.add_argument(
        "--ledger-audit",
        required=True,
        help="Path to receipt ledger audit JSON packet.",
    )
    parser.add_argument(
        "--source-receipt-cid",
        default=None,
        help="Required for charity_tx completion.",
    )
    parser.add_argument(
        "--merkle-anchor-cid",
        default=None,
    )
    parser.add_argument(
        "--require-merkle-anchor",
        action="store_true",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional JSON output path.",
    )

    args = parser.parse_args()

    try:
        certificate = build_completion_certificate(
            action_kind=args.action_kind,
            target_status=args.target_status,
            receipt_cid=args.receipt_cid,
            ledger_audit=load_json(Path(args.ledger_audit)),
            source_receipt_cid=args.source_receipt_cid,
            merkle_anchor_cid=args.merkle_anchor_cid,
            require_merkle_anchor=args.require_merkle_anchor,
        )
    except CapitalActionGateError as exc:
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

    if args.output:
        write_completion_certificate(certificate, Path(args.output))

    print(
        json.dumps(
            {
                "ok": True,
                "certificate": certificate,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
