from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class HealthWriter:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, payload: Dict[str, Any]) -> None:
        body = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        self.path.write_text(json.dumps(body, indent=2), encoding="utf-8")
