"""Profile-centric REST endpoints surfaced to the macOS client."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status

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
    LearnerProfilePayload,
    OnboardingAssessmentPayload,
    OnboardingAssessmentTaskPayload,
    OnboardingCurriculumPayload,
    SkillRatingPayload,
)
from .assessment_submission import submission_payload, submission_store
from .curriculum_sequencer import generate_schedule_for_user
from .learner_profile import CurriculumSchedule, LearnerProfile, ScheduleWarning, profile_store
from .telemetry import emit_event
from .tools import _schedule_payload


router = APIRouter(prefix="/api/profile", tags=["profile"])
logger = logging.getLogger(__name__)


def _serialize_profile(profile: LearnerProfile) -> LearnerProfilePayload:
    plan = profile.elo_category_plan
    plan_payload: EloCategoryPlanPayload | None = None
    if plan:
        plan_payload = EloCategoryPlanPayload(
            generated_at=plan.generated_at,
            source_goal=plan.source_goal,
            strategy_notes=plan.strategy_notes,
            categories=[
                EloCategoryDefinitionPayload(
                    key=category.key,
                    label=category.label,
                    description=category.description,
                    focus_areas=category.focus_areas,
                    weight=category.weight,
                    rubric=[
                        EloRubricBandPayload(level=band.level, descriptor=band.descriptor)
                        for band in category.rubric
                    ],
                    starting_rating=category.starting_rating,
                )
                for category in plan.categories
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
    schedule_payload = _schedule_payload(profile.curriculum_schedule)
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
    submissions = submission_store.list_user(profile.username)
    submission_payloads = [submission_payload(entry) for entry in submissions[:12]]

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
        curriculum_schedule=schedule_payload,
        onboarding_assessment=assessment_payload,
        onboarding_assessment_result=assessment_result_payload,
        assessment_submissions=submission_payloads,
    )


@router.get("/{username}", response_model=LearnerProfilePayload, status_code=status.HTTP_200_OK)
def get_profile(username: str) -> LearnerProfilePayload:
    profile = profile_store.get(username)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learner profile for '{username}' was not found.",
        )
    return _serialize_profile(profile)


@router.get(
    "/{username}/elo-plan",
    response_model=EloCategoryPlanPayload,
    status_code=status.HTTP_200_OK,
)
def get_elo_category_plan(username: str) -> EloCategoryPlanPayload:
    profile = profile_store.get(username)
    if profile is None or profile.elo_category_plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ELO categories for '{username}' are not set.",
        )
    payload = _serialize_profile(profile)
    if payload.elo_category_plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ELO categories for '{username}' are not set.",
        )
    return payload.elo_category_plan


@router.get(
    "/{username}/schedule",
    response_model=CurriculumSchedulePayload,
    status_code=status.HTTP_200_OK,
)
def get_curriculum_schedule(
    username: str,
    refresh: bool = Query(
        default=False,
        description="Set to true to regenerate the schedule using the latest learner signals.",
    ),
) -> CurriculumSchedulePayload:
    profile = profile_store.get(username)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learner profile for '{username}' was not found.",
        )
    fallback_schedule: CurriculumSchedule | None = None
    previous_schedule = profile.curriculum_schedule.model_copy(deep=True) if profile.curriculum_schedule else None
    refresh_error: Exception | None = None
    if refresh or profile.curriculum_schedule is None:
        try:
            profile = generate_schedule_for_user(username)
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            refresh_error = exc
            if previous_schedule is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc
        except Exception as exc:  # noqa: BLE001
            refresh_error = exc
            if previous_schedule is None:
                logger.exception("Unexpected failure regenerating schedule for %s", username)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Unable to regenerate the curriculum schedule. Try again shortly.",
                ) from exc
        if refresh_error is not None and previous_schedule is not None:
            logger.warning(
                "Falling back to previous schedule for %s after refresh failure: %s",
                username,
                refresh_error,
            )
            fallback_schedule = _schedule_with_warning(previous_schedule, refresh_error)
            profile = profile_store.set_curriculum_schedule(username, fallback_schedule)
            emit_event(
                "schedule_refresh_fallback",
                username=username,
                status="fallback",
                had_prior_schedule=True,
                error=str(refresh_error),
                exception_type=refresh_error.__class__.__name__,
                item_count=len(fallback_schedule.items),
                warnings=len(fallback_schedule.warnings),
            )
        elif refresh_error is None:
            emit_event(
                "schedule_refresh",
                username=username,
                status="success",
                regenerated=True,
                item_count=len(profile.curriculum_schedule.items) if profile.curriculum_schedule else 0,
                is_stale=bool(profile.curriculum_schedule.is_stale) if profile.curriculum_schedule else False,
            )
    schedule_payload = _schedule_payload(profile.curriculum_schedule)
    if schedule_payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    if fallback_schedule is not None:
        schedule_payload.is_stale = True
    elif not refresh and profile.curriculum_schedule is not None:
        emit_event(
            "schedule_refresh",
            username=username,
            status="skipped",
            regenerated=False,
            item_count=len(profile.curriculum_schedule.items),
            is_stale=bool(profile.curriculum_schedule.is_stale),
        )
    return schedule_payload


def _schedule_with_warning(schedule: CurriculumSchedule, error: Exception) -> CurriculumSchedule:
    warning = ScheduleWarning(
        code="refresh_failed",
        message=f"Using the previous schedule (refresh failed at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}).",
        detail=str(error),
    )
    updated = schedule.model_copy(deep=True)
    updated.is_stale = True
    updated.warnings = (updated.warnings + [warning])[-5:]
    return updated


__all__ = ["router"]
