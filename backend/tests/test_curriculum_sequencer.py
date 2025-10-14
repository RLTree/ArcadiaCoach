"""Tests for the curriculum sequencer service introduced in Phase 11."""

from __future__ import annotations

from datetime import datetime, timezone

from app.assessment_result import AssessmentCategoryOutcome, AssessmentGradingResult
from app.curriculum_sequencer import CurriculumSequencer
from app.learner_profile import (
    CurriculumModule,
    CurriculumPlan,
    CurriculumSchedule,
    EloCategoryDefinition,
    EloCategoryPlan,
    EloRubricBand,
    LearnerProfile,
    SequencedWorkItem,
)
from app.profile_routes import _serialize_profile


def _category(key: str, label: str, weight: float) -> EloCategoryDefinition:
    return EloCategoryDefinition(
        key=key,
        label=label,
        description=f"{label} mastery",
        focus_areas=["practice", "reflection"],
        weight=weight,
        rubric=[
            EloRubricBand(level="Developing", descriptor="Needs guided practice."),
            EloRubricBand(level="Fluent", descriptor="Can operate autonomously."),
        ],
        starting_rating=1100,
    )


def test_curriculum_sequencer_prioritises_low_scores() -> None:
    plan = EloCategoryPlan(
        categories=[
            _category("backend", "Backend Systems", 1.4),
            _category("frontend", "Frontend Flow", 0.6),
        ]
    )
    curriculum = CurriculumPlan(
        overview="Personalised curriculum starter.",
        success_criteria=["Ship a stable release candidate."],
        modules=[
            CurriculumModule(
                module_id="backend-foundations",
                category_key="backend",
                title="Backend Foundations",
                summary="Harden async workflows and observability.",
                objectives=["Review async patterns", "Add structured logging"],
                activities=["Pair review critical path"],
                deliverables=["Instrument the job runner"],
                estimated_minutes=80,
            ),
            CurriculumModule(
                module_id="frontend-overview",
                category_key="frontend",
                title="SwiftUI Refinements",
                summary="Elevate state management and accessibility polish.",
                objectives=["Modernise navigation stack"],
                activities=["Audit accessibility tree"],
                deliverables=["Ship accessibility backlog triage"],
                estimated_minutes=50,
            ),
        ],
    )
    assessment = AssessmentGradingResult(
        submission_id="sub-123",
        evaluated_at=datetime.now(timezone.utc),
        overall_feedback="Great potential with backend depth required next.",
        strengths=["Creative debugging"],
        focus_areas=["Backend architecture"],
        task_results=[],
        category_outcomes=[
            AssessmentCategoryOutcome(
                category_key="backend",
                average_score=0.55,
                initial_rating=1000,
                starting_rating=1100,
                rating_delta=-25,
                rationale="Missed async race conditions.",
            ),
            AssessmentCategoryOutcome(
                category_key="frontend",
                average_score=0.82,
                initial_rating=1220,
                starting_rating=1100,
                rating_delta=18,
                rationale="Solid comprehension with minor polish gaps.",
            ),
        ],
    )
    profile = LearnerProfile(
        username="coder",
        goal="Ship a resilient backend for the Arcadia agent.",
        use_case="Automate grading workflows.",
        strengths="Strong SwiftUI delivery, needs backend flow practice.",
        elo_snapshot={"backend": 1040, "frontend": 1235},
        elo_category_plan=plan,
        curriculum_plan=curriculum,
        onboarding_assessment_result=assessment,
    )

    sequencer = CurriculumSequencer(daily_capacity_minutes=120)
    schedule = sequencer.build_schedule(profile)

    assert schedule.items, "Sequencer should emit at least one item."
    assert schedule.items[0].item_id == "lesson-backend-foundations"
    quiz = next(item for item in schedule.items if item.item_id == "quiz-backend-foundations")
    assert quiz.prerequisites == ["lesson-backend-foundations"]
    milestone = next(item for item in schedule.items if item.kind == "milestone")
    assert set(milestone.prerequisites) == {"lesson-backend-foundations", "quiz-backend-foundations"}
    assert schedule.time_horizon_days >= 7
    assert "Backend architecture" in (schedule.cadence_notes or "")
    assert all(
        later.recommended_day_offset >= earlier.recommended_day_offset
        for earlier, later in zip(schedule.items, schedule.items[1:])
    )
    assert schedule.is_stale is False
    assert schedule.warnings == []
    assert not any(item.user_adjusted for item in schedule.items)


def test_profile_serialization_includes_schedule_payload() -> None:
    schedule = CurriculumSchedule(
        items=[
            SequencedWorkItem(
                item_id="lesson-intro",
                category_key="backend",
                kind="lesson",
                title="Intro Lesson",
                summary="Kick-off workshop.",
                objectives=["Set up environment"],
                prerequisites=[],
                recommended_minutes=40,
                recommended_day_offset=0,
                focus_reason="Assessment score 50%",
                expected_outcome="Environment ready",
                effort_level="moderate",
            ),
            SequencedWorkItem(
                item_id="quiz-intro",
                category_key="backend",
                kind="quiz",
                title="Intro Quiz",
                summary="Quick check-in.",
                objectives=["Confirm setup understanding"],
                prerequisites=["lesson-intro"],
                recommended_minutes=20,
                recommended_day_offset=0,
                focus_reason="Validate baseline",
                expected_outcome="Score above 70%",
                effort_level="light",
            ),
        ]
    )
    profile = LearnerProfile(
        username="tester",
        goal="Land backend improvements.",
        elo_snapshot={"backend": 1100},
        curriculum_schedule=schedule,
    )

    payload = _serialize_profile(profile)

    assert payload.curriculum_schedule is not None
    assert len(payload.curriculum_schedule.items) == 2
    assert payload.curriculum_schedule.items[1].prerequisites == ["lesson-intro"]
    assert payload.curriculum_schedule.is_stale is False
    assert payload.curriculum_schedule.warnings == []
