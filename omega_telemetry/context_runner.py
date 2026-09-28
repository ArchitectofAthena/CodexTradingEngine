"""Operator-invoked, observation-only Omega telemetry runner."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Any

import aiohttp

from .config_tools import load_config, positive_int
from .db import TelemetryDB
from .health import HealthWriter
from .pricing import PriceResolver
from .sentiment_tracker import SentimentTracker
from .signal_observer import SignalObserver
from .whale_watcher import WhaleWatcher

logger = logging.getLogger(__name__)

BOUNDARY = {
    "authority": False,
    "artifact_is_command": False,
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

    # Validate and construct all workers before scheduling any background work.
    observers = config.get("observers", [])
    sentiment_config = config.get("sentiment", {})
    whale_config = config.get("whale", {})
    if not isinstance(observers, list) or not all(isinstance(item, dict) for item in observers):
        raise ValueError("observers must be an array of objects")
    if not isinstance(sentiment_config, dict):
        raise ValueError("sentiment must be an object")
    if not isinstance(whale_config, dict):
        raise ValueError("whale must be an object")
    symbol_map = whale_config.get("symbol_to_coingecko_id", {})
    chains = whale_config.get("chains", [])
    if not isinstance(symbol_map, dict):
        raise ValueError("whale.symbol_to_coingecko_id must be an object")
    if not isinstance(chains, list) or not all(isinstance(item, dict) for item in chains):
        raise ValueError("whale.chains must be an array of objects")
    interval = positive_int(config.get("health_interval_seconds", 30), "health_interval_seconds")
    timeout = aiohttp.ClientTimeout(
        total=positive_int(config.get("http_timeout_seconds", 30), "http_timeout_seconds", 60)
    )
    database = TelemetryDB(str(config.get("database_path", "data/omega_telemetry.sqlite")))
    health = HealthWriter(str(config.get("health_path", "logs/omega_health.json")))

    async with aiohttp.ClientSession(timeout=timeout) as session:
        workers: list[tuple[str, Any]] = []
        for observer_config in observers:
            if observer_config.get("enabled", True):
                observer = SignalObserver(database, observer_config)
                workers.append((f"signal:{observer.name}", observer))

        if sentiment_config.get("enabled", False):
            rules_path = Path(
                str(sentiment_config.get("rules_path", "rules/market_signal_rules.json"))
            )
            if not await asyncio.to_thread(rules_path.is_file):
                raise FileNotFoundError(f"Sentiment rules file not found: {rules_path}")
            tracker = SentimentTracker(session, database, sentiment_config, rules_path)
            workers.append(("sentiment", tracker))

        if whale_config.get("enabled", False):
            price_resolver = PriceResolver(
                session=session,
                symbol_to_id={str(key): str(value) for key, value in symbol_map.items()},
                timeout_seconds=positive_int(
                    whale_config.get("price_timeout_seconds", 15), "price_timeout_seconds", 60
                ),
            )
            for chain_config in chains:
                if chain_config.get("enabled", False):
                    watcher = WhaleWatcher(session, database, chain_config, price_resolver)
                    workers.append((f"whale:{watcher.chain_name}", watcher))

        tasks: list[asyncio.Task[Any]] = []

        def write_health(status: str) -> None:
            health.write(
                {
                    "status": status,
                    "feed_freshness": "unverified",
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

        async def heartbeat() -> None:
            while True:
                # A running coroutine proves liveness, not successful/fresh feeds.
                status = "idle" if not workers else "running"
                if any(task.done() for task in tasks):
                    status = "degraded"
                write_health(status)
                await asyncio.sleep(interval)

        try:
            tasks.extend(
                asyncio.create_task(worker.run_forever(), name=name) for name, worker in workers
            )
            tasks.append(asyncio.create_task(heartbeat(), name="heartbeat"))
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            write_health("stopped")
            raise
        except Exception:
            write_health("failed")
            raise
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


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
