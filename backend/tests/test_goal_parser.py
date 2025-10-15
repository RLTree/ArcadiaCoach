from __future__ import annotations

import pytest

from app.goal_parser import _merge_duplicate_tracks, _sanitize_track
from app.learner_profile import FoundationModuleReference, FoundationTrack


def test_sanitize_track_removes_invalid_weeks() -> None:
    module_valid = FoundationModuleReference(
        module_id="mod-valid",
        category_key="foundations",
        priority="core",
        suggested_weeks=3,
        notes="",
    )
    module_zero = FoundationModuleReference.model_construct(
        module_id="mod-zero",
        category_key="foundations",
        priority="core",
        suggested_weeks=0,
        notes="",
    )
    module_negative = FoundationModuleReference.model_construct(
        module_id="mod-negative",
        category_key="foundations",
        priority="core",
        suggested_weeks=-2,
        notes="",
    )
    track = FoundationTrack.model_construct(
        track_id="example",
        label="Example",
        priority="now",
        confidence="medium",
        weight=1.0,
        technologies=["Python"],
        focus_areas=["syntax"],
        prerequisites=[],
        recommended_modules=[module_valid, module_zero, module_negative],
        suggested_weeks=0,
        notes=None,
    )

    sanitized = _sanitize_track(track)

    module_weeks = [module.suggested_weeks for module in sanitized.recommended_modules]
    assert all(week is not None and week >= 1 for week in module_weeks)
    assert sanitized.suggested_weeks == sum(int(week) for week in module_weeks if week is not None)


def test_merge_duplicate_tracks_combines_fields() -> None:
    module_a = FoundationModuleReference(
        module_id="foundation-python-syntax",
        category_key="python-foundations",
        priority="core",
        suggested_weeks=4,
        notes="Practice daily",
    )
    module_b = FoundationModuleReference(
        module_id="foundation-python-syntax",
        category_key="python-foundations",
        priority="reinforcement",
        suggested_weeks=5,
        notes="",
    )
    track_primary = FoundationTrack(
        track_id="python-foundations",
        label="Python Foundations",
        priority="now",
        confidence="medium",
        weight=1.0,
        technologies=["Python"],
        focus_areas=["syntax"],
        prerequisites=["Basics"],
        recommended_modules=[module_a],
        suggested_weeks=6,
        notes="Focus on fundamentals.",
    )
    track_secondary = FoundationTrack(
        track_id="python-foundations",
        label="Python Foundations",
        priority="up_next",
        confidence="high",
        weight=1.5,
        technologies=["CLI"],
        focus_areas=["tooling"],
        prerequisites=["Basics", "Typing"],
        recommended_modules=[module_b],
        suggested_weeks=8,
        notes="Review tooling.",
    )

    merged = _merge_duplicate_tracks([track_primary, track_secondary])

    assert len(merged) == 1
    track = merged[0]
    assert track.weight == pytest.approx(1.5)
    assert track.priority == "now"
    assert track.confidence == "high"
    assert sorted(track.focus_areas) == ["syntax", "tooling"]
    assert sorted(track.prerequisites) == ["Basics", "Typing"]
    assert any(module.priority == "core" for module in track.recommended_modules)
