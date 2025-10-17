"""Developer utilities for manual resets and submission inspection (Phase 4)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from .agent_models import AssessmentSubmissionPayload, CurriculumSchedulePayload
from .assessment_submission import submission_payload, submission_store
from .assessment_attachments import attachment_store
from .learner_profile import LearnerProfile, profile_store
from .curriculum_sequencer import generate_schedule_for_user
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


class DeveloperEloBoostRequest(BaseModel):
    username: str = Field(..., min_length=1)
    category_key: Optional[str] = Field(default=None, description="Restrict boost to a single category key")
    target_rating: int = Field(default=1400, ge=0, le=5000)
    preserve_requirements: bool = Field(default=True, description="Keep milestone requirements at or below their previous thresholds")
    complete_prior_items: bool = Field(
        default=True,
        description="Mark earlier lessons/quizzes complete so milestone locks clear after boosting ratings.",
    )


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
    schedule_payload = _schedule_payload(
        refreshed.curriculum_schedule,
        elo_snapshot=getattr(refreshed, "elo_snapshot", {}),
        elo_plan=getattr(refreshed, "elo_category_plan", None),
    )
    if schedule_payload is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to prepare the updated schedule.",
        )
    return schedule_payload


@router.post(
    "/boost-elo",
    response_model=CurriculumSchedulePayload,
    status_code=status.HTTP_200_OK,
)
def developer_boost_elo(payload: DeveloperEloBoostRequest) -> CurriculumSchedulePayload:
    username = payload.username.strip()
    if not username:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username cannot be empty.",
        )
    profile = profile_store.get(username)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learner profile for '{username}' was not found.",
        )
    snapshot = dict(getattr(profile, "elo_snapshot", {}) or {})
    if not snapshot and payload.category_key is None:
        plan = getattr(profile, "elo_category_plan", None)
        if plan and getattr(plan, "categories", None):
            snapshot = {category.key: int(category.starting_rating) for category in plan.categories if category.key}
    if payload.category_key is not None:
        categories: Set[str] = {payload.category_key.strip()}
    else:
        categories = set(snapshot.keys())
    if not categories:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No categories available to boost ELO ratings.",
        )
    target = max(int(payload.target_rating), 1100)
    metadata = {"elo": {key: target for key in categories}}

    original_requirements: Dict[str, Dict[str, int]] = {}
    original_queue: Dict[str, Dict[str, int]] = {}
    if payload.preserve_requirements and getattr(profile, "curriculum_schedule", None):
        for item in profile.curriculum_schedule.items:
            if getattr(item, "milestone_requirements", None):
                original_requirements[item.item_id] = {
                    req.category_key: int(req.minimum_rating)
                    for req in item.milestone_requirements
                }
        for entry in getattr(profile.curriculum_schedule, "milestone_queue", []) or []:
            if getattr(entry, "requirements", None):
                original_queue[entry.item_id] = {
                    req.category_key: int(req.minimum_rating)
                    for req in entry.requirements
                }

    def _restore_requirements_for_schedule(current: CurriculumSchedule) -> LearnerProfile:
        for item in current.items:
            if item.kind != "milestone":
                continue
            preserved = original_requirements.get(item.item_id)
            if not preserved:
                continue
            for requirement in getattr(item, "milestone_requirements", []) or []:
                old_min = preserved.get(requirement.category_key)
                if old_min is not None and requirement.minimum_rating > old_min:
                    requirement.minimum_rating = old_min
                if getattr(requirement, "current_rating", 0) < requirement.minimum_rating:
                    requirement.current_rating = requirement.minimum_rating
            if getattr(item, "requirement_progress_snapshot", None):
                for snapshot_req in item.requirement_progress_snapshot:
                    old_min = preserved.get(snapshot_req.category_key)
                    if old_min is not None and snapshot_req.minimum_rating > old_min:
                        snapshot_req.minimum_rating = old_min
                    if snapshot_req.current_rating < snapshot_req.minimum_rating:
                        snapshot_req.current_rating = snapshot_req.minimum_rating

        if getattr(current, "milestone_queue", None):
            for entry in current.milestone_queue:
                preserved = original_queue.get(entry.item_id)
                if not preserved:
                    continue
                for requirement in getattr(entry, "requirements", []) or []:
                    old_min = preserved.get(requirement.category_key)
                    if old_min is not None and requirement.minimum_rating > old_min:
                        requirement.minimum_rating = old_min
                    if requirement.current_rating < requirement.minimum_rating:
                        requirement.current_rating = requirement.minimum_rating

        profile_store.set_curriculum_schedule(username, current)
        refreshed = profile_store.get(username)
        if refreshed is None or refreshed.curriculum_schedule is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No curriculum schedule configured for '{username}'.",
            )
        return refreshed

    profile_store.apply_metadata(username, metadata)
    boosted_profile = generate_schedule_for_user(username)
    schedule = boosted_profile.curriculum_schedule
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No curriculum schedule configured for '{username}'.",
        )

    if payload.complete_prior_items:
        now = datetime.now(timezone.utc)
        for item in schedule.items:
            if item.kind == "milestone":
                continue
            if getattr(item, "launch_status", "pending") == "completed":
                continue
            try:
                profile_store.update_schedule_item(
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
        boosted_profile = generate_schedule_for_user(username)
        schedule = boosted_profile.curriculum_schedule
        if schedule is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No curriculum schedule configured for '{username}'.",
            )

    if payload.preserve_requirements and (original_requirements or original_queue):
        boosted_profile = _restore_requirements_for_schedule(schedule)
        schedule = boosted_profile.curriculum_schedule

    schedule_payload = _schedule_payload(
        schedule,
        elo_snapshot=getattr(boosted_profile, "elo_snapshot", {}),
        elo_plan=getattr(boosted_profile, "elo_category_plan", None),
    )
    if schedule_payload is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to prepare the updated schedule.",
        )
    emit_event(
        "developer_elo_boost",
        username=username,
        categories=";".join(sorted(categories)),
        target_rating=target,
    )
    return schedule_payload


__all__ = ["router"]
