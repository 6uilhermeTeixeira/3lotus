from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class MarketStore:
    """Thread-safe rolling market context and local audit trail."""

    def __init__(self, path: Path, window_seconds: int = 900, audit_retention_days: int = 30) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.window_ms = window_seconds * 1000
        self.audit_retention_ms = audit_retention_days * 86_400_000
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS ticks (
                collector_id TEXT NOT NULL, symbol TEXT NOT NULL,
                time_msc INTEGER NOT NULL, sequence INTEGER NOT NULL,
                bid REAL NOT NULL, ask REAL NOT NULL, last REAL NOT NULL,
                volume INTEGER NOT NULL, volume_real REAL NOT NULL, flags INTEGER NOT NULL,
                PRIMARY KEY (collector_id, symbol, time_msc, sequence)
            );
            CREATE INDEX IF NOT EXISTS ticks_symbol_time ON ticks(symbol, time_msc);
            CREATE TABLE IF NOT EXISTS book_snapshots (
                id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, time_msc INTEGER NOT NULL,
                levels_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decisions (
                request_id TEXT PRIMARY KEY, created_msc INTEGER NOT NULL,
                symbol TEXT NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL,
                latency_ms REAL NOT NULL, response_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY, request_id TEXT NOT NULL,
                created_msc INTEGER NOT NULL, action TEXT NOT NULL,
                sent INTEGER NOT NULL, retcode INTEGER NOT NULL
            );
            """
        )
        self.connection.commit()
        self.ticks_received = 0
        self.duplicate_ticks = 0
        self.decisions_total = 0
        self.executions_total = 0
        self.last_tick_msc: int | None = None
        self.last_decision: dict[str, Any] | None = None

    @staticmethod
    def _validate_tick(raw: object) -> tuple[int, int, float, float, float, int, float, int]:
        if not isinstance(raw, dict):
            raise ValueError("tick must be an object")
        time_msc, sequence = int(raw["time_msc"]), int(raw["sequence"])
        bid, ask = float(raw["bid"]), float(raw["ask"])
        if time_msc <= 0 or sequence < 0 or bid <= 0 or ask < bid:
            raise ValueError("invalid tick")
        return (
            time_msc, sequence, bid, ask, float(raw.get("last", 0)),
            int(raw.get("volume", 0)), float(raw.get("volume_real", 0)), int(raw.get("flags", 0)),
        )

    def ingest(self, payload: dict[str, Any]) -> dict[str, float]:
        collector = str(payload.get("collector_id") or "lotus-runner-bridge")
        symbol = str(payload.get("symbol") or "").upper()
        point_size = float(payload.get("point_size") or 0)
        raw_ticks = payload.get("ticks") or []
        if not symbol or point_size <= 0 or not isinstance(raw_ticks, list) or len(raw_ticks) > 2000:
            raise ValueError("invalid market batch")
        rows = [self._validate_tick(item) for item in raw_ticks]
        keys = [(row[0], row[1]) for row in rows]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("ticks must be ordered and unique")
        book = payload.get("order_book") or []
        if not isinstance(book, list) or len(book) > 500:
            raise ValueError("invalid order book")
        for level in book:
            if not isinstance(level, dict) or level.get("side") not in {"bid", "ask"}:
                raise ValueError("invalid order book level")
            if float(level.get("price", 0)) <= 0 or float(level.get("volume", 0)) < 0:
                raise ValueError("invalid order book level")
        with self.lock:
            before = self.connection.total_changes
            self.connection.executemany(
                "INSERT OR IGNORE INTO ticks VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(collector, symbol, *row) for row in rows],
            )
            inserted = self.connection.total_changes - before
            self.ticks_received += inserted
            self.duplicate_ticks += len(rows) - inserted
            if rows:
                self.last_tick_msc = rows[-1][0]
                cutoff = rows[-1][0] - self.window_ms
                self.connection.execute("DELETE FROM ticks WHERE symbol=? AND time_msc<?", (symbol, cutoff))
            if book:
                stamp = rows[-1][0] if rows else int(time.time() * 1000)
                self.connection.execute(
                    "INSERT INTO book_snapshots(symbol,time_msc,levels_json) VALUES(?,?,?)",
                    (symbol, stamp, json.dumps(book, separators=(",", ":"))),
                )
                self.connection.execute("DELETE FROM book_snapshots WHERE symbol=? AND time_msc<?", (symbol, stamp - self.window_ms))
            self.connection.commit()
        return self.indicators(symbol, point_size, bool(book))

    def indicators(self, symbol: str, point_size: float, book_available: bool) -> dict[str, float]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT time_msc,bid,ask FROM ticks WHERE symbol=? ORDER BY time_msc,sequence",
                (symbol.upper(),),
            ).fetchall()
        ready = bool(rows and rows[-1][0] - rows[0][0] >= self.window_ms - 2000)
        move_points = 0.0
        if ready:
            first_mid = (rows[0][1] + rows[0][2]) / 2
            last_mid = (rows[-1][1] + rows[-1][2]) / 2
            move_points = (last_mid - first_mid) / point_size
        return {
            "impulse_900s_ready": 1.0 if ready else 0.0,
            "impulse_900s_move_points": move_points,
            "order_book_ready": 1.0 if book_available else 0.0,
            "tick_count_900s": float(len(rows)),
        }

    def record_decision(self, request_id: str, symbol: str, response: dict[str, Any], latency_ms: float) -> None:
        created = int(time.time() * 1000)
        with self.lock:
            self.connection.execute(
                "INSERT OR REPLACE INTO decisions VALUES(?,?,?,?,?,?,?)",
                (request_id, created, symbol, str(response.get("action")), str(response.get("reason")), latency_ms, json.dumps(response, separators=(",", ":"))),
            )
            self.connection.execute("DELETE FROM decisions WHERE created_msc<?", (created - self.audit_retention_ms,))
            self.connection.commit()
            self.decisions_total += 1
            self.last_decision = {**response, "request_id": request_id, "latency_ms": round(latency_ms, 3), "created_msc": created}

    def record_execution(self, payload: dict[str, Any]) -> None:
        request_id = str(payload.get("request_id") or "")
        action = str(payload.get("action") or "")
        if len(request_id) < 3 or action not in {"buy", "sell"}:
            raise ValueError("invalid execution report")
        created = int(time.time() * 1000)
        with self.lock:
            self.connection.execute(
                "INSERT INTO executions(request_id,created_msc,action,sent,retcode) VALUES(?,?,?,?,?)",
                (request_id, created, action, 1 if payload.get("sent") else 0, int(payload.get("retcode", 0))),
            )
            self.connection.execute("DELETE FROM executions WHERE created_msc<?", (created - self.audit_retention_ms,))
            self.connection.commit()
            self.executions_total += 1

    def market_status(self) -> dict[str, Any]:
        now = int(time.time() * 1000)
        return {
            "last_tick_msc": self.last_tick_msc,
            "last_tick_age_ms": None if self.last_tick_msc is None else max(0, now - self.last_tick_msc),
            "ticks_received": self.ticks_received,
            "duplicate_ticks": self.duplicate_ticks,
        }

    def metrics(self) -> dict[str, Any]:
        return {**self.market_status(), "decisions_total": self.decisions_total, "executions_total": self.executions_total}
