from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

import aiohttp

from .models import PricePoint


class PriceResolver:
    """CoinGecko-backed USD price resolver for telemetry context."""

    COINGECKO_SIMPLE_PRICE = "https://api.coingecko.com/api/v3/simple/price"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        symbol_to_id: Dict[str, str],
        timeout_seconds: int = 15,
    ) -> None:
        self.session = session
        self.symbol_to_id = {k.upper(): v for k, v in symbol_to_id.items()}
        self.timeout_seconds = timeout_seconds
        self._cache: Dict[str, PricePoint] = {}

    async def get_usd_price(self, symbol: str) -> Optional[PricePoint]:
        symbol_up = symbol.upper()
        if symbol_up in self._cache:
            return self._cache[symbol_up]

        coin_id = self.symbol_to_id.get(symbol_up)
        if not coin_id:
            return None

        params = {"ids": coin_id, "vs_currencies": "usd"}
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with self.session.get(
            self.COINGECKO_SIMPLE_PRICE, params=params, timeout=timeout
        ) as resp:
            resp.raise_for_status()
            payload: Dict[str, Any] = await resp.json()

        usd = payload.get(coin_id, {}).get("usd")
        if usd is None:
            return None

        point = PricePoint(symbol=symbol_up, usd=Decimal(str(usd)), source="coingecko")
        self._cache[symbol_up] = point
        return point
