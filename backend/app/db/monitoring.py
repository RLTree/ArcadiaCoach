"""Database observability helpers (Phase 21)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict

from sqlalchemy import event
from sqlalchemy.engine import Engine

from ..telemetry import emit_event


@dataclass
class PoolTelemetryState:
    connects: int = 0
    checkouts: int = 0
    checkins: int = 0
    last_emit: float = 0.0


_STATE_BY_ENGINE: Dict[int, PoolTelemetryState] = {}
_TELEMETRY_INTERVAL = float(os.getenv("ARCADIA_DB_TELEMETRY_INTERVAL", "30"))


def instrument_engine(engine: Engine) -> None:
    """Attach pool event listeners that emit telemetry snapshots."""
    key = id(engine)
    if key in _STATE_BY_ENGINE:
        return

    state = PoolTelemetryState()
    _STATE_BY_ENGINE[key] = state

    def snapshot(event_name: str) -> None:
        now = time.time()
        should_emit = _TELEMETRY_INTERVAL <= 0 or (now - state.last_emit) >= _TELEMETRY_INTERVAL
        if not should_emit:
            return
        state.last_emit = now
        payload = {
            "status": _safe_pool_status(engine),
            "event": event_name,
            "connects": state.connects,
            "checkouts": state.checkouts,
            "checkins": state.checkins,
        }
        emit_event("db_pool_status", **payload)

    @event.listens_for(engine, "connect", retval=False)
    def _on_connect(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        state.connects += 1
        snapshot("db_pool_connect")

    @event.listens_for(engine, "checkout")
    def _on_checkout(dbapi_connection, connection_record, connection_proxy) -> None:  # type: ignore[no-untyped-def]
        state.checkouts += 1
        snapshot("db_pool_checkout")

    @event.listens_for(engine, "checkin")
    def _on_checkin(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        state.checkins += 1
        snapshot("db_pool_checkin")


def get_pool_snapshot(engine: Engine) -> Dict[str, object]:
    """Return the latest counters and pool status for the provided engine."""
    state = _STATE_BY_ENGINE.get(id(engine))
    status = _safe_pool_status(engine)
    return {
        "status": status,
        "connects": state.connects if state else 0,
        "checkouts": state.checkouts if state else 0,
        "checkins": state.checkins if state else 0,
    }


def _safe_pool_status(engine: Engine) -> str:
    try:
        return engine.pool.status()  # type: ignore[no-untyped-call]
    except Exception as exc:  # pragma: no cover - defensive path
        return f"unavailable: {exc}"


__all__ = [
    "get_pool_snapshot",
    "instrument_engine",
]
