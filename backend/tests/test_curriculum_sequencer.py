"""Tests for the curriculum sequencer service introduced in Phase 11."""

from __future__ import annotations

from datetime import datetime, timezone

from app.assessment_result import AssessmentCategoryOutcome, AssessmentGradingResult
from app.curriculum_sequencer import CurriculumSequencer
from app.learner_profile import (
    CategoryPacing,
    CurriculumModule,
    CurriculumPlan,
    CurriculumSchedule,
    EloCategoryDefinition,
    EloCategoryPlan,
    EloRubricBand,
    LearnerProfile,
    ScheduleRationaleEntry,
    SequencedWorkItem,
    FoundationModuleReference,
    FoundationTrack,
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
    assert any(item.item_id.startswith("reinforce-") for item in schedule.items)
    quiz = next(item for item in schedule.items if item.item_id == "quiz-backend-foundations")
    assert quiz.prerequisites == ["lesson-backend-foundations"]
    milestone = next(item for item in schedule.items if item.kind == "milestone")
    assert set(milestone.prerequisites) == {"lesson-backend-foundations", "quiz-backend-foundations"}
    assert schedule.time_horizon_days >= 28
    assert "Backend architecture" in (schedule.cadence_notes or "")
    assert all(
        later.recommended_day_offset >= earlier.recommended_day_offset
        for earlier, later in zip(schedule.items, schedule.items[1:])
    )
    assert schedule.is_stale is False
    assert schedule.warnings == []
    assert not any(item.user_adjusted for item in schedule.items)
    assert schedule.pacing_overview is not None
    assert schedule.category_allocations, "Expected category pacing allocations."
    assert schedule.rationale_history, "Rationale history should be populated."
    assert schedule.rationale_history[-1].related_categories, "Rationale should surface related categories."


def test_sequencer_adds_deep_dive_for_high_priority_track() -> None:
    plan = EloCategoryPlan(
        categories=[
            _category("backend", "Backend Systems", 1.2),
        ]
    )
    curriculum = CurriculumPlan(
        overview="Backend acceleration",
        success_criteria=["Deliver resilient services."],
        modules=[
            CurriculumModule(
                module_id="backend-foundations",
                category_key="backend",
                title="Backend Foundations",
                summary="Harden async patterns and observability.",
                objectives=["Refactor async code", "Instrument tracing"],
                activities=["Audit logging"],
                deliverables=["Ship tracing dashboard"],
                estimated_minutes=120,
            )
        ],
    )
    profile = LearnerProfile(
        username="engineer",
        goal="Ship resilient backend systems.",
        use_case="Automate key services.",
        strengths="Comfortable with SwiftUI, ramping backend skills",
        elo_snapshot={"backend": 980},
        elo_category_plan=plan,
        curriculum_plan=curriculum,
        foundation_tracks=[
            FoundationTrack(
                track_id="backend",
                label="Backend Foundations",
                priority="now",
                confidence="high",
                weight=1.6,
                technologies=["FastAPI"],
                focus_areas=["architecture", "observability"],
                prerequisites=["Python Foundations"],
                recommended_modules=[
                    FoundationModuleReference(
                        module_id="backend-foundations",
                        category_key="backend",
                        priority="core",
                        suggested_weeks=4,
                    )
                ],
            )
        ],
    )

    sequencer = CurriculumSequencer()
    schedule = sequencer.build_schedule(profile)

    deep_dive_items = [item for item in schedule.items if item.item_id.startswith("deepdive-")]
    assert deep_dive_items, "Expected deep dive reinforcement when track weight is high."
    reinforcement = next(item for item in schedule.items if item.item_id == "reinforce-backend-foundations")
    deep_dive = deep_dive_items[0]
    assert deep_dive.category_key == reinforcement.category_key
    assert deep_dive.recommended_minutes >= reinforcement.recommended_minutes


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
        ],
        pacing_overview="Testing cadence summary.",
        category_allocations=[
            CategoryPacing(
                category_key="backend",
                planned_minutes=60,
                target_share=0.5,
                deferral_pressure="medium",
                deferral_count=2,
                max_deferral_days=5,
                rationale="Weight 0.50; ELO 1100",
            )
        ],
        rationale_history=[
            ScheduleRationaleEntry(
                headline="Extended roadmap",
                summary="Focus on backend practice.",
                related_categories=["backend"],
                adjustment_notes=["Maintained learner-selected offsets."],
            )
        ],
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
    assert payload.curriculum_schedule.anchor_date is not None
    assert payload.curriculum_schedule.timezone == "UTC"
    assert payload.curriculum_schedule.items[0].scheduled_for is not None
    assert payload.curriculum_schedule.pacing_overview == "Testing cadence summary."
    assert payload.curriculum_schedule.category_allocations
    assert payload.curriculum_schedule.category_allocations[0].category_key == "backend"
    assert payload.curriculum_schedule.category_allocations[0].deferral_pressure == "medium"
    assert payload.curriculum_schedule.category_allocations[0].deferral_count == 2
    assert payload.curriculum_schedule.rationale_history
    assert payload.curriculum_schedule.rationale_history[0].headline == "Extended roadmap"
