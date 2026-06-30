from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List

import aiohttp

from .config_tools import load_config
from .db import TelemetryDB
from .health import HealthWriter
from .sentiment_tracker import SentimentTracker
from .signal_observer import SignalObserver

logger = logging.getLogger(__name__)


async def run(config_path: str) -> None:
    cfg = load_config(config_path)
    logging.basicConfig(
        level=getattr(logging, str(cfg.get("log_level", "INFO")).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db = TelemetryDB(str(cfg.get("database_path", "data/omega_telemetry.sqlite")))
    health = HealthWriter(str(cfg.get("health_path", "logs/omega_health.json")))

    async with aiohttp.ClientSession() as session:
        tasks: List[asyncio.Task[Any]] = []

        for observer_cfg in cfg.get("observers", []):
            if observer_cfg.get("enabled", True):
                observer = SignalObserver(db, observer_cfg)
                tasks.append(asyncio.create_task(observer.run_forever()))

        signal_cfg: Dict[str, Any] = cfg.get("sentiment", {})
        rules_path = str(signal_cfg.get("rules_path", "rules/market_signal_rules.json"))
        if signal_cfg.get("enabled", False) and Path(rules_path).exists():
            tracker = SentimentTracker(session, db, signal_cfg, rules_path)
            tasks.append(asyncio.create_task(tracker.run_forever()))

        async def heartbeat() -> None:
            while True:
                health.write({"status": "ok", "tasks": len(tasks)})
                await asyncio.sleep(int(cfg.get("health_interval_seconds", 30)))

        tasks.append(asyncio.create_task(heartbeat()))
        await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run passive context telemetry.")
    parser.add_argument("--config", default="config/omega.example.yaml")
    args = parser.parse_args()
    asyncio.run(run(args.config))


if __name__ == "__main__":
    main()
