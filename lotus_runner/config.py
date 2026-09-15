from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Load local runtime configuration without adding a third-party dependency."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


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
    market_db_path: Path | None = None
    tick_window_seconds: int = 900
    decision_debounce_ms: int = 50
    max_spread_points: float = 50.0
    structural_context_pips: float = 1000.0
    structural_ema20_gap_pips: float = 900.0
    structural_max_pivot_extension_pips: float = 50.0
    require_order_book: bool = True
    audit_retention_days: int = 30
    log_path: Path | None = None
    log_max_bytes: int = 5_000_000
    log_backup_count: int = 7

    @classmethod
    def from_environment(cls) -> "Settings":
        root = Path(os.getenv("LOTUS_RUNNER_HOME", Path.cwd())).resolve()
        _load_dotenv(root / ".env")
        root = Path(os.getenv("LOTUS_RUNNER_HOME", root)).resolve()
        database = Path(os.getenv("LOTUS_RUNNER_MARKET_DB", root / "data" / "market.db"))
        return cls(
            host=os.getenv("LOTUS_RUNNER_HOST", "127.0.0.1"),
            port=int(os.getenv("LOTUS_RUNNER_PORT", "1111")),
            strategies_dir=Path(os.getenv("LOTUS_RUNNER_STRATEGIES_DIR", root / "strategies")),
            active_strategy=os.getenv("LOTUS_RUNNER_ACTIVE_STRATEGY", "zigzag-v7"),
            api_key=os.getenv("LOTUS_RUNNER_API_KEY", ""),
            execution_enabled=os.getenv("LOTUS_RUNNER_EXECUTION_ENABLED", "false").lower() == "true",
            allowed_account_login=int(os.getenv("LOTUS_RUNNER_ALLOWED_ACCOUNT_LOGIN", "0")),
            max_live_lot=float(os.getenv("LOTUS_RUNNER_MAX_LIVE_LOT", "0.01")),
            market_db_path=database,
            tick_window_seconds=int(os.getenv("LOTUS_RUNNER_TICK_WINDOW_SECONDS", "900")),
            decision_debounce_ms=int(os.getenv("LOTUS_RUNNER_DECISION_DEBOUNCE_MS", "50")),
            max_spread_points=float(os.getenv("LOTUS_RUNNER_MAX_SPREAD_POINTS", "50")),
            structural_context_pips=float(os.getenv("LOTUS_RUNNER_STRUCTURAL_CONTEXT_PIPS", "1000")),
            structural_ema20_gap_pips=float(os.getenv("LOTUS_RUNNER_STRUCTURAL_EMA20_GAP_PIPS", "900")),
            structural_max_pivot_extension_pips=float(os.getenv("LOTUS_RUNNER_STRUCTURAL_MAX_PIVOT_EXTENSION_PIPS", "50")),
            require_order_book=os.getenv("LOTUS_RUNNER_REQUIRE_ORDER_BOOK", "true").lower() == "true",
            audit_retention_days=int(os.getenv("LOTUS_RUNNER_AUDIT_RETENTION_DAYS", "30")),
            log_path=Path(os.getenv("LOTUS_RUNNER_LOG_PATH", root / "logs" / "lotus-runner.log")),
            log_max_bytes=int(os.getenv("LOTUS_RUNNER_LOG_MAX_BYTES", "5000000")),
            log_backup_count=int(os.getenv("LOTUS_RUNNER_LOG_BACKUP_COUNT", "7")),
        )

    def validate(self) -> None:
        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("LOTUS_RUNNER_HOST must remain loopback-only")
        if not 1 <= self.port <= 65535:
            raise ValueError("LOTUS_RUNNER_PORT must be between 1 and 65535")
        if not 0 < self.max_live_lot <= 0.01:
            raise ValueError("LOTUS_RUNNER_MAX_LIVE_LOT must be > 0 and <= 0.01")
        if self.tick_window_seconds != 900:
            raise ValueError("LOTUS_RUNNER_TICK_WINDOW_SECONDS must remain 900 for ZigZag V7")
        if not 10 <= self.decision_debounce_ms <= 1000:
            raise ValueError("LOTUS_RUNNER_DECISION_DEBOUNCE_MS must be between 10 and 1000")
        if self.max_spread_points <= 0:
            raise ValueError("LOTUS_RUNNER_MAX_SPREAD_POINTS must be positive")
        if self.audit_retention_days < 1 or self.log_max_bytes < 100_000 or self.log_backup_count < 1:
            raise ValueError("audit and log retention settings must be positive")
        if self.execution_enabled and (not self.api_key or self.allowed_account_login <= 0):
            raise ValueError("demo execution requires an API key and an explicit allowed account login")


def load_runtime_config(path: Path) -> dict[str, object]:
    """Optional local configuration. Secrets still come from environment variables."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
