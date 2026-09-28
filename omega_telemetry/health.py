from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class HealthWriter:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, payload: dict[str, Any]) -> None:
        body = {
            "updated_at": datetime.now(UTC).isoformat(),
            **payload,
        }
        self.path.write_text(json.dumps(body, indent=2), encoding="utf-8")
