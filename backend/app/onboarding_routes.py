"""Phase 3 onboarding endpoints for curriculum planning and assessment delivery."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Set

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .agent_models import (
    AssessmentSubmissionPayload,
    LearnerProfilePayload,
    OnboardingAssessmentPayload,
    OnboardingCurriculumPayload,
)
from .config import Settings, get_settings
from .learner_profile import profile_store
from .assessment_submission import AssessmentTaskResponse, submission_payload, submission_store
from .onboarding_assessment import generate_onboarding_bundle
from .tools import _profile_payload  # type: ignore[attr-defined]


router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class OnboardingPlanRequest(BaseModel):
    username: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    use_case: str = ""
    strengths: str = ""
    force: bool = False


class OnboardingStatusResponse(BaseModel):
    username: str
    plan_ready: bool
    assessment_ready: bool
    generated_at: datetime | None = None


class AssessmentStatusUpdate(BaseModel):
    status: Literal["pending", "in_progress", "completed"]


class AssessmentTaskResponseInput(BaseModel):
    task_id: str = Field(..., min_length=1)
    response: str = Field(..., min_length=1)


class AssessmentSubmissionRequest(BaseModel):
    responses: List[AssessmentTaskResponseInput] = Field(..., min_length=1)
    metadata: Dict[str, str] = Field(default_factory=dict)


@router.post("/plan", response_model=LearnerProfilePayload, status_code=status.HTTP_200_OK)
async def create_or_refresh_onboarding_plan(
    payload: OnboardingPlanRequest,
    settings: Settings = Depends(get_settings),
) -> LearnerProfilePayload:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Username cannot be empty.")

    existing = profile_store.get(username)
    if (
        not payload.force
        and existing
        and existing.curriculum_plan
        and existing.onboarding_assessment
        and existing.elo_category_plan
    ):
        return _profile_payload(existing)

    await generate_onboarding_bundle(
        settings=settings,
        username=username,
        goal=payload.goal,
        use_case=payload.use_case,
        strengths=payload.strengths,
    )
    refreshed = profile_store.get(username)
    if refreshed is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist onboarding plan.",
        )
    return _profile_payload(refreshed)


@router.get("/{username}", response_model=LearnerProfilePayload, status_code=status.HTTP_200_OK)
def fetch_onboarding_plan(username: str) -> LearnerProfilePayload:
    profile = profile_store.get(username)
    if profile is None or profile.curriculum_plan is None or profile.onboarding_assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Onboarding plan for '{username}' is not ready.",
        )
    return _profile_payload(profile)


@router.get("/{username}/status", response_model=OnboardingStatusResponse, status_code=status.HTTP_200_OK)
def onboarding_status(username: str) -> OnboardingStatusResponse:
    profile = profile_store.get(username)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No learner profile found for '{username}'.",
        )
    plan_ready = profile.curriculum_plan is not None and profile.elo_category_plan is not None
    assessment_ready = plan_ready and profile.onboarding_assessment is not None
    generated_at: datetime | None = None
    if plan_ready and profile.curriculum_plan:
        generated_at = profile.curriculum_plan.generated_at
    return OnboardingStatusResponse(
        username=profile.username,
        plan_ready=plan_ready,
        assessment_ready=assessment_ready,
        generated_at=generated_at,
    )


@router.get(
    "/{username}/curriculum",
    response_model=OnboardingCurriculumPayload,
    status_code=status.HTTP_200_OK,
)
def get_curriculum(username: str) -> OnboardingCurriculumPayload:
    profile = profile_store.get(username)
    if profile is None or profile.curriculum_plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Curriculum for '{username}' is not ready.",
        )
    payload = _profile_payload(profile)
    if payload.curriculum_plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Curriculum for '{username}' is not ready.",
        )
    return payload.curriculum_plan


@router.get(
    "/{username}/assessment",
    response_model=OnboardingAssessmentPayload,
    status_code=status.HTTP_200_OK,
)
def get_assessment(username: str) -> OnboardingAssessmentPayload:
    profile = profile_store.get(username)
    if profile is None or profile.onboarding_assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment for '{username}' is not ready.",
        )
    payload = _profile_payload(profile)
    if payload.onboarding_assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment for '{username}' is not ready.",
        )
    return payload.onboarding_assessment


@router.post(
    "/{username}/assessment/status",
    response_model=OnboardingAssessmentPayload,
    status_code=status.HTTP_200_OK,
)
def update_assessment_status(username: str, payload: AssessmentStatusUpdate) -> OnboardingAssessmentPayload:
    try:
        profile = profile_store.update_assessment_status(username, payload.status)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if profile.onboarding_assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment for '{username}' has not been generated.",
        )
    transformed = _profile_payload(profile)
    if transformed.onboarding_assessment is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to transform assessment payload.",
        )
    return transformed.onboarding_assessment


@router.post(
    "/{username}/assessment/submissions",
    response_model=AssessmentSubmissionPayload,
    status_code=status.HTTP_201_CREATED,
)
def create_assessment_submission(username: str, payload: AssessmentSubmissionRequest) -> AssessmentSubmissionPayload:
    profile = profile_store.get(username)
    if profile is None or profile.onboarding_assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment for '{username}' is not ready.",
        )

    tasks = {task.task_id: task for task in profile.onboarding_assessment.tasks}
    if not tasks:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No assessment tasks registered for '{username}'.",
        )

    seen: Set[str] = set()
    responses: List[AssessmentTaskResponse] = []
    for entry in payload.responses:
        task_id = entry.task_id.strip()
        if not task_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Task ID cannot be empty.",
            )
        if task_id not in tasks:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Task '{task_id}' does not belong to '{username}'.",
            )
        if task_id in seen:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Task '{task_id}' is duplicated in the submission payload.",
            )
        text = entry.response.strip()
        if not text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Task '{task_id}' response cannot be empty.",
            )
        task = tasks[task_id]
        responses.append(
            AssessmentTaskResponse(
                task_id=task.task_id,
                response=text,
                category_key=task.category_key,
                task_type=task.task_type,  # type: ignore[arg-type]
            )
        )
        seen.add(task_id)

    cleaned_metadata = {
        key: value.strip()
        for key, value in payload.metadata.items()
        if isinstance(key, str) and isinstance(value, str) and value.strip()
    }
    submission = submission_store.record(username, responses, metadata=cleaned_metadata)
    return submission_payload(submission)


@router.get(
    "/{username}/assessment/submissions",
    response_model=List[AssessmentSubmissionPayload],
    status_code=status.HTTP_200_OK,
)
def list_assessment_submissions(username: str) -> List[AssessmentSubmissionPayload]:
    entries = submission_store.list_user(username)
    return [submission_payload(entry) for entry in entries]
