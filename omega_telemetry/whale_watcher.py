"""Read-only EVM transfer observer restored from the Drive Omega archive."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Sequence
from urllib.parse import urlparse

import aiohttp

from .db import TelemetryDB
from .models import WhaleEvent
from .pricing import PriceResolver

logger = logging.getLogger(__name__)

TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa"
    "952ba7f163c4a11628f55a4df523b3ef"
)


def hex_to_int(value: str | None) -> int:
    if not value:
        return 0
    return int(value, 16)


def normalize_address(value: str | None) -> str:
    return "" if not value else value.casefold()


def topic_to_address(topic_value: str) -> str:
    return "0x" + topic_value[-40:].casefold()


def short_addr(value: str) -> str:
    if not value:
        return "unknown"
    return f"{value[:6]}…{value[-4:]}"


def validate_rpc_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("rpc_url must be an absolute http or https URL")
    if parsed.username or parsed.password:
        raise ValueError("rpc_url must not embed credentials")
    return value


@dataclass(slots=True, frozen=True)
class TokenConfig:
    symbol: str
    contract: str
    decimals: int
    enabled: bool = True


class JsonRpcClient:
    """Minimal JSON-RPC reader with an explicit method allowlist."""

    ALLOWED_METHODS = frozenset(
        {"eth_blockNumber", "eth_getBlockByNumber", "eth_getLogs"}
    )

    def __init__(
        self,
        session: aiohttp.ClientSession,
        rpc_url: str,
        timeout_seconds: int = 20,
    ) -> None:
        self.session = session
        self.rpc_url = validate_rpc_url(rpc_url)
        self.timeout_seconds = timeout_seconds
        self._request_id = 0

    async def call(self, method: str, params: Sequence[Any]) -> Any:
        if method not in self.ALLOWED_METHODS:
            raise ValueError(
                f"RPC method is outside the read-only allowlist: {method}"
            )
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": list(params),
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with self.session.post(
            self.rpc_url,
            json=payload,
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            data: Any = await response.json()
        if not isinstance(data, dict):
            raise RuntimeError("RPC response must be an object")
        if "error" in data:
            raise RuntimeError(f"RPC error calling {method}: {data['error']}")
        if "result" not in data:
            raise RuntimeError(f"RPC response for {method} omitted result")
        return data["result"]


class WhaleWatcher:
    """Passive EVM whale observer.

    Reads blocks and Transfer logs, values transfers with public price data, and
    writes local telemetry events. It has no wallet, key, signing, transaction,
    broadcast, order, or capital authority.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        db: TelemetryDB,
        config: dict[str, Any],
        price_resolver: PriceResolver,
    ) -> None:
        self.session = session
        self.db = db
        self.price_resolver = price_resolver
        self.chain_name = str(config["name"])
        native = config["native_asset"]
        if not isinstance(native, dict):
            raise ValueError("native_asset must be an object")
        self.native_symbol = str(native["symbol"]).upper()
        self.native_decimals = int(native.get("decimals", 18))
        self.native_usd_threshold = Decimal(str(native["usd_threshold"]))
        self.token_usd_threshold = Decimal(
            str(config.get("token_usd_threshold", self.native_usd_threshold))
        )
        self.cooldown_minutes = int(config.get("cooldown_minutes", 10))
        self.poll_interval_seconds = int(
            config.get("poll_interval_seconds", 15)
        )
        self.max_blocks_per_poll = max(
            1,
            int(config.get("max_blocks_per_poll", 25)),
        )
        labels = config.get("exchange_labels", {}) or {}
        if not isinstance(labels, dict):
            raise ValueError("exchange_labels must be an object")
        self.exchange_labels = {
            normalize_address(str(address)): str(label)
            for address, label in labels.items()
        }
        self.rpc = JsonRpcClient(
            session,
            str(config["rpc_url"]),
            timeout_seconds=int(config.get("rpc_timeout_seconds", 20)),
        )
        raw_tokens = config.get("erc20_tokens", []) or []
        if not isinstance(raw_tokens, list) or not all(
            isinstance(token, dict) for token in raw_tokens
        ):
            raise ValueError("erc20_tokens must be an array of objects")
        self.tokens = [
            TokenConfig(
                symbol=str(token["symbol"]).upper(),
                contract=normalize_address(str(token["contract"])),
                decimals=int(token.get("decimals", 18)),
                enabled=bool(token.get("enabled", True)),
            )
            for token in raw_tokens
        ]

    async def run_forever(self) -> None:
        logger.info("Whale watcher starting for %s", self.chain_name)
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Whale watcher loop error on %s",
                    self.chain_name,
                )
            await asyncio.sleep(self.poll_interval_seconds)

    async def poll_once(self) -> None:
        latest_block = hex_to_int(
            await self.rpc.call("eth_blockNumber", [])
        )
        state_key = f"whale_watcher:last_block:{self.chain_name}"
        last_seen = self.db.get_state(state_key)
        start_block = (
            latest_block if last_seen is None else int(last_seen) + 1
        )
        if start_block > latest_block:
            return
        bounded_start = max(
            start_block,
            latest_block - self.max_blocks_per_poll + 1,
        )
        if bounded_start > start_block:
            logger.warning(
                "Bounding %s catch-up from block %s to %s",
                self.chain_name,
                start_block,
                bounded_start,
            )
        for block_number in range(bounded_start, latest_block + 1):
            await self._process_block(block_number)
        self.db.set_state(state_key, str(latest_block))

    async def _process_block(self, block_number: int) -> None:
        block = await self.rpc.call(
            "eth_getBlockByNumber",
            [hex(block_number), True],
        )
        if not isinstance(block, dict):
            return
        await self._scan_native_transfers(block)
        await self._scan_erc20_logs(block_number)

    async def _scan_native_transfers(
        self,
        block: dict[str, Any],
    ) -> None:
        price = await self.price_resolver.get_usd_price(
            self.native_symbol
        )
        if price is None:
            logger.warning("No price available for %s", self.native_symbol)
            return
        transactions = block.get("transactions", [])
        if not isinstance(transactions, list):
            return
        for transaction in transactions:
            if not isinstance(transaction, dict):
                continue
            value_wei = Decimal(hex_to_int(transaction.get("value")))
            if value_wei <= 0:
                continue
            amount = value_wei / (Decimal(10) ** self.native_decimals)
            usd_value = amount * price.usd
            if usd_value < self.native_usd_threshold:
                continue
            self._persist_transfer(
                event_source="json_rpc",
                threshold=self.native_usd_threshold,
                amount=amount,
                asset_symbol=self.native_symbol,
                usd_value=usd_value,
                from_address=normalize_address(transaction.get("from")),
                to_address=normalize_address(transaction.get("to")),
                tx_hash=(
                    None
                    if transaction.get("hash") is None
                    else str(transaction.get("hash"))
                ),
                block_number=hex_to_int(block.get("number")),
            )

    async def _scan_erc20_logs(self, block_number: int) -> None:
        for token in (token for token in self.tokens if token.enabled):
            price = await self.price_resolver.get_usd_price(token.symbol)
            if price is None:
                continue
            logs = await self.rpc.call(
                "eth_getLogs",
                [
                    {
                        "fromBlock": hex(block_number),
                        "toBlock": hex(block_number),
                        "address": token.contract,
                        "topics": [TRANSFER_TOPIC],
                    }
                ],
            )
            if not isinstance(logs, list):
                continue
            for log in logs:
                if not isinstance(log, dict):
                    continue
                topics = log.get("topics", [])
                if not isinstance(topics, list) or len(topics) < 3:
                    continue
                amount = Decimal(hex_to_int(log.get("data"))) / (
                    Decimal(10) ** token.decimals
                )
                usd_value = amount * price.usd
                if usd_value < self.token_usd_threshold:
                    continue
                raw_log_index = log.get("logIndex")
                log_index = (
                    None
                    if raw_log_index is None
                    else hex_to_int(str(raw_log_index))
                )
                self._persist_transfer(
                    event_source="erc20_logs",
                    threshold=self.token_usd_threshold,
                    amount=amount,
                    asset_symbol=token.symbol,
                    usd_value=usd_value,
                    from_address=topic_to_address(str(topics[1])),
                    to_address=topic_to_address(str(topics[2])),
                    tx_hash=(
                        None
                        if log.get("transactionHash") is None
                        else str(log.get("transactionHash"))
                    ),
                    block_number=block_number,
                    contract=token.contract,
                    log_index=log_index,
                )

    def _persist_transfer(
        self,
        *,
        event_source: str,
        threshold: Decimal,
        amount: Decimal,
        asset_symbol: str,
        usd_value: Decimal,
        from_address: str,
        to_address: str,
        tx_hash: str | None,
        block_number: int,
        contract: str | None = None,
        log_index: int | None = None,
    ) -> WhaleEvent | None:
        from_label = self.exchange_labels.get(from_address)
        to_label = self.exchange_labels.get(to_address)
        event_type = "large_transfer"
        if to_label and not from_label:
            event_type = "exchange_deposit"
        elif from_label and not to_label:
            event_type = "exchange_withdrawal"
        dedupe_identity = str(tx_hash or block_number)
        if contract is not None:
            dedupe_identity += f":contract:{normalize_address(contract)}"
        if log_index is not None:
            dedupe_identity += f":log:{log_index}"
        dedupe_key = (
            f"{self.chain_name}:{event_type}:"
            f"{dedupe_identity}:{asset_symbol}"
        )
        if self.db.is_duplicate(dedupe_key, self.cooldown_minutes):
            return None
        summary = (
            f"{amount.normalize()} {asset_symbol} (~${usd_value:,.2f}) "
            f"from {from_label or short_addr(from_address)} "
            f"to {to_label or short_addr(to_address)}"
        )
        data: dict[str, Any] = {
            "tx_hash": tx_hash,
            "block_number": block_number,
            "amount": str(amount),
            "asset_symbol": asset_symbol,
            "usd_value": f"{usd_value:.2f}",
            "from_address": from_address,
            "to_address": to_address,
            "from_label": from_label,
            "to_label": to_label,
        }
        if contract is not None:
            data["contract"] = contract
        if log_index is not None:
            data["log_index"] = log_index
        event = WhaleEvent(
            event_type=event_type,
            chain=self.chain_name,
            source=event_source,
            severity=(
                "critical"
                if usd_value >= threshold * Decimal(10)
                else "high"
            ),
            occurred_at=datetime.now(timezone.utc).isoformat(),
            dedupe_key=dedupe_key,
            title=(
                f"{self.chain_name} whale "
                f"{event_type.replace('_', ' ')}"
            ),
            summary=summary,
            data=data,
            amount=str(amount),
            asset_symbol=asset_symbol,
            usd_value=f"{usd_value:.2f}",
            from_address=from_address,
            to_address=to_address,
            from_label=from_label,
            to_label=to_label,
            tx_hash=tx_hash,
        )
        self.db.save_event(event)
        return event
