from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import aiohttp
import feedparser

from .db import TelemetryDB
from .models import SentimentEvent

logger = logging.getLogger(__name__)

TICKER_RE = re.compile(r"(?<!\w)\$([A-Z]{2,10})(?!\w)")


@dataclass(slots=True)
class Rule:
    name: str
    category: str
    weight: float
    patterns: List[str]
    case_sensitive: bool = False


class RuleEngine:
    def __init__(self, rule_payload: Dict[str, Any]) -> None:
        self.rules: List[Rule] = []
        for item in rule_payload.get("rules", []):
            self.rules.append(
                Rule(
                    name=item["name"],
                    category=item["category"],
                    weight=float(item["weight"]),
                    patterns=list(item["patterns"]),
                    case_sensitive=bool(item.get("case_sensitive", False)),
                )
            )

    def score(self, text: str) -> Tuple[float, List[str]]:
        total = 0.0
        matched: List[str] = []
        for rule in self.rules:
            haystack = text if rule.case_sensitive else text.lower()
            patterns = rule.patterns if rule.case_sensitive else [p.lower() for p in rule.patterns]
            if any(pattern in haystack for pattern in patterns):
                total += rule.weight
                matched.append(rule.name)
        return total, matched


class FeedAdapter:
    def __init__(self, session: aiohttp.ClientSession, source_cfg: Dict[str, Any]) -> None:
        self.session = session
        self.source_cfg = source_cfg

    async def fetch_items(self) -> List[Dict[str, Any]]:
        source_type = self.source_cfg["type"]
        if source_type == "rss":
            return await self._fetch_rss()
        if source_type == "json":
            return await self._fetch_json()
        raise ValueError(f"Unsupported sentiment source type: {source_type}")

    async def _fetch_rss(self) -> List[Dict[str, Any]]:
        url = self.source_cfg["url"]
        async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            resp.raise_for_status()
            text = await resp.text()
        parsed = feedparser.parse(text)
        items: List[Dict[str, Any]] = []
        for entry in parsed.entries:
            items.append(
                {
                    "id": entry.get("id") or entry.get("link") or entry.get("title"),
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "url": entry.get("link", ""),
                    "author": entry.get("author", ""),
                    "published": entry.get("published", ""),
                }
            )
        return items

    async def _fetch_json(self) -> List[Dict[str, Any]]:
        url = self.source_cfg["url"]
        items_path = self.source_cfg.get("items_path", [])
        async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            resp.raise_for_status()
            payload = await resp.json()
        cursor: Any = payload
        for part in items_path:
            cursor = cursor[part]
        if not isinstance(cursor, list):
            raise ValueError("JSON adapter items_path did not resolve to a list")
        return list(cursor)


class SentimentTracker:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        db: TelemetryDB,
        config: Dict[str, Any],
        rules_path: str,
    ) -> None:
        self.session = session
        self.db = db
        self.config = config
        self.cooldown_minutes = int(config.get("cooldown_minutes", 10))
        self.poll_interval_seconds = int(config.get("poll_interval_seconds", 60))
        self.min_score = float(config.get("min_score", 3.0))
        self.spike_window_minutes = int(config.get("spike_window_minutes", 15))
        self.spike_threshold_count = int(config.get("spike_threshold_count", 5))
        with open(rules_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.rules = RuleEngine(payload)
        self.adapters = [FeedAdapter(session, src) for src in config.get("sources", [])]

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
            for item in items:
                await self._process_item(item, adapter.source_cfg.get("name", "unknown"))
        await self._emit_spike_events()

    async def _process_item(self, item: Dict[str, Any], source_name: str) -> None:
        text_parts = [item.get("title", ""), item.get("summary", "")]
        text = "\n".join(part for part in text_parts if part).strip()
        if not text:
            return

        score_value, matched_rules = self.rules.score(text)
        if score_value < self.min_score:
            return

        tickers = sorted(set(TICKER_RE.findall(text)))
        severity = "critical" if score_value >= self.min_score * 3 else "high" if score_value >= self.min_score * 2 else "medium"
        dedupe_key = f"sentiment:{source_name}:{item.get('id')}"
        if self.db.is_duplicate(dedupe_key, self.cooldown_minutes):
            return

        ticker_text = f" | tickers: {', '.join(tickers)}" if tickers else ""
        event = SentimentEvent(
            event_type="sentiment_match",
            chain=None,
            source=source_name,
            severity=severity,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            dedupe_key=dedupe_key,
            title=f"Sentiment signal from {source_name}",
            summary=f"score={score_value:.1f}, rules={', '.join(matched_rules)}{ticker_text}",
            data={
                "post_id": item.get("id"),
                "source_url": item.get("url"),
                "author": item.get("author"),
                "score_value": score_value,
                "matched_rules": matched_rules,
                "tickers": tickers,
                "raw_title": item.get("title", ""),
            },
            post_id=item.get("id"),
            source_url=item.get("url"),
            author=item.get("author"),
            score_value=score_value,
            matched_rules=matched_rules,
            tickers=tickers,
        )
        self.db.save_event(event)
        logger.info("Sentiment event: %s", event.summary)

    async def _emit_spike_events(self) -> None:
        recent = self.db.recent_events(event_type="sentiment_match", minutes=self.spike_window_minutes)
        ticker_counts: Dict[str, int] = {}
        for event in recent:
            tickers = event.get("tickers") or event.get("data", {}).get("tickers") or []
            for ticker in tickers:
                ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1

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
                severity="high" if count < self.spike_threshold_count * 2 else "critical",
                occurred_at=datetime.now(timezone.utc).isoformat(),
                dedupe_key=dedupe_key,
                title=f"Sentiment spike for ${ticker}",
                summary=f"{count} tracked posts in the last {self.spike_window_minutes} minutes crossed the spike threshold.",
                data={"ticker": ticker, "count": count, "window_minutes": self.spike_window_minutes},
                post_id=None,
                source_url=None,
                author=None,
                score_value=float(count),
                matched_rules=["burst_detector"],
                tickers=[ticker],
            )
            self.db.save_event(event)
            logger.info("Sentiment spike: %s -> %s", ticker, count)
