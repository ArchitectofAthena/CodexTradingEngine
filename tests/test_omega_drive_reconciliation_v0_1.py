from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from omega_telemetry.db import TelemetryDB
from omega_telemetry.models import PricePoint, SentimentEvent, WhaleEvent
from omega_telemetry.sentiment_tracker import SentimentTracker
from omega_telemetry.whale_watcher import (
    JsonRpcClient,
    WhaleWatcher,
    validate_rpc_url,
)


class StaticPriceResolver:
    async def get_usd_price(self, symbol: str) -> PricePoint:
        return PricePoint(
            symbol=symbol,
            usd=Decimal("2000"),
            source="test",
        )


def test_archived_event_fields_round_trip_through_sqlite(tmp_path: Path) -> None:
    database = TelemetryDB(str(tmp_path / "omega.sqlite"))
    event = SentimentEvent(
        event_type="sentiment_match",
        chain=None,
        source="fixture",
        severity="medium",
        occurred_at=datetime.now(timezone.utc).isoformat(),
        dedupe_key="sentiment:fixture:one",
        title="Fixture signal",
        summary="score=4.0",
        data={"tickers": ["ETH"]},
        post_id="one",
        source_url="https://example.invalid/post/one",
        author="fixture",
        score_value=4.0,
        matched_rules=["surge"],
        tickers=["ETH"],
    )

    database.save_event(event)
    records = database.recent_events(event_type="sentiment_match", minutes=60)

    assert len(records) == 1
    assert records[0]["post_id"] == "one"
    assert records[0]["matched_rules"] == ["surge"]
    assert records[0]["tickers"] == ["ETH"]


def test_sentiment_tracker_uses_stable_dedupe_and_real_db_method(
    tmp_path: Path,
) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "name": "surge",
                        "category": "momentum",
                        "weight": 4.0,
                        "patterns": ["surge"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    database = TelemetryDB(str(tmp_path / "omega.sqlite"))
    tracker = SentimentTracker(
        session=object(),  # type: ignore[arg-type]
        db=database,
        config={"min_score": 3.0, "sources": []},
        rules_path=rules_path,
    )
    item: dict[str, Any] = {
        "id": "post-1",
        "title": "$ETH surge",
        "summary": "",
        "url": "https://example.invalid/post-1",
        "author": "fixture",
    }

    first = tracker._process_item(item, "fixture")
    second = tracker._process_item(item, "fixture")

    assert first is not None
    assert first.tickers == ["ETH"]
    assert isinstance(first.summary, str)
    assert second is None


def test_whale_watcher_persists_exchange_deposit_and_deduplicates(
    tmp_path: Path,
) -> None:
    database = TelemetryDB(str(tmp_path / "omega.sqlite"))
    watcher = WhaleWatcher(
        session=object(),  # type: ignore[arg-type]
        db=database,
        config={
            "name": "base",
            "rpc_url": "https://rpc.example.invalid",
            "native_asset": {
                "symbol": "ETH",
                "decimals": 18,
                "usd_threshold": "1000",
            },
            "exchange_labels": {"0xdef": "Fixture Exchange"},
            "max_blocks_per_poll": 2,
        },
        price_resolver=StaticPriceResolver(),  # type: ignore[arg-type]
    )

    first = watcher._persist_transfer(
        event_source="json_rpc",
        threshold=Decimal("1000"),
        amount=Decimal("1"),
        asset_symbol="ETH",
        usd_value=Decimal("2000"),
        from_address="0xabc",
        to_address="0xdef",
        tx_hash="0x1",
        block_number=1,
    )
    second = watcher._persist_transfer(
        event_source="json_rpc",
        threshold=Decimal("1000"),
        amount=Decimal("1"),
        asset_symbol="ETH",
        usd_value=Decimal("2000"),
        from_address="0xabc",
        to_address="0xdef",
        tx_hash="0x1",
        block_number=1,
    )

    assert isinstance(first, WhaleEvent)
    assert first.event_type == "exchange_deposit"
    assert first.to_label == "Fixture Exchange"
    assert second is None


@pytest.mark.asyncio
async def test_json_rpc_client_rejects_non_observation_method() -> None:
    client = JsonRpcClient(
        session=object(),  # type: ignore[arg-type]
        rpc_url="https://rpc.example.invalid",
    )

    with pytest.raises(ValueError, match="read-only allowlist"):
        await client.call("eth_sendRawTransaction", ["0xdeadbeef"])


@pytest.mark.parametrize(
    "value",
    [
        "file:///tmp/rpc.sock",
        "https://user:secret@rpc.example.invalid",
        "rpc.example.invalid",
    ],
)
def test_rpc_url_validation_fails_closed(value: str) -> None:
    with pytest.raises(ValueError):
        validate_rpc_url(value)
