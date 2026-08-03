import argparse
import json
from pathlib import Path
from typing import Any

from eve_q.immutable_receipts import (
    InMemoryIpfsWriter,
    JsonlReceiptLedger,
    ReceiptSealError,
    seal_receipt,
)
from eve_q.ipfs_adapters import (
    DEFAULT_KUBO_API_URL,
    DEFAULT_MAX_ADD_BYTES,
    DEFAULT_MAX_RESPONSE_BYTES,
    KuboHttpIpfsWriter,
)

BACKEND_MOCK = "mock"
BACKEND_KUBO = "kubo"
BACKENDS = {BACKEND_MOCK, BACKEND_KUBO}


def load_receipt(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def build_ipfs_writer(
    backend: str,
    kubo_api_url: str = DEFAULT_KUBO_API_URL,
    *,
    kubo_timeout_seconds: float = 10.0,
    kubo_max_add_bytes: int = DEFAULT_MAX_ADD_BYTES,
    kubo_max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    allow_remote_kubo: bool = False,
):
    if backend == BACKEND_MOCK:
        return InMemoryIpfsWriter()

    if backend == BACKEND_KUBO:
        return KuboHttpIpfsWriter(
            api_url=kubo_api_url,
            timeout_seconds=kubo_timeout_seconds,
            max_add_bytes=kubo_max_add_bytes,
            max_response_bytes=kubo_max_response_bytes,
            allow_remote=allow_remote_kubo,
        )

    raise ValueError(f"unknown receipt backend: {backend}")


def seal_receipt_file(
    receipt_path: Path,
    ledger_path: Path,
    backend: str = BACKEND_MOCK,
    previous_cid: str | None = None,
    kubo_api_url: str = DEFAULT_KUBO_API_URL,
    *,
    kubo_timeout_seconds: float = 10.0,
    kubo_max_add_bytes: int = DEFAULT_MAX_ADD_BYTES,
    kubo_max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    allow_remote_kubo: bool = False,
) -> dict[str, Any]:
    receipt = load_receipt(receipt_path)
    ipfs = build_ipfs_writer(
        backend,
        kubo_api_url,
        kubo_timeout_seconds=kubo_timeout_seconds,
        kubo_max_add_bytes=kubo_max_add_bytes,
        kubo_max_response_bytes=kubo_max_response_bytes,
        allow_remote_kubo=allow_remote_kubo,
    )
    ledger = JsonlReceiptLedger(ledger_path)

    result = seal_receipt(
        receipt=receipt,
        previous_cid=previous_cid,
        ipfs=ipfs,
        ledger=ledger,
    )

    return {
        "backend": backend,
        "receipt_path": str(receipt_path),
        "ledger_path": str(ledger_path),
        "result": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seal a trade or charity receipt artifact."
    )
    parser.add_argument(
        "--receipt",
        required=True,
        help="Path to receipt JSON file.",
    )
    parser.add_argument(
        "--ledger",
        required=True,
        help="Path to append-only receipt ledger JSONL file.",
    )
    parser.add_argument(
        "--backend",
        default=BACKEND_MOCK,
        choices=sorted(BACKENDS),
        help="Receipt sealing backend.",
    )
    parser.add_argument(
        "--previous-cid",
        default=None,
        help="Previous receipt CID for receipt chaining.",
    )
    parser.add_argument(
        "--kubo-api-url",
        default=DEFAULT_KUBO_API_URL,
        help="Kubo API URL. Loopback-only unless --allow-remote-kubo is explicit.",
    )
    parser.add_argument(
        "--kubo-timeout-seconds",
        type=float,
        default=10.0,
        help="Per-request Kubo timeout.",
    )
    parser.add_argument(
        "--kubo-max-add-bytes",
        type=int,
        default=DEFAULT_MAX_ADD_BYTES,
        help="Maximum receipt envelope bytes submitted to Kubo.",
    )
    parser.add_argument(
        "--kubo-max-response-bytes",
        type=int,
        default=DEFAULT_MAX_RESPONSE_BYTES,
        help="Maximum bytes accepted from Kubo cat responses.",
    )
    parser.add_argument(
        "--allow-remote-kubo",
        action="store_true",
        help="Explicitly permit a non-loopback Kubo API URL.",
    )

    args = parser.parse_args()

    try:
        sealed = seal_receipt_file(
            receipt_path=Path(args.receipt),
            ledger_path=Path(args.ledger),
            backend=args.backend,
            previous_cid=args.previous_cid,
            kubo_api_url=args.kubo_api_url,
            kubo_timeout_seconds=args.kubo_timeout_seconds,
            kubo_max_add_bytes=args.kubo_max_add_bytes,
            kubo_max_response_bytes=args.kubo_max_response_bytes,
            allow_remote_kubo=args.allow_remote_kubo,
        )
    except (ReceiptSealError, ValueError, OSError, RuntimeError) as exc:
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
                **sealed,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
