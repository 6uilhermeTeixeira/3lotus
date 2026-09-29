from pathlib import Path

from lotus_runner.telemetry import TelemetryOutbox


def test_outbox_is_durable_when_remote_is_disabled(tmp_path: Path) -> None:
    database = tmp_path / "market.db"
    outbox = TelemetryOutbox(database, "runner-test")
    event_id = outbox.enqueue("heartbeat", {"status": "ok"})

    assert event_id
    assert outbox.pending() == 1
    assert outbox.flush() == 0
    assert TelemetryOutbox(database, "runner-test").pending() == 1

