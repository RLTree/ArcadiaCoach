from __future__ import annotations

from app.goal_parser import _sanitize_track
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

    assert sanitized.suggested_weeks is None
    assert sanitized.recommended_modules[0].suggested_weeks == 3
    assert sanitized.recommended_modules[1].suggested_weeks is None
    assert sanitized.recommended_modules[2].suggested_weeks is None
