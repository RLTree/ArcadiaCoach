"""Phase 12 schedule refresh telemetry and fallback tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

import pytest
from fastapi.testclient import TestClient

from app.curriculum_sequencer import generate_schedule_for_user, sequencer
from app.learner_profile import (
    CurriculumModule,
    CurriculumPlan,
    EloCategoryDefinition,
    EloCategoryPlan,
    EloRubricBand,
    LearnerProfile,
    profile_store,
)
from app.main import app
from app.telemetry import TelemetryEvent, clear_listeners, register_listener
from zoneinfo import ZoneInfo


def _category(key: str, weight: float = 1.0) -> EloCategoryDefinition:
    return EloCategoryDefinition(
        key=key,
        label=key.title(),
        description=f"{key.title()} mastery",
        focus_areas=["practice"],
        weight=weight,
        rubric=[
            EloRubricBand(level="Developing", descriptor="Needs guided practice."),
            EloRubricBand(level="Fluent", descriptor="Operates autonomously."),
        ],
        starting_rating=1100,
    )


def _curriculum(module_key: str) -> CurriculumPlan:
    return CurriculumPlan(
        overview="Personalised curriculum",
        success_criteria=["Ship MVP"],
        modules=[
            CurriculumModule(
                module_id=f"{module_key}-module",
                category_key=module_key,
                title=f"{module_key.title()} Foundations",
                summary="Deepen mastery.",
                objectives=["Objective A", "Objective B"],
                activities=["Workshop"],
                deliverables=["Summary note"],
                estimated_minutes=60,
            )
        ],
    )


def _profile(username: str) -> LearnerProfile:
    plan = EloCategoryPlan(categories=[_category("backend", 1.2)])
    curriculum = _curriculum("backend")
    return LearnerProfile(
        username=username,
        goal="Improve backend reliability.",
        use_case="Automate assessments.",
        strengths="SwiftUI polish",
        timezone="America/Los_Angeles",
        elo_snapshot={"backend": 1120},
        elo_category_plan=plan,
        curriculum_plan=curriculum,
    )


def _collect_events() -> List[TelemetryEvent]:
    events: List[TelemetryEvent] = []
    clear_listeners()

    def _append(event: TelemetryEvent) -> None:
        events.append(event)

    register_listener(_append)
    return events


def test_schedule_refresh_success_emits_telemetry() -> None:
    username = "scheduler-success"
    profile_store.delete(username)
    profile_store.upsert(_profile(username))
    events = _collect_events()
    client = TestClient(app)

    response = client.get(f"/api/profile/{username}/schedule", params={"refresh": "true"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_stale"] is False
    assert body["warnings"] == []
    assert len(body["items"]) >= 1
    assert body["timezone"] == "America/Los_Angeles"

    refreshed = profile_store.get(username)
    assert refreshed is not None
    assert refreshed.curriculum_schedule is not None
    assert refreshed.curriculum_schedule.is_stale is False
    tz = ZoneInfo("America/Los_Angeles")
    expected_anchor = refreshed.curriculum_schedule.generated_at.astimezone(tz).date().isoformat()
    assert body["anchor_date"] == expected_anchor
    first_item = body["items"][0]
    scheduled_for = datetime.fromisoformat(first_item["scheduled_for"])
    assert scheduled_for.tzinfo is not None
    anchor_date_obj = datetime.strptime(body["anchor_date"], "%Y-%m-%d").date()
    expected_date = anchor_date_obj + timedelta(days=first_item["recommended_day_offset"])
    assert scheduled_for.date().isoformat() == expected_date.isoformat()

    names = [event.name for event in events]
    assert "schedule_generation" in names
    assert "schedule_refresh" in names
    assert "long_range_distribution" in names
    generation_events = [event for event in events if event.name == "schedule_generation"]
    refresh_events = [event for event in events if event.name == "schedule_refresh"]
    distribution_events = [event for event in events if event.name == "long_range_distribution"]
    assert generation_events[0].payload["status"] == "success"
    assert refresh_events[0].payload["status"] == "success"
    assert refresh_events[0].payload["regenerated"] is True
    assert refresh_events[0].payload["sessions_per_week"] >= 2
    assert refresh_events[0].payload["projected_weekly_minutes"] >= 0
    assert "long_range_item_count" in refresh_events[0].payload
    assert "average_session_minutes" in refresh_events[0].payload
    assert distribution_events[0].payload["horizon_days"] == refreshed.curriculum_schedule.time_horizon_days
    assert distribution_events[0].payload["window_unique_count"] >= 1

    clear_listeners()
    profile_store.delete(username)


def test_schedule_generation_respects_adjustments() -> None:
    username = "scheduler-adjust"
    profile_store.delete(username)
    profile_store.upsert(_profile(username))
    initial_profile = generate_schedule_for_user(username)
    assert initial_profile.curriculum_schedule is not None
    first_item = initial_profile.curriculum_schedule.items[0]
    target_offset = first_item.recommended_day_offset + 2

    profile_store.apply_schedule_adjustment(username, first_item.item_id, target_offset)
    adjusted_profile = generate_schedule_for_user(username)
    assert adjusted_profile.curriculum_schedule is not None
    adjusted_item = next(item for item in adjusted_profile.curriculum_schedule.items if item.item_id == first_item.item_id)

    assert adjusted_item.recommended_day_offset >= target_offset
    assert adjusted_item.user_adjusted is True
    assert adjusted_profile.schedule_adjustments[first_item.item_id] == adjusted_item.recommended_day_offset

    profile_store.delete(username)


def test_schedule_adjustment_endpoint_updates_schedule() -> None:
    username = "scheduler-adjust-endpoint"
    profile_store.delete(username)
    profile_store.upsert(_profile(username))
    client = TestClient(app)

    initial = client.get(f"/api/profile/{username}/schedule", params={"refresh": "true"})
    assert initial.status_code == 200, initial.text
    initial_payload = initial.json()
    assert initial_payload["items"], "Expected schedule items."
    item_id = initial_payload["items"][0]["item_id"]
    current_offset = initial_payload["items"][0]["recommended_day_offset"]

    response = client.post(
        f"/api/profile/{username}/schedule/adjust",
        json={"item_id": item_id, "days": 3},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    updated_item = next(item for item in payload["items"] if item["item_id"] == item_id)

    assert updated_item["recommended_day_offset"] >= current_offset + 3
    assert updated_item["user_adjusted"] is True

    refreshed_profile = profile_store.get(username)
    assert refreshed_profile is not None
    assert refreshed_profile.curriculum_schedule is not None
    persisted_item = next(item for item in refreshed_profile.curriculum_schedule.items if item.item_id == item_id)
    assert persisted_item.recommended_day_offset == updated_item["recommended_day_offset"]
    assert refreshed_profile.schedule_adjustments[item_id] == updated_item["recommended_day_offset"]
    assert persisted_item.user_adjusted is True

    profile_store.delete(username)


def test_schedule_slice_query_returns_window() -> None:
    username = "scheduler-slice"
    profile_store.delete(username)
    profile_store.upsert(_profile(username))
    client = TestClient(app)

    initial = client.get(f"/api/profile/{username}/schedule", params={"refresh": "true"})
    assert initial.status_code == 200, initial.text
    full_response = client.get(f"/api/profile/{username}/schedule")
    assert full_response.status_code == 200, full_response.text
    full_payload = full_response.json()
    total_items = len(full_payload["items"])
    assert total_items > 0

    start_day = 1
    day_span = 3
    sliced = client.get(
        f"/api/profile/{username}/schedule",
        params={"start_day": start_day, "day_span": day_span},
    )
    assert sliced.status_code == 200, sliced.text
    payload = sliced.json()
    assert "slice" in payload, payload
    slice_meta = payload["slice"]

    assert slice_meta["start_day"] == start_day
    assert slice_meta["day_span"] == day_span
    assert slice_meta["total_items"] == total_items
    assert slice_meta["total_days"] == full_payload["time_horizon_days"]
    assert "has_more" in slice_meta

    for item in payload["items"]:
        offset = item["recommended_day_offset"]
        assert start_day <= offset < start_day + day_span

    profile_store.delete(username)


def test_schedule_refresh_fallback_reuses_previous_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    username = "scheduler-fallback"
    profile_store.delete(username)
    profile_store.upsert(_profile(username))
    client = TestClient(app)

    # Generate the initial schedule so there is something to fall back to.
    initial = client.get(f"/api/profile/{username}/schedule", params={"refresh": "true"})
    assert initial.status_code == 200, initial.text

    events = _collect_events()

    def _fail_build(_profile: LearnerProfile, **_kwargs: object) -> None:
        raise ValueError("forced failure for testing")

    monkeypatch.setattr(sequencer, "build_schedule", _fail_build)

    fallback_response = client.get(f"/api/profile/{username}/schedule", params={"refresh": "true"})
    assert fallback_response.status_code == 200, fallback_response.text
    payload = fallback_response.json()
    assert payload["is_stale"] is True
    assert payload["warnings"], "Expected fallback warning in schedule payload."
    assert "forced failure" in (payload["warnings"][0]["detail"] or "")

    refreshed = profile_store.get(username)
    assert refreshed is not None
    assert refreshed.curriculum_schedule is not None
    assert refreshed.curriculum_schedule.is_stale is True
    assert refreshed.curriculum_schedule.warnings, "Stored schedule should capture the warning."

    names = [event.name for event in events]
    assert "schedule_generation" in names
    assert "schedule_refresh_fallback" in names
    failure_events = [event for event in events if event.name == "schedule_generation"]
    assert failure_events[0].payload["status"] == "error"
    fallback_events = [event for event in events if event.name == "schedule_refresh_fallback"]
    assert fallback_events[0].payload["status"] == "fallback"
    assert fallback_events[0].payload["had_prior_schedule"] is True
    assert "long_range_item_count" in fallback_events[0].payload
    assert "projected_weekly_minutes" in fallback_events[0].payload

    clear_listeners()
    profile_store.delete(username)
