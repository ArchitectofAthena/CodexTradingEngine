from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .models import Event


class TelemetryDB:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    chain_name TEXT,
                    source TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_dedupe
                ON events (dedupe_key, occurred_at);

                CREATE TABLE IF NOT EXISTS state (
                    state_key TEXT PRIMARY KEY,
                    state_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alert_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dedupe_key TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    delivered INTEGER NOT NULL,
                    response TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_alert_log_dedupe
                ON alert_log (dedupe_key, created_at);
                """)

    def save_event(self, event: Event) -> None:
        record = event.to_record()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO events (
                    event_type, chain_name, source, severity, occurred_at,
                    dedupe_key, title, summary, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["event_type"],
                    record["chain"],
                    record["source"],
                    record["severity"],
                    record["occurred_at"],
                    record["dedupe_key"],
                    record["title"],
                    record["summary"],
                    json.dumps(record, ensure_ascii=False),
                ),
            )

    def is_duplicate(self, dedupe_key: str, cooldown_minutes: int) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)).isoformat()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM events
                WHERE dedupe_key = ? AND occurred_at >= ?
                LIMIT 1
                """,
                (dedupe_key, cutoff),
            ).fetchone()
        return row is not None

    def log_alert(self, dedupe_key: str, channel: str, delivered: bool, response: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO alert_log (dedupe_key, channel, delivered, response, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    dedupe_key,
                    channel,
                    1 if delivered else 0,
                    response,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def set_state(self, key: str, value: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO state (state_key, state_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(state_key)
                DO UPDATE SET state_value = excluded.state_value, updated_at = excluded.updated_at
                """,
                (key, value, now),
            )

    def get_state(self, key: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT state_value FROM state WHERE state_key = ?",
                (key,),
            ).fetchone()
        return None if row is None else str(row["state_value"])

    def recent_events(
        self, event_type: Optional[str] = None, minutes: int = 60
    ) -> List[Dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        sql = """
            SELECT payload_json FROM events
            WHERE occurred_at >= ?
        """
        params: list[Any] = [cutoff]
        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        sql += " ORDER BY occurred_at DESC"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]
