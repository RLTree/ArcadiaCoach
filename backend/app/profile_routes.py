"""Profile-centric REST endpoints surfaced to the macOS client."""

from __future__ import annotations

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
    SequencedWorkItemPayload,
    SkillRatingPayload,
)
from .assessment_submission import submission_payload, submission_store
from .curriculum_sequencer import generate_schedule_for_user
from .learner_profile import CurriculumSchedule, LearnerProfile, profile_store


router = APIRouter(prefix="/api/profile", tags=["profile"])


def _schedule_payload(schedule: CurriculumSchedule | None) -> CurriculumSchedulePayload | None:
    if schedule is None:
        return None
    return CurriculumSchedulePayload(
        generated_at=schedule.generated_at,
        time_horizon_days=schedule.time_horizon_days,
        cadence_notes=schedule.cadence_notes,
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
            )
            for item in schedule.items
        ],
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
    if refresh or profile.curriculum_schedule is None:
        try:
            profile = generate_schedule_for_user(username)
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
    schedule_payload = _schedule_payload(profile.curriculum_schedule)
    if schedule_payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    return schedule_payload


__all__ = ["router"]
