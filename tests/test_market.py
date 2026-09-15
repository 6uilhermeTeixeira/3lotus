from pathlib import Path

from lotus_runner.market import MarketStore


def test_tick_window_becomes_ready_and_is_persisted(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market.db")
    result = store.ingest({
        "collector_id": "test",
        "symbol": "XAUUSD",
        "point_size": 0.01,
        "ticks": [
            {"time_msc": 1_000_000, "sequence": 0, "bid": 2000, "ask": 2000.1},
            {"time_msc": 1_900_000, "sequence": 1, "bid": 2010, "ask": 2010.1},
        ],
        "order_book": [{"side": "bid", "price": 2010, "volume": 1}],
    })
    assert result["impulse_900s_ready"] == 1
    assert result["impulse_900s_move_points"] == 1000
    assert result["order_book_ready"] == 1
    assert store.market_status()["ticks_received"] == 2


def test_duplicate_ticks_are_idempotent(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market.db")
    payload = {
        "collector_id": "test", "symbol": "XAUUSD", "point_size": 0.01,
        "ticks": [{"time_msc": 1_000_000, "sequence": 0, "bid": 2000, "ask": 2000.1}],
    }
    store.ingest(payload)
    store.ingest(payload)
    assert store.market_status()["ticks_received"] == 1
    assert store.market_status()["duplicate_ticks"] == 1


def test_rejects_out_of_order_ticks(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market.db")
    try:
        store.ingest({
            "collector_id": "test", "symbol": "XAUUSD", "point_size": 0.01,
            "ticks": [
                {"time_msc": 2, "sequence": 1, "bid": 2, "ask": 2.1},
                {"time_msc": 1, "sequence": 0, "bid": 1, "ask": 1.1},
            ],
        })
    except ValueError as error:
        assert "ordered" in str(error)
    else:
        raise AssertionError("out-of-order ticks were accepted")
