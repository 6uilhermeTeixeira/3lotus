from lotus_runner.config import Settings


def test_loads_local_dotenv(monkeypatch, tmp_path) -> None:
    (tmp_path / ".env").write_text("LOTUS_RUNNER_ACTIVE_STRATEGY=zigzag-v7\nLOTUS_RUNNER_EXECUTION_ENABLED=false\n")
    monkeypatch.setenv("LOTUS_RUNNER_HOME", str(tmp_path))
    monkeypatch.delenv("LOTUS_RUNNER_ACTIVE_STRATEGY", raising=False)
    settings = Settings.from_environment()
    assert settings.active_strategy == "zigzag-v7"
    assert settings.execution_enabled is False
