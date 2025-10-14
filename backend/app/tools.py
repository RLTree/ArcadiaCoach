"""Utility tools exposed to the Arcadia Coach agent."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from agents import function_tool

from .learner_profile import (
    CurriculumSchedule,
    EloCategoryDefinition,
    EloCategoryPlan,
    EloRubricBand,
    LearnerProfile,
    profile_store,
)
from .vector_memory import learner_memory
from .agent_models import (
    AssessmentCategoryOutcomePayload,
    AssessmentGradingPayload,
    AssessmentRubricEvaluationPayload,
    AssessmentTaskGradePayload,
    CurriculumModulePayload,
    CurriculumSchedulePayload,
    EloCategoryDefinitionPayload,
    EloCategoryPlanPayload,
    EloRubricBandPayload,
    LearnerEloCategoryPlanResponse,
    LearnerMemoryWriteResponse,
    LearnerProfileGetResponse,
    LearnerProfilePayload,
    LearnerProfileUpdateResponse,
    OnboardingAssessmentPayload,
    OnboardingAssessmentTaskPayload,
    OnboardingCurriculumPayload,
    ScheduleWarningPayload,
    SequencedWorkItemPayload,
    SkillRatingPayload,
)


def _progress_payload(idx: int, total: int) -> Dict[str, Any]:
    display = min(idx + 1, total) if total > 0 else 0
    has_next = display < total
    return {
        "progress": {
            "idx": idx,
            "display": display,
            "total": total,
            "has_next": has_next,
        }
    }


@function_tool(strict_mode=False)
def progress_start(total: int) -> Dict[str, Any]:
    """Initialise a multi-step progress tracker."""
    if total <= 0:
        total = 1
    return _progress_payload(idx=0, total=total)


@function_tool(strict_mode=False)
def progress_advance(idx: int, total: int) -> Dict[str, Any]:
    """Advance the progress tracker and surface the updated status."""
    if total <= 0:
        total = 1
    next_idx = min(idx + 1, total - 1)
    return _progress_payload(idx=next_idx, total=total)

def _schedule_payload(schedule: Optional[CurriculumSchedule]) -> Optional[CurriculumSchedulePayload]:
    if schedule is None:
        return None
    warnings = [
        ScheduleWarningPayload(
            code=getattr(warning, "code", "refresh_failed"),
            message=getattr(warning, "message", ""),
            detail=getattr(warning, "detail", None),
            generated_at=getattr(warning, "generated_at", schedule.generated_at),
        )
        for warning in getattr(schedule, "warnings", [])
    ]
    return CurriculumSchedulePayload(
        generated_at=schedule.generated_at,
        time_horizon_days=schedule.time_horizon_days,
        cadence_notes=schedule.cadence_notes,
        is_stale=getattr(schedule, "is_stale", False),
        warnings=warnings,
        items=[
            SequencedWorkItemPayload(
                item_id=item.item_id,
                kind=item.kind,
                category_key=item.category_key,
                title=item.title,
                summary=item.summary,
                objectives=list(item.objectives),
                prerequisites=list(item.prerequisites),
                recommended_minutes=item.recommended_minutes,
                recommended_day_offset=item.recommended_day_offset,
                effort_level=item.effort_level,
                focus_reason=item.focus_reason,
                expected_outcome=item.expected_outcome,
                user_adjusted=getattr(item, "user_adjusted", False),
            )
            for item in schedule.items
        ],
    )


def _profile_payload(profile: LearnerProfile) -> LearnerProfilePayload:
    plan = profile.elo_category_plan
    plan_payload: EloCategoryPlanPayload | None = None
    if plan:
        plan_payload = EloCategoryPlanPayload(
            generated_at=plan.generated_at,
            source_goal=plan.source_goal,
            strategy_notes=plan.strategy_notes,
            categories=[
                EloCategoryDefinitionPayload(
                    key=definition.key,
                    label=definition.label,
                    description=definition.description,
                    focus_areas=definition.focus_areas,
                    weight=definition.weight,
                    rubric=[
                        EloRubricBandPayload(level=band.level, descriptor=band.descriptor)
                        for band in definition.rubric
                    ],
                    starting_rating=definition.starting_rating,
                )
                for definition in plan.categories
            ],
        )
    curriculum_payload: OnboardingCurriculumPayload | None = None
    if profile.curriculum_plan:
        curriculum = profile.curriculum_plan
        curriculum_payload = OnboardingCurriculumPayload(
            generated_at=curriculum.generated_at,
            overview=curriculum.overview,
            success_criteria=list(curriculum.success_criteria),
            modules=[
                CurriculumModulePayload(
                    module_id=module.module_id,
                    category_key=module.category_key,
                    title=module.title,
                    summary=module.summary,
                    objectives=list(module.objectives),
                    activities=list(module.activities),
                    deliverables=list(module.deliverables),
                    estimated_minutes=module.estimated_minutes,
                )
                for module in curriculum.modules
            ],
        )
    assessment_payload: OnboardingAssessmentPayload | None = None
    if profile.onboarding_assessment:
        assessment = profile.onboarding_assessment
        assessment_payload = OnboardingAssessmentPayload(
            generated_at=assessment.generated_at,
            status=assessment.status,
            tasks=[
                OnboardingAssessmentTaskPayload(
                    task_id=task.task_id,
                    category_key=task.category_key,
                    title=task.title,
                    task_type=task.task_type,
                    prompt=task.prompt,
                    guidance=task.guidance,
                    rubric=list(task.rubric),
                    expected_minutes=task.expected_minutes,
                    starter_code=task.starter_code,
                    answer_key=task.answer_key,
                )
                for task in assessment.tasks
            ],
        )
    assessment_result_payload: AssessmentGradingPayload | None = None
    if profile.onboarding_assessment_result:
        result = profile.onboarding_assessment_result
        assessment_result_payload = AssessmentGradingPayload(
            submission_id=result.submission_id,
            evaluated_at=result.evaluated_at,
            overall_feedback=result.overall_feedback,
            strengths=list(result.strengths),
            focus_areas=list(result.focus_areas),
            task_results=[
                AssessmentTaskGradePayload(
                    task_id=task.task_id,
                    category_key=task.category_key,
                    task_type=task.task_type,
                    score=task.score,
                    confidence=task.confidence,
                    feedback=task.feedback,
                    strengths=list(task.strengths),
                    improvements=list(task.improvements),
                    rubric=[
                        AssessmentRubricEvaluationPayload(
                            criterion=rubric.criterion,
                            met=rubric.met,
                            notes=rubric.notes,
                            score=rubric.score,
                        )
                        for rubric in task.rubric
                    ],
                )
                for task in result.task_results
            ],
            category_outcomes=[
                AssessmentCategoryOutcomePayload(
                    category_key=outcome.category_key,
                    average_score=outcome.average_score,
                    initial_rating=outcome.initial_rating,
                    starting_rating=outcome.starting_rating,
                    rating_delta=outcome.rating_delta,
                    rationale=outcome.rationale,
                )
                for outcome in result.category_outcomes
            ],
        )
    return LearnerProfilePayload(
        username=profile.username,
        goal=profile.goal,
        use_case=profile.use_case,
        strengths=profile.strengths,
        knowledge_tags=profile.knowledge_tags,
        recent_sessions=profile.recent_sessions,
        memory_records=profile.memory_records,
        skill_ratings=[
            SkillRatingPayload(category=category, rating=value)
            for category, value in profile.elo_snapshot.items()
        ],
        memory_index_id=profile.memory_index_id,
        last_updated=profile.last_updated,
        elo_category_plan=plan_payload,
        curriculum_plan=curriculum_payload,
        curriculum_schedule=_schedule_payload(getattr(profile, "curriculum_schedule", None)),
        onboarding_assessment=assessment_payload,
        onboarding_assessment_result=assessment_result_payload,
    )


@function_tool(strict_mode=False)
def elo_update(
    elo: Dict[str, float] | None,
    skill_weights: Dict[str, float] | None,
    score: float,
    problem_rating: int,
    K: int = 24,
) -> Dict[str, Any]:
    """Update learner skill ratings using a weighted Elo adjustment."""
    if elo is None:
        elo = {}
    if skill_weights is None:
        skill_weights = {}

    updated: Dict[str, float] = {}
    total_weight = sum(max(weight, 0.0) for weight in skill_weights.values()) or 1.0

    for skill, weight in skill_weights.items():
        weight = max(weight, 0.0) / total_weight
        rating = elo.get(skill, 1200.0)
        expected = 1.0 / (1.0 + 10 ** ((problem_rating - rating) / 400.0))
        delta = K * weight * (score - expected)
        updated[skill] = rating + delta

    # Persist untouched skills
    for skill, rating in elo.items():
        updated.setdefault(skill, rating)

    return {"updated_elo": updated}


@function_tool(strict_mode=False)
def learner_profile_get(username: str) -> LearnerProfileGetResponse:
    """Fetch the persisted learner profile for the given username."""
    profile = profile_store.get(username)
    if profile is None:
        return LearnerProfileGetResponse(found=False, profile=None)
    payload = _profile_payload(profile)
    return LearnerProfileGetResponse(found=True, profile=payload)


@function_tool(strict_mode=False)
def learner_profile_update(
    username: str,
    goal: str | None = None,
    use_case: str | None = None,
    strengths: str | None = None,
    knowledge_tags: List[str] | None = None,
) -> LearnerProfileUpdateResponse:
    """Update learner profile fields and return the refreshed profile snapshot."""
    metadata: Dict[str, Any] = {}
    if goal is not None:
        metadata["goal"] = goal
    if use_case is not None:
        metadata["use_case"] = use_case
    if strengths is not None:
        metadata["strengths"] = strengths
    if knowledge_tags is not None:
        metadata["knowledge_tags"] = knowledge_tags
    profile = profile_store.apply_metadata(username, metadata)
    payload = _profile_payload(profile)
    return LearnerProfileUpdateResponse(profile=payload)


@function_tool(strict_mode=False)
def learner_memory_write(
    username: str, note: str, tags: List[str] | None = None
) -> LearnerMemoryWriteResponse:
    """Record a personalised memory note for the learner."""
    result = learner_memory.record_note(username=username, note=note, tags=tags or [])
    return LearnerMemoryWriteResponse(
        note_id=result["note_id"],
        vector_store_id=result["vector_store_id"],
        status=result["status"],
    )


def _normalise_category_key(key: str, label: str) -> str:
    candidate = key.strip() if isinstance(key, str) else ""
    if not candidate and isinstance(label, str):
        candidate = label
    slug_chars: List[str] = []
    for char in candidate:
        if char.isalnum():
            slug_chars.append(char.lower())
        elif char in {" ", "-", "_", "/"}:
            slug_chars.append("-")
    slug = "".join(slug_chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "category-1"


@function_tool(strict_mode=False)
def learner_elo_category_plan_set(
    username: str,
    categories: List[EloCategoryDefinitionPayload],
    source_goal: str | None = None,
    strategy_notes: str | None = None,
) -> LearnerEloCategoryPlanResponse:
    """Persist the learner's skill category plan and return the updated snapshot."""
    normalized_categories: List[EloCategoryDefinition] = []
    seen_keys: Set[str] = set()

    for entry in categories:
        key = _normalise_category_key(entry.key, entry.label)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        label = entry.label.strip() if isinstance(entry.label, str) else key.title()
        description = entry.description.strip() if isinstance(entry.description, str) else ""
        focus = [
            focus_area.strip()
            for focus_area in entry.focus_areas
            if isinstance(focus_area, str) and focus_area.strip()
        ]
        rubric = [
            EloRubricBand(level=band.level.strip(), descriptor=band.descriptor.strip())
            for band in entry.rubric
            if isinstance(band.level, str) and band.level.strip()
        ]
        normalized_categories.append(
            EloCategoryDefinition(
                key=key,
                label=label,
                description=description,
                focus_areas=focus,
                weight=max(entry.weight, 0.0),
                rubric=rubric,
                starting_rating=max(int(entry.starting_rating), 0),
            )
        )

    plan = EloCategoryPlan(
        source_goal=source_goal.strip() if isinstance(source_goal, str) and source_goal else None,
        strategy_notes=strategy_notes.strip() if isinstance(strategy_notes, str) and strategy_notes else None,
        categories=normalized_categories,
    )
    profile = profile_store.set_elo_category_plan(username, plan)
    payload = _profile_payload(profile)
    if payload.elo_category_plan is None:
        raise ValueError("Failed to persist learner ELO category plan.")
    return LearnerEloCategoryPlanResponse(username=profile.username, plan=payload.elo_category_plan)


AGENT_SUPPORT_TOOLS = [
    progress_start,
    progress_advance,
    elo_update,
    learner_profile_get,
    learner_profile_update,
    learner_memory_write,
    learner_elo_category_plan_set,
]

__all__ = [
    "AGENT_SUPPORT_TOOLS",
    "elo_update",
    "learner_memory_write",
    "learner_elo_category_plan_set",
    "learner_profile_get",
    "learner_profile_update",
    "progress_advance",
    "progress_start",
]
