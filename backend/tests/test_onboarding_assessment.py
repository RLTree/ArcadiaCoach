"""Tests for onboarding curriculum and assessment persistence helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.learner_profile import (
    AssessmentSection,
    AssessmentTask,
    CurriculumModule,
    CurriculumPlan,
    LearnerProfileStore,
    OnboardingAssessment,
)
from app.onboarding_assessment import _ensure_task_coverage


def _store(tmp_path: Path) -> LearnerProfileStore:
    path = tmp_path / "profiles.json"
    return LearnerProfileStore(path)


def test_set_curriculum_and_assessment_persists_fields(tmp_path: Path) -> None:
    store = _store(tmp_path)
    curriculum = CurriculumPlan(
        overview="Launch pad for backend specialisation",
        success_criteria=["Complete code assessment", "Explain architecture trade-offs"],
        modules=[
            CurriculumModule(
                module_id="foundations",
                category_key="backend-foundations",
                title="Backend foundations",
                summary="Refresh async Python and FastAPI pragmatics.",
                objectives=["Rehearse async patterns"],
                activities=["Pair program request handlers"],
                deliverables=["Refactor existing endpoint"],
                estimated_minutes=90,
            )
        ],
    )
    assessment = OnboardingAssessment(
        tasks=[
            AssessmentTask(
                task_id="foundations-concept-1",
                category_key="backend-foundations",
                title="Explain async pitfalls",
                task_type="concept_check",
                prompt="Describe a race condition you recently fixed.",
                guidance="Be concrete about coroutine scheduling.",
                rubric=["Highlights failure scenario", "Provides mitigation"],
                expected_minutes=12,
            )
        ],
        sections=[
            AssessmentSection(
                section_id="concept",
                title="Conceptual Foundations",
                intent="concept",
                expected_minutes=12,
                tasks=[
                    AssessmentTask(
                        task_id="foundations-concept-1",
                        category_key="backend-foundations",
                        title="Explain async pitfalls",
                        task_type="concept_check",
                        prompt="Describe a race condition you recently fixed.",
                        guidance="Be concrete about coroutine scheduling.",
                        rubric=["Highlights failure scenario", "Provides mitigation"],
                        expected_minutes=12,
                        section_id="concept",
                    )
                ],
            )
        ]
    )

    result = store.set_curriculum_and_assessment("learner", curriculum, assessment)

    assert result.curriculum_plan is not None
    assert result.curriculum_plan.overview == curriculum.overview
    assert result.onboarding_assessment is not None
    assert len(result.onboarding_assessment.tasks) == 1
    assert len(result.onboarding_assessment.sections) == 1

    updated = store.update_assessment_status("learner", "in_progress")
    assert updated.onboarding_assessment is not None
    assert updated.onboarding_assessment.status == "in_progress"

    with pytest.raises(LookupError):
        store.update_assessment_status("missing", "completed")

    with pytest.raises(ValueError):
        store.update_assessment_status("learner", "done")


def test_ensure_task_coverage_adds_missing_categories() -> None:
    categories = [("ml-systems", "ML Systems")]
    modules = [
        CurriculumModule(
            module_id="ml-systems",
            category_key="ml-systems",
            title="ML Ops overview",
            summary="Review deployment, monitoring, and evaluation loops.",
            objectives=["Outline ML deployment steps"],
            activities=[],
            deliverables=[],
            estimated_minutes=75,
        )
    ]
    tasks: list[AssessmentTask] = []

    ensured = _ensure_task_coverage(categories, modules, tasks)
    matching = [task for task in ensured if task.category_key == "ml-systems"]

    assert {task.task_type for task in matching} == {"concept_check", "code"}
    assert all(task.expected_minutes > 0 for task in matching)


def test_ensure_task_coverage_handles_augmented_categories_without_modules() -> None:
    categories = [
        ("backend-foundations", "Backend Foundations"),
        ("data-fluency", "Data Fluency"),
        ("backend-foundations", "Duplicate backend entry"),
    ]
    modules = [
        CurriculumModule(
            module_id="backend-foundations",
            category_key="backend-foundations",
            title="Backend Foundations",
            summary="Deepen backend mastery.",
            objectives=["Ship reliable services"],
            activities=[],
            deliverables=[],
            estimated_minutes=80,
        )
    ]
    tasks = [
        AssessmentTask(
            task_id="backend-foundations-concept",
            category_key="backend-foundations",
            title="Backend Reflection",
            task_type="concept_check",
            prompt="Explain recent backend learning.",
            guidance="Be specific about async patterns.",
            rubric=["Highlights async gap"],
            expected_minutes=15,
        )
    ]

    ensured = _ensure_task_coverage(categories, modules, tasks)

    backend_tasks = [task for task in ensured if task.category_key == "backend-foundations"]
    data_tasks = [task for task in ensured if task.category_key == "data-fluency"]

    assert {task.task_type for task in backend_tasks} == {"concept_check", "code"}
    assert {task.task_type for task in data_tasks} == {"concept_check", "code"}
