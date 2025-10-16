"""Tests for the curriculum sequencer service introduced in Phase 11."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.assessment_result import AssessmentCategoryOutcome, AssessmentGradingResult
from app.curriculum_sequencer import (
    CurriculumSequencer,
    LONG_RANGE_THRESHOLD_DAYS,
    NEAR_TERM_SMOOTHING_WINDOW_DAYS,
    MAX_CONSECUTIVE_CATEGORY_ITEMS,
)
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
    MilestoneCompletion,
)
from app.profile_routes import _serialize_profile
from app.tools import _schedule_payload


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


def test_large_modules_are_split_into_multiple_sessions() -> None:
    plan = EloCategoryPlan(
        categories=[
            _category("ml", "Machine Learning", 1.2),
        ]
    )
    curriculum = CurriculumPlan(
        overview="Deep dive curriculum",
        success_criteria=["Ship advanced ML pipeline"],
        modules=[
            CurriculumModule(
                module_id="ml-foundations",
                category_key="ml",
                title="ML Foundations Marathon",
                summary="Expanded coverage of ML theory and practice.",
                objectives=["Revisit ML math", "Implement core algorithms"],
                activities=["Work through extended labs"],
                deliverables=["Document takeaway journal"],
                estimated_minutes=540,
            )
        ],
    )
    profile = LearnerProfile(
        username="long-session",
        goal="Become a senior ML engineer.",
        use_case="Advanced curriculum planning",
        strengths="Strong coding background",
        elo_snapshot={"ml": 900},
        elo_category_plan=plan,
        curriculum_plan=curriculum,
    )

    sequencer = CurriculumSequencer()
    schedule = sequencer.build_schedule(profile)

    lesson_parts = [item for item in schedule.items if item.item_id.startswith("lesson-ml-foundations")]
    assert len(lesson_parts) == math.ceil(540 / 120)
    assert sum(part.recommended_minutes for part in lesson_parts) == 540
    assert all(part.recommended_minutes <= 120 for part in lesson_parts)
    assert lesson_parts[0].item_id == "lesson-ml-foundations"
    assert lesson_parts[-1].item_id == "lesson-ml-foundations-part5"

    quiz_parts = [item for item in schedule.items if item.item_id.startswith("quiz-ml-foundations")]
    assert quiz_parts, "Expected quiz segments for split module."
    assert quiz_parts[0].prerequisites == [lesson_parts[-1].item_id]
    assert all(part.recommended_minutes <= 120 for part in quiz_parts)


def test_dependency_order_precedes_priority() -> None:
    plan = EloCategoryPlan(
        categories=[
            _category("python", "Python Foundations", 1.0),
        ]
    )
    curriculum = CurriculumPlan(
        overview="Python progression",
        success_criteria=["Ship dependable Python automation."],
        modules=[
            CurriculumModule(
                module_id="python-testing",
                category_key="python",
                title="Testing & Tooling",
                summary="Advanced testing patterns.",
                objectives=["Adopt pytest and tooling."],
                activities=["Backfill tests."],
                deliverables=["Testing plan."],
                estimated_minutes=120,
                tier=2,
                prerequisite_module_ids=["python-basics"],
            ),
            CurriculumModule(
                module_id="python-basics",
                category_key="python",
                title="Python Basics",
                summary="Refresh syntax fundamentals.",
                objectives=["Reinforce syntax."],
                activities=["Syntax drills."],
                deliverables=["Practice journal."],
                estimated_minutes=90,
                tier=1,
            ),
        ],
    )
    profile = LearnerProfile(
        username="dependency-check",
        goal="Automate workflows with reliable Python tooling.",
        use_case="Agent support.",
        strengths="Strong SwiftUI background",
        elo_snapshot={"python": 950},
        elo_category_plan=plan,
        curriculum_plan=curriculum,
    )

    sequencer = CurriculumSequencer()
    schedule = sequencer.build_schedule(profile)

    lesson_ids = [item.item_id for item in schedule.items if item.item_id.startswith("lesson-")]
    assert lesson_ids, "Expected lessons in the generated schedule."
    assert lesson_ids[0] == "lesson-python-basics", "Intro module should precede dependent advanced module."
    assert any(item.item_id == "lesson-python-testing" for item in schedule.items)


def test_milestone_rotates_after_recent_completion() -> None:
    plan = EloCategoryPlan(
        categories=[
            _category("backend", "Backend Systems", 1.2),
            _category("frontend", "Frontend Flow", 1.1),
        ]
    )
    curriculum = CurriculumPlan(
        overview="Full stack progression",
        success_criteria=["Ship cohesive feature"],
        modules=[
            CurriculumModule(
                module_id="backend-api",
                category_key="backend",
                title="Backend API Foundations",
                summary="Harden API ergonomics.",
                objectives=["Design endpoints"],
                activities=["Workshop"],
                deliverables=["API spec"],
                estimated_minutes=80,
            ),
            CurriculumModule(
                module_id="frontend-ui",
                category_key="frontend",
                title="Frontend UI Iteration",
                summary="Polish SwiftUI flows.",
                objectives=["Improve state flow"],
                activities=["UI refactor"],
                deliverables=["Updated views"],
                estimated_minutes=70,
            ),
        ],
    )
    profile = LearnerProfile(
        username="milestone-rotation",
        goal="Ship cohesive feature",
        use_case="Adaptive curriculum",
        strengths="Testing discipline",
        elo_snapshot={"backend": 980, "frontend": 940},
        elo_category_plan=plan,
        curriculum_plan=curriculum,
        milestone_completions=[
            MilestoneCompletion(
                completion_id="complete-backend",
                item_id="milestone-backend",
                category_key="backend",
                title="Milestone Backend",
                recorded_at=datetime.now(timezone.utc),
                elo_focus=["backend"],
            )
        ],
    )

    sequencer = CurriculumSequencer()
    schedule = sequencer.build_schedule(profile)

    milestone_items = [item for item in schedule.items if item.kind == "milestone"]
    assert milestone_items, "Expected milestone in generated schedule."
    assert milestone_items[0].category_key == "frontend"


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
    assert schedule.time_horizon_days >= 150
    assert "Backend architecture" in (schedule.cadence_notes or "")
    assert all(
        later.recommended_day_offset >= earlier.recommended_day_offset
        for earlier, later in zip(schedule.items, schedule.items[1:])
    )
    assert schedule.is_stale is False
    assert schedule.warnings == []
    assert not any(item.user_adjusted for item in schedule.items)
    assert schedule.pacing_overview is not None
    assert "minutes/week" in (schedule.pacing_overview or "")
    assert schedule.category_allocations, "Expected category pacing allocations."
    assert schedule.rationale_history, "Rationale history should be populated."
    assert schedule.rationale_history[-1].related_categories, "Rationale should surface related categories."
    assert schedule.long_range_item_count >= 1
    assert schedule.projected_weekly_minutes > 0
    assert schedule.sessions_per_week >= 2
    assert schedule.extended_weeks >= 20
    assert schedule.long_range_category_keys, "Expected long-range categories to be captured."


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


def test_schedule_payload_marks_milestone_locked() -> None:
    schedule = CurriculumSchedule(
        items=[
            SequencedWorkItem(
                item_id="lesson-foundations",
                category_key="backend",
                kind="lesson",
                title="Backend Foundations",
                objectives=[],
                prerequisites=[],
                recommended_minutes=60,
                recommended_day_offset=0,
                effort_level="moderate",
                launch_status="pending",
            ),
            SequencedWorkItem(
                item_id="milestone-backend",
                category_key="backend",
                kind="milestone",
                title="Backend Milestone",
                objectives=[],
                prerequisites=["lesson-foundations"],
                recommended_minutes=120,
                recommended_day_offset=1,
                effort_level="focus",
                launch_status="pending",
            ),
        ]
    )
    payload = _schedule_payload(schedule)
    assert payload is not None
    assert payload.items[1].launch_locked_reason is not None
    guidance = payload.items[1].milestone_guidance
    assert guidance is not None
    assert guidance.state == "locked"
    assert "Locked" in guidance.badges

    schedule.items[0].launch_status = "completed"
    payload_after = _schedule_payload(schedule)
    assert payload_after is not None
    assert payload_after.items[1].launch_locked_reason is None
    guidance_after = payload_after.items[1].milestone_guidance
    assert guidance_after is not None
    assert guidance_after.state == "ready"


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
        sessions_per_week=3,
        projected_weekly_minutes=240,
        long_range_item_count=2,
        extended_weeks=24,
        long_range_category_keys=["backend"],
    )
    profile = LearnerProfile(
        username="tester",
        goal="Land backend improvements.",
        elo_snapshot={"backend": 1100},
        curriculum_schedule=schedule,
    )

    from unittest.mock import patch

    with patch("app.profile_routes.submission_store.list_user", return_value=[]):
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
    assert payload.curriculum_schedule.sessions_per_week == 3
    assert payload.curriculum_schedule.projected_weekly_minutes == 240
    assert payload.curriculum_schedule.long_range_item_count == 2
    assert payload.curriculum_schedule.extended_weeks == 24
    assert payload.curriculum_schedule.long_range_category_keys == ["backend"]
    assert payload.curriculum_schedule.items[0].launch_status == "pending"
    assert payload.curriculum_schedule.items[0].last_launched_at is None


def test_sequencer_near_term_mix_spans_categories() -> None:
    plan = EloCategoryPlan(
        categories=[
            _category("backend", "Backend Systems", 1.4),
            _category("frontend", "Frontend Flow", 1.1),
            _category("data", "Data Foundations", 1.0),
        ]
    )
    curriculum = CurriculumPlan(
        overview="Cross-disciplinary roadmap.",
        success_criteria=["Ship cohesive experience."],
        modules=[
            CurriculumModule(
                module_id="backend-async",
                category_key="backend",
                title="Async Services",
                summary="Strengthen backend async primitives.",
                objectives=["Refine async tasks"],
                activities=["Instrument tracing"],
                deliverables=["Async audit"],
                estimated_minutes=90,
            ),
            CurriculumModule(
                module_id="frontend-accessibility",
                category_key="frontend",
                title="Accessible Navigation",
                summary="Harden SwiftUI navigation for accessibility.",
                objectives=["Improve focus order"],
                activities=["Audit accessibility tree"],
                deliverables=["Accessibility report"],
                estimated_minutes=70,
            ),
            CurriculumModule(
                module_id="data-modeling",
                category_key="data",
                title="Data Modeling",
                summary="Establish durable analytics pipelines.",
                objectives=["Design warehouse schema"],
                activities=["Model critical dashboards"],
                deliverables=["Schema proposal"],
                estimated_minutes=80,
            ),
        ],
    )
    profile = LearnerProfile(
        username="mix-check",
        goal="Deliver cohesive full-stack improvements.",
        use_case="Adaptive curriculum coaching.",
        strengths="Strong design instincts",
        elo_snapshot={"backend": 950, "frontend": 1020, "data": 980},
        elo_category_plan=plan,
        curriculum_plan=curriculum,
    )

    sequencer = CurriculumSequencer()
    schedule = sequencer.build_schedule(profile)

    window_limit = NEAR_TERM_SMOOTHING_WINDOW_DAYS
    window_categories = {
        item.category_key for item in schedule.items if item.recommended_day_offset < window_limit
    }

    assert len(window_categories) >= 3, "Expected at least three categories represented in the near-term window."


def test_long_range_refreshers_limit_consecutive_runs() -> None:
    plan = EloCategoryPlan(
        categories=[
            _category("backend", "Backend Systems", 1.3),
            _category("frontend", "Frontend Flow", 1.0),
            _category("data", "Data Fluency", 0.9),
        ]
    )
    curriculum = CurriculumPlan(
        overview="Balanced roadmap.",
        success_criteria=["Ship balanced upgrades."],
        modules=[
            CurriculumModule(
                module_id="backend-foundations",
                category_key="backend",
                title="Backend Foundations",
                summary="Refresh backend architecture.",
                objectives=["Refactor core services"],
                activities=["Pair on service design"],
                deliverables=["Async plan"],
                estimated_minutes=100,
            ),
            CurriculumModule(
                module_id="frontend-polish",
                category_key="frontend",
                title="Frontend Polish",
                summary="Elevate SwiftUI ergonomics.",
                objectives=["Improve state management"],
                activities=["Accessibility audit"],
                deliverables=["Navigation prototype"],
                estimated_minutes=80,
            ),
            CurriculumModule(
                module_id="data-analytics",
                category_key="data",
                title="Analytics Foundations",
                summary="Build analytics baseline.",
                objectives=["Define metrics"],
                activities=["Author dashboards"],
                deliverables=["Analytics backlog"],
                estimated_minutes=85,
            ),
        ],
    )
    profile = LearnerProfile(
        username="long-range-check",
        goal="Sustain balanced learning momentum.",
        use_case="Adaptive loop improvements.",
        strengths="Rapid prototyping",
        elo_snapshot={"backend": 920, "frontend": 1010, "data": 960},
        elo_category_plan=plan,
        curriculum_plan=curriculum,
    )

    sequencer = CurriculumSequencer()
    schedule = sequencer.build_schedule(profile)

    long_range_items = [
        item for item in schedule.items if item.recommended_day_offset >= LONG_RANGE_THRESHOLD_DAYS
    ]
    assert long_range_items, "Expected spaced refreshers to populate the long-range horizon."
    long_range_categories = {item.category_key for item in long_range_items}
    assert len(long_range_categories) >= 2, "Expected at least two categories in the long-range sequence."

    consecutive = 1
    for earlier, later in zip(long_range_items, long_range_items[1:]):
        if later.category_key == earlier.category_key:
            consecutive += 1
            assert (
                consecutive <= MAX_CONSECUTIVE_CATEGORY_ITEMS
            ), f"Detected {consecutive} consecutive items for {later.category_key}"
        else:
            consecutive = 1
