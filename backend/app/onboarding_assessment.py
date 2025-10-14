"""Orchestrates onboarding curriculum planning and assessment generation (Phase 3)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Sequence, Tuple, cast
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
    AssessmentSection,
    AssessmentTask,
    CurriculumModule,
    CurriculumPlan,
    EloCategoryDefinition,
    EloCategoryPlan,
    EloRubricBand,
    FoundationTrack,
    GoalParserInference,
    OnboardingAssessment,
    profile_store,
)
from .memory_store import MemoryStore
from .telemetry import emit_event
from .curriculum_foundations import ensure_foundational_curriculum
from .curriculum_sequencer import generate_schedule_for_user
from .goal_parser import ensure_goal_inference
logger = logging.getLogger(__name__)


class OnboardingPlanResult(BaseModel):
    """Internal helper payload returned by the onboarding planner."""

    curriculum: OnboardingCurriculumPayload
    assessment: List[OnboardingAssessmentTaskPayload]


def _reasoning_effort(value: str) -> ReasoningEffort:
    allowed = {"minimal", "low", "medium", "high"}
    effort = value if value in allowed else "medium"
    return cast(ReasoningEffort, effort)


MIN_TASKS_PER_CATEGORY = 3


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


def _normalise_category_definition(entry: Any) -> EloCategoryDefinition:
    key = entry.key.strip() if isinstance(entry.key, str) else ""
    label = entry.label.strip() if isinstance(entry.label, str) else ""
    if not key:
        key = _slugify(label, "category")
    description = entry.description.strip() if isinstance(entry.description, str) else ""
    focus = [
        item.strip()
        for item in getattr(entry, "focus_areas", []) or []
        if isinstance(item, str) and item.strip()
    ]
    rubric_payload = getattr(entry, "rubric", []) or []
    rubric: List[EloRubricBand] = []
    for band in rubric_payload:
        level = getattr(band, "level", "")
        descriptor = getattr(band, "descriptor", "")
        if isinstance(level, str) and level.strip():
            rubric.append(
                EloRubricBand(
                    level=level.strip(),
                    descriptor=descriptor.strip() if isinstance(descriptor, str) else "",
                )
            )
    weight = float(entry.weight) if isinstance(entry.weight, (int, float)) else 1.0
    starting = int(entry.starting_rating) if isinstance(entry.starting_rating, (int, float)) else 1100
    return EloCategoryDefinition(
        key=key,
        label=label or key.replace("-", " ").title(),
        description=description,
        focus_areas=focus,
        weight=max(weight, 0.0),
        rubric=rubric,
        starting_rating=max(starting, 0),
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


def _default_extension_task(
    category_key: str,
    label: str,
    module: CurriculumModule | None,
    sequence: int,
) -> AssessmentTask:
    slug = _slugify(f"{category_key}-scenario-{sequence}", f"{category_key}-scenario-{sequence}")
    summary = module.summary if module else f"Identify practical applications for {label.lower()}."
    prompt = (
        f"Describe a scenario where {label.lower()} becomes critical to delivering your goal. "
        "Explain the signals that reveal an issue, how you would triage it, and the steps you would take to resolve or escalate."
    )
    guidance = (
        f"Anchor your answer in the onboarding module context: {summary}. "
        "List at least one risk you would monitor and how you would communicate progress."
    )
    rubric = [
        "Provides a realistic scenario tied to the learner's objectives.",
        "Highlights telemetry, heuristics, or decision points used to evaluate success.",
        "Identifies trade-offs, risks, or follow-up actions for sustained improvement.",
    ]
    return AssessmentTask(
        task_id=slug,
        category_key=category_key,
        title=f"{label} Scenario Walkthrough",
        task_type="concept_check",  # type: ignore[arg-type]
        prompt=prompt,
        guidance=guidance,
        rubric=rubric,
        expected_minutes=18,
    )


def _ensure_task_coverage(
    categories: Iterable[Tuple[str, str]],
    modules: List[CurriculumModule],
    tasks: List[AssessmentTask],
) -> List[AssessmentTask]:
    seen: set[str] = set()
    ordered_categories: List[Tuple[str, str]] = []
    for category_key, label in categories:
        normalized_key = category_key.strip()
        if not normalized_key or normalized_key in seen:
            continue
        seen.add(normalized_key)
        ordered_categories.append((normalized_key, label))

    by_category: Dict[str, Dict[str, List[AssessmentTask]]] = {}

    def _register(task: AssessmentTask) -> None:
        entry = by_category.setdefault(task.category_key, {"concept_check": [], "code": []})
        entry.setdefault(task.task_type, []).append(task)

    for task in tasks:
        _register(task)

    modules_by_category: Dict[str, CurriculumModule] = {}
    for module in modules:
        modules_by_category.setdefault(module.category_key, module)

    final_tasks = list(tasks)
    for category_key, label in ordered_categories:
        coverage = by_category.setdefault(category_key, {"concept_check": [], "code": []})
        module = modules_by_category.get(category_key)
        if not coverage.get("concept_check"):
            concept = _default_concept_task(category_key, label, module)
            final_tasks.append(concept)
            _register(concept)
            coverage = by_category[category_key]
        if not coverage.get("code"):
            code_task = _default_code_task(category_key, label, module)
            final_tasks.append(code_task)
            _register(code_task)
            coverage = by_category[category_key]

        total = len(coverage.get("concept_check", [])) + len(coverage.get("code", []))
        extension_index = 1
        while total < MIN_TASKS_PER_CATEGORY:
            extension = _default_extension_task(category_key, label, module, extension_index)
            final_tasks.append(extension)
            _register(extension)
            coverage = by_category[category_key]
            total = len(coverage.get("concept_check", [])) + len(coverage.get("code", []))
            extension_index += 1

    return final_tasks


def _sum_minutes(tasks: Iterable[AssessmentTask]) -> int:
    return sum(task.expected_minutes for task in tasks)


def _select_category(
    categories: Sequence[EloCategoryDefinition],
    keywords: Iterable[str],
    fallback: str,
) -> str:
    lowered_keywords = [keyword.lower() for keyword in keywords]
    for category in categories:
        haystack = (
            " ".join(
                [
                    category.key,
                    category.label,
                    category.description,
                    " ".join(category.focus_areas),
                ]
            ).lower()
        )
        if any(keyword in haystack for keyword in lowered_keywords):
            return category.key
    return fallback


def _find_track_for_keywords(
    inference: GoalParserInference | None,
    keywords: Iterable[str],
) -> FoundationTrack | None:
    if inference is None:
        return None
    lowered = [keyword.lower() for keyword in keywords]
    for track in inference.tracks:
        haystack = " ".join(
            [track.track_id, track.label, " ".join(track.technologies), " ".join(track.focus_areas)]
        ).lower()
        if any(keyword in haystack for keyword in lowered):
            return track
    return None


def _create_section(
    section_id: str,
    title: str,
    intent: str,
    description: str,
    tasks: List[AssessmentTask],
) -> AssessmentSection:
    return AssessmentSection(
        section_id=section_id,
        title=title,
        description=description,
        intent=intent,  # type: ignore[arg-type]
        expected_minutes=max(_sum_minutes(tasks), 15),
        tasks=tasks,
    )


def _create_data_task(
    category_key: str,
    inference: GoalParserInference | None,
) -> AssessmentTask:
    track = _find_track_for_keywords(inference, ["data", "analysis", "pandas", "numpy", "ml"])
    context = track.label if track else "data workflows"
    prompt = (
        f"Using Python, outline how you would load, validate, and explore a dataset that supports your long-term goal. "
        f"Demonstrate critical steps in {context.lower()} by writing sample code or pseudocode, "
        "including how you would catch data quality issues and communicate insights."
    )
    guidance = (
        "Describe the libraries, validation checks, and summarisation steps you rely on before modelling or decision-making. "
        "Highlight where you automate the workflow and the questions you would ask after the initial pass."
    )
    rubric = [
        "Describes a reproducible ingestion and validation process.",
        "Shows familiarity with vectorised operations or tidy data pipelines.",
        "Explains how insights connect back to the learner's long-term goal.",
    ]
    starter_code = (
        "import pandas as pd\n\n"
        "# Load a dataset related to your goal.\n"
        "df = pd.read_csv(\"./sample.csv\")\n"
        "print(df.head())\n"
    )
    task_id = _slugify(f"{category_key}-data-diagnostic", "data-diagnostic")
    return AssessmentTask(
        task_id=task_id,
        category_key=category_key,
        title="Data Manipulation Diagnostic",
        task_type="code",  # type: ignore[arg-type]
        section_id="data",
        prompt=prompt,
        guidance=guidance,
        rubric=rubric,
        expected_minutes=35,
        starter_code=starter_code,
    )


def _create_architecture_task(
    category_key: str,
    inference: GoalParserInference | None,
) -> AssessmentTask:
    track = _find_track_for_keywords(inference, ["architecture", "backend", "system", "service", "api"])
    system_label = track.label if track else "your target system"
    prompt = (
        f"Sketch the high-level architecture for {system_label.lower()}, highlighting the core components, data flows, "
        "and reliability considerations you would prioritise in the first implementation."
    )
    guidance = (
        "List the services, queues, or modules you would build, and explain how you would monitor, test, and iterate on them. "
        "Call out any open questions you would investigate before shipping."
    )
    rubric = [
        "Identifies key components and responsibilities with clear boundaries.",
        "Addresses deployment, observability, or failure recovery considerations.",
        "Connects the architecture back to the learner's stated goal and constraints.",
    ]
    task_id = _slugify(f"{category_key}-architecture-plan", "architecture-plan")
    return AssessmentTask(
        task_id=task_id,
        category_key=category_key,
        title="Architecture Planning Reflection",
        task_type="concept_check",  # type: ignore[arg-type]
        section_id="architecture",
        prompt=prompt,
        guidance=guidance,
        rubric=rubric,
        expected_minutes=25,
    )


def _create_tooling_task(
    category_key: str,
    inference: GoalParserInference | None,
) -> AssessmentTask:
    track = _find_track_for_keywords(inference, ["tooling", "workflow", "testing", "automation", "devops"])
    label = track.label if track else "your development workflow"
    prompt = (
        f"Detail the tooling stack you rely on (or plan to adopt) to support {label.lower()}, covering editors, "
        "automation, testing, documentation, and accessibility preferences."
    )
    guidance = (
        "Explain how each tool speeds up feedback loops, reduces cognitive load, or supports collaboration. "
        "Call out gaps you want to close over the next month."
    )
    rubric = [
        "Lists concrete tools and explains why each matters for the learner's goals.",
        "Highlights gaps or pain points that should shape upcoming lessons.",
        "Connects tooling choices to sustainable, accessible workflows.",
    ]
    task_id = _slugify(f"{category_key}-tooling-audit", "tooling-audit")
    return AssessmentTask(
        task_id=task_id,
        category_key=category_key,
        title="Tooling & Workflow Audit",
        task_type="concept_check",  # type: ignore[arg-type]
        section_id="tooling",
        prompt=prompt,
        guidance=guidance,
        rubric=rubric,
        expected_minutes=20,
    )


def _build_assessment_sections(
    base_tasks: List[AssessmentTask],
    categories: Sequence[EloCategoryDefinition],
    inference: GoalParserInference | None,
) -> Tuple[List[AssessmentTask], List[AssessmentSection]]:
    final_tasks = [task.model_copy(deep=True) for task in base_tasks]
    sections: List[AssessmentSection] = []

    concept_tasks = [task for task in final_tasks if task.task_type == "concept_check"]
    for task in concept_tasks:
        task.section_id = "concept"
    if concept_tasks:
        sections.append(
            _create_section(
                section_id="concept",
                title="Conceptual Foundations",
                intent="concept",
                description="Capture baseline conceptual understanding across priority categories.",
                tasks=concept_tasks,
            )
        )

    code_tasks = [task for task in final_tasks if task.task_type == "code"]
    for task in code_tasks:
        task.section_id = "coding"
    if code_tasks:
        sections.append(
            _create_section(
                section_id="coding",
                title="Hands-on Coding",
                intent="coding",
                description="Evaluate implementation habits and code fluency before advancing the roadmap.",
                tasks=code_tasks,
            )
        )

    fallback_category = categories[0].key if categories else (final_tasks[0].category_key if final_tasks else "foundations")
    data_category = _select_category(categories, ["data", "analysis", "numpy", "pandas", "ml"], fallback_category)
    data_task = _create_data_task(data_category, inference)
    final_tasks.append(data_task)
    sections.append(
        _create_section(
            section_id="data",
            title="Data Manipulation",
            intent="data",
            description="Probe data wrangling instincts, validation habits, and exploratory analysis workflows.",
            tasks=[data_task],
        )
    )

    architecture_category = _select_category(
        categories,
        ["architecture", "backend", "system", "service", "api"],
        fallback_category,
    )
    architecture_task = _create_architecture_task(architecture_category, inference)
    final_tasks.append(architecture_task)
    sections.append(
        _create_section(
            section_id="architecture",
            title="Architecture & Systems",
            intent="architecture",
            description="Assess systems thinking, planning, and reliability considerations.",
            tasks=[architecture_task],
        )
    )

    tooling_category = _select_category(
        categories,
        ["tooling", "workflow", "testing", "automation", "devops"],
        fallback_category,
    )
    tooling_task = _create_tooling_task(tooling_category, inference)
    final_tasks.append(tooling_task)
    sections.append(
        _create_section(
            section_id="tooling",
            title="Tooling & Workflow",
            intent="tooling",
            description="Understand the learner's habits around automation, accessibility, and daily workflows.",
            tasks=[tooling_task],
        )
    )

    return final_tasks, sections


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
    inference = await ensure_goal_inference(settings, username, goal, use_case, strengths)
    inference_snapshot = inference.model_dump(mode="json")
    context = ArcadiaAgentContext.model_construct(
        thread=thread,
        store=MemoryStore(),
        request_context={
            "metadata": metadata,
            "profile": profile_snapshot,
            "goal_inference": inference_snapshot,
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
    foundation_insights = json.dumps(
        {
            "summary": inference.summary,
            "target_outcomes": inference.target_outcomes,
            "tracks": [track.model_dump(mode="json") for track in inference.tracks],
            "missing_templates": inference.missing_templates,
        },
        ensure_ascii=False,
        indent=2,
    )

    message = (
        "Design an onboarding curriculum and initial assessment for the learner described below. "
        "Sequence the curriculum into 3-5 modules, tie each to the ELO categories you define, "
        "and create assessment tasks aligned to those categories. "
        "Focus on AuDHD-friendly pacing (chunked steps, explicit success criteria, minimal sensory load). "
        "Return the structured JSON payload described after the learner brief.\n\n"
        f"{learner_brief}\n"
        "Goal parser insights:\n"
        f"{foundation_insights}\n\n"
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

    category_definitions: List[EloCategoryDefinition] = []
    seen_keys: set[str] = set()
    for entry in plan_payload.categories:
        definition = _normalise_category_definition(entry)
        if definition.key in seen_keys:
            continue
        seen_keys.add(definition.key)
        category_definitions.append(definition)

    curriculum_payload: OnboardingCurriculumPayload = plan_payload.curriculum
    modules = [_normalise_module(module) for module in curriculum_payload.modules]
    curriculum = CurriculumPlan(
        generated_at=datetime.now(timezone.utc),
        overview=curriculum_payload.overview.strip(),
        success_criteria=[criterion.strip() for criterion in curriculum_payload.success_criteria if criterion.strip()],
        modules=modules,
    )

    augmented_categories, augmented_curriculum = ensure_foundational_curriculum(
        goal=goal or "",
        plan=curriculum,
        categories=category_definitions,
        assessment_result=None,
        goal_inference=inference,
    )

    plan = EloCategoryPlan(
        source_goal=goal.strip() if isinstance(goal, str) and goal.strip() else None,
        strategy_notes=plan_payload.profile_summary.strip()
        if isinstance(plan_payload.profile_summary, str) and plan_payload.profile_summary.strip()
        else None,
        categories=augmented_categories,
    )
    if inference.summary:
        notes: List[str] = []
        if plan.strategy_notes:
            notes.append(plan.strategy_notes)
        notes.append(f"Goal parser focus: {inference.summary}")
        plan.strategy_notes = "\n\n".join(notes)
    profile_store.set_elo_category_plan(username, plan)
    curriculum = augmented_curriculum
    modules = list(curriculum.modules)

    base_tasks = [_normalise_task(task) for task in plan_payload.assessment]
    all_categories = [(category.key, category.label) for category in augmented_categories]
    ensured_tasks = _ensure_task_coverage(all_categories, modules, base_tasks)
    final_tasks, assessment_sections = _build_assessment_sections(ensured_tasks, augmented_categories, inference)
    assessment = OnboardingAssessment(
        generated_at=datetime.now(timezone.utc),
        status="pending",
        tasks=final_tasks,
        sections=assessment_sections,
    )

    profile_store.set_curriculum_and_assessment(username, curriculum, assessment)
    try:
        generate_schedule_for_user(username)
        emit_event(
            "schedule_generation_post_onboarding",
            username=username,
            status="success",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to generate schedule during onboarding for %s", username)
        emit_event(
            "schedule_generation_post_onboarding",
            username=username,
            status="error",
            error=str(exc),
            exception_type=exc.__class__.__name__,
        )
    return curriculum, assessment
