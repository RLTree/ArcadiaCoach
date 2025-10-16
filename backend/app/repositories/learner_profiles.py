"""Database-backed learner profile repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..assessment_result import AssessmentGradingResult
from ..curriculum_foundations import ensure_foundational_curriculum
from ..db.models import (
    CurriculumScheduleItemModel,
    CurriculumScheduleModel,
    LearnerMemoryRecordModel,
    LearnerProfileModel,
    PersistenceAuditEventModel,
)
from ..learner_profile import (
    CurriculumPlan,
    CurriculumSchedule,
    FoundationTrack,
    GoalParserInference,
    LearnerProfile,
    MemoryRecord,
    OnboardingAssessment,
    SequencedWorkItem,
    DEFAULT_VECTOR_STORE_ID,
    EloCategoryPlan,
    MilestoneProgress,
)

MAX_MEMORY_RECORDS = 150


def _normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not normalized:
        raise ValueError("Username cannot be empty.")
    return normalized


class LearnerProfileRepository:
    """Persistence helper that mirrors the previous JSON-backed store API."""

    def get(self, session: Session, username: str) -> LearnerProfile | None:
        normalized = _normalize_username(username)
        stmt = select(LearnerProfileModel).where(LearnerProfileModel.username == normalized)
        model = session.execute(stmt).scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(session, model)

    def upsert(self, session: Session, profile: LearnerProfile) -> LearnerProfile:
        normalized = _normalize_username(profile.username)
        stmt = select(LearnerProfileModel).where(LearnerProfileModel.username == normalized)
        model = session.execute(stmt).scalar_one_or_none()
        if model is None:
            model = LearnerProfileModel(username=normalized, memory_index_id=profile.memory_index_id)
            session.add(model)

        self._apply_profile(model, profile)
        self._sync_memory_records(session, model, profile.memory_records)
        session.flush()
        self._record_audit(session, model.id, "profile_upsert", {"username": normalized})
        return self._to_domain(session, model)

    def apply_metadata(self, session: Session, username: str, metadata: Dict[str, Any]) -> LearnerProfile:
        model = self._require_model(session, username, create_if_missing=True)
        updated = False

        def _maybe_update_text(field: str) -> None:
            value = metadata.get(field)
            nonlocal updated
            if isinstance(value, str):
                trimmed = value.strip()
                if trimmed and getattr(model, field) != trimmed:
                    setattr(model, field, trimmed)
                    updated = True

        _maybe_update_text("goal")
        _maybe_update_text("use_case")
        _maybe_update_text("strengths")

        tz_value = metadata.get("timezone")
        if isinstance(tz_value, str):
            trimmed = tz_value.strip()
            if trimmed and trimmed != model.timezone:
                model.timezone = trimmed
                updated = True

        tags_payload = metadata.get("knowledge_tags")
        if isinstance(tags_payload, Iterable) and not isinstance(tags_payload, (str, bytes)):
            combined = {tag.lower(): tag for tag in model.knowledge_tags or []}
            for tag in tags_payload:
                if isinstance(tag, str) and tag.strip():
                    combined[tag.strip().lower()] = tag.strip()
            new_tags = list(combined.values())
            if new_tags != model.knowledge_tags:
                model.knowledge_tags = new_tags
                updated = True

        session_id = metadata.get("session_id")
        if isinstance(session_id, str) and session_id:
            sessions = list(model.recent_sessions or [])
            if session_id not in sessions:
                sessions.append(session_id)
                model.recent_sessions = sessions[-10:]
                updated = True

        elo_payload = metadata.get("elo")
        if isinstance(elo_payload, dict):
            snapshot = dict(model.elo_snapshot or {})
            mutated = False
            for key, value in elo_payload.items():
                if isinstance(key, str) and isinstance(value, (int, float)):
                    snapshot[key] = int(value)
                    mutated = True
            if mutated:
                model.elo_snapshot = snapshot
                updated = True

        if updated:
            model.last_updated = datetime.now(timezone.utc)
            session.flush()
            self._record_audit(session, model.id, "profile_apply_metadata", {"username": model.username})
        return self._to_domain(session, model)

    def append_memory(self, session: Session, username: str, note_id: str, note: str, tags: Iterable[str]) -> LearnerProfile:
        model = self._require_model(session, username, create_if_missing=True)
        record = LearnerMemoryRecordModel(
            learner_id=model.id,
            note_id=note_id,
            note=note,
            tags=[tag.strip() for tag in tags if tag and tag.strip()],
        )
        session.add(record)
        model.last_updated = datetime.now(timezone.utc)

        stmt = (
            select(LearnerMemoryRecordModel)
            .where(LearnerMemoryRecordModel.learner_id == model.id)
            .order_by(LearnerMemoryRecordModel.created_at.asc())
        )
        records = session.execute(stmt).scalars().all()
        if len(records) > MAX_MEMORY_RECORDS:
            for stale in records[:-MAX_MEMORY_RECORDS]:
                session.delete(stale)
        session.flush()
        self._record_audit(session, model.id, "memory_append", {"note_id": note_id})
        return self._to_domain(session, model)

    def set_elo_category_plan(self, session: Session, username: str, plan: EloCategoryPlan) -> LearnerProfile:
        model = self._require_model(session, username, create_if_missing=True)
        model.elo_category_plan = plan.model_dump(mode="json")

        snapshot = dict(model.elo_snapshot or {})
        for category in plan.categories:
            snapshot.setdefault(category.key, int(category.starting_rating))
        model.elo_snapshot = snapshot
        model.last_updated = datetime.now(timezone.utc)
        session.flush()
        self._record_audit(session, model.id, "elo_plan_update", {"category_count": len(plan.categories)})
        return self._to_domain(session, model)

    def set_curriculum_and_assessment(
        self,
        session: Session,
        username: str,
        curriculum: CurriculumPlan,
        assessment: OnboardingAssessment,
    ) -> LearnerProfile:
        model = self._require_model(session, username, create_if_missing=True)
        model.curriculum_plan = curriculum.model_dump(mode="json")
        model.onboarding_assessment = assessment.model_dump(mode="json")
        model.schedule_adjustments = {}
        self._delete_schedule(session, model.id)
        model.last_updated = datetime.now(timezone.utc)
        session.flush()
        self._record_audit(session, model.id, "curriculum_assessment_set", {})
        return self._to_domain(session, model)

    def set_goal_inference(
        self,
        session: Session,
        username: str,
        inference: GoalParserInference,
    ) -> LearnerProfile:
        model = self._require_model(session, username, create_if_missing=True)
        model.goal_inference = inference.model_dump(mode="json")
        model.foundation_tracks = [
            track.model_dump(mode="json") for track in inference.tracks
        ]
        model.last_updated = datetime.now(timezone.utc)
        session.flush()
        self._record_audit(session, model.id, "goal_inference_set", {"track_count": len(inference.tracks)})
        return self._to_domain(session, model)

    def set_curriculum_schedule(
        self,
        session: Session,
        username: str,
        schedule: CurriculumSchedule,
        *,
        adjustments: Optional[Dict[str, int]] = None,
    ) -> LearnerProfile:
        model = self._require_model(session, username)
        schedule_model = self._get_schedule_model(session, model.id)
        if schedule_model is None:
            schedule_model = CurriculumScheduleModel(learner_id=model.id)
            session.add(schedule_model)
            session.flush([schedule_model])

        schedule_model.generated_at = schedule.generated_at
        schedule_model.time_horizon_days = schedule.time_horizon_days
        schedule_model.timezone = schedule.timezone
        schedule_model.cadence_notes = schedule.cadence_notes
        schedule_model.is_stale = schedule.is_stale
        schedule_model.pacing_overview = schedule.pacing_overview
        schedule_model.warnings = [warning.model_dump(mode="json") for warning in schedule.warnings]
        schedule_model.category_allocations = [
            allocation.model_dump(mode="json") for allocation in schedule.category_allocations
        ]
        schedule_model.rationale_history = [
            entry.model_dump(mode="json") for entry in schedule.rationale_history
        ]
        schedule_model.sessions_per_week = schedule.sessions_per_week
        schedule_model.projected_weekly_minutes = schedule.projected_weekly_minutes
        schedule_model.long_range_item_count = schedule.long_range_item_count
        schedule_model.extended_weeks = schedule.extended_weeks
        schedule_model.long_range_category_keys = list(schedule.long_range_category_keys)

        self._replace_schedule_items(session, schedule_model, schedule.items)

        if adjustments is not None:
            sanitized = {
                item_id: max(int(offset), 0)
                for item_id, offset in adjustments.items()
                if isinstance(item_id, str)
            }
            model.schedule_adjustments = sanitized
        else:
            allowed_ids = {item.item_id for item in schedule.items}
            model.schedule_adjustments = {
                item_id: offset
                for item_id, offset in (model.schedule_adjustments or {}).items()
                if item_id in allowed_ids
            }

        if schedule_model.timezone and schedule_model.timezone != model.timezone:
            model.timezone = schedule_model.timezone

        model.last_updated = datetime.now(timezone.utc)
        session.flush()
        self._record_audit(session, model.id, "curriculum_schedule_set", {"item_count": len(schedule.items)})
        return self._to_domain(session, model)

    def update_schedule_item(
        self,
        session: Session,
        username: str,
        item_id: str,
        *,
        status: Optional[str] = None,
        last_launched_at: Optional[datetime] = None,
        last_completed_at: Optional[datetime] = None,
        active_session_id: Optional[str] = None,
        clear_active_session: bool = False,
        milestone_progress: Optional[MilestoneProgress] = None,
    ) -> LearnerProfile:
        model = self._require_model(session, username)
        schedule_model = self._get_schedule_model(session, model.id)
        if schedule_model is None:
            raise LookupError(f"No curriculum schedule configured for '{username}'.")
        stmt = (
            select(CurriculumScheduleItemModel)
            .where(
                CurriculumScheduleItemModel.schedule_id == schedule_model.id,
                CurriculumScheduleItemModel.item_id == item_id,
            )
        )
        record = session.execute(stmt).scalar_one_or_none()
        if record is None:
            raise LookupError(f"Schedule item '{item_id}' not found for '{username}'.")

        update_values: dict[str, Any] = {}
        if status:
            update_values["status"] = status
        if last_launched_at is not None:
            update_values["last_started_at"] = last_launched_at
        if last_completed_at is not None:
            update_values["last_completed_at"] = last_completed_at
        if clear_active_session:
            update_values["active_session_id"] = None
        elif active_session_id is not None:
            update_values["active_session_id"] = active_session_id
        if milestone_progress is not None:
            update_values["milestone_progress"] = milestone_progress.model_dump(mode="json")
        elif status and status != "completed" and record.kind == "milestone":
            update_values["milestone_progress"] = None

        if update_values:
            session.execute(
                update(CurriculumScheduleItemModel)
                .where(CurriculumScheduleItemModel.id == record.id)
                .values(**update_values)
            )

        session.flush()
        model.last_updated = datetime.now(timezone.utc)
        self._record_audit(
            session,
            model.id,
            "curriculum_schedule_item_update",
            {
                "item_id": item_id,
                "status": status,
                "clear_active_session": clear_active_session,
                "progress_recorded": milestone_progress is not None,
            },
        )
        return self._to_domain(session, model)

    def apply_schedule_adjustment(self, session: Session, username: str, item_id: str, target_offset: int) -> LearnerProfile:
        model = self._require_model(session, username)
        if not item_id:
            raise ValueError("Schedule item id cannot be empty.")
        adjustments = dict(model.schedule_adjustments or {})
        adjustments[item_id] = max(int(target_offset), 0)
        model.schedule_adjustments = adjustments
        model.last_updated = datetime.now(timezone.utc)
        session.flush()
        self._record_audit(session, model.id, "schedule_adjustment", {"item_id": item_id, "offset": target_offset})
        return self._to_domain(session, model)

    def update_schedule_adjustments(self, session: Session, username: str, adjustments: Dict[str, int]) -> LearnerProfile:
        model = self._require_model(session, username)
        sanitized = {
            item_id: max(int(offset), 0)
            for item_id, offset in adjustments.items()
            if isinstance(item_id, str)
        }
        model.schedule_adjustments = sanitized
        model.last_updated = datetime.now(timezone.utc)
        session.flush()
        self._record_audit(session, model.id, "schedule_adjustments_update", {"count": len(sanitized)})
        return self._to_domain(session, model)

    def apply_assessment_result(
        self,
        session: Session,
        username: str,
        result: AssessmentGradingResult,
        elo_snapshot: Dict[str, int],
    ) -> LearnerProfile:
        model = self._require_model(session, username)
        model.onboarding_assessment_result = result.model_dump(mode="json")
        if model.onboarding_assessment is not None:
            payload = dict(model.onboarding_assessment)
            payload["status"] = "completed"
            model.onboarding_assessment = payload

        if elo_snapshot:
            sanitized = {
                key: max(int(value), 0)
                for key, value in elo_snapshot.items()
                if isinstance(key, str)
            }
            snapshot = dict(model.elo_snapshot or {})
            snapshot.update(sanitized)
            model.elo_snapshot = snapshot

        if model.curriculum_plan:
            categories = []
            if model.elo_category_plan:
                categories = EloCategoryPlan.model_validate(model.elo_category_plan).categories
            curriculum_plan = CurriculumPlan.model_validate(model.curriculum_plan)
            goal_inference = (
                GoalParserInference.model_validate(model.goal_inference) if model.goal_inference else None
            )
            augmented_categories, augmented_curriculum = ensure_foundational_curriculum(
                goal=model.goal or "",
                plan=curriculum_plan,
                categories=categories,
                assessment_result=result,
                goal_inference=goal_inference,
            )
            if model.elo_category_plan:
                plan = EloCategoryPlan.model_validate(model.elo_category_plan)
                plan.categories = augmented_categories
                model.elo_category_plan = plan.model_dump(mode="json")
            else:
                model.elo_category_plan = EloCategoryPlan(categories=augmented_categories).model_dump(mode="json")
            model.curriculum_plan = augmented_curriculum.model_dump(mode="json")
            snapshot = dict(model.elo_snapshot or {})
            for category in augmented_categories:
                snapshot.setdefault(category.key, int(category.starting_rating))
            model.elo_snapshot = snapshot

        model.last_updated = datetime.now(timezone.utc)
        session.flush()
        self._record_audit(session, model.id, "assessment_result_applied", {"submission_id": result.submission_id})
        return self._to_domain(session, model)

    def update_assessment_status(self, session: Session, username: str, status: str) -> LearnerProfile:
        if status not in {"pending", "in_progress", "completed"}:
            raise ValueError(f"Unsupported onboarding assessment status: {status}")
        model = self._require_model(session, username)
        if model.onboarding_assessment is None:
            raise LookupError(f"Assessment for '{username}' has not been generated.")
        payload = dict(model.onboarding_assessment)
        payload["status"] = status
        model.onboarding_assessment = payload
        model.last_updated = datetime.now(timezone.utc)
        session.flush()
        self._record_audit(session, model.id, "assessment_status_update", {"status": status})
        return self._to_domain(session, model)

    def delete(self, session: Session, username: str) -> bool:
        normalized = _normalize_username(username)
        stmt = select(LearnerProfileModel).where(LearnerProfileModel.username == normalized)
        model = session.execute(stmt).scalar_one_or_none()
        if model is None:
            return False
        learner_id = model.id
        session.delete(model)
        session.flush()
        self._record_audit(session, learner_id, "profile_delete", {"username": normalized})
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_model(
        self,
        session: Session,
        username: str,
        *,
        create_if_missing: bool = False,
    ) -> LearnerProfileModel:
        normalized = _normalize_username(username)
        stmt = select(LearnerProfileModel).where(LearnerProfileModel.username == normalized)
        model = session.execute(stmt).scalar_one_or_none()
        if model is None and create_if_missing:
            model = LearnerProfileModel(
                username=normalized,
                memory_index_id=DEFAULT_VECTOR_STORE_ID,
            )
            session.add(model)
            session.flush()
        if model is None:
            raise LookupError(f"Learner profile '{username}' does not exist.")
        return model

    def _apply_profile(self, model: LearnerProfileModel, profile: LearnerProfile) -> None:
        model.goal = profile.goal or ""
        model.use_case = profile.use_case or ""
        model.strengths = profile.strengths or ""
        model.timezone = profile.timezone
        model.knowledge_tags = list(profile.knowledge_tags or [])
        model.recent_sessions = list(profile.recent_sessions or [])
        model.memory_index_id = profile.memory_index_id or DEFAULT_VECTOR_STORE_ID
        model.elo_snapshot = dict(profile.elo_snapshot or {})
        model.elo_category_plan = (
            profile.elo_category_plan.model_dump(mode="json") if profile.elo_category_plan else None
        )
        model.curriculum_plan = (
            profile.curriculum_plan.model_dump(mode="json") if profile.curriculum_plan else None
        )
        model.schedule_adjustments = dict(profile.schedule_adjustments or {})
        model.onboarding_assessment = (
            profile.onboarding_assessment.model_dump(mode="json") if profile.onboarding_assessment else None
        )
        model.onboarding_assessment_result = (
            profile.onboarding_assessment_result.model_dump(mode="json")
            if profile.onboarding_assessment_result
            else None
        )
        model.goal_inference = (
            profile.goal_inference.model_dump(mode="json") if profile.goal_inference else None
        )
        model.foundation_tracks = [
            track.model_dump(mode="json") for track in profile.foundation_tracks
        ]
        model.last_updated = profile.last_updated or datetime.now(timezone.utc)

    def _sync_memory_records(
        self,
        session: Session,
        model: LearnerProfileModel,
        records: Iterable[MemoryRecord],
    ) -> None:
        session.execute(
            delete(LearnerMemoryRecordModel).where(LearnerMemoryRecordModel.learner_id == model.id)
        )
        for record in records:
            session.add(
                LearnerMemoryRecordModel(
                    learner_id=model.id,
                    note_id=record.note_id,
                    note=record.note,
                    tags=list(record.tags or []),
                    created_at=record.created_at,
                )
            )

    def _to_domain(self, session: Session, model: LearnerProfileModel) -> LearnerProfile:
        payload: Dict[str, Any] = {
            "username": model.username,
            "goal": model.goal or "",
            "use_case": model.use_case or "",
            "strengths": model.strengths or "",
            "timezone": model.timezone,
            "knowledge_tags": model.knowledge_tags or [],
            "recent_sessions": model.recent_sessions or [],
            "memory_records": self._load_memory_records(session, model.id),
            "memory_index_id": model.memory_index_id or DEFAULT_VECTOR_STORE_ID,
            "elo_snapshot": model.elo_snapshot or {},
            "schedule_adjustments": model.schedule_adjustments or {},
            "last_updated": model.last_updated or datetime.now(timezone.utc),
        }

        if model.elo_category_plan:
            payload["elo_category_plan"] = EloCategoryPlan.model_validate(model.elo_category_plan)
        if model.curriculum_plan:
            payload["curriculum_plan"] = CurriculumPlan.model_validate(model.curriculum_plan)
        if model.onboarding_assessment:
            payload["onboarding_assessment"] = OnboardingAssessment.model_validate(model.onboarding_assessment)
        if model.onboarding_assessment_result:
            payload["onboarding_assessment_result"] = AssessmentGradingResult.model_validate(
                model.onboarding_assessment_result
            )
        if model.goal_inference:
            payload["goal_inference"] = GoalParserInference.model_validate(model.goal_inference)
        if model.foundation_tracks:
            payload["foundation_tracks"] = [
                FoundationTrack.model_validate(entry) for entry in model.foundation_tracks
            ]

        schedule = self._load_schedule(session, model.id)
        if schedule:
            payload["curriculum_schedule"] = schedule

        return LearnerProfile.model_validate(payload)

    def _load_memory_records(self, session: Session, learner_id) -> list[MemoryRecord]:
        stmt = (
            select(LearnerMemoryRecordModel)
            .where(LearnerMemoryRecordModel.learner_id == learner_id)
            .order_by(LearnerMemoryRecordModel.created_at.desc())
        )
        records = session.execute(stmt).scalars().all()
        return [
            MemoryRecord(
                note_id=record.note_id,
                note=record.note,
                tags=list(record.tags or []),
                created_at=record.created_at,
            )
            for record in records
        ]

    def _load_schedule(self, session: Session, learner_id) -> Optional[CurriculumSchedule]:
        schedule_model = self._get_schedule_model(session, learner_id)
        if schedule_model is None:
            return None
        stmt = (
            select(CurriculumScheduleItemModel)
            .where(CurriculumScheduleItemModel.schedule_id == schedule_model.id)
            .order_by(CurriculumScheduleItemModel.recommended_day_offset.asc(), CurriculumScheduleItemModel.id.asc())
        )
        items = session.execute(stmt).scalars().all()
        schedule_payload = {
            "generated_at": schedule_model.generated_at,
            "time_horizon_days": schedule_model.time_horizon_days,
            "timezone": schedule_model.timezone,
            "cadence_notes": schedule_model.cadence_notes,
            "items": [
                {
                    "item_id": item.item_id,
                    "category_key": item.category_key,
                    "kind": item.kind,
                    "title": item.title,
                    "summary": item.summary,
                    "objectives": item.objectives,
                    "prerequisites": item.prerequisites,
                    "recommended_minutes": item.recommended_minutes,
                    "recommended_day_offset": item.recommended_day_offset,
                    "focus_reason": item.focus_reason,
                    "expected_outcome": item.expected_outcome,
                    "effort_level": item.effort_level,
                    "user_adjusted": item.user_adjusted,
                    "launch_status": item.status,
                    "last_launched_at": item.last_started_at,
                    "last_completed_at": item.last_completed_at,
                    "active_session_id": item.active_session_id,
                    "milestone_brief": item.milestone_brief,
                    "milestone_progress": item.milestone_progress,
                }
                for item in items
            ],
            "is_stale": schedule_model.is_stale,
            "warnings": schedule_model.warnings or [],
            "pacing_overview": schedule_model.pacing_overview,
            "category_allocations": schedule_model.category_allocations or [],
            "rationale_history": schedule_model.rationale_history or [],
            "sessions_per_week": schedule_model.sessions_per_week,
            "projected_weekly_minutes": schedule_model.projected_weekly_minutes,
            "long_range_item_count": schedule_model.long_range_item_count,
            "extended_weeks": schedule_model.extended_weeks,
            "long_range_category_keys": schedule_model.long_range_category_keys or [],
        }
        return CurriculumSchedule.model_validate(schedule_payload)

    def _get_schedule_model(self, session: Session, learner_id):
        stmt = select(CurriculumScheduleModel).where(CurriculumScheduleModel.learner_id == learner_id)
        return session.execute(stmt).scalar_one_or_none()

    def _replace_schedule_items(
        self,
        session: Session,
        schedule_model: CurriculumScheduleModel,
        items: Iterable[SequencedWorkItem],
    ) -> None:
        session.execute(
            delete(CurriculumScheduleItemModel).where(CurriculumScheduleItemModel.schedule_id == schedule_model.id)
        )
        for work_item in items:
            session.add(
                CurriculumScheduleItemModel(
                    schedule_id=schedule_model.id,
                    item_id=work_item.item_id,
                    category_key=work_item.category_key,
                    kind=work_item.kind,
                    title=work_item.title,
                    summary=work_item.summary,
                    objectives=list(work_item.objectives),
                    prerequisites=list(work_item.prerequisites),
                    recommended_minutes=work_item.recommended_minutes,
                    recommended_day_offset=work_item.recommended_day_offset,
                    focus_reason=work_item.focus_reason,
                    expected_outcome=work_item.expected_outcome,
                    effort_level=work_item.effort_level,
                    user_adjusted=work_item.user_adjusted,
                    status=getattr(work_item, "launch_status", "pending"),
                    last_started_at=getattr(work_item, "last_launched_at", None),
                    last_completed_at=getattr(work_item, "last_completed_at", None),
                    active_session_id=getattr(work_item, "active_session_id", None),
                    milestone_brief=(
                        work_item.milestone_brief.model_dump(mode="json")
                        if work_item.milestone_brief
                        else None
                    ),
                    milestone_progress=(
                        work_item.milestone_progress.model_dump(mode="json")
                        if work_item.milestone_progress
                        else None
                    ),
                )
            )

    def _delete_schedule(self, session: Session, learner_id) -> None:
        schedule_model = self._get_schedule_model(session, learner_id)
        if schedule_model:
            session.delete(schedule_model)

    def _record_audit(self, session: Session, learner_id, event_type: str, payload: Dict[str, Any]) -> None:
        event = PersistenceAuditEventModel(
            learner_id=learner_id,
            event_type=event_type,
            payload=payload,
            actor="system",
        )
        session.add(event)


learner_profiles = LearnerProfileRepository()

__all__ = ["LearnerProfileRepository", "learner_profiles"]
