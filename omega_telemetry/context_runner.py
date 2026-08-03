"""Operator-invoked, observation-only Omega telemetry runner."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Any

import aiohttp

from .config_tools import load_config
from .db import TelemetryDB
from .health import HealthWriter
from .pricing import PriceResolver
from .sentiment_tracker import SentimentTracker
from .signal_observer import SignalObserver
from .whale_watcher import WhaleWatcher

logger = logging.getLogger(__name__)

BOUNDARY = {
    "authority": False,
    "shadow_mode": True,
    "may_execute": False,
    "may_execute_trades": False,
    "may_sign": False,
    "may_broadcast": False,
    "may_move_capital": False,
}


async def run(config_path: str) -> None:
    config = load_config(config_path)
    logging.basicConfig(
        level=getattr(
            logging,
            str(config.get("log_level", "INFO")).upper(),
            logging.INFO,
        ),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    database = TelemetryDB(
        str(config.get("database_path", "data/omega_telemetry.sqlite"))
    )
    health = HealthWriter(
        str(config.get("health_path", "logs/omega_health.json"))
    )
    timeout = aiohttp.ClientTimeout(
        total=int(config.get("http_timeout_seconds", 30))
    )

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks: list[asyncio.Task[Any]] = []

        observers = config.get("observers", [])
        if not isinstance(observers, list):
            raise ValueError("observers must be an array")
        for observer_config in observers:
            if not isinstance(observer_config, dict):
                continue
            if observer_config.get("enabled", True):
                observer = SignalObserver(database, observer_config)
                tasks.append(
                    asyncio.create_task(
                        observer.run_forever(),
                        name=f"signal:{observer.name}",
                    )
                )

        sentiment_config = config.get("sentiment", {})
        if not isinstance(sentiment_config, dict):
            raise ValueError("sentiment must be an object")
        rules_path = Path(
            str(
                sentiment_config.get(
                    "rules_path",
                    "rules/market_signal_rules.json",
                )
            )
        )
        if sentiment_config.get("enabled", False):
            if not rules_path.is_file():
                raise FileNotFoundError(
                    f"Sentiment rules file not found: {rules_path}"
                )
            tracker = SentimentTracker(
                session,
                database,
                sentiment_config,
                rules_path,
            )
            tasks.append(
                asyncio.create_task(
                    tracker.run_forever(),
                    name="sentiment",
                )
            )

        whale_config = config.get("whale", {})
        if not isinstance(whale_config, dict):
            raise ValueError("whale must be an object")
        if whale_config.get("enabled", False):
            symbol_map = whale_config.get(
                "symbol_to_coingecko_id",
                {},
            )
            if not isinstance(symbol_map, dict):
                raise ValueError(
                    "whale.symbol_to_coingecko_id must be an object"
                )
            price_resolver = PriceResolver(
                session=session,
                symbol_to_id={
                    str(key): str(value)
                    for key, value in symbol_map.items()
                },
                timeout_seconds=int(
                    whale_config.get("price_timeout_seconds", 15)
                ),
            )
            chains = whale_config.get("chains", [])
            if not isinstance(chains, list):
                raise ValueError("whale.chains must be an array")
            for chain_config in chains:
                if not isinstance(chain_config, dict):
                    continue
                if not chain_config.get("enabled", False):
                    continue
                watcher = WhaleWatcher(
                    session=session,
                    db=database,
                    config=chain_config,
                    price_resolver=price_resolver,
                )
                tasks.append(
                    asyncio.create_task(
                        watcher.run_forever(),
                        name=f"whale:{watcher.chain_name}",
                    )
                )

        async def heartbeat() -> None:
            while True:
                health.write(
                    {
                        "status": "ok",
                        "tasks": [
                            {
                                "name": task.get_name(),
                                "done": task.done(),
                                "cancelled": task.cancelled(),
                            }
                            for task in tasks
                        ],
                        **BOUNDARY,
                    }
                )
                await asyncio.sleep(
                    int(config.get("health_interval_seconds", 30))
                )

        tasks.append(
            asyncio.create_task(
                heartbeat(),
                name="heartbeat",
            )
        )
        await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run passive, shadow-only Omega context telemetry."
    )
    parser.add_argument(
        "--config",
        default="config/omega.example.yaml",
    )
    arguments = parser.parse_args()
    asyncio.run(run(arguments.config))


if __name__ == "__main__":
    main()
