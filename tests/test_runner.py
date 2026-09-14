import json
from pathlib import Path

from lotus_runner.config import Settings
from lotus_runner.engine import decide
from lotus_runner.strategies.registry import load_profiles


ROOT = Path(__file__).resolve().parents[1]


def settings() -> Settings:
    return Settings("127.0.0.1", 1111, ROOT / "strategies", "zigzag-v7", "", False, 0, 0.01)


def test_strategy_bundles_pass_integrity_check() -> None:
    profiles = load_profiles(ROOT / "strategies")
    assert set(profiles) == {"zigzag-v7", "zigzag-v8", "combined-v7-v8"}


def test_unimported_v7_fails_closed() -> None:
    profile = load_profiles(ROOT / "strategies")["zigzag-v7"]
    result = decide({"account": {"login": 4006488}}, profile, settings())
    assert result["action"] == "hold"
    assert "disabled" in result["reason"]


def test_tampered_bundle_is_rejected(tmp_path: Path) -> None:
    source = json.loads((ROOT / "strategies" / "zigzag-v7.json").read_text())
    source["enabled"] = True
    (tmp_path / "bad.json").write_text(json.dumps(source))
    try:
        load_profiles(tmp_path)
    except ValueError as error:
        assert "integrity" in str(error)
    else:
        raise AssertionError("tampered bundle was accepted")
