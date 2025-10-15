"""Tests for ELO category deduplication and telemetry."""

from __future__ import annotations

from typing import List

import pytest

from app.agent_models import EloCategoryDefinitionPayload, EloRubricBandPayload
from app.learner_profile import LearnerProfile
from app.telemetry import TelemetryEvent, clear_listeners, register_listener
from app.tools import _apply_elo_category_plan


@pytest.fixture(autouse=True)
def _fake_profile_store(monkeypatch: pytest.MonkeyPatch):
    class _Store:
        def __init__(self) -> None:
            self.plan = None

        def set_elo_category_plan(self, username: str, plan):
            self.plan = plan
            return LearnerProfile(username=username, elo_category_plan=plan)

    store = _Store()
    monkeypatch.setattr("app.tools.profile_store", store)
    return store


def test_elo_category_dedup_merges_duplicates() -> None:
    events: List[TelemetryEvent] = []
    clear_listeners()
    register_listener(events.append)

    categories = [
        EloCategoryDefinitionPayload(
            key="Backend Systems",
            label="Backend Systems",
            description="Services and runtime reliability.",
            focus_areas=["observability", "resilience"],
            weight=1.4,
            rubric=[
                EloRubricBandPayload(level="Developing", descriptor="Needs scaffolding"),
            ],
            starting_rating=1080,
        ),
        EloCategoryDefinitionPayload(
            key="backend-systems",
            label="Backend Delivery",
            description="",
            focus_areas=["observability", "deployment", "testing"],
            weight=1.2,
            rubric=[
                EloRubricBandPayload(level="Proficient", descriptor="Operates independently"),
            ],
            starting_rating=1140,
        ),
    ]

    response = _apply_elo_category_plan("dedup-user", categories, source_goal="Ship API")

    merged = response.plan.categories
    assert len(merged) == 1
    category = merged[0]
    assert category.key == "backend-systems"
    assert sorted(category.focus_areas) == ["deployment", "observability", "resilience", "testing"]
    assert category.weight == pytest.approx(1.4)
    assert category.starting_rating == 1140
    levels = {band.level for band in category.rubric}
    assert levels == {"Developing", "Proficient"}

    collision_events = [event for event in events if event.name == "elo_category_collision"]
    assert collision_events, "Expected a collision telemetry event."
    payload = collision_events[0].payload
    assert payload["username"] == "dedup-user"
    assert payload["collision_count"] == 1
    assert payload["categories"][0]["key"] == "backend-systems"
    assert "Backend Delivery" in payload["categories"][0]["labels"]

    clear_listeners()
