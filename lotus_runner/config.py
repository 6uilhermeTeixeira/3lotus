from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    strategies_dir: Path
    active_strategy: str
    api_key: str
    execution_enabled: bool
    allowed_account_login: int
    max_live_lot: float

    @classmethod
    def from_environment(cls) -> "Settings":
        root = Path(os.getenv("LOTUS_RUNNER_HOME", Path.cwd())).resolve()
        return cls(
            host=os.getenv("LOTUS_RUNNER_HOST", "127.0.0.1"),
            port=int(os.getenv("LOTUS_RUNNER_PORT", "1111")),
            strategies_dir=Path(os.getenv("LOTUS_RUNNER_STRATEGIES_DIR", root / "strategies")),
            active_strategy=os.getenv("LOTUS_RUNNER_ACTIVE_STRATEGY", "zigzag-v7"),
            api_key=os.getenv("LOTUS_RUNNER_API_KEY", ""),
            execution_enabled=os.getenv("LOTUS_RUNNER_EXECUTION_ENABLED", "false").lower() == "true",
            allowed_account_login=int(os.getenv("LOTUS_RUNNER_ALLOWED_ACCOUNT_LOGIN", "0")),
            max_live_lot=float(os.getenv("LOTUS_RUNNER_MAX_LIVE_LOT", "0.01")),
        )

    def validate(self) -> None:
        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("LOTUS_RUNNER_HOST must remain loopback-only")
        if not 1 <= self.port <= 65535:
            raise ValueError("LOTUS_RUNNER_PORT must be between 1 and 65535")
        if not 0 < self.max_live_lot <= 0.01:
            raise ValueError("LOTUS_RUNNER_MAX_LIVE_LOT must be > 0 and <= 0.01")
        if self.execution_enabled and (not self.api_key or self.allowed_account_login <= 0):
            raise ValueError("live execution requires an API key and an explicit allowed account login")


def load_runtime_config(path: Path) -> dict[str, object]:
    """Optional local configuration. Secrets still come from environment variables."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
