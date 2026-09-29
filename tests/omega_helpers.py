"""Offline fixtures shared by Omega perception tests; no network or capital hooks."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from omega_telemetry.db import TelemetryDB
from omega_telemetry.models import Event, PricePoint
from omega_telemetry.sentiment_tracker import SentimentTracker
from omega_telemetry.whale_watcher import TRANSFER_TOPIC, WhaleWatcher

ADDRESS_A = "0x" + "a" * 40
ADDRESS_B = "0x" + "b" * 40
CONTRACT = "0x" + "c" * 40
TX_HASH = "0x" + "d" * 64


class Response:
    def __init__(self, payload: Any = None, status: int = 200, text: str = "ok") -> None:
        self.payload = payload
        self.status = status
        self.body = text
        self.headers: dict[str, str] = {}

    async def __aenter__(self) -> Response:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise ValueError("HTTP error")

    async def json(self, **kwargs: Any) -> Any:
        if "loads" in kwargs:
            return kwargs["loads"](json.dumps(self.payload))
        return self.payload

    async def text(self) -> str:
        return self.body


def session_for(*responses: Response) -> MagicMock:
    session = MagicMock()
    session.get.side_effect = list(responses)
    session.post.side_effect = list(responses)
    return session


def database(tmp_path: Path) -> TelemetryDB:
    return TelemetryDB(str(tmp_path / "telemetry.sqlite"))


def tracker(tmp_path: Path, **config: Any) -> SentimentTracker:
    rules = tmp_path / "rules.json"
    rules.write_text(
        json.dumps(
            {
                "rules": [
                    {"name": "surge", "weight": 4, "patterns": ["surge"]},
                ]
            }
        )
    )
    return SentimentTracker(MagicMock(), database(tmp_path), {"sources": [], **config}, rules)


def post(identity: str = "one", **overrides: Any) -> dict[str, Any]:
    return {
        "id": identity,
        "title": "$ETH surge",
        "author": "author-one",
        "published_at": datetime.now(UTC).isoformat(),
        **overrides,
    }


class StaticPrice:
    def __init__(self, usd: str = "1", observed_at: str | None = None) -> None:
        self.usd = Decimal(usd)
        self.observed_at = observed_at

    async def get_usd_price(self, symbol: str) -> PricePoint:
        return PricePoint(
            symbol, self.usd, "fixture", self.observed_at or datetime.now(UTC).isoformat()
        )


def watcher(tmp_path: Path, **overrides: Any) -> WhaleWatcher:
    return WhaleWatcher(
        MagicMock(),
        database(tmp_path),
        {
            "name": "base",
            "rpc_url": "https://rpc.example.invalid",
            "native_asset": {"symbol": "ETH", "decimals": 18, "usd_threshold": "1000"},
            "token_usd_threshold": "1000",
            "erc20_tokens": [{"symbol": "USDC", "contract": CONTRACT, "decimals": 6}],
            **overrides,
        },
        StaticPrice(),
    )  # type: ignore[arg-type]


def transfer_log(**overrides: Any) -> dict[str, Any]:
    return {
        "address": CONTRACT,
        "blockNumber": "0x2a",
        "removed": False,
        "topics": [
            TRANSFER_TOPIC,
            "0x" + "0" * 24 + ADDRESS_A[2:],
            "0x" + "0" * 24 + ADDRESS_B[2:],
        ],
        "data": hex(2000 * 10**6),
        "logIndex": "0x0",
        "transactionHash": TX_HASH,
        **overrides,
    }


def block(units: int = 2000 * 10**18, **tx_overrides: Any) -> dict[str, Any]:
    return {
        "number": "0x2a",
        "transactions": [
            {
                "value": hex(units),
                "hash": TX_HASH,
                "from": ADDRESS_A,
                "to": ADDRESS_B,
                **tx_overrides,
            }
        ],
    }


def event(**overrides: Any) -> Event:
    return Event(
        **{
            "event_type": "sentiment_match",
            "chain": None,
            "source": "fixture",
            "severity": "high",
            "occurred_at": datetime.now(UTC).isoformat(),
            "dedupe_key": "fixture:one",
            "title": "Signal",
            "summary": "Observation only",
            **overrides,
        }
    )
