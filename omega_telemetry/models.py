"""Telemetry models with enhanced typing.

This module provides validated data models for telemetry events, alerts, and pricing data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from dataclasses import dataclass, field, asdict


def utc_now_iso() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PricePoint:
    """A pricing data point.

    Attributes:
        symbol: Asset symbol (e.g., 'ETH', 'BTC').
        usd: Price in USD.
        source: Source of price data (e.g., 'coingecko').
        timestamp: When this price was fetched.
    """

    symbol: str
    usd: float
    source: str = "unknown"
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class Event:
    """A telemetry event.

    Attributes:
        event_type: Type of event (e.g., 'arb_found', 'execution_error').
        title: Short title.
        summary: Longer description.
        severity: Severity level (critical, high, medium, low).
        source: Event source (e.g., 'pricing_engine', 'execution_loop').
        chain: Blockchain chain if applicable.
        occurred_at: When the event occurred (ISO format).
        data: Additional structured data.
        dedupe_key: Key for deduplication.
    """

    event_type: str
    title: str
    summary: str
    severity: str
    source: str
    occurred_at: str
    chain: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    dedupe_key: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate and initialize dedupe key."""
        if self.dedupe_key is None:
            self.dedupe_key = f"{self.event_type}:{self.chain or 'global'}:{self.source}"
        if self.data is None:
            self.data = {}

    def to_record(self) -> Dict[str, Any]:
        """Convert to database record."""
        return {
            "event_type": self.event_type,
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "source": self.source,
            "chain": self.chain,
            "occurred_at": self.occurred_at,
            "dedupe_key": self.dedupe_key,
            "data": self.data,
        }


@dataclass
class SentimentEvent(Event):
    """Telemetry event specialized for sentiment surfaces.

    This preserves the package import surface expected by omega_telemetry
    while keeping sentiment events compatible with the generic Event model.
    """

    sentiment: Optional[str] = None
    score: Optional[float] = None

    def to_record(self) -> Dict[str, Any]:
        """Convert to database record with optional sentiment fields."""
        record = super().to_record()
        if self.sentiment is not None:
            record["sentiment"] = self.sentiment
        if self.score is not None:
            record["score"] = self.score
        return record


@dataclass
class ChainSignalEvent(Event):
    """Telemetry event specialized for chain signal surfaces."""

    def to_record(self) -> Dict[str, Any]:
        """Convert to database record with a chain-signal marker."""
        record = super().to_record()
        record["chain_signal"] = True
        return record


@dataclass(frozen=True)
class AlertResult:
    """Result of an alert dispatch attempt.

    Attributes:
        channel: Alert channel (e.g., 'telegram', 'discord').
        delivered: Whether alert was successfully delivered.
        response: Response from the alert service.
    """

    channel: str
    delivered: bool
    response: str
