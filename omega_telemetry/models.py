from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


@dataclass(slots=True)
class Event:
    event_type: str
    chain: Optional[str]
    source: str
    severity: str
    occurred_at: str
    dedupe_key: str
    title: str
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WhaleEvent(Event):
    amount: Optional[str] = None
    asset_symbol: Optional[str] = None
    usd_value: Optional[str] = None
    from_address: Optional[str] = None
    to_address: Optional[str] = None
    from_label: Optional[str] = None
    to_label: Optional[str] = None
    tx_hash: Optional[str] = None


@dataclass(slots=True)
class SentimentEvent(Event):
    post_id: Optional[str] = None
    source_url: Optional[str] = None
    author: Optional[str] = None
    score_value: Optional[float] = None
    matched_rules: List[str] = field(default_factory=list)
    tickers: List[str] = field(default_factory=list)


@dataclass(slots=True)
class AlertResult:
    channel: str
    delivered: bool
    response: str


@dataclass(slots=True)
class PricePoint:
    symbol: str
    usd: Decimal
    source: str
    observed_at: str = field(default_factory=iso_now)
