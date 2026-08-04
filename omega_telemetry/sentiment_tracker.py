"""Passive, bounded sentiment telemetry with hardened public-feed transport."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

import aiohttp
import feedparser

from .db import TelemetryDB
from .models import SentimentEvent

logger = logging.getLogger(__name__)

TICKER_RE = re.compile(r"(?<!\w)\$([A-Z]{2,10})(?!\w)")
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RESPONSE_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 10_485_760


class FeedBoundaryError(ValueError):
    """Raised when a configured public feed violates the read-only membrane."""


def normalize_host(host: str) -> str:
    return host.strip().rstrip(".").casefold()


def ip_is_public(value: str) -> bool:
    """Return true only for globally routable unicast addresses."""

    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(address.is_global and not address.is_multicast and not address.is_unspecified)


def validate_feed_url(url: str, allowed_hosts: Sequence[str]) -> str:
    """Validate HTTPS, credential-free, exact-host feed configuration."""

    parsed = urlparse(url)
    if parsed.scheme.casefold() != "https":
        raise FeedBoundaryError("sentiment feeds require HTTPS")
    if parsed.username or parsed.password:
        raise FeedBoundaryError("credentials may not be embedded in feed URLs")
    if not parsed.hostname:
        raise FeedBoundaryError("sentiment feed URL has no hostname")
    host = normalize_host(parsed.hostname)
    normalized_allowlist = {normalize_host(item) for item in allowed_hosts}
    if not normalized_allowlist:
        raise FeedBoundaryError("sentiment feed requires an exact host allowlist")
    if host not in normalized_allowlist:
        raise FeedBoundaryError(f"sentiment feed host is not allowlisted: {host}")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not ip_is_public(str(literal)):
        raise FeedBoundaryError("sentiment feed IP literal is not public")
    return host


def validate_source_config(source_config: Mapping[str, Any]) -> None:
    """Validate one feed source before any network operation."""

    source_type = str(source_config.get("type", "")).casefold()
    if source_type not in {"rss", "json"}:
        raise FeedBoundaryError(f"unsupported sentiment source type: {source_type}")
    url = str(source_config.get("url", ""))
    allowed_hosts = source_config.get("allowed_hosts", [])
    if not isinstance(allowed_hosts, list) or not all(
        isinstance(item, str) and item.strip() for item in allowed_hosts
    ):
        raise FeedBoundaryError("allowed_hosts must be a non-empty array of strings")
    validate_feed_url(url, allowed_hosts)

    timeout_seconds = float(
        source_config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    )
    if not 0 < timeout_seconds <= 60:
        raise FeedBoundaryError("timeout_seconds must be greater than zero and at most 60")
    max_response_bytes = int(
        source_config.get("max_response_bytes", DEFAULT_MAX_RESPONSE_BYTES)
    )
    if not 1 <= max_response_bytes <= MAX_RESPONSE_BYTES:
        raise FeedBoundaryError(
            f"max_response_bytes must be between 1 and {MAX_RESPONSE_BYTES}"
        )
    if source_type == "json":
        items_path = source_config.get("items_path", [])
        if not isinstance(items_path, list) or not all(
            isinstance(part, (str, int)) for part in items_path
        ):
            raise FeedBoundaryError("JSON adapter items_path must contain strings or integers")


async def resolve_public_addresses(host: str) -> frozenset[str]:
    """Resolve a host and reject private, loopback, link-local, or reserved results."""

    def _resolve() -> list[tuple[Any, ...]]:
        return socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)

    try:
        records = await asyncio.to_thread(_resolve)
    except socket.gaierror as exc:
        raise FeedBoundaryError(f"sentiment feed DNS resolution failed: {host}") from exc

    addresses = frozenset(str(record[4][0]).split("%", 1)[0] for record in records)
    if not addresses:
        raise FeedBoundaryError(f"sentiment feed DNS returned no addresses: {host}")
    rejected = sorted(address for address in addresses if not ip_is_public(address))
    if rejected:
        raise FeedBoundaryError(
            "sentiment feed DNS resolved to non-public addresses: " + ", ".join(rejected)
        )
    return addresses


def peer_address(response: aiohttp.ClientResponse) -> str | None:
    """Return the connected peer IP when exposed by aiohttp."""

    connection = response.connection
    if connection is None or connection.transport is None:
        return None
    peer = connection.transport.get_extra_info("peername")
    if not peer:
        return None
    return str(peer[0]).split("%", 1)[0]


async def read_bounded_body(
    response: aiohttp.ClientResponse,
    max_response_bytes: int,
) -> bytes:
    """Read at most the configured number of response bytes."""

    declared = response.headers.get("Content-Length")
    if declared is not None:
        try:
            declared_size = int(declared)
        except ValueError as exc:
            raise FeedBoundaryError("invalid Content-Length from sentiment feed") from exc
        if declared_size > max_response_bytes:
            raise FeedBoundaryError(
                f"sentiment feed response exceeds {max_response_bytes} bytes"
            )

    body = bytearray()
    async for chunk in response.content.iter_chunked(65_536):
        body.extend(chunk)
        if len(body) > max_response_bytes:
            raise FeedBoundaryError(
                f"sentiment feed response exceeds {max_response_bytes} bytes"
            )
    return bytes(body)


@dataclass(slots=True, frozen=True)
class Rule:
    name: str
    category: str
    weight: float
    patterns: tuple[str, ...]
    case_sensitive: bool = False


class RuleEngine:
    def __init__(self, rule_payload: dict[str, Any]) -> None:
        rules: list[Rule] = []
        for item in rule_payload.get("rules", []):
            if not isinstance(item, dict):
                continue
            patterns = item.get("patterns", [])
            if not isinstance(patterns, list) or not all(
                isinstance(value, str) for value in patterns
            ):
                continue
            rules.append(
                Rule(
                    name=str(item.get("name", "unnamed")),
                    category=str(item.get("category", "signal")),
                    weight=float(item.get("weight", 0.0)),
                    patterns=tuple(patterns),
                    case_sensitive=bool(item.get("case_sensitive", False)),
                )
            )
        self.rules = tuple(rules)

    def score(self, text: str) -> tuple[float, list[str]]:
        total = 0.0
        matched: list[str] = []
        for rule in self.rules:
            haystack = text if rule.case_sensitive else text.casefold()
            patterns = (
                rule.patterns
                if rule.case_sensitive
                else tuple(pattern.casefold() for pattern in rule.patterns)
            )
            if any(pattern in haystack for pattern in patterns):
                total += rule.weight
                matched.append(rule.name)
        return total, matched


class FeedAdapter:
    """Fetch one exact-host public feed through a bounded read-only membrane."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        source_config: dict[str, Any],
    ) -> None:
        validate_source_config(source_config)
        self.session = session
        self.source_config = dict(source_config)
        self.url = str(source_config["url"])
        self.allowed_hosts = tuple(str(item) for item in source_config["allowed_hosts"])
        self.host = validate_feed_url(self.url, self.allowed_hosts)
        self.timeout_seconds = float(
            source_config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        )
        self.max_response_bytes = int(
            source_config.get("max_response_bytes", DEFAULT_MAX_RESPONSE_BYTES)
        )

    async def fetch_items(self) -> list[dict[str, Any]]:
        source_type = str(self.source_config.get("type", "")).casefold()
        body = await self._fetch_body()
        if source_type == "rss":
            return self._parse_rss(body)
        if source_type == "json":
            return self._parse_json(body)
        raise FeedBoundaryError(f"unsupported sentiment source type: {source_type}")

    async def _fetch_body(self) -> bytes:
        before = await resolve_public_addresses(self.host)
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        headers = {
            "Accept": "application/json, application/rss+xml, application/atom+xml, text/xml;q=0.8",
            "User-Agent": "CodexTradingEngine-OmegaSentiment/0.2",
        }
        async with self.session.get(
            self.url,
            timeout=timeout,
            allow_redirects=False,
            headers=headers,
        ) as response:
            if 300 <= response.status < 400:
                raise FeedBoundaryError("sentiment feed redirects are disabled")
            response.raise_for_status()
            final_host = validate_feed_url(str(response.url), self.allowed_hosts)
            if final_host != self.host:
                raise FeedBoundaryError("sentiment feed final host changed")
            peer = peer_address(response)
            if peer is not None:
                if not ip_is_public(peer):
                    raise FeedBoundaryError("sentiment feed connected to a non-public peer")
                if peer not in before:
                    raise FeedBoundaryError("sentiment feed peer was not in DNS preflight set")
            body = await read_bounded_body(response, self.max_response_bytes)

        after = await resolve_public_addresses(self.host)
        if before != after:
            raise FeedBoundaryError("sentiment feed DNS changed during retrieval")
        return body

    @staticmethod
    def _parse_rss(body: bytes) -> list[dict[str, Any]]:
        parsed = feedparser.parse(body)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            raise FeedBoundaryError("sentiment RSS payload could not be parsed")
        return [
            {
                "id": entry.get("id") or entry.get("link") or entry.get("title"),
                "title": entry.get("title", ""),
                "summary": entry.get("summary", ""),
                "url": entry.get("link", ""),
                "author": entry.get("author", ""),
            }
            for entry in parsed.entries
        ]

    def _parse_json(self, body: bytes) -> list[dict[str, Any]]:
        try:
            payload: Any = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FeedBoundaryError("sentiment JSON feed is not valid UTF-8 JSON") from exc
        cursor = payload
        for part in self.source_config.get("items_path", []):
            try:
                cursor = cursor[part]
            except (KeyError, IndexError, TypeError) as exc:
                raise FeedBoundaryError(
                    "sentiment JSON items_path does not resolve"
                ) from exc
        if not isinstance(cursor, list) or not all(
            isinstance(item, dict) for item in cursor
        ):
            raise FeedBoundaryError(
                "sentiment JSON items_path must resolve to a list of objects"
            )
        return [dict(item) for item in cursor]


class SentimentTracker:
    """Observe reviewed public sources and persist rule-matched events only.

    This component has no wallet, signing, transaction, order, broadcast, or
    capital authority. It performs bounded public-source reads and local
    telemetry writes.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        db: TelemetryDB,
        config: dict[str, Any],
        rules_path: str | Path,
    ) -> None:
        self.session = session
        self.db = db
        self.cooldown_minutes = int(config.get("cooldown_minutes", 10))
        self.poll_interval_seconds = int(config.get("poll_interval_seconds", 60))
        self.min_score = float(config.get("min_score", 3.0))
        self.spike_window_minutes = int(config.get("spike_window_minutes", 15))
        self.spike_threshold_count = int(config.get("spike_threshold_count", 5))
        with Path(rules_path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("sentiment rules root must be an object")
        self.rules = RuleEngine(payload)
        sources = config.get("sources", [])
        if not isinstance(sources, list) or not all(
            isinstance(item, dict) for item in sources
        ):
            raise ValueError("sentiment sources must be an array of objects")
        self.adapters = [FeedAdapter(session, source) for source in sources]

    async def run_forever(self) -> None:
        logger.info("Sentiment tracker starting")
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Sentiment tracker loop error")
            await asyncio.sleep(self.poll_interval_seconds)

    async def poll_once(self) -> None:
        for adapter in self.adapters:
            items = await adapter.fetch_items()
            source_name = str(adapter.source_config.get("name", "unknown"))
            for item in items:
                self._process_item(item, source_name)
        self._emit_spike_events()

    def _process_item(
        self,
        item: dict[str, Any],
        source_name: str,
    ) -> SentimentEvent | None:
        text = "\n".join(
            value
            for value in (
                str(item.get("title", "")),
                str(item.get("summary", "")),
            )
            if value
        ).strip()
        if not text:
            return None

        score_value, matched_rules = self.rules.score(text)
        if score_value < self.min_score:
            return None

        tickers = sorted(set(TICKER_RE.findall(text)))
        severity = (
            "critical"
            if score_value >= self.min_score * 3
            else "high"
            if score_value >= self.min_score * 2
            else "medium"
        )
        identity = str(item.get("id") or item.get("url") or text)
        stable_id = hashlib.sha256(
            f"{source_name}\0{identity}".encode("utf-8")
        ).hexdigest()[:24]
        dedupe_key = f"sentiment:{source_name}:{stable_id}"
        if self.db.is_duplicate(dedupe_key, self.cooldown_minutes):
            return None

        summary = f"score={score_value:.1f}, rules={', '.join(matched_rules)}"
        if tickers:
            summary += f" | tickers: {', '.join(tickers)}"
        event = SentimentEvent(
            event_type="sentiment_match",
            chain=None,
            source=source_name,
            severity=severity,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            dedupe_key=dedupe_key,
            title=f"Sentiment signal from {source_name}",
            summary=summary,
            data={
                "post_id": item.get("id"),
                "source_url": item.get("url"),
                "author": item.get("author"),
                "score_value": score_value,
                "matched_rules": matched_rules,
                "tickers": tickers,
                "raw_title": item.get("title", ""),
            },
            post_id=None if item.get("id") is None else str(item.get("id")),
            source_url=(
                None if item.get("url") is None else str(item.get("url"))
            ),
            author=(
                None if item.get("author") is None else str(item.get("author"))
            ),
            score_value=score_value,
            matched_rules=matched_rules,
            tickers=tickers,
        )
        self.db.save_event(event)
        return event

    def _emit_spike_events(self) -> list[SentimentEvent]:
        recent = self.db.recent_events(
            event_type="sentiment_match",
            minutes=self.spike_window_minutes,
        )
        ticker_counts: dict[str, int] = {}
        for event in recent:
            tickers = event.get("tickers") or event.get("data", {}).get("tickers") or []
            if not isinstance(tickers, Sequence) or isinstance(tickers, (str, bytes)):
                continue
            for ticker in tickers:
                ticker_text = str(ticker)
                ticker_counts[ticker_text] = ticker_counts.get(ticker_text, 0) + 1

        emitted: list[SentimentEvent] = []
        for ticker, count in ticker_counts.items():
            if count < self.spike_threshold_count:
                continue
            dedupe_key = f"sentiment_spike:{ticker}:{self.spike_window_minutes}"
            if self.db.is_duplicate(dedupe_key, self.cooldown_minutes):
                continue
            event = SentimentEvent(
                event_type="sentiment_spike",
                chain=None,
                source="burst_detector",
                severity=(
                    "high"
                    if count < self.spike_threshold_count * 2
                    else "critical"
                ),
                occurred_at=datetime.now(timezone.utc).isoformat(),
                dedupe_key=dedupe_key,
                title=f"Sentiment spike for ${ticker}",
                summary=(
                    f"{count} tracked posts in the last "
                    f"{self.spike_window_minutes} minutes crossed the spike threshold."
                ),
                data={
                    "ticker": ticker,
                    "count": count,
                    "window_minutes": self.spike_window_minutes,
                },
                score_value=float(count),
                matched_rules=["burst_detector"],
                tickers=[ticker],
            )
            self.db.save_event(event)
            emitted.append(event)
        return emitted


def build_sources(raw_sources: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy and validate configured sources before tracker construction."""

    sources = [dict(item) for item in raw_sources]
    for source in sources:
        validate_source_config(source)
    return sources
