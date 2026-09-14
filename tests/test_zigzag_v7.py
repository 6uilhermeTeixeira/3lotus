from datetime import UTC, datetime, timedelta

from lotus_runner.strategies.zigzag_v7 import evaluate


def candle(at: datetime, price: float) -> dict[str, float | str]:
    return {"timestamp_utc": at.isoformat(), "open": price, "high": price + 0.5, "low": price - 0.5, "close": price, "volume": 1}


def test_v7_requires_h1_history_and_fails_closed() -> None:
    now = datetime(2026, 1, 5, 12, tzinfo=UTC)
    rows = [candle(now - timedelta(minutes=5 * (80 - index)), 2000 + index) for index in range(80)]
    result = evaluate({"timestamp_utc": now.isoformat(), "bid": 2100, "ask": 2100.1, "point_size": 0.01, "candles": rows}, {"expansion_threshold": 6, "calendar_range_floor": 4.5})
    assert result["action"] == "hold"
    assert result["reason"] == "v7_h1_history_warmup"
