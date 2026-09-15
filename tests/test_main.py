from pathlib import Path

from lotus_runner.config import Settings
from lotus_runner.main import RunnerState


def test_runner_ingests_market_data_and_audits_decision(tmp_path: Path) -> None:
    settings = Settings(
        "127.0.0.1", 1111, Path(__file__).resolve().parents[1] / "strategies",
        "zigzag-v7", "", False, 0, 0.01, market_db_path=tmp_path / "market.db",
    )
    state = RunnerState(settings)
    response = state.process({
        "request_id": "request-1",
        "collector_id": "test-collector",
        "bot_id": "zigzag-v7",
        "timestamp_utc": "2026-01-05T12:00:00Z",
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "bid": 2000.0,
        "ask": 2000.1,
        "point_size": 0.01,
        "ticks": [{"time_msc": 1_767_614_400_000, "sequence": 1, "bid": 2000.0, "ask": 2000.1}],
        "order_book": [{"side": "bid", "price": 2000.0, "volume": 1}],
        "candles": [{"timestamp_utc": "2026-01-05T11:55:00Z", "open": 2000, "high": 2001, "low": 1999, "close": 2000, "volume": 1}],
        "account": {"login": 466305, "trade_mode": "demo"},
    })
    assert response["reason"] == "v7_warmup"
    assert response["request_id"] == "request-1"
    assert state.market.last_decision is not None
    assert state.market.metrics()["ticks_received"] == 1


def test_execution_report_is_audited(tmp_path: Path) -> None:
    from lotus_runner.market import MarketStore

    store = MarketStore(tmp_path / "market.db")
    store.record_execution({"request_id": "request-1", "action": "buy", "sent": True, "retcode": 10009})
    assert store.metrics()["executions_total"] == 1
