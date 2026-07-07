import asyncio
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

import aiohttp
import feedparser

from omega_telemetry.models import SentimentEvent

logger = logging.getLogger(__name__)


TICKER_PATTERN = re.compile(r"(?<![A-Za-z0-9_])\$([A-Z][A-Z0-9]{1,9})(?![A-Za-z0-9_])")


@dataclass
class FeedSource:
    name: str
    url: str
    chain: str = "x"
    enabled: bool = True


@dataclass
class SentimentTrackerConfig:
    feeds: list[FeedSource] = field(default_factory=list)
    spike_threshold_count: int = 5
    spike_window_minutes: int = 15
    cooldown_minutes: int = 30
    request_timeout_seconds: int = 20


class SentimentTracker:
    """Passive sentiment observer.

    This tracker reads public feed-style sources, extracts ticker mentions,
    emits sentiment events, and detects short-window ticker spikes.

    Boundary:
    - no wallet access
    - no signing
    - no transaction construction
    - no broadcast
    - no capital movement
    """

    def __init__(
        self,
        db: Any = None,
        config: SentimentTrackerConfig | None = None,
    ) -> None:
        self.db = db
        self.config = config or SentimentTrackerConfig()
        self.spike_threshold_count = self.config.spike_threshold_count
        self.spike_window_minutes = self.config.spike_window_minutes
        self.cooldown_minutes = self.config.cooldown_minutes
        self.request_timeout_seconds = self.config.request_timeout_seconds

    async def fetch_text(self, session: aiohttp.ClientSession, url: str) -> str:
        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        async with session.get(url, timeout=timeout) as response:
            response.raise_for_status()
            return await response.text()

    async def fetch_feed_entries(self, source: FeedSource) -> list[dict[str, Any]]:
        if not source.enabled:
            return []

        try:
            async with aiohttp.ClientSession() as session:
                text = await self.fetch_text(session, source.url)
        except Exception as exc:  # pragma: no cover - network defensive path
            logger.warning("Failed to fetch sentiment feed %s: %s", source.name, exc)
            return []

        parsed = feedparser.parse(text)
        entries: list[dict[str, Any]] = []

        for entry in parsed.entries:
            title = str(entry.get("title", "") or "")
            summary = str(entry.get("summary", "") or "")
            link = str(entry.get("link", "") or "")

            entries.append(
                {
                    "source": source.name,
                    "chain": source.chain,
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "raw": entry,
                }
            )

        return entries

    async def fetch_all_entries(self) -> list[dict[str, Any]]:
        tasks = [self.fetch_feed_entries(source) for source in self.config.feeds if source.enabled]

        if not tasks:
            return []

        results = await asyncio.gather(*tasks)
        entries: list[dict[str, Any]] = []

        for batch in results:
            entries.extend(batch)

        return entries

    @staticmethod
    def extract_tickers(text: str) -> list[str]:
        return sorted({match.group(1).upper() for match in TICKER_PATTERN.finditer(text)})

    @staticmethod
    def score_entry(text: str, tickers: Iterable[str]) -> float:
        ticker_count = len(list(tickers))
        text_length_factor = min(len(text) / 500.0, 1.0)
        return round(float(ticker_count) + text_length_factor, 4)

    def build_event_from_entry(self, entry: dict[str, Any]) -> SentimentEvent | None:
        title = str(entry.get("title", "") or "")
        summary_text = str(entry.get("summary", "") or "")
        combined_text = f"{title}\n{summary_text}".strip()
        tickers = self.extract_tickers(combined_text)

        if not tickers:
            return None

        source = str(entry.get("source", "unknown"))
        chain = str(entry.get("chain", "x"))
        link = str(entry.get("link", "") or "")
        score_value = self.score_entry(combined_text, tickers)

        dedupe_key = f"sentiment_post:{source}:{hash(combined_text)}"

        return SentimentEvent(
            event_type="sentiment_observation",
            chain=chain,
            source=source,
            severity="medium",
            occurred_at=datetime.now(timezone.utc).isoformat(),
            dedupe_key=dedupe_key,
            title=title or "Sentiment observation",
            summary={
                "text": summary_text,
                "tickers": tickers,
                "ticker_count": len(tickers),
            },
            post_id=None,
            source_url=link or None,
            author=None,
            score_value=score_value,
            matched_rules=["ticker_mention"],
            tickers=tickers,
        )

    def save_event(self, event: SentimentEvent) -> None:
        if self.db is None:
            logger.info("Sentiment event observed without db: %s", event.title)
            return

        if hasattr(self.db, "check_dedupe_key") and self.db.check_dedupe_key(
            event.dedupe_key,
            self.cooldown_minutes,
        ):
            return

        self.db.save_event(event)

    def save_events(self, events: Iterable[SentimentEvent]) -> None:
        for event in events:
            self.save_event(event)

    def detect_spikes(self, events: Iterable[SentimentEvent]) -> list[SentimentEvent]:
        ticker_counts: Counter[str] = Counter()

        for event in events:
            for ticker in getattr(event, "tickers", []) or []:
                ticker_counts[ticker] += 1

        spike_events: list[SentimentEvent] = []

        for ticker, count in ticker_counts.items():
            if count < self.spike_threshold_count:
                continue

            dedupe_key = f"sentiment_spike:{ticker}:{self.spike_window_minutes}"
            if self.db and self.db.check_dedupe_key(
                dedupe_key,
                self.cooldown_minutes,
            ):
                continue

            title = (
                f"Sentiment spike for ${ticker}: "
                f"{count} tracked posts in the last "
                f"{self.spike_window_minutes} minutes crossed "
                "the spike threshold."
            )

            event = SentimentEvent(
                event_type="sentiment_spike",
                chain="x",
                source="burst_detector",
                severity="high" if count < self.spike_threshold_count * 2 else "critical",
                occurred_at=datetime.now(timezone.utc).isoformat(),
                dedupe_key=dedupe_key,
                title=title,
                summary={
                    "ticker": ticker,
                    "count": count,
                    "window_minutes": self.spike_window_minutes,
                },
                post_id=None,
                source_url=None,
                author=None,
                score_value=float(count),
                matched_rules=["burst_detector"],
                tickers=[ticker],
            )

            spike_events.append(event)
            logger.info("Sentiment spike: %s -> %s", ticker, count)

        return spike_events

    async def run_once(self) -> list[SentimentEvent]:
        entries = await self.fetch_all_entries()
        events: list[SentimentEvent] = []

        for entry in entries:
            event = self.build_event_from_entry(entry)
            if event is not None:
                events.append(event)

        spike_events = self.detect_spikes(events)
        all_events = events + spike_events
        self.save_events(all_events)

        return all_events


def build_sources(raw_sources: Iterable[dict[str, Any]]) -> list[FeedSource]:
    sources: list[FeedSource] = []

    for item in raw_sources:
        sources.append(
            FeedSource(
                name=str(item.get("name", "unknown")),
                url=str(item.get("url", "")),
                chain=str(item.get("chain", "x")),
                enabled=bool(item.get("enabled", True)),
            )
        )

    return sources


def build_tracker_from_config(
    config: dict[str, Any],
    db: Any = None,
) -> SentimentTracker:
    sentiment_config = config.get("sentiment_tracker", config)
    sources = build_sources(sentiment_config.get("feeds", []))

    tracker_config = SentimentTrackerConfig(
        feeds=sources,
        spike_threshold_count=int(sentiment_config.get("spike_threshold_count", 5)),
        spike_window_minutes=int(sentiment_config.get("spike_window_minutes", 15)),
        cooldown_minutes=int(sentiment_config.get("cooldown_minutes", 30)),
        request_timeout_seconds=int(sentiment_config.get("request_timeout_seconds", 20)),
    )

    return SentimentTracker(db=db, config=tracker_config)
