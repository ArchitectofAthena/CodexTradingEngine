import hashlib
import json
from pathlib import Path
from typing import Any

RECEIPT_SCHEMA = "eve_q.immutable_receipt.v0.1"
RECEIPT_VERSION = "0.1.0"
MOCK_CID_PREFIX = "mock-ipfs-"

COMPLETE_STATUSES = {
    "SETTLED",
    "COMPLETE",
}

FORBIDDEN_FIELDS = {
    "api_key",
    "command",
    "mnemonic",
    "password",
    "private_key",
    "scheduler",
    "secret",
    "seed_phrase",
    "shell",
    "subprocess",
    "wallet_private_key",
    "webhook_url",
}


class ReceiptSealError(RuntimeError):
    pass


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def forbidden_paths(
    value: Any,
    forbidden: set[str] = FORBIDDEN_FIELDS,
    path: str = "$",
) -> list[str]:
    found = []

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"

            if key in forbidden:
                found.append(child_path)

            found.extend(forbidden_paths(child, forbidden, child_path))

    if isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            found.extend(forbidden_paths(child, forbidden, child_path))

    return found


def validate_receipt_payload(receipt: dict[str, Any]) -> None:
    receipt_type = receipt.get("receipt_type")

    if not receipt_type:
        raise ReceiptSealError("receipt_type is required")

    forbidden = forbidden_paths(receipt)

    if forbidden:
        joined = ", ".join(forbidden)
        raise ReceiptSealError(f"forbidden receipt fields present: {joined}")


def envelope_digest(envelope: dict[str, Any]) -> str:
    digest_source = dict(envelope)
    digest_source.pop("local_sha256", None)

    return sha256_hex(canonical_json_bytes(digest_source))


def build_receipt_envelope(
    receipt: dict[str, Any],
    previous_cid: str | None = None,
) -> dict[str, Any]:
    validate_receipt_payload(receipt)

    envelope = {
        "schema": RECEIPT_SCHEMA,
        "version": RECEIPT_VERSION,
        "receipt": receipt,
        "previous_cid": previous_cid,
        "execution_authority": "none",
        "artifact_is_command": False,
        "may_execute": False,
        "may_move_capital": False,
        "human_promotion_required": True,
    }

    envelope["local_sha256"] = envelope_digest(envelope)
    return envelope


class InMemoryIpfsWriter:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.pins: set[str] = set()

    def add_and_pin(self, data: bytes) -> str:
        cid = MOCK_CID_PREFIX + sha256_hex(data)
        self.objects[cid] = data
        self.pins.add(cid)

        return cid

    def cat(self, cid: str) -> bytes:
        return self.objects[cid]

    def is_pinned(self, cid: str) -> bool:
        return cid in self.pins


class JsonlReceiptLedger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read_events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []

        events = []

        for line in self.path.read_text().splitlines():
            if line.strip():
                events.append(json.loads(line))

        return events

    def append_event(self, event: dict[str, Any]) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        events = self.read_events()
        sequence = len(events) + 1

        entry = {
            "sequence": sequence,
            **event,
        }

        with self.path.open("a") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

        return entry


def seal_receipt(
    receipt: dict[str, Any],
    previous_cid: str | None,
    ipfs: InMemoryIpfsWriter,
    ledger: JsonlReceiptLedger,
) -> dict[str, Any]:
    envelope = build_receipt_envelope(receipt, previous_cid)
    data = canonical_json_bytes(envelope)

    cid = ipfs.add_and_pin(data)

    if not ipfs.is_pinned(cid):
        raise ReceiptSealError("receipt CID was not pinned")

    resolved = ipfs.cat(cid)

    if resolved != data:
        raise ReceiptSealError("IPFS CID verification failed")

    event = ledger.append_event(
        {
            "event_type": "receipt_pinned",
            "cid": cid,
            "local_sha256": sha256_hex(data),
            "envelope_sha256": envelope["local_sha256"],
            "previous_cid": previous_cid,
            "receipt_type": receipt["receipt_type"],
            "execution_authority": "none",
            "artifact_is_command": False,
            "may_execute": False,
            "may_move_capital": False,
        }
    )

    return {
        "status": "IPFS_PINNED_VERIFIED",
        "cid": cid,
        "local_sha256": sha256_hex(data),
        "envelope_sha256": envelope["local_sha256"],
        "envelope": envelope,
        "ledger_event": event,
    }


def require_receipt_cid_for_completion(
    action_kind: str,
    target_status: str,
    receipt_cid: str | None,
) -> bool:
    if target_status in COMPLETE_STATUSES and not receipt_cid:
        raise ReceiptSealError(
            f"{action_kind} cannot reach {target_status} " "without verified receipt CID"
        )

    return True


def mark_action_complete(
    action_kind: str,
    receipt_cid: str | None,
    target_status: str = "COMPLETE",
) -> dict[str, str]:
    require_receipt_cid_for_completion(
        action_kind,
        target_status,
        receipt_cid,
    )

    return {
        "action_kind": action_kind,
        "status": target_status,
        "receipt_cid": str(receipt_cid),
    }
