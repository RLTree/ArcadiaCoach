"""Orchestrates onboarding curriculum planning and assessment generation (Phase 3)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple, cast
from uuid import uuid4

from agents import ModelSettings, RunConfig, Runner
from chatkit.types import ThreadMetadata
from openai.types.shared.reasoning import Reasoning
from openai.types.shared.reasoning_effort import ReasoningEffort
from pydantic import BaseModel, ValidationError

from .agent_models import (
    CurriculumModulePayload,
    OnboardingAssessmentTaskPayload,
    OnboardingCurriculumPayload,
    OnboardingPlanPayload,
)
from .arcadia_agent import ArcadiaAgentContext, get_arcadia_agent
from .config import Settings
from .learner_profile import (
    AssessmentTask,
    CurriculumModule,
    CurriculumPlan,
    OnboardingAssessment,
    profile_store,
)
from .memory_store import MemoryStore
from .tools import learner_elo_category_plan_set


logger = logging.getLogger(__name__)


class OnboardingPlanResult(BaseModel):
    """Internal helper payload returned by the onboarding planner."""

    curriculum: OnboardingCurriculumPayload
    assessment: List[OnboardingAssessmentTaskPayload]


def _reasoning_effort(value: str) -> ReasoningEffort:
    allowed = {"minimal", "low", "medium", "high"}
    effort = value if value in allowed else "medium"
    return cast(ReasoningEffort, effort)


def _slugify(value: str, fallback: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value or "")
    slug = normalized.strip("-") or fallback
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug


def _coerce_plan_output(payload: Any) -> OnboardingPlanPayload:
    if isinstance(payload, OnboardingPlanPayload):
        return payload
    if isinstance(payload, dict):
        return OnboardingPlanPayload.model_validate(payload)
    if isinstance(payload, BaseModel):
        return OnboardingPlanPayload.model_validate(payload.model_dump())
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Agent returned invalid JSON for onboarding plan: {exc}") from exc
        return OnboardingPlanPayload.model_validate(data)
    raise TypeError(f"Unsupported onboarding plan payload type: {type(payload).__name__}")


def _normalise_module(payload: CurriculumModulePayload) -> CurriculumModule:
    module_id = payload.module_id.strip() if isinstance(payload.module_id, str) else ""
    if not module_id:
        module_id = _slugify(payload.title, f"{payload.category_key}-module")
    return CurriculumModule(
        module_id=module_id,
        category_key=payload.category_key.strip() or _slugify(payload.title, "general"),
        title=payload.title.strip(),
        summary=payload.summary.strip(),
        objectives=[objective.strip() for objective in payload.objectives if objective.strip()],
        activities=[activity.strip() for activity in payload.activities if activity.strip()],
        deliverables=[deliverable.strip() for deliverable in payload.deliverables if deliverable.strip()],
        estimated_minutes=payload.estimated_minutes if payload.estimated_minutes and payload.estimated_minutes > 0 else None,
    )


def _normalise_task(payload: OnboardingAssessmentTaskPayload) -> AssessmentTask:
    task_id = payload.task_id.strip() if isinstance(payload.task_id, str) else ""
    if not task_id:
        task_id = _slugify(f"{payload.category_key}-{payload.title}", "assessment-task")
    task_type = payload.task_type if payload.task_type in {"concept_check", "code"} else "concept_check"
    expected = payload.expected_minutes if payload.expected_minutes and payload.expected_minutes > 0 else 15
    return AssessmentTask(
        task_id=task_id,
        category_key=payload.category_key.strip(),
        title=payload.title.strip(),
        task_type=task_type,  # type: ignore[arg-type]
        prompt=payload.prompt.strip(),
        guidance=payload.guidance.strip(),
        rubric=[descriptor.strip() for descriptor in payload.rubric if descriptor.strip()],
        expected_minutes=expected,
        starter_code=payload.starter_code.strip() if isinstance(payload.starter_code, str) and payload.starter_code.strip() else None,
        answer_key=payload.answer_key.strip() if isinstance(payload.answer_key, str) and payload.answer_key.strip() else None,
    )


def _default_concept_task(category_key: str, label: str, module: CurriculumModule | None) -> AssessmentTask:
    slug = _slugify(f"{category_key}-concept", f"{category_key}-concept")
    summary = module.summary if module else "Review the fundamentals for this skill."
    prompt = (
        f"Summarise the most critical idea you need to master for **{label}** "
        "and explain how you would apply it in your work. Provide at least one concrete example."
    )
    guidance = f"Draw from the curriculum overview: {summary}"
    rubric = [
        "Highlights a key principle or pattern tied to the category.",
        "Connects the idea to the learner's stated goal or use case.",
        "Provides a concrete example demonstrating understanding.",
    ]
    return AssessmentTask(
        task_id=slug,
        category_key=category_key,
        title=f"{label} Concept Reflection",
        task_type="concept_check",  # type: ignore[arg-type]
        prompt=prompt,
        guidance=guidance,
        rubric=rubric,
        expected_minutes=10,
    )


def _default_code_task(category_key: str, label: str, module: CurriculumModule | None) -> AssessmentTask:
    slug = _slugify(f"{category_key}-code", f"{category_key}-code")
    summary = module.summary if module else "Implement a focused exercise that reflects the skill."
    prompt = (
        f"Write Swift or Python code (your choice) that demonstrates the core {label.lower()} capability. "
        "Keep the snippet under 60 lines and include inline comments for key decisions."
    )
    guidance = f"Base your solution on the onboarding module summary: {summary}"
    rubric = [
        "Implements the requested behaviour without critical defects.",
        "Includes descriptive comments or docstrings explaining key steps.",
        "Shows idiomatic structure for the chosen language.",
    ]
    starter_code = "// Start coding here if you choose Swift.\n" "import Foundation\n\n"
    starter_code += "# Or switch to Python by clearing this snippet.\n"
    return AssessmentTask(
        task_id=slug,
        category_key=category_key,
        title=f"{label} Coding Task",
        task_type="code",  # type: ignore[arg-type]
        prompt=prompt,
        guidance=guidance,
        rubric=rubric,
        expected_minutes=25,
        starter_code=starter_code,
    )


def _ensure_task_coverage(
    categories: Iterable[Tuple[str, str]],
    modules: List[CurriculumModule],
    tasks: List[AssessmentTask],
) -> List[AssessmentTask]:
    by_category: Dict[str, Dict[str, List[AssessmentTask]]] = {}
    for task in tasks:
        by_category.setdefault(task.category_key, {"concept_check": [], "code": []})
        by_category[task.category_key].setdefault(task.task_type, []).append(task)

    modules_by_category: Dict[str, CurriculumModule] = {}
    for module in modules:
        modules_by_category.setdefault(module.category_key, module)

    final_tasks = list(tasks)
    for category_key, label in categories:
        coverage = by_category.get(category_key, {"concept_check": [], "code": []})
        module = modules_by_category.get(category_key)
        if not coverage.get("concept_check"):
            final_tasks.append(_default_concept_task(category_key, label, module))
        if not coverage.get("code"):
            final_tasks.append(_default_code_task(category_key, label, module))
    return final_tasks


async def generate_onboarding_bundle(
    settings: Settings,
    username: str,
    goal: str,
    use_case: str,
    strengths: str,
) -> Tuple[CurriculumPlan, OnboardingAssessment]:
    """Invoke the Arcadia agent to generate curriculum + assessment for onboarding."""
    agent = get_arcadia_agent(settings.arcadia_agent_model, settings.arcadia_agent_enable_web)
    thread = ThreadMetadata.model_construct(id=f"onboarding-{_slugify(username, 'learner')}-{uuid4().hex[:6]}")
    metadata: Dict[str, Any] = {
        "username": username,
        "goal": goal,
        "use_case": use_case,
        "strengths": strengths,
    }
    profile = profile_store.apply_metadata(username, metadata)
    profile_snapshot = profile.model_dump(mode="json")
    context = ArcadiaAgentContext.model_construct(
        thread=thread,
        store=MemoryStore(),
        request_context={
            "metadata": metadata,
            "profile": profile_snapshot,
        },
        sanitized_input=None,
        web_enabled=settings.arcadia_agent_enable_web,
        reasoning_level=settings.arcadia_agent_reasoning,
        attachments=[],
    )

    schema_description = (
        "Respond strictly as JSON with keys: profile_summary, curriculum, categories, assessment.\n"
        "curriculum.overview: string, curriculum.success_criteria: string array (>=2 entries).\n"
        "curriculum.modules: array of objects with module_id, category_key, title, summary, objectives (string array), "
        "activities (string array), deliverables (string array), estimated_minutes (integer minutes or null).\n"
        "categories: array of Elo category definitions with key, label, description, focus_areas (array), weight (float), "
        "rubric (array of {level, descriptor}), starting_rating (int).\n"
        "assessment: array of tasks with task_id, category_key, title, task_type ('concept_check' or 'code'), prompt, "
        "guidance, rubric (string array), expected_minutes (int), starter_code (string or null), answer_key (string or null).\n"
        "Ensure every category appears in assessment with at least one concept_check and one code task."
    )

    learner_brief = (
        f"Learner username: {username or 'unspecified'}\n"
        f"Long-term goal: {goal or 'unspecified'}\n"
        f"Primary use case: {use_case or 'unspecified'}\n"
        f"Strengths / prior experience: {strengths or 'unspecified'}\n"
    )

    message = (
        "Design an onboarding curriculum and initial assessment for the learner described below. "
        "Sequence the curriculum into 3-5 modules, tie each to the ELO categories you define, "
        "and create assessment tasks aligned to those categories. "
        "Focus on AuDHD-friendly pacing (chunked steps, explicit success criteria, minimal sensory load). "
        "Return the structured JSON payload described after the learner brief.\n\n"
        f"{learner_brief}\n"
        f"{schema_description}"
    )

    try:
        result = await Runner.run(
            agent,
            message,
            context=context,
            run_config=RunConfig(
                model_settings=ModelSettings(
                    reasoning=Reasoning(
                        effort=_reasoning_effort(settings.arcadia_agent_reasoning),
                        summary="auto",
                    ),
                )
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to generate onboarding bundle: %s", exc)
        raise

    try:
        plan_payload = _coerce_plan_output(result.final_output)
    except (ValidationError, ValueError, TypeError) as exc:
        logger.error("Invalid onboarding plan payload: %s", exc)
        raise

    # Persist the ELO category plan using the existing tool helper for consistency.
    learner_elo_category_plan_set(
        username=username,
        categories=plan_payload.categories,
        source_goal=goal or None,
        strategy_notes=plan_payload.profile_summary,
    )

    curriculum_payload: OnboardingCurriculumPayload = plan_payload.curriculum
    modules = [_normalise_module(module) for module in curriculum_payload.modules]
    curriculum = CurriculumPlan(
        generated_at=datetime.now(timezone.utc),
        overview=curriculum_payload.overview.strip(),
        success_criteria=[criterion.strip() for criterion in curriculum_payload.success_criteria if criterion.strip()],
        modules=modules,
    )

    base_tasks = [_normalise_task(task) for task in plan_payload.assessment]
    categories = [(category.key, category.label) for category in plan_payload.categories]
    ensured_tasks = _ensure_task_coverage(categories, modules, base_tasks)
    assessment = OnboardingAssessment(
        generated_at=datetime.now(timezone.utc),
        status="pending",
        tasks=ensured_tasks,
    )

    profile_store.set_curriculum_and_assessment(username, curriculum, assessment)
    return curriculum, assessment
