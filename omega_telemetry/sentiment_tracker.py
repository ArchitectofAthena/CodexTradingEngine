"""Passive, rule-based sentiment telemetry with deterministic deduplication."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import aiohttp
import feedparser

from .db import TelemetryDB
from .models import SentimentEvent

logger = logging.getLogger(__name__)

TICKER_RE = re.compile(r"(?<!\w)\$([A-Z]{2,10})(?!\w)")


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
    def __init__(
        self,
        session: aiohttp.ClientSession,
        source_config: dict[str, Any],
    ) -> None:
        self.session = session
        self.source_config = source_config

    async def fetch_items(self) -> list[dict[str, Any]]:
        source_type = str(self.source_config.get("type", "")).casefold()
        if source_type == "rss":
            return await self._fetch_rss()
        if source_type == "json":
            return await self._fetch_json()
        raise ValueError(f"Unsupported sentiment source type: {source_type}")

    async def _fetch_rss(self) -> list[dict[str, Any]]:
        url = str(self.source_config["url"])
        timeout = aiohttp.ClientTimeout(total=20)
        async with self.session.get(url, timeout=timeout) as response:
            response.raise_for_status()
            text = await response.text()
        parsed = feedparser.parse(text)
        return [
            {
                "id": entry.get("id")
                or entry.get("link")
                or entry.get("title"),
                "title": entry.get("title", ""),
                "summary": entry.get("summary", ""),
                "url": entry.get("link", ""),
                "author": entry.get("author", ""),
            }
            for entry in parsed.entries
        ]

    async def _fetch_json(self) -> list[dict[str, Any]]:
        url = str(self.source_config["url"])
        items_path = self.source_config.get("items_path", [])
        if not isinstance(items_path, list):
            raise ValueError("JSON adapter items_path must be a list")
        timeout = aiohttp.ClientTimeout(total=20)
        async with self.session.get(url, timeout=timeout) as response:
            response.raise_for_status()
            payload: Any = await response.json()
        cursor = payload
        for part in items_path:
            cursor = cursor[part]
        if not isinstance(cursor, list) or not all(
            isinstance(item, dict) for item in cursor
        ):
            raise ValueError(
                "JSON adapter items_path did not resolve to a list of objects"
            )
        return list(cursor)


class SentimentTracker:
    """Observe configured public sources and persist rule-matched events only.

    This component has no wallet, signing, transaction, order, broadcast, or
    capital authority. It performs public-source reads and local telemetry writes.
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
        self.spike_threshold_count = int(
            config.get("spike_threshold_count", 5)
        )
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
            post_id=(
                None if item.get("id") is None else str(item.get("id"))
            ),
            source_url=(
                None if item.get("url") is None else str(item.get("url"))
            ),
            author=(
                None
                if item.get("author") is None
                else str(item.get("author"))
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
            tickers = (
                event.get("tickers")
                or event.get("data", {}).get("tickers")
                or []
            )
            if not isinstance(tickers, Sequence) or isinstance(
                tickers, (str, bytes)
            ):
                continue
            for ticker in tickers:
                ticker_text = str(ticker)
                ticker_counts[ticker_text] = (
                    ticker_counts.get(ticker_text, 0) + 1
                )

        emitted: list[SentimentEvent] = []
        for ticker, count in ticker_counts.items():
            if count < self.spike_threshold_count:
                continue
            dedupe_key = (
                f"sentiment_spike:{ticker}:{self.spike_window_minutes}"
            )
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
                    f"{self.spike_window_minutes} minutes crossed "
                    "the spike threshold."
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


def build_sources(
    raw_sources: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [dict(item) for item in raw_sources]
