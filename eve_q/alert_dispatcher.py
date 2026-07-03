"""Enhanced alert system with retry logic and deduplication.

This module provides robust alert dispatching with exponential backoff retry,
sliding window deduplication, and multi-channel support.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

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
    """Exponential backoff retry policy.
    
    Attributes:
        max_retries: Maximum number of retry attempts.
        initial_backoff_seconds: Initial backoff duration.
        max_backoff_seconds: Maximum backoff duration.
        backoff_multiplier: Exponential backoff multiplier.
    """
    max_retries: int = 3
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    backoff_multiplier: float = 2.0

    def get_backoff(self, attempt: int) -> float:
        """Calculate backoff duration for attempt number.
        
        Args:
            attempt: Attempt number (0-indexed).
            
        Returns:
            Backoff duration in seconds.
        """
        backoff = self.initial_backoff_seconds * (self.backoff_multiplier ** attempt)
        return min(backoff, self.max_backoff_seconds)


@dataclass
class AlertDeduplicationWindow:
    """Sliding window deduplication for alerts.
    
    Attributes:
        window_minutes: Deduplication window size in minutes.
        dedupe_keys: Set of recent dedupe keys within window.
        timestamps: Timestamps of alerts.
    """
    window_minutes: int = 15
    dedupe_keys: Dict[str, datetime] = field(default_factory=dict)

    def is_duplicate(self, key: str) -> bool:
        """Check if alert is a duplicate within the window.
        
        Args:
            key: Deduplication key.
            
        Returns:
            True if duplicate within window.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=self.window_minutes)

        # Clean up old entries
        self.dedupe_keys = {
            k: v for k, v in self.dedupe_keys.items() if v > cutoff
        }

        if key in self.dedupe_keys:
            return True

        self.dedupe_keys[key] = now
        return False

    def reset(self) -> None:
        """Clear deduplication state."""
        self.dedupe_keys.clear()


@dataclass(frozen=True)
class AlertResult:
    """Result of alert dispatch.
    
    Attributes:
        channel: Alert channel used.
        delivered: Whether alert was successfully delivered.
        response: Response from service.
        attempt: Attempt number.
        error: Error message if applicable.
    """
    channel: str
    delivered: bool
    response: str
    attempt: int = 1
    error: Optional[str] = None


class AlertDispatcher:
    """Enhanced alert dispatcher with retry and deduplication.
    
    Example:
        >>> dispatcher = AlertDispatcher(
        ...     session=aiohttp.ClientSession(),
        ...     config={
        ...         "telegram": {
        ...             "enabled": True,
        ...             "bot_token": "...",
        ...             "chat_id": "...",
        ...         }
        ...     }
        ... )
        >>> result = await dispatcher.send("critical", "System Alert", "Details...")
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        config: Dict[str, Any],
        retry_policy: Optional[RetryPolicy] = None,
        shadow_mode: bool = True,
    ) -> None:
        """Initialize alert dispatcher.
        
        Args:
            session: aiohttp ClientSession for HTTP requests.
            config: Configuration dict with channel settings.
            retry_policy: Exponential backoff retry policy.
            shadow_mode: If True, log alerts instead of sending.
        """
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
        
        Args:
            severity: Alert severity (critical, high, medium, low).
            title: Alert title.
            summary: Alert summary/body.
            dedupe_key: Optional key for deduplication.
            data: Additional structured data.
            
        Returns:
            List of AlertResult for each channel attempt.
        """
        if dedupe_key and self.dedup_window.is_duplicate(dedupe_key):
            logger.debug(f"Duplicate alert suppressed: {dedupe_key}")
            return []

        message = self._format_message(severity, title, summary, data)

        if self.shadow_mode:
            logger.info(f"SHADOW ALERT [{severity}]\n{message}")
            return [
                AlertResult(
                    channel="shadow",
                    delivered=True,
                    response="shadow_mode",
                )
            ]

        results: List[AlertResult] = []

        telegram_cfg = self.config.get("telegram", {})
        discord_cfg = self.config.get("discord", {})
        webhook_cfg = self.config.get("webhook", {})

        if telegram_cfg.get("enabled"):
            result = await self._send_with_retry(
                self._send_telegram,
                title,
                message,
                telegram_cfg,
                AlertChannel.TELEGRAM,
            )
            results.append(result)

        if discord_cfg.get("enabled"):
            result = await self._send_with_retry(
                self._send_discord,
                title,
                message,
                discord_cfg,
                AlertChannel.DISCORD,
            )
            results.append(result)

        if webhook_cfg.get("enabled"):
            result = await self._send_with_retry(
                self._send_webhook,
                {"title": title, "message": message, "severity": severity, "data": data},
                None,
                webhook_cfg,
                AlertChannel.WEBHOOK,
            )
            results.append(result)

        return results

    async def _send_with_retry(
        self,
        send_func: Callable,
        *args: Any,
        channel: AlertChannel,
    ) -> AlertResult:
        """Send alert with exponential backoff retry.
        
        Args:
            send_func: Async function to call.
            args: Arguments to pass to send_func.
            channel: Alert channel.
            
        Returns:
            AlertResult after final attempt.
        """
        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                result = await send_func(*args)
                if result.delivered:
                    return result
            except Exception as exc:
                logger.warning(
                    f"Alert send failed (attempt {attempt + 1}/{self.retry_policy.max_retries + 1}): {exc}"
                )

            if attempt < self.retry_policy.max_retries:
                backoff = self.retry_policy.get_backoff(attempt)
                await asyncio.sleep(backoff)

        return AlertResult(
            channel=channel.value,
            delivered=False,
            response="Failed after max retries",
            attempt=self.retry_policy.max_retries + 1,
        )

    async def _send_telegram(
        self, title: str, message: str, cfg: Dict[str, Any]
    ) -> AlertResult:
        """Send alert via Telegram.
        
        Args:
            title: Alert title.
            message: Alert message.
            cfg: Telegram config.
            
        Returns:
            AlertResult.
        """
        token = cfg.get("bot_token")
        chat_id = cfg.get("chat_id")
        if not token or not chat_id:
            return AlertResult(
                channel="telegram",
                delivered=False,
                response="Missing credentials",
            )

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": f"*{title}*\n\n{message}",
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        try:
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                text = await resp.text()
                delivered = 200 <= resp.status < 300
                return AlertResult(
                    channel="telegram",
                    delivered=delivered,
                    response=text[:500],
                )
        except Exception as exc:
            raise exc

    async def _send_discord(
        self, title: str, message: str, cfg: Dict[str, Any]
    ) -> AlertResult:
        """Send alert via Discord.
        
        Args:
            title: Alert title.
            message: Alert message.
            cfg: Discord config.
            
        Returns:
            AlertResult.
        """
        webhook_url = cfg.get("webhook_url")
        if not webhook_url:
            return AlertResult(
                channel="discord",
                delivered=False,
                response="Missing webhook URL",
            )

        payload = {
            "embeds": [
                {
                    "title": title,
                    "description": message,
                    "color": 16711680,  # Red
                }
            ]
        }

        try:
            async with self.session.post(
                webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                text = await resp.text()
                delivered = 200 <= resp.status < 300
                return AlertResult(
                    channel="discord",
                    delivered=delivered,
                    response=text[:500] or "OK",
                )
        except Exception as exc:
            raise exc

    async def _send_webhook(
        self, payload: Dict[str, Any], _unused: Any, cfg: Dict[str, Any]
    ) -> AlertResult:
        """Send alert via custom webhook.
        
        Args:
            payload: Alert payload.
            _unused: Unused parameter for consistency.
            cfg: Webhook config.
            
        Returns:
            AlertResult.
        """
        webhook_url = cfg.get("url")
        if not webhook_url:
            return AlertResult(
                channel="webhook",
                delivered=False,
                response="Missing webhook URL",
            )

        try:
            async with self.session.post(
                webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                text = await resp.text()
                delivered = 200 <= resp.status < 300
                return AlertResult(
                    channel="webhook",
                    delivered=delivered,
                    response=text[:500] or "OK",
                )
        except Exception as exc:
            raise exc

    @staticmethod
    def _format_message(
        severity: str, title: str, summary: str, data: Optional[Dict[str, Any]]
    ) -> str:
        """Format alert message.
        
        Args:
            severity: Alert severity.
            title: Alert title.
            summary: Alert summary.
            data: Additional data.
            
        Returns:
            Formatted message string.
        """
        emoji = {"critical": "🚨", "high": "⚠️", "medium": "🔎", "low": "ℹ️"}.get(
            severity, "ℹ️"
        )
        lines = [f"{emoji} {title}", summary]
        if data:
            for key, value in data.items():
                lines.append(f"{key}: {value}")
        return "\n".join(lines)
