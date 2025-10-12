"""Developer utilities for manual resets and submission inspection (Phase 4)."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from .agent_models import AssessmentSubmissionPayload
from .assessment_submission import submission_payload, submission_store
from .learner_profile import profile_store


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


__all__ = ["router"]
