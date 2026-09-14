from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .config import Settings
from .engine import decide
from .strategies.registry import load_profiles


class RunnerState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.latest_account: dict[str, Any] | None = None

    def profiles(self):
        return load_profiles(self.settings.strategies_dir)


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
                self.send_json(HTTPStatus.OK, {"status": "ok", "service": "lotus-runner", "timestamp_utc": datetime.now(UTC).isoformat()})
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
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"detail": "not found"})

        def do_POST(self) -> None:
            if self.path != "/decision":
                self.send_json(HTTPStatus.NOT_FOUND, {"detail": "not found"})
                return
            if not self.authorized():
                self.send_json(HTTPStatus.UNAUTHORIZED, {"detail": "invalid API key"})
                return
            try:
                payload = self.read_json()
                account = payload.get("account")
                if not isinstance(account, dict):
                    raise ValueError("account snapshot is required")
                state.latest_account = account
                profiles = state.profiles()
                strategy_id = str(payload.get("bot_id") or state.settings.active_strategy)
                self.send_json(HTTPStatus.OK, decide(payload, profiles.get(strategy_id), state.settings))
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": str(error)})
    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Lotus Runner")
    parser.add_argument("--check", action="store_true", help="validate configuration and strategy bundles")
    args = parser.parse_args()
    settings = Settings.from_environment()
    settings.validate()
    state = RunnerState(settings)
    profiles = state.profiles()
    if args.check:
        print(json.dumps({"status": "ok", "strategies": sorted(profiles), "execution_enabled": settings.execution_enabled}))
        return
    server = ThreadingHTTPServer((settings.host, settings.port), build_handler(state))
    print(f"Lotus Runner listening on http://{settings.host}:{settings.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
