from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from .db import TelemetryDB
from .models import Event

logger = logging.getLogger(__name__)


class SignalObserver:
    """Neutral context observer scaffold.

    This class records periodic context ticks into the local event store. It is
    intentionally read-only and contains no action hooks.
    """

    def __init__(self, db: TelemetryDB, config: Dict[str, Any]) -> None:
        self.db = db
        self.config = config
        self.name = str(config.get("name", "signal"))
        self.poll_interval_seconds = int(config.get("poll_interval_seconds", 30))

    async def run_forever(self) -> None:
        logger.info("Signal observer starting for %s", self.name)
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Signal observer loop error for %s", self.name)
            await asyncio.sleep(self.poll_interval_seconds)

    async def poll_once(self) -> None:
        observed_at = datetime.now(timezone.utc).isoformat()
        event = Event(
            event_type="signal_tick",
            chain=None,
            source=self.name,
            severity="low",
            occurred_at=observed_at,
            dedupe_key=f"signal_tick:{self.name}:{observed_at}",
            title=f"{self.name} signal tick",
            summary="Context observer heartbeat recorded.",
            data={"observer": self.name},
        )
        self.db.save_event(event)
