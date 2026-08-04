from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from omega_telemetry.db import TelemetryDB
from omega_telemetry.models import PricePoint
from omega_telemetry.whale_watcher import WhaleWatcher


class StaticPriceResolver:
    async def get_usd_price(self, symbol: str) -> PricePoint:
        return PricePoint(symbol=symbol, usd=Decimal("1"), source="test")


def watcher(tmp_path: Path) -> tuple[WhaleWatcher, TelemetryDB]:
    database = TelemetryDB(str(tmp_path / "omega.sqlite"))
    instance = WhaleWatcher(
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
            "token_usd_threshold": "1000",
            "erc20_tokens": [],
        },
        price_resolver=StaticPriceResolver(),  # type: ignore[arg-type]
    )
    return instance, database


def persist_log(
    instance: WhaleWatcher,
    *,
    log_index: int,
):
    return instance._persist_transfer(
        event_source="erc20_logs",
        threshold=Decimal("1000"),
        amount=Decimal("2000"),
        asset_symbol="USDC",
        usd_value=Decimal("2000"),
        from_address="0xabc",
        to_address="0xdef",
        tx_hash="0xsame-transaction",
        block_number=42,
        contract="0xtoken",
        log_index=log_index,
    )


def test_distinct_logs_in_one_transaction_are_not_collapsed(
    tmp_path: Path,
) -> None:
    instance, database = watcher(tmp_path)

    first = persist_log(instance, log_index=7)
    second = persist_log(instance, log_index=8)
    duplicate = persist_log(instance, log_index=7)

    assert first is not None
    assert second is not None
    assert duplicate is None
    assert first.dedupe_key != second.dedupe_key

    records = database.recent_events(event_type="large_transfer", minutes=60)
    assert len(records) == 2
    assert {record["data"]["log_index"] for record in records} == {7, 8}
