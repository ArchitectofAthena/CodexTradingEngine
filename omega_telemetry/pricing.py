from __future__ import annotations

import json
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

from .config_tools import positive_int
from .models import PricePoint


class PriceResolver:
    """CoinGecko-backed USD price resolver for telemetry context."""

    COINGECKO_SIMPLE_PRICE = "https://api.coingecko.com/api/v3/simple/price"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        symbol_to_id: dict[str, str],
        timeout_seconds: int = 15,
        cache_ttl_seconds: int = 60,
    ) -> None:
        self.session = session
        self.symbol_to_id = {k.upper(): v for k, v in symbol_to_id.items()}
        self.timeout_seconds = positive_int(timeout_seconds, "price timeout", 60)
        self.cache_ttl_seconds = positive_int(cache_ttl_seconds, "price cache TTL", 60)
        self._cache: dict[str, PricePoint] = {}
        self._cached_at: dict[str, float] = {}

    async def get_usd_price(self, symbol: str) -> PricePoint | None:
        symbol_up = symbol.upper()
        if (
            symbol_up in self._cache
            and 0 <= time.monotonic() - self._cached_at[symbol_up] < self.cache_ttl_seconds
        ):
            return self._cache[symbol_up]
        self._cache.pop(symbol_up, None)
        self._cached_at.pop(symbol_up, None)

        coin_id = self.symbol_to_id.get(symbol_up)
        if not coin_id:
            return None

        params = {"ids": coin_id, "vs_currencies": "usd"}
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        try:
            async with self.session.get(
                self.COINGECKO_SIMPLE_PRICE, params=params, timeout=timeout, allow_redirects=False
            ) as resp:
                if 300 <= resp.status < 400:
                    return None
                resp.raise_for_status()
                payload: Any = await resp.json(
                    loads=lambda body: json.loads(body, parse_float=Decimal)
                )
            if not isinstance(payload, dict) or not isinstance(payload.get(coin_id), dict):
                return None
            raw = payload[coin_id].get("usd")
            if isinstance(raw, bool) or not isinstance(raw, (str, int, Decimal)):
                return None
            usd = Decimal(raw)
            if (
                not usd.is_finite()
                or usd <= 0
                or abs(usd.adjusted()) > 100
                or len(usd.as_tuple().digits) > 80
            ):
                return None
        except (TimeoutError, aiohttp.ClientError, ValueError, InvalidOperation):
            return None

        point = PricePoint(symbol=symbol_up, usd=usd, source="coingecko")
        self._cache[symbol_up] = point
        self._cached_at[symbol_up] = time.monotonic()
        return point
