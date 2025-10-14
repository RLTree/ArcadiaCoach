"""Onboarding endpoints for curriculum planning, assessment delivery, and grading (Phases 3 & 5)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Literal, Optional, Set

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .agent_models import (
    AssessmentGradingPayload,
    AssessmentSubmissionAttachmentPayload,
    AssessmentSubmissionPayload,
    LearnerProfilePayload,
    OnboardingAssessmentPayload,
    OnboardingCurriculumPayload,
)
from .curriculum_sequencer import generate_schedule_for_user
from .config import Settings, get_settings
from .learner_profile import profile_store
from .assessment_grading import grade_submission
from .assessment_submission import (
    AssessmentSubmissionAttachment,
    AssessmentTaskResponse,
    submission_payload,
    submission_store,
)
from .assessment_attachments import attachment_store, PendingAssessmentAttachment
from .onboarding_assessment import generate_onboarding_bundle
from .tools import _profile_payload  # type: ignore[attr-defined]
from .telemetry import emit_event


router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])
logger = logging.getLogger(__name__)


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


class AssessmentAttachmentLinkRequest(BaseModel):
    name: Optional[str] = None
    url: str = Field(..., min_length=1)
    description: Optional[str] = None


def _attachment_payload(username: str, entry: PendingAssessmentAttachment) -> AssessmentSubmissionAttachmentPayload:
    structured = AssessmentSubmissionAttachment.from_pending(entry)
    return structured.as_payload(username)


@router.get(
    "/{username}/assessment/attachments",
    response_model=List[AssessmentSubmissionAttachmentPayload],
    status_code=status.HTTP_200_OK,
)
def list_pending_assessment_attachments(username: str) -> List[AssessmentSubmissionAttachmentPayload]:
    entries = attachment_store.list_pending(username)
    return [_attachment_payload(username, entry) for entry in entries]


@router.post(
    "/{username}/assessment/attachments/files",
    response_model=AssessmentSubmissionAttachmentPayload,
    status_code=status.HTTP_201_CREATED,
)
async def upload_assessment_attachment_file(
    username: str,
    file: UploadFile = File(...),
    description: Optional[str] = Form(default=None),
) -> AssessmentSubmissionAttachmentPayload:
    data = await file.read()
    entry = attachment_store.add_file(
        username=username,
        filename=file.filename or "attachment",
        content=data,
        content_type=file.content_type,
        description=description,
    )
    return _attachment_payload(username, entry)


@router.post(
    "/{username}/assessment/attachments/links",
    response_model=AssessmentSubmissionAttachmentPayload,
    status_code=status.HTTP_201_CREATED,
)
def create_assessment_attachment_link(
    username: str,
    payload: AssessmentAttachmentLinkRequest,
) -> AssessmentSubmissionAttachmentPayload:
    entry = attachment_store.add_link(
        username=username,
        name=payload.name or payload.url,
        url=payload.url,
        description=payload.description,
    )
    return _attachment_payload(username, entry)


@router.delete(
    "/{username}/assessment/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_pending_assessment_attachment(username: str, attachment_id: str) -> Response:
    attachment_store.delete(username, attachment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{username}/assessment/attachments/{attachment_id}/download",
    status_code=status.HTTP_200_OK,
)
def download_assessment_attachment(username: str, attachment_id: str) -> FileResponse:
    trimmed = attachment_id.strip()
    if not trimmed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found.",
        )

    # Check pending attachments first.
    for entry in attachment_store.list_pending(username):
        if entry.attachment_id == trimmed and entry.kind == "file" and entry.stored_path:
            try:
                path = attachment_store.resolve_stored_path(entry.stored_path)
            except (FileNotFoundError, ValueError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Attachment file is unavailable.",
                ) from exc
            return FileResponse(
                path,
                media_type=entry.content_type or "application/octet-stream",
                filename=entry.name,
            )

    # Fallback to persisted submissions.
    submissions = submission_store.list_user(username)
    for submission in submissions:
        for attachment in submission.attachments:
            if attachment.attachment_id == trimmed and attachment.kind == "file" and attachment.stored_path:
                try:
                    path = attachment_store.resolve_stored_path(attachment.stored_path)
                except (FileNotFoundError, ValueError) as exc:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Attachment file is unavailable.",
                    ) from exc
                return FileResponse(
                    path,
                    media_type=attachment.content_type or "application/octet-stream",
                    filename=attachment.name,
                )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Attachment not found.",
    )


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
async def create_assessment_submission(
    username: str,
    payload: AssessmentSubmissionRequest,
    settings: Settings = Depends(get_settings),
) -> AssessmentSubmissionPayload:
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
    pending_attachments = attachment_store.consume(username)
    structured_attachments = [
        AssessmentSubmissionAttachment.from_pending(entry) for entry in pending_attachments
    ]

    submission = submission_store.record(
        username,
        responses,
        metadata=cleaned_metadata,
        attachments=structured_attachments,
    )

    grading_result, rating_updates = await grade_submission(
        settings=settings,
        profile=profile,
        submission=submission,
        tasks=tasks,
    )
    updated_submission = submission_store.apply_grading(username, submission.submission_id, grading_result)
    profile_store.apply_assessment_result(username, grading_result, rating_updates)
    try:
        generate_schedule_for_user(username)
        emit_event(
            "schedule_generation_post_grading",
            username=username,
            status="success",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to generate schedule after grading for %s", username)
        emit_event(
            "schedule_generation_post_grading",
            username=username,
            status="error",
            error=str(exc),
            exception_type=exc.__class__.__name__,
        )
    return submission_payload(updated_submission)


@router.get(
    "/{username}/assessment/submissions",
    response_model=List[AssessmentSubmissionPayload],
    status_code=status.HTTP_200_OK,
)
def list_assessment_submissions(username: str) -> List[AssessmentSubmissionPayload]:
    entries = submission_store.list_user(username)
    return [submission_payload(entry) for entry in entries]


@router.get(
    "/{username}/assessment/result",
    response_model=AssessmentGradingPayload,
    status_code=status.HTTP_200_OK,
)
def get_assessment_result(username: str) -> AssessmentGradingPayload:
    profile = profile_store.get(username)
    if profile is None or profile.onboarding_assessment_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Grading result for '{username}' is not available.",
        )
    payload = _profile_payload(profile)
    if payload.onboarding_assessment_result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to transform grading payload.",
        )
    return payload.onboarding_assessment_result
