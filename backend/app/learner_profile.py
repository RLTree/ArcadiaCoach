"""Learner profile models and persistence helpers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Literal, Optional

from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .assessment_result import AssessmentGradingResult
from .db.session import session_scope

logger = logging.getLogger(__name__)

DEFAULT_VECTOR_STORE_ID = "vs_68e81d741f388191acdaabce2f92b7d5"
MAX_MEMORY_RECORDS = 150


if TYPE_CHECKING:
    from .repositories.learner_profiles import LearnerProfileRepository


def _repo() -> "LearnerProfileRepository":
    from .repositories.learner_profiles import learner_profiles as repository

    return repository


class MemoryRecord(BaseModel):
    note_id: str
    note: str
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EloRubricBand(BaseModel):
    """Rubric descriptor for an ELO band. Defined in Phase 2 (see docs/phase-2-elo-category-planning.md)."""

    level: str
    descriptor: str


class EloCategoryDefinition(BaseModel):
    """Category definition persisted during Phase 2 planning."""
    key: str
    label: str
    description: str
    focus_areas: List[str] = Field(default_factory=list)
    weight: float = Field(default=1.0, ge=0.0)
    rubric: List[EloRubricBand] = Field(default_factory=list)
    starting_rating: int = Field(default=1100, ge=0)


class EloCategoryPlan(BaseModel):
    """Aggregate learner skill plan introduced in Phase 2."""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_goal: Optional[str] = None
    strategy_notes: Optional[str] = None
    categories: List[EloCategoryDefinition] = Field(default_factory=list)


class CurriculumModule(BaseModel):
    """Single module within the onboarding curriculum outline."""

    module_id: str
    category_key: str
    title: str
    summary: str
    objectives: List[str] = Field(default_factory=list)
    activities: List[str] = Field(default_factory=list)
    deliverables: List[str] = Field(default_factory=list)
    estimated_minutes: Optional[int] = None
    tier: Optional[int] = Field(default=None, ge=1)
    prerequisite_module_ids: List[str] = Field(default_factory=list)


class FoundationModuleReference(BaseModel):
    """Reference to a reusable module template within a foundation track."""

    module_id: str
    category_key: str
    priority: Literal["core", "reinforcement", "extension"] = "core"
    suggested_weeks: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = None


class FoundationTrack(BaseModel):
    """Inferred foundation track derived from learner goals and context."""

    track_id: str
    label: str
    priority: Literal["now", "up_next", "later"] = "now"
    confidence: Literal["low", "medium", "high"] = "medium"
    weight: float = Field(default=1.0, ge=0.0)
    technologies: List[str] = Field(default_factory=list)
    focus_areas: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)
    recommended_modules: List[FoundationModuleReference] = Field(default_factory=list)
    suggested_weeks: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = None


class GoalParserInference(BaseModel):
    """Snapshot of the goal parser agent's foundation mapping (introduced in Phase 16)."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary: Optional[str] = None
    target_outcomes: List[str] = Field(default_factory=list)
    tracks: List[FoundationTrack] = Field(default_factory=list)
    missing_templates: List[str] = Field(default_factory=list)


class CurriculumPlan(BaseModel):
    """Curriculum outline generated during onboarding."""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overview: str = ""
    success_criteria: List[str] = Field(default_factory=list)
    modules: List[CurriculumModule] = Field(default_factory=list)


class SequencedWorkItem(BaseModel):
    """Single learning activity emitted by the curriculum sequencer (Phase 11)."""

    item_id: str
    category_key: str
    kind: Literal["lesson", "quiz", "milestone"]
    title: str
    summary: str = ""
    objectives: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)
    recommended_minutes: int = Field(default=45, ge=5)
    recommended_day_offset: int = Field(default=0, ge=0)
    focus_reason: Optional[str] = None
    expected_outcome: Optional[str] = None
    effort_level: Literal["light", "moderate", "focus"] = "moderate"
    user_adjusted: bool = Field(default=False)


class ScheduleWarning(BaseModel):
    """Warning surfaced when the schedule falls back to previously generated data."""

    code: Literal["refresh_failed", "stale_schedule"] = "refresh_failed"
    message: str
    detail: Optional[str] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CategoryPacing(BaseModel):
    """Summary of planned effort allocation for a given curriculum category."""

    category_key: str
    planned_minutes: int = Field(default=0, ge=0)
    target_share: float = Field(default=0.0, ge=0.0)
    deferral_pressure: Literal["low", "medium", "high"] = "low"
    deferral_count: int = Field(default=0, ge=0)
    max_deferral_days: int = Field(default=0, ge=0)
    rationale: Optional[str] = None


class ScheduleRationaleEntry(BaseModel):
    """Narrative explaining why the schedule evolved in its current direction."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    headline: str
    summary: str
    related_categories: List[str] = Field(default_factory=list)
    adjustment_notes: List[str] = Field(default_factory=list)


class CurriculumSchedule(BaseModel):
    """Rolling schedule for upcoming lessons, quizzes, and milestones."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    time_horizon_days: int = Field(default=14, ge=1)
    timezone: Optional[str] = None
    cadence_notes: Optional[str] = None
    items: List[SequencedWorkItem] = Field(default_factory=list)
    is_stale: bool = Field(default=False)
    warnings: List[ScheduleWarning] = Field(default_factory=list)
    pacing_overview: Optional[str] = None
    category_allocations: List[CategoryPacing] = Field(default_factory=list)
    rationale_history: List[ScheduleRationaleEntry] = Field(default_factory=list)
    sessions_per_week: int = Field(default=4, ge=1)
    projected_weekly_minutes: int = Field(default=0, ge=0)
    long_range_item_count: int = Field(default=0, ge=0)
    extended_weeks: int = Field(default=0, ge=0)
    long_range_category_keys: List[str] = Field(default_factory=list)


class AssessmentTask(BaseModel):
    """Assessment task delivered during onboarding assessment."""
    task_id: str
    category_key: str
    title: str
    task_type: Literal["concept_check", "code"]
    section_id: Optional[str] = None
    prompt: str
    guidance: str
    rubric: List[str] = Field(default_factory=list)
    expected_minutes: int = Field(default=20, ge=1)
    starter_code: Optional[str] = None
    answer_key: Optional[str] = None


class AssessmentSection(BaseModel):
    """Grouping of assessment tasks into themed sections (Phase 16)."""

    section_id: str
    title: str
    description: str = ""
    intent: Literal["concept", "coding", "data", "architecture", "tooling", "custom"] = "concept"
    expected_minutes: int = Field(default=45, ge=0)
    tasks: List[AssessmentTask] = Field(default_factory=list)


class OnboardingAssessment(BaseModel):
    """Personalised assessment bundle generated for onboarding."""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal["pending", "in_progress", "completed"] = "pending"
    tasks: List[AssessmentTask] = Field(default_factory=list)
    sections: List[AssessmentSection] = Field(default_factory=list)


class LearnerProfile(BaseModel):
    username: str
    goal: str = ""
    use_case: str = ""
    strengths: str = ""
    timezone: Optional[str] = None
    knowledge_tags: List[str] = Field(default_factory=list)
    recent_sessions: List[str] = Field(default_factory=list)
    memory_records: List[MemoryRecord] = Field(default_factory=list)
    memory_index_id: str = Field(default=DEFAULT_VECTOR_STORE_ID)
    elo_snapshot: Dict[str, int] = Field(default_factory=dict)
    elo_category_plan: Optional[EloCategoryPlan] = None
    curriculum_plan: Optional[CurriculumPlan] = None
    curriculum_schedule: Optional[CurriculumSchedule] = None
    schedule_adjustments: Dict[str, int] = Field(default_factory=dict)
    onboarding_assessment: Optional[OnboardingAssessment] = None
    onboarding_assessment_result: Optional[AssessmentGradingResult] = None
    goal_inference: Optional[GoalParserInference] = None
    foundation_tracks: List[FoundationTrack] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LearnerProfileStore:
    """Database-backed facade that preserves the previous store API."""

    def get(self, username: str) -> Optional[LearnerProfile]:
        with session_scope(commit=False) as session:
            profile = _repo().get(session, username)
            return profile.model_copy(deep=True) if profile else None

    def upsert(self, profile: LearnerProfile) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().upsert(session, profile)
            return stored.model_copy(deep=True)

    def apply_metadata(self, username: str, metadata: Dict[str, Any]) -> LearnerProfile:
        payload = dict(metadata)
        timezone_value = payload.get("timezone")
        if isinstance(timezone_value, str):
            normalized = self._normalise_timezone(timezone_value)
            if normalized:
                payload["timezone"] = normalized
            else:
                payload.pop("timezone", None)
        with session_scope() as session:
            stored = _repo().apply_metadata(session, username, payload)
            return stored.model_copy(deep=True)

    def append_memory(self, username: str, note_id: str, note: str, tags: Iterable[str]) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().append_memory(session, username, note_id, note, tags)
            return stored.model_copy(deep=True)

    def set_elo_category_plan(self, username: str, plan: EloCategoryPlan) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().set_elo_category_plan(session, username, plan)
            return stored.model_copy(deep=True)

    def set_curriculum_and_assessment(
        self,
        username: str,
        curriculum: CurriculumPlan,
        assessment: OnboardingAssessment,
    ) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().set_curriculum_and_assessment(session, username, curriculum, assessment)
            return stored.model_copy(deep=True)

    def set_goal_inference(self, username: str, inference: GoalParserInference) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().set_goal_inference(session, username, inference)
            return stored.model_copy(deep=True)

    def set_curriculum_schedule(
        self,
        username: str,
        schedule: CurriculumSchedule,
        *,
        adjustments: Optional[Dict[str, int]] = None,
    ) -> LearnerProfile:
        resolved_tz = schedule.timezone or self._extract_timezone(username)
        normalized_tz = self._normalise_timezone(resolved_tz) if resolved_tz else "UTC"
        schedule.timezone = normalized_tz
        with session_scope() as session:
            stored = _repo().set_curriculum_schedule(
                session,
                username,
                schedule,
                adjustments=adjustments,
            )
            return stored.model_copy(deep=True)

    def apply_schedule_adjustment(self, username: str, item_id: str, target_offset: int) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().apply_schedule_adjustment(session, username, item_id, target_offset)
            return stored.model_copy(deep=True)

    def update_schedule_adjustments(self, username: str, adjustments: Dict[str, int]) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().update_schedule_adjustments(session, username, adjustments)
            return stored.model_copy(deep=True)

    def apply_assessment_result(
        self,
        username: str,
        result: AssessmentGradingResult,
        elo_snapshot: Dict[str, int],
    ) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().apply_assessment_result(session, username, result, elo_snapshot)
            return stored.model_copy(deep=True)

    def update_assessment_status(self, username: str, status: str) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().update_assessment_status(session, username, status)
            return stored.model_copy(deep=True)

    def delete(self, username: str) -> bool:
        with session_scope() as session:
            return _repo().delete(session, username)

    def _extract_timezone(self, username: str) -> Optional[str]:
        profile = self.get(username)
        return profile.timezone if profile else None

    @staticmethod
    def _normalise_timezone(raw: str) -> Optional[str]:
        trimmed = raw.strip()
        if not trimmed:
            return None
        try:
            zone = ZoneInfo(trimmed)
        except ZoneInfoNotFoundError:
            logger.warning("Ignoring unsupported timezone value: %s", trimmed)
            return None
        except Exception:  # noqa: BLE001
            logger.warning("Failed to parse timezone value: %s", trimmed)
            return None
        return zone.key


profile_store = LearnerProfileStore()

__all__ = [
    "AssessmentGradingResult",
    "AssessmentTask",
    "CurriculumModule",
    "CurriculumPlan",
    "CurriculumSchedule",
    "ScheduleWarning",
    "EloCategoryDefinition",
    "EloCategoryPlan",
    "EloRubricBand",
    "LearnerProfile",
    "LearnerProfileStore",
    "SequencedWorkItem",
    "OnboardingAssessment",
    "MemoryRecord",
    "profile_store",
]
