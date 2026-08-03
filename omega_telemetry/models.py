"""Validated, serialization-safe models for passive Omega telemetry."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Event:
    event_type: str
    chain: str | None
    source: str
    severity: str
    occurred_at: str
    dedupe_key: str
    title: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ChainSignalEvent(Event):
    """Compatibility marker for generic chain-derived observations."""


@dataclass(slots=True)
class WhaleEvent(Event):
    amount: str | None = None
    asset_symbol: str | None = None
    usd_value: str | None = None
    from_address: str | None = None
    to_address: str | None = None
    from_label: str | None = None
    to_label: str | None = None
    tx_hash: str | None = None


@dataclass(slots=True)
class SentimentEvent(Event):
    post_id: str | None = None
    source_url: str | None = None
    author: str | None = None
    score_value: float | None = None
    matched_rules: list[str] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class AlertResult:
    channel: str
    delivered: bool
    response: str


@dataclass(slots=True, frozen=True)
class PricePoint:
    symbol: str
    usd: Decimal
    source: str
    observed_at: str = field(default_factory=utc_now_iso)
