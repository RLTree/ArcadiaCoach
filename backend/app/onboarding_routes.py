"""Phase 3 onboarding endpoints for curriculum planning and assessment delivery."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .agent_models import LearnerProfilePayload, OnboardingAssessmentPayload, OnboardingCurriculumPayload
from .config import Settings, get_settings
from .learner_profile import profile_store
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
