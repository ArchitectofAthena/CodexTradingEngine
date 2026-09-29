"""Deceptive inputs must be rejected, bounded, or explicitly low-confidence."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from omega_telemetry import context_runner
from omega_telemetry.alert_module import AlertDispatcher, format_event_message
from omega_telemetry.config_loader import load_config
from omega_telemetry.pricing import PriceResolver
from omega_telemetry.sentiment_tracker import RuleEngine
from omega_telemetry.signal_observer import SignalObserver
from omega_telemetry.whale_watcher import JsonRpcClient
from tests.omega_helpers import (
    ADDRESS_A,
    ADDRESS_B,
    Response,
    StaticPrice,
    block,
    database,
    event,
    post,
    session_for,
    tracker,
    transfer_log,
    watcher,
)


@pytest.mark.parametrize(
    "title", ["Great, another $ETH surge. /s", "$ETH surge guaranteed, buy now!"]
)
def test_adversarial_sarcasm_and_spoofed_sentiment_are_not_confidence(
    tmp_path: Path, title: str
) -> None:
    result = tracker(tmp_path)._process_item(post(title=title), "unverified-feed")
    assert result is not None
    assert result.data["confidence"] == "low"
    assert {"keyword_only", "authenticity_unverified", "single_post"} <= set(
        result.data["quality_flags"]
    )
    assert result.data["authority"] is False
    assert result.data["artifact_is_command"] is False


def test_adversarial_coordinated_reposts_cannot_multiply_spike_count(tmp_path: Path) -> None:
    instance = tracker(tmp_path)
    for index in range(12):
        instance._process_item(post(str(index), title="  $ETH   SURGE  "), f"mirror-{index}")
    assert instance._emit_spike_events() == []


def test_adversarial_distinct_coordinated_posts_still_have_low_confidence(tmp_path: Path) -> None:
    instance = tracker(tmp_path)
    for index in range(5):
        instance._process_item(post(str(index), title=f"$ETH surge claim {index}"), "one-feed")
    bursts = instance._emit_spike_events()
    assert len(bursts) == 1
    assert bursts[0].data["confidence"] == "low"
    assert {"coordination_not_excluded", "single_source", "single_author"} <= set(
        bursts[0].data["quality_flags"]
    )
    assert instance._emit_spike_events() == []


@pytest.mark.parametrize("stamp", [None, "broken", "2000-01-01T00:00:00Z", "2999-01-01T00:00:00Z"])
def test_adversarial_unknown_stale_or_future_posts_do_not_make_fresh_spikes(
    tmp_path: Path, stamp: str | None
) -> None:
    instance = tracker(tmp_path)
    for index in range(6):
        result = instance._process_item(
            post(str(index), title=f"$ETH surge {index}", published_at=stamp), "feed"
        )
        assert result is not None
        assert result.data["confidence"] == "low"
        assert result.data["spike_eligible"] is False
    assert instance._emit_spike_events() == []


def test_adversarial_one_post_is_not_a_burst(tmp_path: Path) -> None:
    instance = tracker(tmp_path)
    instance._process_item(post(title="$ETH $ETH $ETH surge"), "feed")
    assert instance._emit_spike_events() == []


@pytest.mark.parametrize("weight", ["NaN", "Infinity", "-Infinity"])
def test_adversarial_nonfinite_rule_weights_rejected(weight: str) -> None:
    with pytest.raises(ValueError):
        RuleEngine({"rules": [{"weight": weight, "patterns": ["surge"]}]})


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0", True, {}, "invalid"])
async def test_adversarial_invalid_prices_never_become_valuations(value: object) -> None:
    session = session_for(Response({"ethereum": {"usd": value}}))
    result = await PriceResolver(session, {"ETH": "ethereum"}).get_usd_price("ETH")
    assert result is None


async def test_adversarial_expired_price_cache_is_refreshed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = session_for(
        Response({"ethereum": {"usd": "1000"}}), Response({"ethereum": {"usd": "1"}})
    )
    clock = [1000.0]
    monkeypatch.setattr("time.monotonic", lambda: clock[0])
    resolver = PriceResolver(session, {"ETH": "ethereum"})
    first = await resolver.get_usd_price("ETH")
    clock[0] += 61
    second = await resolver.get_usd_price("ETH")
    assert first is not None and second is not None
    assert first.usd == Decimal("1000") and second.usd == Decimal("1")
    assert session.get.call_count == 2


async def test_adversarial_stale_price_cannot_promote_dust_to_whale(tmp_path: Path) -> None:
    instance = watcher(tmp_path)
    instance.price_resolver = StaticPrice("1000000", "2000-01-01T00:00:00Z")  # type: ignore[assignment]
    await instance._scan_native_transfers(block(10**16))
    assert instance.db.recent_events() == []


@pytest.mark.parametrize(
    "patch",
    [
        {"removed": True},
        {"address": ADDRESS_A},
        {"blockNumber": "0x29"},
        {"topics": ["0xwrong", "0x" + "0" * 64, "0x" + "0" * 64]},
        {"logIndex": None},
        {"transactionHash": None},
        {"data": "-0x1"},
        {"data": "garbage"},
        {"data": "0x" + "f" * 65},
    ],
)
async def test_adversarial_spoofed_or_removed_erc20_logs_are_rejected(
    tmp_path: Path, patch: dict[str, Any]
) -> None:
    instance = watcher(tmp_path)
    instance.rpc.call = AsyncMock(return_value=[transfer_log(**patch)])
    await instance._scan_erc20_logs(42)
    assert instance.db.recent_events() == []


async def test_adversarial_dust_does_not_cross_decimal_threshold(tmp_path: Path) -> None:
    instance = watcher(tmp_path)
    instance.native_usd_threshold = Decimal("1000000000000")
    just_below = 10**30 - 1
    await instance._scan_native_transfers(block(just_below))
    assert instance.db.recent_events() == []


async def test_adversarial_malformed_native_transfer_does_not_hide_next_valid_one(
    tmp_path: Path,
) -> None:
    instance = watcher(tmp_path)
    feed = block()
    feed["transactions"].insert(0, {"value": "not-hex"})
    await instance._scan_native_transfers(feed)
    assert len(instance.db.recent_events()) == 1


@pytest.mark.parametrize("same_address", [True, False])
async def test_adversarial_self_and_exchange_internal_transfers_are_not_accumulation(
    tmp_path: Path, same_address: bool
) -> None:
    instance = watcher(tmp_path, exchange_labels={ADDRESS_A: "Exchange", ADDRESS_B: "Exchange"})
    await instance._scan_native_transfers(block(to=ADDRESS_A if same_address else ADDRESS_B))
    records = instance.db.recent_events()
    assert len(records) == 1
    data = records[0]["data"]
    assert data["confidence"] == "low"
    assert data["directional_signal"] == "unknown"
    assert ("self_transfer" if same_address else "exchange_internal") in data["quality_flags"]


async def test_adversarial_round_trip_transfers_remain_observations(tmp_path: Path) -> None:
    instance = watcher(tmp_path)
    await instance._scan_native_transfers(block())
    await instance._scan_native_transfers(
        block(hash="0x" + "e" * 64, **{"from": ADDRESS_B, "to": ADDRESS_A})
    )
    records = instance.db.recent_events()
    assert len(records) == 2
    assert all(row["data"]["directional_signal"] == "unknown" for row in records)
    assert all("beneficial_ownership_unknown" in row["data"]["quality_flags"] for row in records)


@pytest.mark.parametrize(
    "reply",
    [
        {"jsonrpc": "2.0", "id": 99, "result": "0x2a"},
        {"id": 1, "result": "0x2a"},
        {"jsonrpc": "2.0", "id": True, "result": "0x2a"},
    ],
)
async def test_adversarial_rpc_reply_must_match_request(reply: dict) -> None:
    session = session_for(Response(reply))
    with pytest.raises(RuntimeError):
        await JsonRpcClient(session, "https://rpc.example.invalid").call("eth_blockNumber", [])


async def test_adversarial_missing_block_must_not_advance_cursor(tmp_path: Path) -> None:
    instance = watcher(tmp_path)
    instance.rpc.call = AsyncMock(side_effect=["0x2a", None])
    with pytest.raises(ValueError):
        await instance.poll_once()
    assert instance.db.get_state("whale_watcher:last_block:base") is None


async def test_adversarial_alert_threshold_flapping_is_suppressed_across_restart(
    tmp_path: Path,
) -> None:
    db = database(tmp_path)
    first = AlertDispatcher(MagicMock(), db, {})
    assert (await first.dispatch(event(severity="high")))[0].delivered
    second = AlertDispatcher(MagicMock(), db, {})
    result = await second.dispatch(event(severity="medium"))
    assert not result[0].delivered
    assert result[0].response == "duplicate_cooldown"


async def test_adversarial_unique_alert_flood_is_bounded(tmp_path: Path) -> None:
    dispatcher = AlertDispatcher(MagicMock(), database(tmp_path), {"max_alerts_per_window": 2})
    results = [
        await dispatcher.dispatch(event(dedupe_key=f"attacker:{index}")) for index in range(8)
    ]
    assert sum(result[0].delivered for result in results) == 2
    assert results[-1][0].response == "rate_limited"


@pytest.mark.parametrize(
    "timestamp", ["2000-01-01T00:00:00Z", "2999-01-01T00:00:00Z", "not-a-time"]
)
async def test_adversarial_stale_or_forged_alert_timestamp_is_suppressed(
    tmp_path: Path, timestamp: str
) -> None:
    session = MagicMock()
    result = await AlertDispatcher(session, database(tmp_path), {}).dispatch(
        event(occurred_at=timestamp)
    )
    assert not result[0].delivered
    session.post.assert_not_called()


def test_adversarial_low_confidence_warning_survives_alert_formatting() -> None:
    message = format_event_message(
        event(data={"confidence": "low", "quality_flags": ["keyword_only"]})
    )
    assert "Confidence: low" in message and "keyword_only" in message


async def test_adversarial_discord_mentions_do_not_amplify_alerts(tmp_path: Path) -> None:
    session = session_for(Response(status=204))
    dispatcher = AlertDispatcher(
        session,
        database(tmp_path),
        {"discord": {"enabled": True, "webhook_url": "https://example.invalid/fixture"}},
        shadow_mode=False,
    )
    await dispatcher.dispatch(event(title="@everyone @here <@123>"))
    assert session.post.call_args.kwargs["json"]["allowed_mentions"] == {"parse": []}


@pytest.mark.parametrize("value", ["[]", "false", "42", "a string"])
def test_adversarial_invalid_config_root_is_not_silently_accepted(
    tmp_path: Path, value: str
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(value)
    with pytest.raises(ValueError):
        load_config(path)


@pytest.mark.parametrize("interval", [0, -1])
def test_adversarial_observer_busy_loop_config_is_rejected(tmp_path: Path, interval: int) -> None:
    with pytest.raises(ValueError):
        SignalObserver(database(tmp_path), {"poll_interval_seconds": interval})


async def test_adversarial_invalid_runner_config_starts_no_workers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = {
        "database_path": str(tmp_path / "db.sqlite"),
        "health_path": str(tmp_path / "health.json"),
        "observers": [{}],
        "sentiment": [],
    }
    monkeypatch.setattr(context_runner, "load_config", lambda _: config)
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_session.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(context_runner.aiohttp, "ClientSession", lambda **_: mock_session)
    created: list[asyncio.Task[Any]] = []
    create = asyncio.create_task

    def capture(coro: Coroutine[Any, Any, Any], **kwargs: Any) -> asyncio.Task[Any]:
        task = create(coro, **kwargs)
        created.append(task)
        return task

    monkeypatch.setattr(context_runner.asyncio, "create_task", capture)
    try:
        with pytest.raises(ValueError, match="sentiment"):
            await context_runner.run("unused")
        assert created == []
    finally:
        for task in created:
            task.cancel()
        await asyncio.gather(*created, return_exceptions=True)
