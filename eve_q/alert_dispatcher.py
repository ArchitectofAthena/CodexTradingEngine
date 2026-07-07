"""Enhanced alert system with retry logic and shadow-mode safety.

The dispatcher defaults to shadow mode. In shadow mode it returns a synthetic
success result and never performs outbound HTTP calls.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class AlertChannel(str, Enum):
    """Supported alert channels."""

    TELEGRAM = "telegram"
    DISCORD = "discord"
    WEBHOOK = "webhook"
    EMAIL = "email"


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff retry policy."""

    max_retries: int = 3
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    backoff_multiplier: float = 2.0

    def get_backoff(self, attempt: int) -> float:
        """Calculate backoff duration for an attempt number."""
        backoff = self.initial_backoff_seconds * (self.backoff_multiplier**attempt)
        return min(backoff, self.max_backoff_seconds)


@dataclass
class AlertDeduplicationWindow:
    """Sliding window deduplication for alerts."""

    window_minutes: int = 15
    dedupe_keys: Dict[str, datetime] = field(default_factory=dict)

    def is_duplicate(self, key: str) -> bool:
        """Return True when key already appeared within the active window."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=self.window_minutes)

        self.dedupe_keys = {key_: ts for key_, ts in self.dedupe_keys.items() if ts > cutoff}

        if key in self.dedupe_keys:
            return True

        self.dedupe_keys[key] = now
        return False

    def reset(self) -> None:
        """Clear deduplication state."""
        self.dedupe_keys.clear()


@dataclass(frozen=True)
class AlertResult:
    """Result of alert dispatch."""

    channel: str
    delivered: bool
    response: str
    attempt: int = 1
    error: Optional[str] = None


SendFunc = Callable[..., Awaitable[AlertResult]]


class AlertDispatcher:
    """Enhanced alert dispatcher with retry, deduplication, and shadow-mode safety.

    Safety boundary:
    - shadow_mode=True never sends outbound HTTP requests.
    - non-shadow mode still requires explicit per-channel enabled config.
    - alerts are external effects only; they do not authorize execution or capital movement.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        config: Dict[str, Any],
        retry_policy: Optional[RetryPolicy] = None,
        shadow_mode: bool = True,
    ) -> None:
        """Initialize alert dispatcher."""
        self.session = session
        self.config = config
        self.retry_policy = retry_policy or RetryPolicy()
        self.shadow_mode = shadow_mode
        self.dedup_window = AlertDeduplicationWindow()

    async def send(
        self,
        severity: str,
        title: str,
        summary: str,
        dedupe_key: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> List[AlertResult]:
        """Send alert to configured channels with retry.

        In shadow mode this method logs and returns a synthetic result without
        touching Telegram, Discord, webhook, or any other external endpoint.
        """
        if dedupe_key and self.dedup_window.is_duplicate(dedupe_key):
            logger.debug("Duplicate alert suppressed: %s", dedupe_key)
            return []

        message = self._format_message(severity, title, summary, data)

        if self.shadow_mode:
            logger.info("SHADOW ALERT [%s]\n%s", severity, message)
            return [
                AlertResult(
                    channel="shadow",
                    delivered=True,
                    response="shadow_mode_no_external_send",
                )
            ]

        results: List[AlertResult] = []

        telegram_cfg = self.config.get("telegram", {})
        discord_cfg = self.config.get("discord", {})
        webhook_cfg = self.config.get("webhook", {})

        if telegram_cfg.get("enabled"):
            results.append(
                await self._send_with_retry(
                    self._send_telegram,
                    title,
                    message,
                    telegram_cfg,
                    channel=AlertChannel.TELEGRAM,
                )
            )

        if discord_cfg.get("enabled"):
            results.append(
                await self._send_with_retry(
                    self._send_discord,
                    title,
                    message,
                    discord_cfg,
                    channel=AlertChannel.DISCORD,
                )
            )

        if webhook_cfg.get("enabled"):
            payload = {"title": title, "message": message, "severity": severity, "data": data}
            results.append(
                await self._send_with_retry(
                    self._send_webhook,
                    payload,
                    webhook_cfg,
                    channel=AlertChannel.WEBHOOK,
                )
            )

        return results

    async def _send_with_retry(
        self,
        send_func: SendFunc,
        *args: Any,
        channel: AlertChannel,
    ) -> AlertResult:
        """Send alert with exponential backoff retry."""
        last_error: Optional[str] = None

        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                result = await send_func(*args)
                if result.delivered:
                    return result
                last_error = result.error or result.response
            except Exception as exc:  # pragma: no cover - error path tested by callers
                last_error = str(exc)
                logger.warning(
                    "Alert send failed (attempt %s/%s): %s",
                    attempt + 1,
                    self.retry_policy.max_retries + 1,
                    exc,
                )

            if attempt < self.retry_policy.max_retries:
                backoff = self.retry_policy.get_backoff(attempt)
                await asyncio.sleep(backoff)

        return AlertResult(
            channel=channel.value,
            delivered=False,
            response="Failed after max retries",
            attempt=self.retry_policy.max_retries + 1,
            error=last_error,
        )

    async def _send_telegram(
        self,
        title: str,
        message: str,
        cfg: Dict[str, Any],
    ) -> AlertResult:
        """Send alert via Telegram."""
        token = cfg.get("bot_token")
        chat_id = cfg.get("chat_id")
        if not token or not chat_id:
            return AlertResult(
                channel="telegram",
                delivered=False,
                response="Missing credentials",
                error="missing_credentials",
            )

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": f"*{title}*\n\n{message}",
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        async with self.session.post(
            url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            text = await resp.text()
            delivered = 200 <= resp.status < 300
            return AlertResult(
                channel="telegram",
                delivered=delivered,
                response=text[:500] or "OK",
            )

    async def _send_discord(
        self,
        title: str,
        message: str,
        cfg: Dict[str, Any],
    ) -> AlertResult:
        """Send alert via Discord."""
        webhook_url = cfg.get("webhook_url")
        if not webhook_url:
            return AlertResult(
                channel="discord",
                delivered=False,
                response="Missing webhook URL",
                error="missing_webhook_url",
            )

        payload = {
            "embeds": [
                {
                    "title": title,
                    "description": message,
                    "color": 16711680,
                }
            ]
        }

        async with self.session.post(
            webhook_url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            text = await resp.text()
            delivered = 200 <= resp.status < 300
            return AlertResult(
                channel="discord",
                delivered=delivered,
                response=text[:500] or "OK",
            )

    async def _send_webhook(
        self,
        payload: Dict[str, Any],
        cfg: Dict[str, Any],
    ) -> AlertResult:
        """Send alert via custom webhook."""
        webhook_url = cfg.get("url")
        if not webhook_url:
            return AlertResult(
                channel="webhook",
                delivered=False,
                response="Missing webhook URL",
                error="missing_webhook_url",
            )

        async with self.session.post(
            webhook_url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            text = await resp.text()
            delivered = 200 <= resp.status < 300
            return AlertResult(
                channel="webhook",
                delivered=delivered,
                response=text[:500] or "OK",
            )

    @staticmethod
    def _format_message(
        severity: str,
        title: str,
        summary: str,
        data: Optional[Dict[str, Any]],
    ) -> str:
        """Format alert message."""
        emoji = {"critical": "🚨", "high": "⚠️", "medium": "🔎", "low": "ℹ️"}.get(
            severity,
            "ℹ️",
        )
        lines = [f"{emoji} {title}", summary]
        if data:
            for key, value in data.items():
                lines.append(f"{key}: {value}")
        return "\n".join(lines)
