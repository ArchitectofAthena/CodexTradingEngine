from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .config_tools import positive_int
from .db import TelemetryDB
from .models import AlertResult, Event, timestamp_age_seconds

logger = logging.getLogger(__name__)


def format_event_message(event: Event) -> str:
    prefix = {
        "critical": "🚨",
        "high": "⚠️",
        "medium": "🔎",
        "low": "ℹ️",
    }.get(event.severity, "ℹ️")
    lines = [
        f"{prefix} {event.title}",
        event.summary,
        f"Type: {event.event_type}",
    ]
    if event.chain:
        lines.append(f"Chain: {event.chain}")
    lines.append(f"Time: {event.occurred_at}")
    extra = event.data or {}
    if "confidence" in extra:
        lines.append(f"Confidence: {extra['confidence']}")
    if extra.get("quality_flags"):
        lines.append("Limitations: " + ", ".join(str(flag) for flag in extra["quality_flags"]))
    if "tx_hash" in extra:
        lines.append(f"Tx: {extra['tx_hash']}")
    if "source_url" in extra:
        lines.append(f"Link: {extra['source_url']}")
    return "\n".join(lines)


class AlertDispatcher:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        db: TelemetryDB,
        config: dict[str, Any],
        shadow_mode: bool = True,
    ) -> None:
        self.session = session
        self.db = db
        self.config = config
        self.shadow_mode = shadow_mode
        self.cooldown_minutes = positive_int(config.get("cooldown_minutes", 10), "cooldown_minutes")
        self.rate_window_seconds = positive_int(
            config.get("rate_window_seconds", 60), "rate_window_seconds"
        )
        self.max_alerts_per_window = positive_int(
            config.get("max_alerts_per_window", 20), "max_alerts_per_window", 100
        )
        self.max_event_age_seconds = positive_int(
            config.get("max_event_age_seconds", 900), "max_event_age_seconds"
        )
        self._dispatch_lock = asyncio.Lock()

    async def dispatch(self, event: Event) -> list[AlertResult]:
        # Serialize callers to this dispatcher so the read/check/delivery cannot race.
        async with self._dispatch_lock:
            age = timestamp_age_seconds(event.occurred_at)
            reason: str | None
            if age is None:
                reason = "invalid_timestamp"
            elif age < -30:
                reason = "future_event"
            elif age > self.max_event_age_seconds:
                reason = "stale_event"
            else:
                reason = self.db.alert_suppression_reason(
                    event.dedupe_key,
                    self.cooldown_minutes,
                    self.rate_window_seconds,
                    self.max_alerts_per_window,
                )
            if reason:
                result = AlertResult(channel="suppressed", delivered=False, response=reason)
                self.db.log_alert(
                    event.dedupe_key, result.channel, result.delivered, result.response
                )
                return [result]
            return await self._dispatch(event)

    async def _dispatch(self, event: Event) -> list[AlertResult]:
        if self.shadow_mode:
            logger.info("SHADOW ALERT\n%s", format_event_message(event))
            result = AlertResult(channel="shadow", delivered=True, response="shadow_mode")
            self.db.log_alert(event.dedupe_key, result.channel, result.delivered, result.response)
            return [result]

        results: list[AlertResult] = []
        telegram_cfg = self.config.get("telegram", {})
        discord_cfg = self.config.get("discord", {})

        if telegram_cfg.get("enabled"):
            results.append(await self._send_telegram(event, telegram_cfg))
        if discord_cfg.get("enabled"):
            results.append(await self._send_discord(event, discord_cfg))

        if not results:
            result = AlertResult(
                channel="shadow-fallback", delivered=False, response="no_channels_configured"
            )
            self.db.log_alert(event.dedupe_key, result.channel, result.delivered, result.response)
            return [result]

        for result in results:
            self.db.log_alert(event.dedupe_key, result.channel, result.delivered, result.response)
        return results

    async def _send_telegram(self, event: Event, cfg: dict[str, Any]) -> AlertResult:
        token = cfg.get("bot_token")
        chat_id = cfg.get("chat_id")
        if not token or not chat_id:
            return AlertResult(
                channel="telegram", delivered=False, response="missing_telegram_credentials"
            )

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": format_event_message(event),
            "disable_web_page_preview": True,
        }
        try:
            async with self.session.post(url, json=payload) as resp:
                delivered = 200 <= resp.status < 300
                return AlertResult(
                    channel="telegram", delivered=delivered, response=f"http_status:{resp.status}"
                )
        except Exception as exc:
            return AlertResult(channel="telegram", delivered=False, response=type(exc).__name__)

    async def _send_discord(self, event: Event, cfg: dict[str, Any]) -> AlertResult:
        webhook_url = cfg.get("webhook_url")
        if not webhook_url:
            return AlertResult(
                channel="discord", delivered=False, response="missing_discord_webhook"
            )

        try:
            async with self.session.post(
                webhook_url,
                json={"content": format_event_message(event), "allowed_mentions": {"parse": []}},
            ) as resp:
                delivered = 200 <= resp.status < 300
                return AlertResult(
                    channel="discord", delivered=delivered, response=f"http_status:{resp.status}"
                )
        except Exception as exc:
            return AlertResult(channel="discord", delivered=False, response=type(exc).__name__)
