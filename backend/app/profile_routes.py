"""Profile-centric REST endpoints surfaced to the macOS client."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from time import perf_counter

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from .agent_models import (
    AssessmentCategoryOutcomePayload,
    AssessmentGradingPayload,
    AssessmentRubricEvaluationPayload,
    AssessmentTaskGradePayload,
    AssessmentSectionPayload,
    CurriculumModulePayload,
    CurriculumSchedulePayload,
    EloCategoryDefinitionPayload,
    EloCategoryPlanPayload,
    EloRubricBandPayload,
    FoundationModuleReferencePayload,
    FoundationTrackPayload,
    GoalParserInferencePayload,
    LearnerProfilePayload,
    OnboardingAssessmentPayload,
    OnboardingAssessmentTaskPayload,
    OnboardingCurriculumPayload,
    SkillRatingPayload,
)
from .assessment_submission import submission_payload, submission_store
from .curriculum_sequencer import generate_schedule_for_user
from .learner_profile import (
    AssessmentSection,
    AssessmentTask,
    CurriculumSchedule,
    LearnerProfile,
    OnboardingAssessment,
    ScheduleWarning,
    FoundationModuleReference,
    FoundationTrack,
    slice_schedule,
    profile_store,
)
from .telemetry import emit_event
from .tools import _schedule_payload
from .onboarding_assessment import _ensure_task_coverage, _build_assessment_sections


router = APIRouter(prefix="/api/profile", tags=["profile"])
logger = logging.getLogger(__name__)

MAX_DEFER_DAYS = 21


class ScheduleAdjustmentRequest(BaseModel):
    item_id: str = Field(..., min_length=1)
    days: int = Field(default=1, ge=1, le=MAX_DEFER_DAYS)
    target_day_offset: Optional[int] = Field(default=None, ge=0, le=42)
    reason: Optional[str] = Field(default=None, max_length=160)


def _ensure_assessment_task_coverage(profile: LearnerProfile) -> OnboardingAssessment | None:
    assessment = profile.onboarding_assessment
    if assessment is None:
        return None
    plan = profile.elo_category_plan
    if plan is None or not plan.categories:
        return assessment
    modules = list(profile.curriculum_plan.modules) if profile.curriculum_plan else []
    categories = [(category.key, category.label) for category in plan.categories]
    ensured_tasks = _ensure_task_coverage(categories, modules, list(assessment.tasks))
    tasks, sections = _build_assessment_sections(ensured_tasks, plan.categories, profile.goal_inference)
    if tasks != assessment.tasks or sections != assessment.sections:
        assessment = assessment.model_copy(update={"tasks": tasks, "sections": sections})
        profile.onboarding_assessment = assessment
    return assessment


def _module_reference_payload(reference: FoundationModuleReference) -> FoundationModuleReferencePayload:
    return FoundationModuleReferencePayload(
        module_id=reference.module_id,
        category_key=reference.category_key,
        priority=reference.priority,
        suggested_weeks=reference.suggested_weeks,
        notes=reference.notes,
    )


def _track_payload(track: FoundationTrack) -> FoundationTrackPayload:
    return FoundationTrackPayload(
        track_id=track.track_id,
        label=track.label,
        priority=track.priority,
        confidence=track.confidence,
        weight=track.weight,
        technologies=list(track.technologies),
        focus_areas=list(track.focus_areas),
        prerequisites=list(track.prerequisites),
        recommended_modules=[_module_reference_payload(module) for module in track.recommended_modules],
        suggested_weeks=track.suggested_weeks,
        notes=track.notes,
    )


def _assessment_task_payload(task: AssessmentTask) -> OnboardingAssessmentTaskPayload:
    return OnboardingAssessmentTaskPayload(
        task_id=task.task_id,
        category_key=task.category_key,
        section_id=getattr(task, "section_id", None),
        title=task.title,
        task_type=task.task_type,
        prompt=task.prompt,
        guidance=task.guidance,
        rubric=list(task.rubric),
        expected_minutes=task.expected_minutes,
        starter_code=task.starter_code,
        answer_key=task.answer_key,
    )


def _assessment_section_payload(section: AssessmentSection) -> AssessmentSectionPayload:
    return AssessmentSectionPayload(
        section_id=section.section_id,
        title=section.title,
        description=section.description,
        intent=section.intent,
        expected_minutes=section.expected_minutes,
        tasks=[_assessment_task_payload(task) for task in section.tasks],
    )


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
        assessment = _ensure_assessment_task_coverage(profile)
        if assessment is None:
            assessment = profile.onboarding_assessment
        task_payloads = [_assessment_task_payload(task) for task in assessment.tasks]
        section_payloads = [_assessment_section_payload(section) for section in assessment.sections]
        assessment_payload = OnboardingAssessmentPayload(
            generated_at=assessment.generated_at,
            status=assessment.status,
            tasks=task_payloads,
            sections=section_payloads,
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
    track_payloads = [_track_payload(track) for track in getattr(profile, "foundation_tracks", []) or []]
    inference_payload: GoalParserInferencePayload | None = None
    if profile.goal_inference:
        inference_payload = GoalParserInferencePayload(
            generated_at=profile.goal_inference.generated_at,
            summary=profile.goal_inference.summary,
            target_outcomes=list(profile.goal_inference.target_outcomes),
            tracks=[_track_payload(track) for track in profile.goal_inference.tracks],
            missing_templates=list(profile.goal_inference.missing_templates),
        )
        if not track_payloads:
            track_payloads = [_track_payload(track) for track in profile.goal_inference.tracks]
    submissions = submission_store.list_user(profile.username)
    submission_payloads = [submission_payload(entry) for entry in submissions[:12]]

    return LearnerProfilePayload(
        username=profile.username,
        goal=profile.goal,
        use_case=profile.use_case,
        strengths=profile.strengths,
        timezone=profile.timezone,
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
        goal_inference=inference_payload,
        foundation_tracks=track_payloads,
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
    start_day: Optional[int] = Query(
        default=None,
        ge=0,
        description="Optional day offset to start the returned slice (0 = today).",
    ),
    day_span: Optional[int] = Query(
        default=None,
        ge=1,
        le=42,
        description="Number of days to include in the slice. Defaults to the remaining horizon.",
    ),
    page_token: Optional[int] = Query(
        default=None,
        ge=0,
        description="Resume token from a previous schedule slice (next_start_day).",
    ),
) -> CurriculumSchedulePayload:
    started_at = perf_counter()
    requested_start = page_token if page_token is not None else start_day
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
                warnings=len(fallback_schedule.warnings),
                **_schedule_metrics(fallback_schedule),
            )
        elif refresh_error is None:
            emit_event(
                "schedule_refresh",
                username=username,
                status="success",
                regenerated=True,
                **_schedule_metrics(profile.curriculum_schedule),
            )
    profile = profile_store.get(username)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learner profile for '{username}' was not found.",
        )
    schedule = profile.curriculum_schedule
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    sliced_schedule = slice_schedule(schedule, requested_start, day_span)
    schedule_payload = _schedule_payload(sliced_schedule)
    if schedule_payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    duration_ms = round((perf_counter() - started_at) * 1000.0, 2)

    if fallback_schedule is not None:
        schedule_payload.is_stale = True
    elif not refresh and profile.curriculum_schedule is not None:
        emit_event(
            "schedule_refresh",
            username=username,
            status="skipped",
            regenerated=False,
            **_schedule_metrics(profile.curriculum_schedule),
        )

    if requested_start is not None or day_span is not None or page_token is not None:
        slice_meta = schedule_payload.slice
        emit_event(
            "schedule_slice",
            username=username,
            status="fallback" if fallback_schedule is not None else "success",
            start_day=requested_start if requested_start is not None else 0,
            day_span=day_span,
            page_token=page_token,
            item_count=len(schedule_payload.items),
            total_items=slice_meta.total_items if slice_meta is not None else len(schedule.items),
            total_days=slice_meta.total_days if slice_meta is not None else schedule_payload.time_horizon_days,
            has_more=slice_meta.has_more if slice_meta is not None else False,
            next_start_day=slice_meta.next_start_day if slice_meta is not None else None,
            duration_ms=duration_ms,
        )
    return schedule_payload


@router.post(
    "/{username}/schedule/adjust",
    response_model=CurriculumSchedulePayload,
    status_code=status.HTTP_200_OK,
)
def adjust_curriculum_schedule(username: str, payload: ScheduleAdjustmentRequest) -> CurriculumSchedulePayload:
    profile = profile_store.get(username)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learner profile for '{username}' was not found.",
        )
    schedule = profile.curriculum_schedule
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    item_id = payload.item_id.strip()
    if not item_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Schedule item id cannot be empty.",
        )
    matching = next((item for item in schedule.items if item.item_id == item_id), None)
    if matching is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule item '{item_id}' was not found.",
        )
    current_offset = matching.recommended_day_offset
    if payload.target_day_offset is not None:
        target_offset = max(int(payload.target_day_offset), 0)
        target_offset = min(target_offset, current_offset + MAX_DEFER_DAYS)
    else:
        target_offset = current_offset + int(payload.days)
    if target_offset <= current_offset:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Reschedule offset must be later than the current day.",
        )
    reason = (payload.reason or "").strip() or "defer"
    try:
        profile_store.apply_schedule_adjustment(username, item_id, target_offset)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    emit_event(
        "schedule_adjustment",
        username=username,
        item_id=item_id,
        previous_offset=current_offset,
        requested_offset=target_offset,
        delta_days=target_offset - current_offset,
        reason=reason,
    )
    try:
        refreshed = generate_schedule_for_user(username)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to regenerate schedule after adjustment for %s", username)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to regenerate the curriculum schedule after the adjustment.",
        ) from exc
    schedule_payload = _schedule_payload(refreshed.curriculum_schedule)
    if schedule_payload is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Schedule regeneration did not return a schedule.",
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
def _schedule_metrics(schedule: CurriculumSchedule | None) -> Dict[str, Any]:
    if schedule is None:
        return {}
    total_minutes = sum(item.recommended_minutes for item in schedule.items)
    unique_days = len({item.recommended_day_offset for item in schedule.items})
    slice_meta = getattr(schedule, "slice", None)
    metrics: Dict[str, Any] = {
        "item_count": len(schedule.items),
        "is_stale": bool(schedule.is_stale),
        "horizon_days": schedule.time_horizon_days,
        "sessions_per_week": schedule.sessions_per_week,
        "projected_weekly_minutes": schedule.projected_weekly_minutes,
        "total_minutes": total_minutes,
        "average_session_minutes": int(round(total_minutes / max(unique_days, 1))) if schedule.items else 0,
        "long_range_item_count": schedule.long_range_item_count,
        "long_range_category_count": len(getattr(schedule, "long_range_category_keys", [])),
        "long_range_weeks": schedule.extended_weeks,
        "user_adjusted_count": sum(1 for item in schedule.items if item.user_adjusted),
    }
    if slice_meta is not None:
        metrics.update(
            {
                "slice_start_day": slice_meta.start_day,
                "slice_day_span": slice_meta.day_span,
                "slice_has_more": slice_meta.has_more,
                "slice_total_items": slice_meta.total_items,
            }
        )
        if slice_meta.next_start_day is not None:
            metrics["slice_next_start_day"] = slice_meta.next_start_day
    return metrics
