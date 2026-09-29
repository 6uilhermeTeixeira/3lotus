import json
from pathlib import Path

from lotus_runner.config import Settings
from lotus_runner import engine
from lotus_runner.engine import decide
from lotus_runner.strategies.registry import load_profiles


ROOT = Path(__file__).resolve().parents[1]


def settings() -> Settings:
    return Settings("127.0.0.1", 7772, ROOT / "strategies", "zigzag-v7", "", False, 0, 0.01)


def test_strategy_bundles_pass_integrity_check() -> None:
    profiles = load_profiles(ROOT / "strategies")
    assert set(profiles) == {"zigzag-v7", "zigzag-scalper-v2", "core-zigzag-v3"}
    assert profiles["zigzag-v7"].runnable
    assert profiles["zigzag-scalper-v2"].runnable
    assert profiles["core-zigzag-v3"].id == "zigzag-scalper-v2"


def test_unimported_v7_fails_closed() -> None:
    profile = load_profiles(ROOT / "strategies")["zigzag-v7"]
    result = decide({"account": {"login": 466305}}, profile, settings())
    assert result["action"] == "hold"
    assert result["reason"] == "v7_invalid_market_snapshot"


def test_execution_rejects_non_demo_account() -> None:
    profile = load_profiles(ROOT / "strategies")["zigzag-v7"]
    configured = Settings("127.0.0.1", 7772, ROOT / "strategies", "zigzag-v7", "test-key", True, 466305, 0.01)
    result = decide({"account": {"login": 466305, "trade_mode": "real"}}, profile, configured)
    assert result["action"] == "hold"
    assert result["reason"] == "execution is restricted to demo accounts"


def test_tampered_bundle_is_rejected(tmp_path: Path) -> None:
    source = json.loads((ROOT / "strategies" / "zigzag-v7.json").read_text())
    source["enabled"] = False
    (tmp_path / "bad.json").write_text(json.dumps(source))
    try:
        load_profiles(tmp_path)
    except ValueError as error:
        assert "integrity" in str(error)
    else:
        raise AssertionError("tampered bundle was accepted")


def test_demo_candidate_is_promoted_with_explicit_execution_prices(monkeypatch) -> None:
    profile = load_profiles(ROOT / "strategies")["zigzag-v7"]
    configured = Settings("127.0.0.1", 7772, ROOT / "strategies", "zigzag-v7", "test-key", True, 466305, 0.01)
    monkeypatch.setattr(engine, "evaluate_zigzag_v7", lambda *_: {
        "action": "hold", "reason": "shadow_signal", "size": 0.0, "risk_checks": [],
        "metadata": {
            "candidate": True, "suggested_action": "buy", "suggested_size": 0.01,
            "entry_price": 2000.1, "stop_loss_price": 1999.5, "take_profit_price": 2010.1,
        },
    })
    result = engine.decide({"account": {"login": 466305, "trade_mode": "demo"}}, profile, configured)
    assert result["action"] == "buy"
    assert result["size"] == 0.01
    assert result["stop_loss_price"] == 1999.5


def test_demo_candidate_without_stop_fails_closed(monkeypatch) -> None:
    profile = load_profiles(ROOT / "strategies")["zigzag-v7"]
    configured = Settings("127.0.0.1", 7772, ROOT / "strategies", "zigzag-v7", "test-key", True, 466305, 0.01)
    monkeypatch.setattr(engine, "evaluate_zigzag_v7", lambda *_: {
        "action": "hold", "reason": "shadow_signal", "size": 0.0, "risk_checks": [],
        "metadata": {"candidate": True, "suggested_action": "buy", "suggested_size": 0.01, "entry_price": 2000.1},
    })
    result = engine.decide({"account": {"login": 466305, "trade_mode": "demo"}}, profile, configured)
    assert result["action"] == "hold"
    assert "stop_loss_price" in result["reason"]
