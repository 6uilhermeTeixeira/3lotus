from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class TelemetryOutbox:
    """Durable, best-effort delivery of runner events to 3lotus."""

    def __init__(self, database: Path, runner_id: str, url: str = "", token: str = "") -> None:
        self.database = database
        self.runner_id = runner_id
        self.url = url
        self.token = token
        self.lock = threading.RLock()
        database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry_outbox (
                    event_id TEXT PRIMARY KEY,
                    emitted_at_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT ''
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def enqueue(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        strategy_id: str = "",
        strategy_version: str = "",
        account_environment: str = "unknown",
    ) -> str:
        event_id = str(uuid.uuid4())
        emitted_at = datetime.now(UTC).isoformat()
        event = {
            "schema_version": "1.0",
            "event_id": event_id,
            "runner_id": self.runner_id,
            "event_type": event_type,
            "emitted_at_utc": emitted_at,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "account_environment": account_environment,
            "payload": payload,
        }
        with self.lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO telemetry_outbox(event_id, emitted_at_utc, payload_json) VALUES (?, ?, ?)",
                (event_id, emitted_at, json.dumps(event, separators=(",", ":"))),
            )
        return event_id

    def pending(self) -> int:
        with self.lock, self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM telemetry_outbox").fetchone()
        return int(row[0]) if row else 0

    def flush(self, limit: int = 100) -> int:
        if not self.url:
            return 0
        with self.lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id, payload_json FROM telemetry_outbox ORDER BY emitted_at_utc LIMIT ?",
                (limit,),
            ).fetchall()
        if not rows:
            return 0
        request = urllib.request.Request(
            f"{self.url}/api/v1/events/batch",
            data=json.dumps({"events": [json.loads(row[1]) for row in rows]}).encode(),
            method="POST",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                result = json.loads(response.read())
            completed = set(result.get("accepted", [])) | set(result.get("duplicates", []))
            if completed:
                with self.lock, self._connect() as connection:
                    connection.executemany("DELETE FROM telemetry_outbox WHERE event_id = ?", [(item,) for item in completed])
            return len(completed)
        except (OSError, ValueError, urllib.error.URLError) as error:
            with self.lock, self._connect() as connection:
                connection.executemany(
                    "UPDATE telemetry_outbox SET attempts = attempts + 1, last_error = ? WHERE event_id = ?",
                    [(str(error)[:500], row[0]) for row in rows],
                )
            return 0

