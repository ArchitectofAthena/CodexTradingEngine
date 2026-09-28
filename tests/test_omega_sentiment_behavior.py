"""Sentiment rules, bounded feeds, and burst behavior exercised offline."""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from omega_telemetry.sentiment_tracker import (
    FeedAdapter,
    FeedBoundaryError,
    RuleEngine,
    SentimentTracker,
    ip_is_public,
    peer_address,
    read_bounded_body,
    resolve_public_addresses,
    validate_feed_url,
    validate_source_config,
)
from tests.omega_helpers import Response, database, post, session_for, tracker


def source(**overrides: Any) -> dict[str, Any]:
    return {
        "name": "fixture",
        "type": "json",
        "url": "https://feed.example.org/data",
        "allowed_hosts": ["feed.example.org"],
        "items_path": ["items"],
        **overrides,
    }


class FeedResponse(Response):
    def __init__(self, body: bytes = b'{"items": []}', **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.url = "https://feed.example.org/data"
        self.content = self
        self.chunks = [body]
        self.connection = MagicMock()
        self.connection.transport.get_extra_info.return_value = ("8.8.8.8", 443)

    async def iter_chunked(self, size: int) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk


def test_rule_scoring_counts_each_rule_once_and_respects_case() -> None:
    rules = RuleEngine(
        {
            "rules": [
                None,
                {"patterns": "invalid"},
                {"patterns": [42]},
                {"name": "momentum", "weight": 3, "patterns": ["surge", "moon"]},
                {"name": "specific", "weight": 2, "patterns": ["UP"], "case_sensitive": True},
            ]
        }
    )
    assert rules.score("SURGE surge moon UP") == (5, ["momentum", "specific"])
    assert rules.score("surge up") == (3, ["momentum"])
    assert rules.score("") == (0, [])


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "", "summary": ""},
        {"title": "unmatched"},
        {"title": None},
        {"title": {}},
        {"summary": []},
    ],
)
def test_empty_low_score_and_malformed_items_do_not_persist(
    tmp_path: Path, changes: dict[str, Any]
) -> None:
    instance = tracker(tmp_path)
    assert instance._process_item(post(**changes), "fixture") is None
    assert instance.db.recent_events() == []


@pytest.mark.parametrize("minimum,severity", [(4, "medium"), (2, "high"), (1, "critical")])
def test_match_severity_boundaries_are_salience_only(
    tmp_path: Path, minimum: int, severity: str
) -> None:
    instance = tracker(tmp_path, min_score=minimum)
    observed = instance._process_item(
        post(title="surge", id=None, author=None, url=None), "fixture"
    )
    assert observed is not None and observed.severity == severity
    assert observed.tickers == [] and observed.post_id is None
    assert observed.source_url is None and observed.author is None
    assert observed.data["confidence"] == "low"
    assert instance._process_item(post(title="surge", id=None), "fixture") is None


@pytest.mark.parametrize("count,severity", [(5, "high"), (10, "critical")])
def test_independent_content_burst_preserves_counts_and_low_confidence(
    tmp_path: Path, count: int, severity: str
) -> None:
    instance = tracker(tmp_path)
    for i in range(count):
        instance._process_item(
            post(str(i), title=f"$ETH $BTC surge {i}", author=f"author-{i}"), f"source-{i}"
        )
    bursts = instance._emit_spike_events()
    assert {burst.tickers[0] for burst in bursts} == {"ETH", "BTC"}
    assert all(burst.data["count"] == count and burst.severity == severity for burst in bursts)
    assert all(burst.data["unique_sources"] == count for burst in bursts)
    assert all(burst.data["confidence"] == "low" for burst in bursts)
    assert all("single_author" not in burst.data["quality_flags"] for burst in bursts)


def test_burst_rechecks_publication_time_as_clock_advances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = tracker(tmp_path)
    for i in range(5):
        instance._process_item(post(str(i), title=f"$ETH surge {i}"), "fixture")
    monkeypatch.setattr("omega_telemetry.sentiment_tracker.timestamp_age_seconds", lambda _: 901)
    assert instance._emit_spike_events() == []


def test_legacy_or_malformed_stored_records_cannot_inflate_bursts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = tracker(tmp_path)
    records = []
    for tickers, fingerprint in [("ETH", "one"), (["ETH"], None)]:
        records.append(
            {
                "data": {
                    "published_at": datetime.now(UTC).isoformat(),
                    "spike_eligible": True,
                    "content_fingerprint": fingerprint,
                },
                "tickers": tickers,
            }
        )
    monkeypatch.setattr(instance.db, "recent_events", lambda **_: records)
    assert instance._emit_spike_events() == []


async def test_poll_continues_other_sources_when_one_feed_fails(tmp_path: Path) -> None:
    instance = tracker(tmp_path)
    bad = MagicMock(source_config={"name": "bad"})
    bad.fetch_items = AsyncMock(side_effect=FeedBoundaryError("fixture"))
    good = MagicMock(source_config={"name": "good"})
    good.fetch_items = AsyncMock(return_value=[post()])
    instance.adapters = [bad, good]
    await instance.poll_once()
    assert [row["source"] for row in instance.db.recent_events()] == ["good"]


@pytest.mark.parametrize(
    "config",
    [
        {"sources": {}},
        {"sources": [None]},
        {"min_score": "NaN"},
        {"min_score": 0},
        {"spike_threshold_count": 1},
    ],
)
def test_tracker_config_fails_explicitly(tmp_path: Path, config: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        tracker(tmp_path, **config)


def test_rules_root_must_be_object(tmp_path: Path) -> None:
    path = tmp_path / "rules.json"
    path.write_text("[]")
    with pytest.raises(ValueError, match="rules root"):
        SentimentTracker(MagicMock(), database(tmp_path), {}, path)


@pytest.mark.parametrize(
    "overrides",
    [
        {"type": "unsupported"},
        {"allowed_hosts": "feed.example.org"},
        {"allowed_hosts": [""]},
        {"items_path": "items"},
        {"items_path": [None]},
    ],
)
def test_source_config_rejects_malformed_adapter_settings(overrides: dict[str, Any]) -> None:
    with pytest.raises(FeedBoundaryError):
        validate_source_config(source(**overrides))


def test_host_normalization_and_missing_host() -> None:
    assert (
        validate_feed_url("https://FEED.EXAMPLE.ORG./data", ["feed.example.org"])
        == "feed.example.org"
    )
    with pytest.raises(FeedBoundaryError, match="hostname"):
        validate_feed_url("https:///path", ["feed.example.org"])
    assert not ip_is_public("invalid")


@pytest.mark.parametrize("body", [b"\xff", b"{not json}", b'{"missing": []}', b'{"items": {}}'])
def test_malformed_json_feed_fails_closed(body: bytes) -> None:
    with pytest.raises(FeedBoundaryError):
        FeedAdapter(MagicMock(), source())._parse_json(body)


def test_json_items_path_supports_list_indices() -> None:
    adapter = FeedAdapter(MagicMock(), source(items_path=["envelopes", 0, "posts"]))
    assert adapter._parse_json(b'{"envelopes": [{"posts": [{"id": "one"}]}]}') == [{"id": "one"}]


def test_rss_retains_publication_time_and_rejects_garbage() -> None:
    body = b'<rss version="2.0"><channel><title>Fixture</title><item><guid>one</guid><title>$ETH surge</title><link>https://example.invalid/one</link><pubDate>Mon, 28 Sep 2026 12:00:00 GMT</pubDate></item></channel></rss>'
    items = FeedAdapter._parse_rss(body)
    assert items[0]["id"] == "one" and items[0]["published_at"] == "Mon, 28 Sep 2026 12:00:00 GMT"
    with pytest.raises(FeedBoundaryError, match="RSS"):
        FeedAdapter._parse_rss(b"not XML")


@pytest.mark.parametrize("source_type", ["json", "rss"])
async def test_feed_fetch_validates_transport_and_parses(
    source_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = (
        b'{"items": [{"id": "one"}]}'
        if source_type == "json"
        else b'<rss version="2.0"><channel><title>Test</title></channel></rss>'
    )
    session = session_for(FeedResponse(body))
    resolve = AsyncMock(return_value=frozenset({"8.8.8.8"}))
    monkeypatch.setattr("omega_telemetry.sentiment_tracker.resolve_public_addresses", resolve)
    adapter = FeedAdapter(session, source(type=source_type))
    items = await adapter.fetch_items()
    assert items == ([{"id": "one"}] if source_type == "json" else [])
    assert session.get.call_args.kwargs["allow_redirects"] is False
    assert resolve.await_count == 2


@pytest.mark.parametrize("attack", ["redirect", "host", "private_peer", "wrong_peer", "dns_change"])
async def test_adversarial_feed_transport_membrane_remains_closed(
    attack: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = FeedResponse()
    dns = [frozenset({"8.8.8.8"}), frozenset({"8.8.8.8"})]
    if attack == "redirect":
        response.status = 302
    elif attack == "host":
        response.url = "https://other.example.org/data"
    elif attack in {"private_peer", "wrong_peer"}:
        response.connection.transport.get_extra_info.return_value = (
            "127.0.0.1" if attack == "private_peer" else "1.1.1.1",
            443,
        )
    else:
        dns[1] = frozenset({"1.1.1.1"})
    monkeypatch.setattr(
        "omega_telemetry.sentiment_tracker.resolve_public_addresses", AsyncMock(side_effect=dns)
    )
    adapter = FeedAdapter(
        session_for(response), source(allowed_hosts=["feed.example.org", "other.example.org"])
    )
    with pytest.raises(FeedBoundaryError):
        await adapter.fetch_items()


@pytest.mark.parametrize("addresses", [[], ["127.0.0.1"], ["8.8.8.8", "10.0.0.1"]])
async def test_adversarial_dns_empty_or_private_answers_fail(
    addresses: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, (address, 443)) for address in addresses],
    )
    with pytest.raises(FeedBoundaryError):
        await resolve_public_addresses("feed.example.org")


async def test_dns_resolution_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("8.8.8.8", 443))]
    )
    assert await resolve_public_addresses("fixture") == frozenset({"8.8.8.8"})
    monkeypatch.setattr(socket, "getaddrinfo", MagicMock(side_effect=socket.gaierror()))
    with pytest.raises(FeedBoundaryError, match="resolution failed"):
        await resolve_public_addresses("fixture")


def test_peer_address_optional_connection_and_ipv6_scope() -> None:
    response = FeedResponse()
    response.connection.transport.get_extra_info.return_value = ("2606:4700:4700::1111%eth0", 443)
    assert peer_address(response) == "2606:4700:4700::1111"
    response.connection.transport.get_extra_info.return_value = None
    assert peer_address(response) is None
    response.connection = None
    assert peer_address(response) is None


async def test_invalid_content_length_is_rejected() -> None:
    response = FeedResponse()
    response.headers["Content-Length"] = "garbage"
    with pytest.raises(FeedBoundaryError, match="Content-Length"):
        await read_bounded_body(response, 100)
