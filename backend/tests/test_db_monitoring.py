from __future__ import annotations

from sqlalchemy import create_engine, text

from app.db import monitoring


def test_instrument_engine_emits_telemetry(monkeypatch) -> None:
    emitted: list[tuple[str, dict[str, object]]] = []

    def record(event_name: str, **payload: object) -> None:
        emitted.append((event_name, payload))

    monkeypatch.setattr(monitoring, "_TELEMETRY_INTERVAL", 0)
    monkeypatch.setattr(monitoring, "emit_event", record)

    engine = create_engine("sqlite:///:memory:", future=True)
    try:
        monitoring.instrument_engine(engine)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        assert emitted, "Expected telemetry emission when instrumentation is active."
        event_name, payload = emitted[0]
        assert event_name == "db_pool_status"
        assert payload["connects"] >= 1
    finally:
        engine.dispose()
