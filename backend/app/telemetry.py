"""Lightweight telemetry helpers for backend instrumentation (Phase 12)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Any, Callable, Dict, List

logger = logging.getLogger("arcadia.telemetry")


@dataclass(frozen=True)
class TelemetryEvent:
    name: str
    payload: Dict[str, Any]


_listeners: List[Callable[[TelemetryEvent], None]] = []
_lock = RLock()


def register_listener(listener: Callable[[TelemetryEvent], None]) -> None:
    """Register an in-process listener (used in tests)."""
    with _lock:
        _listeners.append(listener)


def clear_listeners() -> None:
    """Remove all registered listeners. Mainly used to reset test state."""
    with _lock:
        _listeners.clear()


def emit_event(name: str, **fields: Any) -> None:
    """Emit a structured telemetry event and fan it out to listeners."""
    payload = _sanitize(fields)
    event = TelemetryEvent(name=name, payload=payload)

    with _lock:
        listeners = list(_listeners)

    for listener in listeners:
        try:
            listener(event)
        except Exception:  # noqa: BLE001
            logger.exception("Telemetry listener failed for %s", name)

    structured = {"event": name, **payload}
    logger.info("TELEMETRY %s", json.dumps(structured, default=_json_default))


def _sanitize(fields: Dict[str, Any]) -> Dict[str, Any]:
    sanitized: Dict[str, Any] = {}
    for key, value in fields.items():
        if isinstance(value, datetime):
            sanitized[key] = value.isoformat()
        else:
            sanitized[key] = value
    return sanitized


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


__all__ = [
    "TelemetryEvent",
    "clear_listeners",
    "emit_event",
    "register_listener",
]
