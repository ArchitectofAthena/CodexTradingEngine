"""Runtime, notification, and local storage coverage with no external transport."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from omega_telemetry import context_runner
from omega_telemetry.alert_module import AlertDispatcher, format_event_message
from omega_telemetry.config_loader import load_config
from omega_telemetry.config_tools import positive_int
from omega_telemetry.health import HealthWriter
from omega_telemetry.models import timestamp_age_seconds
from omega_telemetry.signal_observer import SignalObserver
from tests.omega_helpers import Response, database, event, session_for, tracker, watcher


@pytest.mark.parametrize(
    "content, expected", [("", {}), ("null", {}), ("observers: []", {"observers": []})]
)
def test_config_alias_reads_yaml(tmp_path: Path, content: str, expected: dict[str, Any]) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(content)
    assert load_config(path) == expected


def test_config_missing_and_malformed_yaml_fail(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    with pytest.raises(FileNotFoundError):
        load_config(path)
    path.write_text("[unterminated")
    with pytest.raises(yaml.YAMLError):
        load_config(path)


def test_adversarial_yaml_object_construction_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("!!python/object/apply:builtins.eval ['1 + 1']")
    with pytest.raises(yaml.YAMLError):
        load_config(path)


@pytest.mark.parametrize("value", [True, 1.5, 0, -1, 86401, "bad"])
def test_bounded_intervals_reject_invalid_values(value: Any) -> None:
    with pytest.raises(ValueError):
        positive_int(value, "interval")


def test_timestamp_requires_timezone_and_accepts_rss_format() -> None:
    assert timestamp_age_seconds("2026-09-28T12:00:00") is None
    stamp = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
    age = timestamp_age_seconds(stamp)
    assert age is not None and 0 <= age < 2


def test_database_state_events_and_delivery_audit_round_trip(tmp_path: Path) -> None:
    db = database(tmp_path)
    assert db.get_state("cursor") is None
    db.set_state("cursor", "41")
    db.set_state("cursor", "42")
    assert db.get_state("cursor") == "42"
    current = event(dedupe_key="'; DROP TABLE events; --")
    db.save_event(current)
    db.save_event(event(dedupe_key="old", occurred_at="2000-01-01T00:00:00+00:00"))
    assert db.is_duplicate(current.dedupe_key, 10)
    assert not db.is_duplicate("old", 10)
    assert db.recent_events() == [current.to_record()]
    assert db.recent_events("not_present") == []
    db.log_alert(current.dedupe_key, "shadow", True, "shadow_mode")
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2
        assert conn.execute("SELECT delivered FROM alert_log").fetchone()[0] == 1


def test_health_writer_creates_parent_and_replaces_document(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "health.json"
    health = HealthWriter(str(path))
    health.write({"status": "running", "authority": False})
    first = json.loads(path.read_text())
    assert first["authority"] is False and timestamp_age_seconds(first["updated_at"]) is not None
    health.write({"status": "stopped"})
    assert json.loads(path.read_text())["status"] == "stopped"


async def test_signal_tick_is_liveness_only_even_with_action_config(tmp_path: Path) -> None:
    db = database(tmp_path)
    observer = SignalObserver(db, {"name": "observer", "authority": True, "may_execute": True})
    await observer.poll_once()
    row = db.recent_events("signal_tick")[0]
    assert row["source"] == "observer"
    assert row["data"]["market_evidence"] is False
    assert row["data"]["authority"] is False
    assert row["data"]["artifact_is_command"] is False


@pytest.mark.parametrize("kind", ["observer", "sentiment", "whale"])
@pytest.mark.parametrize("poll_fails", [False, True])
async def test_worker_loop_recovers_and_propagates_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, poll_fails: bool
) -> None:
    instance = {
        "observer": lambda: SignalObserver(database(tmp_path), {}),
        "sentiment": lambda: tracker(tmp_path),
        "whale": lambda: watcher(tmp_path),
    }[kind]()
    instance.poll_once = AsyncMock(
        side_effect=[RuntimeError("fixture") if poll_fails else None, asyncio.CancelledError()]
    )
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await instance.run_forever()
    assert instance.poll_once.await_count == 2
    sleep.assert_awaited_once_with(instance.poll_interval_seconds)


def configure_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **extra: Any) -> MagicMock:
    config = {
        "database_path": str(tmp_path / "db.sqlite"),
        "health_path": str(tmp_path / "health.json"),
        **extra,
    }
    monkeypatch.setattr(context_runner, "load_config", lambda _: config)
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(context_runner.aiohttp, "ClientSession", lambda **_: session)
    return session


@pytest.mark.parametrize(
    "config",
    [
        {"observers": {}},
        {"observers": ["bad"]},
        {"whale": []},
        {"whale": {"symbol_to_coingecko_id": []}},
        {"whale": {"chains": {}}},
        {"whale": {"chains": [None]}},
        {"health_interval_seconds": 0},
    ],
)
async def test_runner_rejects_bad_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config: dict[str, Any]
) -> None:
    configure_runner(tmp_path, monkeypatch, **config)
    with pytest.raises(ValueError):
        await context_runner.run("fixture")


async def test_runner_missing_rules_starts_no_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_runner(
        tmp_path,
        monkeypatch,
        observers=[{}],
        sentiment={"enabled": True, "rules_path": str(tmp_path / "missing")},
    )
    start = MagicMock()
    monkeypatch.setattr(context_runner.asyncio, "create_task", start)
    with pytest.raises(FileNotFoundError):
        await context_runner.run("fixture")
    start.assert_not_called()


@pytest.mark.parametrize("enabled, finishes", [(False, False), (True, False), (True, True)])
async def test_runner_health_boundaries_and_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool, finishes: bool
) -> None:
    rules = tmp_path / "rules.json"
    rules.write_text('{"rules": []}')
    session = configure_runner(
        tmp_path,
        monkeypatch,
        boundary={key: not value for key, value in context_runner.BOUNDARY.items()},
        observers=[{"name": "context", "enabled": enabled}, {"enabled": False}],
        sentiment={"enabled": enabled, "rules_path": str(rules), "sources": []},
        whale={
            "enabled": enabled,
            "chains": [
                {"enabled": False},
                {
                    "enabled": enabled,
                    "name": "base",
                    "rpc_url": "https://rpc.example.invalid",
                    "native_asset": {"symbol": "ETH", "usd_threshold": "1000"},
                },
            ],
        },
    )
    ready = asyncio.Event()
    stopped = asyncio.Event()
    reports: list[dict[str, Any]] = []
    worker_names: list[str] = []

    async def work(self: Any) -> None:
        worker_names.append(asyncio.current_task().get_name())
        if not finishes:
            await stopped.wait()

    for cls in (
        context_runner.SignalObserver,
        context_runner.SentimentTracker,
        context_runner.WhaleWatcher,
    ):
        monkeypatch.setattr(cls, "run_forever", work)
    original = HealthWriter.write

    def capture(self: HealthWriter, payload: dict[str, Any]) -> None:
        original(self, payload)
        reports.append(payload)
        ready.set()

    monkeypatch.setattr(HealthWriter, "write", capture)
    task = asyncio.create_task(context_runner.run("fixture"))
    try:
        await asyncio.wait_for(ready.wait(), timeout=2)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert reports[0]["status"] == ("degraded" if finishes else "running" if enabled else "idle")
    assert reports[-1]["status"] == "stopped"
    for report in reports:
        assert report["feed_freshness"] == "unverified"
        assert all(report[key] == value for key, value in context_runner.BOUNDARY.items())
    assert set(worker_names) == (
        {"signal:context", "sentiment", "whale:base"} if enabled else set()
    )
    assert not any(
        t.get_name() in {"signal:context", "sentiment", "whale:base", "heartbeat"}
        for t in asyncio.all_tasks()
    )
    session.post.assert_not_called()
    session.get.assert_not_called()
    session.__aexit__.assert_awaited_once()


async def test_runner_failure_cancels_siblings_and_records_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = configure_runner(tmp_path, monkeypatch, observers=[{}])
    monkeypatch.setattr(
        SignalObserver, "run_forever", AsyncMock(side_effect=RuntimeError("fixture"))
    )
    with pytest.raises(RuntimeError, match="fixture"):
        await context_runner.run("fixture")
    assert json.loads((tmp_path / "health.json").read_text())["status"] == "failed"
    assert not any(task.get_name() == "heartbeat" for task in asyncio.all_tasks())
    session.__aexit__.assert_awaited_once()


def test_runner_cli_passes_config_without_changing_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = AsyncMock()
    monkeypatch.setattr(context_runner, "run", run)
    monkeypatch.setattr(sys, "argv", ["omega-context", "--config", "fixture.yaml"])
    context_runner.main()
    run.assert_awaited_once_with("fixture.yaml")


def test_alert_format_preserves_transaction_source_and_chain() -> None:
    message = format_event_message(
        event(
            chain="base",
            severity="unrecognized",
            data={"tx_hash": "fixture-hash", "source_url": "https://example.invalid"},
        )
    )
    assert "ℹ️" in message and "Chain: base" in message
    assert "Tx: fixture-hash" in message and "Link: https://example.invalid" in message


async def test_alert_default_shadow_never_uses_configured_channels(tmp_path: Path) -> None:
    session = MagicMock()
    dispatcher = AlertDispatcher(
        session,
        database(tmp_path),
        {"shadow_mode": False, "telegram": {"enabled": True}, "discord": {"enabled": True}},
    )
    result = await dispatcher.dispatch(event())
    assert result[0].channel == "shadow" and result[0].delivered
    session.post.assert_not_called()


@pytest.mark.parametrize(
    "config, responses",
    [
        ({}, ["no_channels_configured"]),
        ({"telegram": {"enabled": True}}, ["missing_telegram_credentials"]),
        ({"discord": {"enabled": True}}, ["missing_discord_webhook"]),
    ],
)
async def test_unconfigured_notifications_are_logged(
    tmp_path: Path, config: dict[str, Any], responses: list[str]
) -> None:
    dispatcher = AlertDispatcher(MagicMock(), database(tmp_path), config, shadow_mode=False)
    results = await dispatcher.dispatch(event())
    assert [result.response for result in results] == responses
    assert not any(result.delivered for result in results)


@pytest.mark.parametrize("status", [200, 429])
async def test_both_notification_channels_log_http_outcome(tmp_path: Path, status: int) -> None:
    session = session_for(Response(status=status), Response(status=status))
    dispatcher = AlertDispatcher(
        session,
        database(tmp_path),
        {
            "telegram": {"enabled": True, "bot_token": "fixture", "chat_id": "fixture"},
            "discord": {"enabled": True, "webhook_url": "https://example.invalid"},
        },
        shadow_mode=False,
    )
    results = await dispatcher.dispatch(event())
    assert {result.channel for result in results} == {"telegram", "discord"}
    assert all(result.delivered == (status == 200) for result in results)
    assert all(result.response == f"http_status:{status}" for result in results)


async def test_adversarial_notification_errors_do_not_copy_provider_secrets(tmp_path: Path) -> None:
    session = MagicMock()
    session.post.side_effect = RuntimeError("fixture-sensitive-URL-must-not-be-stored")
    dispatcher = AlertDispatcher(
        session,
        database(tmp_path),
        {
            "telegram": {"enabled": True, "bot_token": "fixture", "chat_id": "fixture"},
            "discord": {"enabled": True, "webhook_url": "https://example.invalid"},
        },
        shadow_mode=False,
    )
    results = await dispatcher.dispatch(event())
    assert all(result.response == "RuntimeError" for result in results)
    with dispatcher.db.connect() as conn:
        assert all(
            "sensitive" not in row[0] for row in conn.execute("SELECT response FROM alert_log")
        )


async def test_adversarial_concurrent_alert_duplicates_deliver_once(tmp_path: Path) -> None:
    dispatcher = AlertDispatcher(MagicMock(), database(tmp_path), {})
    results = await asyncio.gather(*(dispatcher.dispatch(event()) for _ in range(10)))
    assert sum(result[0].delivered for result in results) == 1


async def test_alert_cooldown_expires_without_mutating_event_time(tmp_path: Path) -> None:
    db = database(tmp_path)
    dispatcher = AlertDispatcher(MagicMock(), db, {})
    await dispatcher.dispatch(event())
    with db.connect() as conn:
        conn.execute(
            "UPDATE alert_log SET created_at = ?",
            ((datetime.now(UTC) - timedelta(minutes=11)).isoformat(),),
        )
    assert (await dispatcher.dispatch(event()))[0].delivered
