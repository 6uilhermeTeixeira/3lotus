from pathlib import Path

from lotus_runner.config import Settings


def test_loads_local_dotenv(monkeypatch, tmp_path) -> None:
    (tmp_path / ".env").write_text("LOTUS_RUNNER_ACTIVE_STRATEGY=zigzag-v7\nLOTUS_RUNNER_EXECUTION_ENABLED=false\n")
    monkeypatch.setenv("LOTUS_RUNNER_HOME", str(tmp_path))
    monkeypatch.delenv("LOTUS_RUNNER_ACTIVE_STRATEGY", raising=False)
    settings = Settings.from_environment()
    assert settings.active_strategy == "zigzag-v7"
    assert settings.execution_enabled is False


def test_rejects_noncanonical_tick_window() -> None:
    settings = Settings("127.0.0.1", 7772, Path("strategies"), "zigzag-v7", "", False, 0, 0.01, tick_window_seconds=60)
    try:
        settings.validate()
    except ValueError as error:
        assert "must remain 900" in str(error)
    else:
        raise AssertionError("noncanonical tick window was accepted")
