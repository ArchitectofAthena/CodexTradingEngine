from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("configuration root must be an object")
    return payload


def positive_int(value: Any, name: str, maximum: int = 86400) -> int:
    """Reject booleans, fractional values and unbounded/busy-loop settings."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    number = int(value)
    if not 1 <= number <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return number
