"""Telemetry listener that persists key events for dashboard consumption (Phase 29)."""

from __future__ import annotations

import logging
from typing import Set

from .telemetry import TelemetryEvent, register_listener
from .db.session import session_scope
from .repositories.learner_profiles import learner_profiles

logger = logging.getLogger(__name__)

_MONITORED_EVENTS: Set[str] = {
    "schedule_launch_initiated",
    "schedule_launch_completed",
    "milestone_completion_recorded",
}


def _persist_event(event: TelemetryEvent) -> None:
    if event.name not in _MONITORED_EVENTS:
        return
    username = event.payload.get("username")
    if not isinstance(username, str) or not username.strip():
        return
    try:
        with session_scope() as session:
            learner_profiles.record_telemetry_event(session, username, event.name, event.payload)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to persist telemetry event for username=%s", username)


register_listener(_persist_event)

__all__ = ["_MONITORED_EVENTS"]
