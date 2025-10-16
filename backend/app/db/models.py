"""ORM models backing the Arcadia Coach persistence layer."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin

JSONType = JSON


class LearnerProfileModel(TimestampMixin, Base):
    __tablename__ = "learner_profiles"
    __table_args__ = (Index("ix_learner_profiles_username", "username", unique=True),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    goal: Mapped[str] = mapped_column(Text, default="", nullable=False)
    use_case: Mapped[str] = mapped_column(Text, default="", nullable=False)
    strengths: Mapped[str] = mapped_column(Text, default="", nullable=False)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    knowledge_tags: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    recent_sessions: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    memory_index_id: Mapped[str] = mapped_column(String(64), nullable=False)
    elo_snapshot: Mapped[dict[str, int]] = mapped_column(JSONType, default=dict, nullable=False)
    elo_category_plan: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    curriculum_plan: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    schedule_adjustments: Mapped[dict[str, int]] = mapped_column(JSONType, default=dict, nullable=False)
    onboarding_assessment: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    onboarding_assessment_result: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    goal_inference: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    foundation_tracks: Mapped[list[dict]] = mapped_column(JSONType, default=list, nullable=False)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    schedule: Mapped["CurriculumScheduleModel"] = relationship(
        back_populates="learner", cascade="all, delete-orphan", uselist=False
    )
    memory_records: Mapped[list["LearnerMemoryRecordModel"]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )
    submissions: Mapped[list["AssessmentSubmissionModel"]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["AssessmentAttachmentModel"]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )
    milestone_completions: Mapped[list["MilestoneCompletionModel"]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )


class LearnerMemoryRecordModel(Base):
    __tablename__ = "learner_memory_records"
    __table_args__ = (UniqueConstraint("note_id", name="uq_memory_note_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learner_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note_id: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    learner: Mapped[LearnerProfileModel] = relationship(back_populates="memory_records")


class CurriculumScheduleModel(Base):
    __tablename__ = "curriculum_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    learner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learner_profiles.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    time_horizon_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64))
    cadence_notes: Mapped[str | None] = mapped_column(Text)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pacing_overview: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list[dict]] = mapped_column(JSONType, default=list, nullable=False)
    category_allocations: Mapped[list[dict]] = mapped_column(JSONType, default=list, nullable=False)
    rationale_history: Mapped[list[dict]] = mapped_column(JSONType, default=list, nullable=False)
    sessions_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    projected_weekly_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    long_range_item_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extended_weeks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    long_range_category_keys: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)

    learner: Mapped[LearnerProfileModel] = relationship(back_populates="schedule")
    items: Mapped[list["CurriculumScheduleItemModel"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )


class CurriculumScheduleItemModel(Base):
    __tablename__ = "curriculum_schedule_items"
    __table_args__ = (Index("ix_schedule_items_day_offset", "recommended_day_offset"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    schedule_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("curriculum_schedules.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    category_key: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    objectives: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    prerequisites: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    recommended_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    recommended_day_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    focus_reason: Mapped[str | None] = mapped_column(Text)
    expected_outcome: Mapped[str | None] = mapped_column(Text)
    effort_level: Mapped[str] = mapped_column(String(16), nullable=False)
    user_adjusted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    milestone_brief: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    milestone_progress: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    milestone_project: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    schedule: Mapped[CurriculumScheduleModel] = relationship(back_populates="items")


class MilestoneCompletionModel(TimestampMixin, Base):
    __tablename__ = "milestone_completions"
    __table_args__ = (
        Index("ix_milestone_completions_learner", "learner_id"),
        UniqueConstraint("learner_id", "item_id", name="uq_milestone_completion_item"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    learner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learner_profiles.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    category_key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    headline: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    external_links: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    attachment_ids: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    elo_focus: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    recommended_day_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    project_status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    evaluation_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evaluation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    elo_delta: Mapped[int] = mapped_column(Integer, default=12, nullable=False)

    learner: Mapped[LearnerProfileModel] = relationship(back_populates="milestone_completions")


class AssessmentSubmissionModel(Base):
    __tablename__ = "assessment_submissions"
    __table_args__ = (
        Index("ix_assessment_submissions_learner", "learner_id"),
        Index("ix_assessment_submissions_created", "submitted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    learner_id: Mapped[uuid.UUID] = mapped_column(
        String(36), ForeignKey("learner_profiles.id", ondelete="CASCADE"), nullable=False
    )
    submission_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    responses: Mapped[list[dict]] = mapped_column(JSONType, default=list, nullable=False)
    attachments: Mapped[list[dict]] = mapped_column(JSONType, default=list, nullable=False)
    metadata_payload: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)
    grading: Mapped[dict | None] = mapped_column(JSONType)

    learner: Mapped[LearnerProfileModel] = relationship(back_populates="submissions")


class AssessmentAttachmentModel(Base):
    __tablename__ = "assessment_attachments"
    __table_args__ = (
        Index("ix_assessment_attachments_learner", "learner_id"),
        Index("ix_assessment_attachments_consumed", "is_consumed"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    attachment_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    learner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learner_profiles.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    stored_path: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    is_consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    learner: Mapped[LearnerProfileModel] = relationship(back_populates="attachments")


class PersistenceAuditEventModel(Base):
    __tablename__ = "persistence_audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    learner_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("learner_profiles.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    actor: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    learner: Mapped[LearnerProfileModel | None] = relationship()


__all__ = [
    "AssessmentAttachmentModel",
    "AssessmentSubmissionModel",
    "CurriculumScheduleItemModel",
    "CurriculumScheduleModel",
    "LearnerMemoryRecordModel",
    "LearnerProfileModel",
    "MilestoneCompletionModel",
    "PersistenceAuditEventModel",
]
