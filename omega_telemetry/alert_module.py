from __future__ import annotations

import logging
from typing import Any, Dict, List

import aiohttp

from .db import TelemetryDB
from .models import AlertResult, Event

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
        config: Dict[str, Any],
        shadow_mode: bool = True,
    ) -> None:
        self.session = session
        self.db = db
        self.config = config
        self.shadow_mode = shadow_mode

    async def dispatch(self, event: Event) -> List[AlertResult]:
        if self.shadow_mode:
            logger.info("SHADOW ALERT\n%s", format_event_message(event))
            result = AlertResult(channel="shadow", delivered=True, response="shadow_mode")
            self.db.log_alert(event.dedupe_key, result.channel, result.delivered, result.response)
            return [result]

        results: List[AlertResult] = []
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

    async def _send_telegram(self, event: Event, cfg: Dict[str, Any]) -> AlertResult:
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
                text = await resp.text()
                delivered = 200 <= resp.status < 300
                return AlertResult(channel="telegram", delivered=delivered, response=text[:500])
        except Exception as exc:
            return AlertResult(
                channel="telegram", delivered=False, response=f"{type(exc).__name__}: {exc}"
            )

    async def _send_discord(self, event: Event, cfg: Dict[str, Any]) -> AlertResult:
        webhook_url = cfg.get("webhook_url")
        if not webhook_url:
            return AlertResult(
                channel="discord", delivered=False, response="missing_discord_webhook"
            )

        try:
            async with self.session.post(
                webhook_url, json={"content": format_event_message(event)}
            ) as resp:
                text = await resp.text()
                delivered = 200 <= resp.status < 300
                return AlertResult(channel="discord", delivered=delivered, response=text[:500])
        except Exception as exc:
            return AlertResult(
                channel="discord", delivered=False, response=f"{type(exc).__name__}: {exc}"
            )
