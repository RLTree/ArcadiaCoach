"""Tests for the curriculum foundation augmentation helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from app.assessment_result import AssessmentCategoryOutcome, AssessmentGradingResult, TaskGradingResult
from app.curriculum_foundations import ensure_foundational_curriculum
from app.learner_profile import (
    CurriculumModule,
    CurriculumPlan,
    EloCategoryDefinition,
    EloRubricBand,
)


def _category(key: str) -> EloCategoryDefinition:
    return EloCategoryDefinition(
        key=key,
        label=key.replace("-", " ").title(),
        description=f"{key} mastery",
        focus_areas=["practice"],
        weight=1.0,
        rubric=[
            EloRubricBand(level="Exploring", descriptor="Learning the basics."),
            EloRubricBand(level="Proficient", descriptor="Confident independently."),
        ],
        starting_rating=1100,
    )


def test_foundations_expand_modules_for_low_scores() -> None:
    plan = CurriculumPlan(
        overview="Initial plan",
        success_criteria=["Ship an MVP"],
        modules=[
            CurriculumModule(
                module_id="existing-module",
                category_key="ai-research",
                title="Existing Module",
                summary="Initial module from agent.",
                objectives=["Objective A"],
                activities=["Activity"],
                deliverables=["Deliverable"],
                estimated_minutes=120,
            )
        ],
    )
    categories = [
        _category("ai-research"),
    ]
    result = AssessmentGradingResult(
        submission_id="sub-1",
        evaluated_at=datetime.now(timezone.utc),
        overall_feedback="Needs fundamentals reinforcement.",
        strengths=[],
        focus_areas=["Python", "Numerical reasoning"],
        task_results=[
            TaskGradingResult(
                task_id="task-1",
                category_key="ai-research",
                task_type="code",
                score=0.2,
                confidence="low",
                feedback="Missing implementation.",
                strengths=[],
                improvements=["Rebuild foundations"],
                rubric=[],
            )
        ],
        category_outcomes=[
            AssessmentCategoryOutcome(
                category_key="ai-research",
                average_score=0.25,
                initial_rating=980,
                starting_rating=1100,
                rating_delta=-80,
                rationale="Limited baseline knowledge.",
            )
        ],
    )

    augmented_categories, augmented_plan = ensure_foundational_curriculum(
        goal="Become a data science and machine learning engineer.",
        plan=plan,
        categories=categories,
        assessment_result=result,
    )

    category_keys = {entry.key for entry in augmented_categories}
    assert "python-foundations" in category_keys
    assert "data-manipulation" in category_keys
    assert "math-statistics" in category_keys
    assert "machine-learning" in category_keys

    module_ids = {module.module_id for module in augmented_plan.modules}
    assert "foundation-python-syntax" in module_ids
    assert "foundation-pandas-proficiency" in module_ids
    assert "foundation-ml-baselines" in module_ids
    assert len(module_ids) > len({module.module_id for module in plan.modules})
    assert "Ship a daily Python practice log covering syntax, functions, and modules." in augmented_plan.success_criteria


def test_foundation_augmentation_is_idempotent() -> None:
    plan = CurriculumPlan(
        overview="Plan",
        success_criteria=[],
        modules=[],
    )
    categories: list[EloCategoryDefinition] = []

    augmented_categories, augmented_plan = ensure_foundational_curriculum(
        goal="Ship AI tooling for analytics teams.",
        plan=plan,
        categories=categories,
        assessment_result=None,
    )

    second_categories, second_plan = ensure_foundational_curriculum(
        goal="Ship AI tooling for analytics teams.",
        plan=augmented_plan,
        categories=augmented_categories,
        assessment_result=None,
    )

    assert len(second_plan.modules) == len(augmented_plan.modules)
    assert {entry.key for entry in second_categories} == {entry.key for entry in augmented_categories}
