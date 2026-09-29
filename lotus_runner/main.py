from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from typing import Any

from .config import Settings
from .engine import decide
from .market import MarketStore
from .strategies.registry import load_profiles
from .telemetry import TelemetryOutbox


LOGGER = logging.getLogger("lotus_runner")


class RunnerState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.lock = threading.RLock()
        self.latest_account: dict[str, Any] | None = None
        database = settings.market_db_path or settings.strategies_dir.parent / "data" / "market.db"
        self.market = MarketStore(database, settings.tick_window_seconds, settings.audit_retention_days)
        self.telemetry = TelemetryOutbox(database, settings.runner_id, settings.telemetry_url, settings.telemetry_token)
        self.candles: dict[str, list[dict[str, Any]]] = {}
        self.last_request_id: dict[str, str] = {}
        self.last_evaluation_ns: dict[str, int] = {}

    def profiles(self):
        return load_profiles(self.settings.strategies_dir)

    def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            symbol = str(payload.get("symbol") or "").upper()
            request_id = str(payload.get("request_id") or "")
            if not symbol or len(request_id) < 3:
                raise ValueError("symbol and request_id are required")
            if self.last_request_id.get(symbol) == request_id:
                return hold_response("duplicate_market_event")
            now_ns = time.monotonic_ns()
            account = payload.get("account")
            if not isinstance(account, dict):
                raise ValueError("account snapshot is required")
            self.latest_account = account
            incoming_candles = payload.get("candles") or []
            if incoming_candles:
                if not isinstance(incoming_candles, list) or len(incoming_candles) > 5000:
                    raise ValueError("invalid candle history")
                self.candles[symbol] = incoming_candles
            if symbol not in self.candles:
                raise ValueError("candle history is required before tick-only updates")
            indicators = self.market.ingest(payload)
            self.last_request_id[symbol] = request_id
            prior_ns = self.last_evaluation_ns.get(symbol, 0)
            if prior_ns and (now_ns - prior_ns) / 1_000_000 < self.settings.decision_debounce_ms:
                return hold_response("decision_debounce")
            prepared = {
                **payload,
                "symbol": symbol,
                "candles": self.candles[symbol],
                "indicators": {**(payload.get("indicators") or {}), **indicators},
                "runtime_limits": {
                    "max_spread_points": self.settings.max_spread_points,
                    "structural_context_pips": self.settings.structural_context_pips,
                    "structural_ema20_gap_pips": self.settings.structural_ema20_gap_pips,
                    "structural_max_pivot_extension_pips": self.settings.structural_max_pivot_extension_pips,
                    "require_order_book": self.settings.require_order_book,
                },
            }
            started = time.perf_counter_ns()
            profiles = self.profiles()
            strategy_id = str(prepared.get("bot_id") or self.settings.active_strategy)
            response = decide(prepared, profiles.get(strategy_id), self.settings)
            latency_ms = (time.perf_counter_ns() - started) / 1_000_000
            self.market.record_decision(request_id, symbol, response, latency_ms)
            profile = profiles.get(strategy_id)
            self.telemetry.enqueue(
                "decision",
                {"request_id": request_id, "symbol": symbol, "response": response, "latency_ms": round(latency_ms, 3)},
                strategy_id=strategy_id,
                strategy_version=profile.version if profile else "",
                account_environment=str(account.get("environment") or account.get("trade_mode") or "unknown"),
            )
            LOGGER.info(json.dumps({"event": "decision", "request_id": request_id, "symbol": symbol, "latency_ms": round(latency_ms, 3), "action": response.get("action"), "reason": response.get("reason")}, separators=(",", ":")))
            self.last_evaluation_ns[symbol] = now_ns
            return {**response, "request_id": request_id, "decision_latency_ms": round(latency_ms, 3)}


def hold_response(reason: str) -> dict[str, Any]:
    return {"action": "hold", "reason": reason, "size": 0.0, "risk_checks": [], "metadata": {"candidate": False}}


def build_handler(state: RunnerState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LotusRunner/0.1"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def send_json(self, status: HTTPStatus, body: dict[str, Any]) -> None:
            raw = json.dumps(body, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1_000_000:
                raise ValueError("invalid request size")
            return json.loads(self.rfile.read(length))

        def authorized(self) -> bool:
            expected = state.settings.api_key
            return not expected or self.headers.get("X-Lotus-Api-Key", "") == expected

        def do_GET(self) -> None:
            if self.path == "/health":
                self.send_json(HTTPStatus.OK, {"status": "ok", "service": "2lotus-runner", "timestamp_utc": datetime.now(UTC).isoformat()})
            elif self.path == "/ready":
                try:
                    profiles = state.profiles()
                    self.send_json(HTTPStatus.OK, {"status": "ready", "strategies": len(profiles), "execution_enabled": state.settings.execution_enabled})
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "not_ready", "detail": str(error)})
            elif self.path == "/api/account":
                self.send_json(HTTPStatus.OK, {"account": state.latest_account, "connected": state.latest_account is not None})
            elif self.path == "/api/strategies":
                profiles = state.profiles()
                self.send_json(HTTPStatus.OK, {"items": [{"id": p.id, "name": p.name, "version": p.version, "enabled": p.enabled, "runnable": p.runnable} for p in profiles.values()]})
            elif self.path == "/api/market/status":
                self.send_json(HTTPStatus.OK, state.market.market_status())
            elif self.path == "/api/decisions/latest":
                self.send_json(HTTPStatus.OK, {"item": state.market.last_decision})
            elif self.path == "/api/metrics":
                self.send_json(HTTPStatus.OK, {**state.market.metrics(), "telemetry_outbox_pending": state.telemetry.pending()})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"detail": "not found"})

        def do_POST(self) -> None:
            if self.path not in {"/decision", "/execution"}:
                self.send_json(HTTPStatus.NOT_FOUND, {"detail": "not found"})
                return
            if not self.authorized():
                self.send_json(HTTPStatus.UNAUTHORIZED, {"detail": "invalid API key"})
                return
            try:
                payload = self.read_json()
                if self.path == "/execution":
                    state.market.record_execution(payload)
                    state.telemetry.enqueue("order_result", payload)
                    LOGGER.info(json.dumps({"event": "execution", **payload}, separators=(",", ":")))
                    self.send_json(HTTPStatus.OK, {"status": "recorded"})
                else:
                    self.send_json(HTTPStatus.OK, state.process(payload))
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                if str(error) == "candle history is required before tick-only updates":
                    self.send_json(HTTPStatus.OK, {
                        "action": "hold",
                        "reason": "candle_history_warmup_required",
                        "size": 0.0,
                        "risk_checks": [],
                        "metadata": {"candidate": False, "retry_history": True},
                    })
                else:
                    self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": str(error)})
    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Lotus Runner")
    parser.add_argument("--check", action="store_true", help="validate configuration and strategy bundles")
    args = parser.parse_args()
    settings = Settings.from_environment()
    settings.validate()
    log_path = settings.log_path or settings.strategies_dir.parent / "logs" / "lotus-runner.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_path, maxBytes=settings.log_max_bytes, backupCount=settings.log_backup_count, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.setLevel(logging.INFO)
    LOGGER.addHandler(handler)
    state = RunnerState(settings)
    profiles = state.profiles()
    if args.check:
        print(json.dumps({"status": "ok", "strategies": sorted(profiles), "execution_enabled": settings.execution_enabled}))
        return
    if settings.telemetry_url:
        def flush_telemetry() -> None:
            while True:
                state.telemetry.flush()
                time.sleep(settings.telemetry_interval_seconds)

        threading.Thread(target=flush_telemetry, name="telemetry-outbox", daemon=True).start()
    server = ThreadingHTTPServer((settings.host, settings.port), build_handler(state))
    print(f"2lotus runner listening on http://{settings.host}:{settings.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
