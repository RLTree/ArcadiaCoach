from __future__ import annotations

import importlib

from sqlalchemy import delete

from app.telemetry import emit_event
from app.telemetry_pipeline import _MONITORED_EVENTS  # ensure module loads listener
from app.learner_profile import LearnerProfile, profile_store
from app.db.session import session_scope
from app.db.models import PersistenceAuditEventModel


def test_schedule_launch_events_persist() -> None:
    importlib.reload(importlib.import_module("app.telemetry_pipeline"))
    username = "telemetry-phase29"

    # Ensure clean slate
    try:
        profile_store.delete(username)
    except Exception:
        pass
    profile_store.upsert(LearnerProfile(username=username))

    with session_scope() as session:
        session.execute(
            delete(PersistenceAuditEventModel).where(
                PersistenceAuditEventModel.event_type.in_(_MONITORED_EVENTS)
            )
        )

    emit_event(
        "schedule_launch_initiated",
        username=username,
        item_id="lesson-x",
        kind="lesson",
        status="started",
    )

    events = profile_store.recent_telemetry_events(username)
    assert events, "Expected telemetry events to be persisted"
    assert events[0].event_type == "schedule_launch_initiated"
    assert events[0].payload["item_id"] == "lesson-x"

    try:
        profile_store.delete(username)
    except Exception:
        pass
