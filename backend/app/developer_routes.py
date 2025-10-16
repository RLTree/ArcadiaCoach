"""Developer utilities for manual resets and submission inspection (Phase 4)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Set

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from .agent_models import AssessmentSubmissionPayload, CurriculumSchedulePayload
from .assessment_submission import submission_payload, submission_store
from .assessment_attachments import attachment_store
from .learner_profile import profile_store
from .tools import _schedule_payload
from .telemetry import emit_event


router = APIRouter(prefix="/api/developer", tags=["developer"])


class DeveloperResetRequest(BaseModel):
    username: str = Field(..., min_length=1)


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
def developer_reset(payload: DeveloperResetRequest) -> Response:
    username = payload.username.strip()
    if not username:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username cannot be empty.",
        )
    profile_store.delete(username)
    submission_store.delete_user(username)
    attachment_store.purge_user(username)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/submissions",
    response_model=List[AssessmentSubmissionPayload],
    status_code=status.HTTP_200_OK,
)
def developer_submissions(username: Optional[str] = Query(default=None)) -> List[AssessmentSubmissionPayload]:
    if username:
        entries = submission_store.list_user(username)
    else:
        entries = submission_store.list_all()
    return [submission_payload(entry) for entry in entries]


class DeveloperAutoCompleteRequest(BaseModel):
    username: str = Field(..., min_length=1)
    include_lessons: bool = True
    include_quizzes: bool = True


@router.post(
    "/auto-complete",
    response_model=CurriculumSchedulePayload,
    status_code=status.HTTP_200_OK,
)
def developer_auto_complete(payload: DeveloperAutoCompleteRequest) -> CurriculumSchedulePayload:
    username = payload.username.strip()
    if not username:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username cannot be empty.",
        )
    kinds: Set[str] = set()
    if payload.include_lessons:
        kinds.add("lesson")
    if payload.include_quizzes:
        kinds.add("quiz")
    if not kinds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select at least one item type to auto-complete.",
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
    now = datetime.now(timezone.utc)
    for item in schedule.items:
        if item.kind not in kinds:
            continue
        if item.launch_status == "completed":
            continue
        previous_status = item.launch_status
        try:
            result = profile_store.update_schedule_item(
                username,
                item.item_id,
                status="completed",
                last_completed_at=now,
                clear_active_session=True,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        emit_event(
            "schedule_launch_completed",
            username=username,
            item_id=item.item_id,
            kind=item.kind,
            status="completed",
            previous_status=previous_status,
            progress_recorded=False,
            source="developer_auto_complete",
        )
        schedule = result.curriculum_schedule
        if schedule is None:
            break
    refreshed = profile_store.get(username)
    if refreshed is None or refreshed.curriculum_schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )
    schedule_payload = _schedule_payload(refreshed.curriculum_schedule)
    if schedule_payload is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to prepare the updated schedule.",
        )
    return schedule_payload


__all__ = ["router"]
