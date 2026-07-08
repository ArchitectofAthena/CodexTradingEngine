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
):
    if backend == BACKEND_MOCK:
        return InMemoryIpfsWriter()

    if backend == BACKEND_KUBO:
        return KuboHttpIpfsWriter(api_url=kubo_api_url)

    raise ValueError(f"unknown receipt backend: {backend}")


def seal_receipt_file(
    receipt_path: Path,
    ledger_path: Path,
    backend: str = BACKEND_MOCK,
    previous_cid: str | None = None,
    kubo_api_url: str = DEFAULT_KUBO_API_URL,
) -> dict[str, Any]:
    receipt = load_receipt(receipt_path)
    ipfs = build_ipfs_writer(backend, kubo_api_url)
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
    parser = argparse.ArgumentParser(description="Seal a trade or charity receipt artifact.")
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
        help="Local Kubo API URL for kubo backend.",
    )

    args = parser.parse_args()

    try:
        sealed = seal_receipt_file(
            receipt_path=Path(args.receipt),
            ledger_path=Path(args.ledger),
            backend=args.backend,
            previous_cid=args.previous_cid,
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
                **sealed,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
