"""Learner profile models and persistence helpers."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Literal, Optional, Set, Tuple

from pydantic import BaseModel, Field, model_validator, ValidationInfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .assessment_result import AssessmentGradingResult
from .cache import schedule_cache
from .config import get_settings
from .db.session import session_scope

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_VECTOR_STORE_ID = "vs_68e81d741f388191acdaabce2f92b7d5"
MAX_MEMORY_RECORDS = 150
MAX_MILESTONE_COMPLETIONS = 100


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


class MilestonePrerequisite(BaseModel):
    """Requirement that must be satisfied before unlocking a milestone."""

    item_id: str
    title: str
    kind: Literal["lesson", "quiz", "milestone"]
    status: Literal["pending", "in_progress", "completed"] = "pending"
    required: bool = Field(default=True)
    recommended_day_offset: Optional[int] = None


class MilestoneProject(BaseModel):
    """Goal-aligned milestone project definition (Phase 30)."""

    project_id: str
    title: str
    goal_alignment: str
    summary: Optional[str] = None
    deliverables: List[str] = Field(default_factory=list)
    evidence_checklist: List[str] = Field(default_factory=list)
    recommended_tools: List[str] = Field(default_factory=list)
    evaluation_focus: List[str] = Field(default_factory=list)
    evaluation_steps: List[str] = Field(default_factory=list)


class MilestoneRequirement(BaseModel):
    """Rating requirement that must be satisfied before unlocking a milestone."""

    category_key: str
    category_label: str
    minimum_rating: int = Field(default=1200, ge=0)
    rationale: Optional[str] = None
    current_rating: int = Field(default=0, ge=0)
    progress_percent: float = Field(default=0.0, ge=0.0, le=1.0)
    last_met_at: Optional[datetime] = None


class MilestoneQueueEntry(BaseModel):
    """Aggregated milestone entry rendered in the dedicated dashboard queue."""

    item_id: str
    title: str
    summary: Optional[str] = None
    category_key: str
    readiness_state: Literal["locked", "ready", "in_progress", "completed"] = "locked"
    badges: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    launch_locked_reason: Optional[str] = None
    last_updated_at: Optional[datetime] = None
    requirements: List[MilestoneRequirement] = Field(default_factory=list)


class MilestoneBrief(BaseModel):
    """Structured milestone brief rendered in-app (Phase 27)."""

    headline: str
    summary: Optional[str] = None
    objectives: List[str] = Field(default_factory=list)
    deliverables: List[str] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)
    external_work: List[str] = Field(default_factory=list)
    capture_prompts: List[str] = Field(default_factory=list)
    prerequisites: List[MilestonePrerequisite] = Field(default_factory=list)
    elo_focus: List[str] = Field(default_factory=list)
    resources: List[str] = Field(default_factory=list)
    kickoff_steps: List[str] = Field(default_factory=list)
    coaching_prompts: List[str] = Field(default_factory=list)
    project: Optional[MilestoneProject] = None
    requirements: List[MilestoneRequirement] = Field(default_factory=list)
    rationale: Optional[str] = None
    authored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    authored_by_model: Optional[str] = None
    reasoning_effort: Optional[str] = None
    source: Literal["agent", "template"] = "template"
    warnings: List[str] = Field(default_factory=list)
    advisor_version: Optional[str] = None
    advisor_warnings: List[str] = Field(default_factory=list)


class MilestoneProgress(BaseModel):
    """Learner-provided milestone progress snapshot."""

    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None
    external_links: List[str] = Field(default_factory=list)
    attachment_ids: List[str] = Field(default_factory=list)
    project_status: Literal["not_started", "building", "ready_for_review", "blocked", "completed"] = "not_started"
    next_steps: List[str] = Field(default_factory=list)


class MilestoneGuidance(BaseModel):
    """Dynamic milestone guidance generated for UI surfaces (Phase 29)."""

    state: Literal["locked", "ready", "in_progress", "awaiting_submission", "completed"] = "locked"
    summary: str
    badges: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    last_update_at: Optional[datetime] = None


class MilestoneCompletion(BaseModel):
    """Historical record capturing milestone completion details (Phase 28)."""

    completion_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    item_id: str
    category_key: str
    title: str
    headline: Optional[str] = None
    summary: Optional[str] = None
    notes: Optional[str] = None
    external_links: List[str] = Field(default_factory=list)
    attachment_ids: List[str] = Field(default_factory=list)
    elo_focus: List[str] = Field(default_factory=list)
    recommended_day_offset: Optional[int] = None
    session_id: Optional[str] = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    project_status: Literal["not_started", "building", "ready_for_review", "blocked", "completed"] = "completed"
    evaluation_outcome: Optional[Literal["passed", "needs_revision", "failed"]] = None
    evaluation_notes: Optional[str] = None
    elo_delta: int = 12

    @model_validator(mode="before")
    def _normalize_project_status(cls, data: dict[str, Any]) -> dict[str, Any]:
        if isinstance(data, dict):
            status = data.get("project_status")
            outcome = data.get("evaluation_outcome")
            if outcome == "needs_revision" and status in {None, "", "completed"}:
                data["project_status"] = "ready_for_review"
            elif outcome == "failed" and status in {None, "", "completed"}:
                data["project_status"] = "blocked"
        return data


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
    launch_status: Literal["pending", "in_progress", "completed"] = "pending"
    last_launched_at: Optional[datetime] = None
    last_completed_at: Optional[datetime] = None
    active_session_id: Optional[str] = None
    milestone_brief: Optional[MilestoneBrief] = None
    milestone_progress: Optional[MilestoneProgress] = None
    milestone_project: Optional[MilestoneProject] = None
    milestone_requirements: List[MilestoneRequirement] = Field(default_factory=list)
    requirement_advisor_version: Optional[str] = None
    requirement_progress_snapshot: List[MilestoneRequirement] = Field(default_factory=list)
    unlock_notified_at: Optional[datetime] = None


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


class ScheduleSliceMetadata(BaseModel):
    """Metadata describing a paginated slice of the curriculum schedule."""

    start_day: int = Field(ge=0)
    end_day: int = Field(ge=0)
    day_span: int = Field(ge=1)
    total_items: int = Field(ge=0)
    total_days: int = Field(ge=0)
    has_more: bool = False
    next_start_day: Optional[int] = Field(default=None, ge=0)


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
    slice: Optional[ScheduleSliceMetadata] = None
    milestone_queue: List[MilestoneQueueEntry] = Field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_username(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("Username cannot be empty.")
    return normalized


def _normalise_timezone(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
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


def _strip_schedule_slice(schedule: CurriculumSchedule) -> CurriculumSchedule:
    clone = schedule.model_copy(deep=True)
    clone.slice = None
    return clone


def slice_schedule(
    schedule: CurriculumSchedule,
    start_day: Optional[int] = None,
    day_span: Optional[int] = None,
) -> CurriculumSchedule:
    """Return a copy of the schedule filtered to the requested day window."""
    if start_day is None and day_span is None:
        return _strip_schedule_slice(schedule)

    start = max(int(start_day) if start_day is not None else 0, 0)
    total_days = max(schedule.time_horizon_days, 1)
    span = max(int(day_span) if day_span is not None else total_days - start, 1)
    limit = start + span

    clone = schedule.model_copy(deep=True)
    full_items = sorted(clone.items, key=lambda item: item.recommended_day_offset)
    filtered: List[SequencedWorkItem] = [
        item for item in full_items if start <= item.recommended_day_offset < limit
    ]

    if filtered:
        end_day = max(item.recommended_day_offset for item in filtered)
    else:
        end_day = start

    has_more = any(item.recommended_day_offset >= limit for item in full_items)
    next_start = limit if has_more else None

    clone.items = filtered
    clone.slice = ScheduleSliceMetadata(
        start_day=start,
        end_day=end_day,
        day_span=span,
        total_items=len(full_items),
        total_days=total_days,
        has_more=has_more,
        next_start_day=next_start,
    )
    return clone


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
    milestone_completions: List[MilestoneCompletion] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=_now)


class _DatabaseLearnerProfileStore:
    """Database-backed persistence layer mirroring the legacy store API."""

    @staticmethod
    def _clone(profile: LearnerProfile) -> LearnerProfile:
        copy = profile.model_copy(deep=True)
        if copy.curriculum_schedule:
            copy.curriculum_schedule.slice = None
        return copy

    def get(self, username: str) -> Optional[LearnerProfile]:
        with session_scope(commit=False) as session:
            profile = _repo().get(session, username)
            return self._clone(profile) if profile else None

    def upsert(self, profile: LearnerProfile) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().upsert(session, profile)
            return self._clone(stored)

    def apply_metadata(self, username: str, metadata: Dict[str, Any]) -> LearnerProfile:
        payload = dict(metadata)
        tz_value = payload.get("timezone")
        if isinstance(tz_value, str):
            normalized = _normalise_timezone(tz_value)
            if normalized:
                payload["timezone"] = normalized
            else:
                payload.pop("timezone", None)
        with session_scope() as session:
            stored = _repo().apply_metadata(session, username, payload)
            return self._clone(stored)

    def append_memory(self, username: str, note_id: str, note: str, tags: Iterable[str]) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().append_memory(session, username, note_id, note, tags)
            return self._clone(stored)

    def set_elo_category_plan(self, username: str, plan: EloCategoryPlan) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().set_elo_category_plan(session, username, plan)
            return self._clone(stored)

    def set_curriculum_and_assessment(
        self,
        username: str,
        curriculum: CurriculumPlan,
        assessment: OnboardingAssessment,
    ) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().set_curriculum_and_assessment(session, username, curriculum, assessment)
            return self._clone(stored)

    def set_goal_inference(self, username: str, inference: GoalParserInference) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().set_goal_inference(session, username, inference)
            return self._clone(stored)

    def set_curriculum_schedule(
        self,
        username: str,
        schedule: CurriculumSchedule,
        *,
        adjustments: Optional[Dict[str, int]] = None,
    ) -> LearnerProfile:
        prepared = schedule.model_copy(deep=True)
        resolved_tz = prepared.timezone or self._extract_timezone(username)
        prepared.timezone = _normalise_timezone(resolved_tz) or "UTC"
        prepared.slice = None
        with session_scope() as session:
            stored = _repo().set_curriculum_schedule(
                session,
                username,
                prepared,
                adjustments=adjustments,
            )
            return self._clone(stored)

    def update_schedule_item(
        self,
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
        with session_scope() as session:
            stored = _repo().update_schedule_item(
                session,
                username,
                item_id,
                status=status,
                last_launched_at=last_launched_at,
                last_completed_at=last_completed_at,
                active_session_id=active_session_id,
                clear_active_session=clear_active_session,
                milestone_progress=milestone_progress,
            )
            return self._clone(stored)

    def record_milestone_completion(self, username: str, completion: MilestoneCompletion) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().record_milestone_completion(session, username, completion)
            return self._clone(stored)

    def apply_schedule_adjustment(self, username: str, item_id: str, target_offset: int) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().apply_schedule_adjustment(session, username, item_id, target_offset)
            return self._clone(stored)

    def update_schedule_adjustments(self, username: str, adjustments: Dict[str, int]) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().update_schedule_adjustments(session, username, adjustments)
            return self._clone(stored)

    def recent_telemetry_events(self, username: str, limit: int = 50):
        with session_scope(commit=False) as session:
            return _repo().recent_telemetry_events(session, username, limit=limit)

    def apply_assessment_result(
        self,
        username: str,
        result: AssessmentGradingResult,
        elo_snapshot: Dict[str, int],
    ) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().apply_assessment_result(session, username, result, elo_snapshot)
            return self._clone(stored)

    def update_assessment_status(self, username: str, status: str) -> LearnerProfile:
        with session_scope() as session:
            stored = _repo().update_assessment_status(session, username, status)
            return self._clone(stored)

    def delete(self, username: str) -> bool:
        with session_scope() as session:
            return _repo().delete(session, username)

    def _extract_timezone(self, username: str) -> Optional[str]:
        profile = self.get(username)
        return profile.timezone if profile else None


class _LegacyLearnerProfileStore:
    """JSON-backed legacy persistence used for rollback and offline modes."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or DATA_DIR / "learner_profiles.json"
        self._lock = threading.RLock()

    @staticmethod
    def _clone(profile: LearnerProfile) -> LearnerProfile:
        copy = profile.model_copy(deep=True)
        if copy.curriculum_schedule:
            copy.curriculum_schedule.slice = None
        return copy

    def _load_unlocked(self) -> Dict[str, LearnerProfile]:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        profiles: Dict[str, LearnerProfile] = {}
        for key, payload in raw.items():
            try:
                profiles[key] = LearnerProfile.model_validate(payload)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to parse legacy learner profile %s", key)
        return profiles

    def _write_unlocked(self, profiles: Dict[str, LearnerProfile]) -> None:
        payload = {
            username: self._prepare_for_storage(profile)
            for username, profile in profiles.items()
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    @staticmethod
    def _prepare_for_storage(profile: LearnerProfile) -> Dict[str, Any]:
        clone = profile.model_copy(deep=True)
        clone.username = _normalize_username(clone.username)
        if clone.curriculum_schedule:
            clone.curriculum_schedule.slice = None
        return clone.model_dump(mode="json")

    @staticmethod
    def _touch(profile: LearnerProfile) -> None:
        profile.last_updated = _now()

    def _ensure_profile(
        self,
        profiles: Dict[str, LearnerProfile],
        username: str,
        *,
        create: bool,
    ) -> tuple[LearnerProfile, bool]:
        normalized = _normalize_username(username)
        profile = profiles.get(normalized)
        created = False
        if profile is None:
            if not create:
                raise LookupError(f"Learner profile for '{username}' was not found.")
            profile = LearnerProfile(username=normalized)
            profiles[normalized] = profile
            created = True
        return profile, created

    def get(self, username: str) -> Optional[LearnerProfile]:
        normalized = _normalize_username(username)
        with self._lock:
            profiles = self._load_unlocked()
            profile = profiles.get(normalized)
            return self._clone(profile) if profile else None

    def upsert(self, profile: LearnerProfile) -> LearnerProfile:
        clone = profile.model_copy(deep=True)
        clone.username = _normalize_username(clone.username)
        if clone.curriculum_schedule:
            clone.curriculum_schedule.slice = None
        with self._lock:
            profiles = self._load_unlocked()
            self._touch(clone)
            profiles[clone.username] = clone
            self._write_unlocked(profiles)
        return self._clone(clone)

    def apply_metadata(self, username: str, metadata: Dict[str, Any]) -> LearnerProfile:
        with self._lock:
            profiles = self._load_unlocked()
            profile, created = self._ensure_profile(profiles, username, create=True)
            updated = created

            def _maybe_update(field: str) -> None:
                nonlocal updated
                value = metadata.get(field)
                if isinstance(value, str):
                    trimmed = value.strip()
                    if trimmed and getattr(profile, field) != trimmed:
                        setattr(profile, field, trimmed)
                        updated = True

            _maybe_update("goal")
            _maybe_update("use_case")
            _maybe_update("strengths")

            tz_value = metadata.get("timezone")
            if isinstance(tz_value, str):
                normalized_tz = _normalise_timezone(tz_value)
                if normalized_tz and profile.timezone != normalized_tz:
                    profile.timezone = normalized_tz
                    updated = True

            tags_payload = metadata.get("knowledge_tags")
            if isinstance(tags_payload, Iterable) and not isinstance(tags_payload, (str, bytes)):
                combined = {tag.lower(): tag for tag in profile.knowledge_tags}
                for tag in tags_payload:
                    if isinstance(tag, str) and tag.strip():
                        combined[tag.strip().lower()] = tag.strip()
                new_tags = list(combined.values())
                if new_tags != profile.knowledge_tags:
                    profile.knowledge_tags = new_tags
                    updated = True

            session_id = metadata.get("session_id")
            if isinstance(session_id, str) and session_id:
                sessions = list(profile.recent_sessions)
                if session_id not in sessions:
                    sessions.append(session_id)
                    profile.recent_sessions = sessions[-10:]
                    updated = True

            elo_payload = metadata.get("elo")
            if isinstance(elo_payload, dict):
                snapshot = dict(profile.elo_snapshot)
                mutated = False
                for key, value in elo_payload.items():
                    if isinstance(key, str) and isinstance(value, (int, float)):
                        snapshot[key] = int(value)
                        mutated = True
                if mutated:
                    profile.elo_snapshot = snapshot
                    updated = True

            if updated:
                self._touch(profile)
                self._write_unlocked(profiles)
            return self._clone(profile)

    def append_memory(self, username: str, note_id: str, note: str, tags: Iterable[str]) -> LearnerProfile:
        with self._lock:
            profiles = self._load_unlocked()
            profile, _ = self._ensure_profile(profiles, username, create=True)
            record = MemoryRecord(
                note_id=note_id,
                note=note,
                tags=[tag.strip() for tag in tags if tag and tag.strip()],
                created_at=_now(),
            )
            records = list(profile.memory_records)
            records.append(record)
            profile.memory_records = records[-MAX_MEMORY_RECORDS:]
            self._touch(profile)
            self._write_unlocked(profiles)
            return self._clone(profile)

    def update_schedule_item(
        self,
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
        with self._lock:
            profiles = self._load_unlocked()
            profile, _ = self._ensure_profile(profiles, username, create=False)
            schedule = profile.curriculum_schedule
            if schedule is None:
                raise LookupError(f"No curriculum schedule configured for '{username}'.")
            matching = next((item for item in schedule.items if item.item_id == item_id), None)
            if matching is None:
                raise LookupError(f"Schedule item '{item_id}' not found for '{username}'.")
            if status:
                matching.launch_status = status
            if last_launched_at is not None:
                matching.last_launched_at = last_launched_at
            if last_completed_at is not None:
                matching.last_completed_at = last_completed_at
            if clear_active_session:
                matching.active_session_id = None
            elif active_session_id is not None:
                matching.active_session_id = active_session_id
            if milestone_progress is not None:
                matching.milestone_progress = milestone_progress.model_copy(deep=True)
            elif status and status != "completed" and matching.kind == "milestone":
                matching.milestone_progress = None
            self._touch(profile)
            self._write_unlocked(profiles)
            return self._clone(profile)

    def record_milestone_completion(self, username: str, completion: MilestoneCompletion) -> LearnerProfile:
        clone = completion.model_copy(deep=True)
        with self._lock:
            profiles = self._load_unlocked()
            profile, _ = self._ensure_profile(profiles, username, create=True)
            history = list(profile.milestone_completions or [])
            for index, existing in enumerate(history):
                if existing.item_id == clone.item_id:
                    history[index] = clone
                    break
            else:
                history.insert(0, clone)
            profile.milestone_completions = history[:MAX_MILESTONE_COMPLETIONS]
            snapshot = dict(profile.elo_snapshot or {})
            focus = list(clone.elo_focus or []) or [clone.category_key]
            elo_delta = int(getattr(clone, "elo_delta", 12))
            for key in focus:
                if isinstance(key, str) and key:
                    snapshot[key] = max(int(snapshot.get(key, 1100)) + elo_delta, 0)
            profile.elo_snapshot = snapshot
            self._touch(profile)
            self._write_unlocked(profiles)
            return self._clone(profile)

    def set_elo_category_plan(self, username: str, plan: EloCategoryPlan) -> LearnerProfile:
        with self._lock:
            profiles = self._load_unlocked()
            profile, _ = self._ensure_profile(profiles, username, create=True)
            profile.elo_category_plan = plan.model_copy(deep=True)
            snapshot = dict(profile.elo_snapshot)
            for category in plan.categories:
                snapshot.setdefault(category.key, int(category.starting_rating))
            profile.elo_snapshot = snapshot
            self._touch(profile)
            self._write_unlocked(profiles)
            return self._clone(profile)

    def set_curriculum_and_assessment(
        self,
        username: str,
        curriculum: CurriculumPlan,
        assessment: OnboardingAssessment,
    ) -> LearnerProfile:
        with self._lock:
            profiles = self._load_unlocked()
            profile, _ = self._ensure_profile(profiles, username, create=True)
            profile.curriculum_plan = curriculum.model_copy(deep=True)
            profile.onboarding_assessment = assessment.model_copy(deep=True)
            profile.schedule_adjustments = {}
            profile.curriculum_schedule = None
            self._touch(profile)
            self._write_unlocked(profiles)
            return self._clone(profile)

    def set_goal_inference(self, username: str, inference: GoalParserInference) -> LearnerProfile:
        with self._lock:
            profiles = self._load_unlocked()
            profile, _ = self._ensure_profile(profiles, username, create=True)
            profile.goal_inference = inference.model_copy(deep=True)
            profile.foundation_tracks = [track.model_copy(deep=True) for track in inference.tracks]
            self._touch(profile)
            self._write_unlocked(profiles)
            return self._clone(profile)

    def set_curriculum_schedule(
        self,
        username: str,
        schedule: CurriculumSchedule,
        *,
        adjustments: Optional[Dict[str, int]] = None,
    ) -> LearnerProfile:
        with self._lock:
            profiles = self._load_unlocked()
            profile, _ = self._ensure_profile(profiles, username, create=False)
            prepared = schedule.model_copy(deep=True)
            prepared.slice = None
            if prepared.timezone:
                profile.timezone = prepared.timezone
            profile.curriculum_schedule = prepared
            if adjustments is not None:
                profile.schedule_adjustments = {
                    item_id: max(int(offset), 0)
                    for item_id, offset in adjustments.items()
                    if isinstance(item_id, str)
                }
            else:
                allowed = {item.item_id for item in prepared.items}
                profile.schedule_adjustments = {
                    item_id: offset
                    for item_id, offset in profile.schedule_adjustments.items()
                    if item_id in allowed
                }
            self._touch(profile)
            self._write_unlocked(profiles)
            return self._clone(profile)

    def apply_schedule_adjustment(self, username: str, item_id: str, target_offset: int) -> LearnerProfile:
        if not item_id:
            raise ValueError("Schedule item id cannot be empty.")
        with self._lock:
            profiles = self._load_unlocked()
            profile, _ = self._ensure_profile(profiles, username, create=False)
            adjustments = dict(profile.schedule_adjustments)
            adjustments[item_id] = max(int(target_offset), 0)
            profile.schedule_adjustments = adjustments
            self._touch(profile)
            self._write_unlocked(profiles)
            return self._clone(profile)

    def update_schedule_adjustments(self, username: str, adjustments: Dict[str, int]) -> LearnerProfile:
        with self._lock:
            profiles = self._load_unlocked()
            profile, _ = self._ensure_profile(profiles, username, create=False)
            profile.schedule_adjustments = {
                item_id: max(int(offset), 0)
                for item_id, offset in adjustments.items()
                if isinstance(item_id, str)
            }
            self._touch(profile)
            self._write_unlocked(profiles)
            return self._clone(profile)

    def recent_telemetry_events(self, username: str, limit: int = 50):
        return []

    def apply_assessment_result(
        self,
        username: str,
        result: AssessmentGradingResult,
        elo_snapshot: Dict[str, int],
    ) -> LearnerProfile:
        with self._lock:
            profiles = self._load_unlocked()
            profile, _ = self._ensure_profile(profiles, username, create=False)
            profile.onboarding_assessment_result = result.model_copy(deep=True)
            if profile.onboarding_assessment is not None:
                assessment = profile.onboarding_assessment.model_copy(deep=True)
                assessment.status = "completed"
                profile.onboarding_assessment = assessment

            if elo_snapshot:
                snapshot = dict(profile.elo_snapshot)
                for key, value in elo_snapshot.items():
                    if isinstance(key, str) and isinstance(value, (int, float)):
                        snapshot[key] = max(int(value), 0)
                profile.elo_snapshot = snapshot

            if profile.curriculum_plan:
                curriculum = profile.curriculum_plan.model_copy(deep=True)
                plan_categories = list(profile.elo_category_plan.categories) if profile.elo_category_plan else []
                goal_inference = profile.goal_inference.model_copy(deep=True) if profile.goal_inference else None
                from .curriculum_foundations import ensure_foundational_curriculum
                augmented_categories, augmented_curriculum = ensure_foundational_curriculum(
                    goal=profile.goal,
                    plan=curriculum,
                    categories=plan_categories,
                    assessment_result=result,
                    goal_inference=goal_inference,
                )
                if profile.elo_category_plan:
                    plan = profile.elo_category_plan.model_copy(deep=True)
                    plan.categories = augmented_categories
                    profile.elo_category_plan = plan
                else:
                    profile.elo_category_plan = EloCategoryPlan(categories=augmented_categories)
                profile.curriculum_plan = augmented_curriculum
                snapshot = dict(profile.elo_snapshot)
                for category in profile.elo_category_plan.categories:
                    snapshot.setdefault(category.key, int(category.starting_rating))
                profile.elo_snapshot = snapshot

            self._touch(profile)
            self._write_unlocked(profiles)
            return self._clone(profile)

    def update_assessment_status(self, username: str, status: str) -> LearnerProfile:
        if status not in {"pending", "in_progress", "completed"}:
            raise ValueError(f"Unsupported onboarding assessment status: {status}")
        with self._lock:
            profiles = self._load_unlocked()
            profile, _ = self._ensure_profile(profiles, username, create=False)
            if profile.onboarding_assessment is None:
                raise LookupError(f"Assessment for '{username}' has not been generated.")
            assessment = profile.onboarding_assessment.model_copy(deep=True)
            assessment.status = status
            profile.onboarding_assessment = assessment
            self._touch(profile)
            self._write_unlocked(profiles)
            return self._clone(profile)

    def delete(self, username: str) -> bool:
        normalized = _normalize_username(username)
        with self._lock:
            profiles = self._load_unlocked()
            if normalized not in profiles:
                return False
            profiles.pop(normalized, None)
            self._write_unlocked(profiles)
        return True


def _normalise_category_key_local(key: str, label: str) -> str:
    candidate = key.strip() if isinstance(key, str) else ""
    if not candidate and isinstance(label, str):
        candidate = label
    slug_chars: List[str] = []
    for char in candidate:
        if char.isalnum():
            slug_chars.append(char.lower())
        elif char in {" ", "-", "_", "/"}:
            slug_chars.append("-")
    slug = "".join(slug_chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "category-1"


def _merge_focus_areas(existing: List[str], incoming: List[str]) -> List[str]:
    merged: Dict[str, None] = {}
    for value in existing + incoming:
        trimmed = value.strip()
        if trimmed and trimmed not in merged:
            merged[trimmed] = None
    return list(merged.keys())


def _merge_rubric(existing: List[EloRubricBand], incoming: List[EloRubricBand]) -> List[EloRubricBand]:
    merged: Dict[str, EloRubricBand] = {entry.level.lower(): entry for entry in existing}
    for entry in incoming:
        key = entry.level.lower()
        if key not in merged or not merged[key].descriptor:
            merged[key] = entry
    return list(merged.values())


def _merge_category_definitions(
    primary: EloCategoryDefinition,
    secondary: EloCategoryDefinition,
) -> EloCategoryDefinition:
    label = primary.label or secondary.label
    description = primary.description or secondary.description
    focus = _merge_focus_areas(primary.focus_areas, secondary.focus_areas)
    rubric = _merge_rubric(primary.rubric, secondary.rubric)
    weight = max(primary.weight, secondary.weight, 0.0)
    starting_rating = max(primary.starting_rating, secondary.starting_rating, 0)
    return primary.model_copy(
        update={
            "label": label or primary.key.replace("-", " ").title(),
            "description": description,
            "focus_areas": focus,
            "rubric": rubric,
            "weight": weight,
            "starting_rating": starting_rating,
        }
    )


def _sanitize_category_definition(entry: EloCategoryDefinition) -> EloCategoryDefinition:
    return entry.model_copy(
        update={
            "key": _normalise_category_key_local(entry.key, entry.label),
            "label": entry.label.strip() if isinstance(entry.label, str) else entry.key.replace("-", " ").title(),
            "description": entry.description.strip() if isinstance(entry.description, str) else "",
            "focus_areas": [focus.strip() for focus in entry.focus_areas if focus.strip()],
            "weight": max(entry.weight, 0.0),
            "rubric": [
                EloRubricBand(level=band.level.strip(), descriptor=band.descriptor.strip())
                for band in entry.rubric
                if isinstance(band.level, str) and band.level.strip()
            ],
            "starting_rating": max(int(entry.starting_rating), 0),
        }
    )


def _dedupe_elo_plan(plan: EloCategoryPlan) -> Tuple[EloCategoryPlan, bool]:
    mutated = False
    categories: Dict[str, EloCategoryDefinition] = {}
    order: List[str] = []
    for entry in plan.categories:
        sanitized = _sanitize_category_definition(entry)
        key = sanitized.key
        if sanitized != entry:
            mutated = True
        if key in categories:
            categories[key] = _merge_category_definitions(categories[key], sanitized)
            mutated = True
        else:
            categories[key] = sanitized
            order.append(key)
    merged = [categories[key] for key in order]
    if len(merged) != len(plan.categories):
        mutated = True
    if not mutated:
        return plan, False
    return plan.model_copy(update={"categories": merged}), True


def _dedupe_foundation_tracks(tracks: List[FoundationTrack]) -> Tuple[List[FoundationTrack], bool]:
    seen: Dict[str, FoundationTrack] = {}
    order: List[str] = []
    changed = False
    for track in tracks:
        key = track.label.strip().lower()
        if key in seen:
            changed = True
            continue
        seen[key] = track
        order.append(key)
    return [seen[key] for key in order], changed


class LearnerProfileStore:
    """Facade that delegates to database or legacy persistence based on configuration."""

    def __init__(self, legacy_path: Path | None = None) -> None:
        settings = get_settings()
        self._mode = settings.arcadia_persistence_mode
        self._db_store = _DatabaseLearnerProfileStore()
        self._legacy_store = _LegacyLearnerProfileStore(path=legacy_path)
        self._pending_resync: Set[str] = set()

    def _call(self, method: str, *args, **kwargs):
        username = self._extract_username(args)
        if self._mode == "hybrid" and username is not None:
            self._try_resync(username)
        if self._mode == "legacy":
            store = self._legacy_store
            return getattr(store, method)(*args, **kwargs)
        try:
            store = self._db_store
            return getattr(store, method)(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            if self._mode == "hybrid":
                logger.warning(
                    "Database persistence error during %s; falling back to legacy store: %s",
                    method,
                    exc,
                )
                self._mark_for_resync(username)
                return getattr(self._legacy_store, method)(*args, **kwargs)
            raise

    def _sync_cache(self, username: str, profile: Optional[LearnerProfile]) -> None:
        if profile and profile.curriculum_schedule:
            schedule_cache.set(username, profile.curriculum_schedule)
        else:
            schedule_cache.invalidate(username)

    def _extract_username(self, args: Tuple[Any, ...]) -> Optional[str]:
        if not args:
            return None
        candidate = args[0]
        if isinstance(candidate, LearnerProfile):
            return candidate.username
        if isinstance(candidate, str):
            return candidate
        return None

    def _mark_for_resync(self, username: Optional[str]) -> None:
        if username is None:
            return
        try:
            normalized = _normalize_username(username)
        except ValueError:
            return
        self._pending_resync.add(normalized)

    def _try_resync(self, username: str) -> None:
        try:
            normalized = _normalize_username(username)
        except ValueError:
            return
        if normalized not in self._pending_resync:
            return
        self._resync_from_legacy(username, normalized)

    def _resync_from_legacy(self, username: str, normalized: str) -> None:
        legacy_profile = self._legacy_store.get(username)
        if legacy_profile is None:
            try:
                self._db_store.delete(username)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to remove database profile for %s during resync: %s", username, exc)
                return
            self._pending_resync.discard(normalized)
            schedule_cache.invalidate(username)
            return
        try:
            self._db_store.upsert(legacy_profile)
            if legacy_profile.curriculum_schedule:
                self._db_store.set_curriculum_schedule(
                    username,
                    legacy_profile.curriculum_schedule,
                    adjustments=legacy_profile.schedule_adjustments,
                )
            if legacy_profile.elo_category_plan:
                self._db_store.set_elo_category_plan(username, legacy_profile.elo_category_plan)
            if legacy_profile.goal_inference:
                self._db_store.set_goal_inference(username, legacy_profile.goal_inference)
            for completion in getattr(legacy_profile, "milestone_completions", []) or []:
                self._db_store.record_milestone_completion(username, completion)
            self._pending_resync.discard(normalized)
            self._sync_cache(username, legacy_profile)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to resync legacy profile for %s: %s", username, exc)

    def get(self, username: str) -> Optional[LearnerProfile]:
        profile = self._call("get", username)
        if profile is not None:
            profile = self._sanitize_profile(username, profile)
        self._sync_cache(username, profile)
        return profile

    def upsert(self, profile: LearnerProfile) -> LearnerProfile:
        stored = self._call("upsert", profile)
        self._sync_cache(profile.username, stored)
        return stored

    def apply_metadata(self, username: str, metadata: Dict[str, Any]) -> LearnerProfile:
        stored = self._call("apply_metadata", username, metadata)
        self._sync_cache(username, stored)
        return stored

    def append_memory(self, username: str, note_id: str, note: str, tags: Iterable[str]) -> LearnerProfile:
        stored = self._call("append_memory", username, note_id, note, tags)
        self._sync_cache(username, stored)
        return stored

    def set_elo_category_plan(self, username: str, plan: EloCategoryPlan) -> LearnerProfile:
        normalized_plan, _ = _dedupe_elo_plan(plan)
        stored = self._call("set_elo_category_plan", username, normalized_plan)
        self._sync_cache(username, stored)
        return stored

    def set_curriculum_and_assessment(
        self,
        username: str,
        curriculum: CurriculumPlan,
        assessment: OnboardingAssessment,
    ) -> LearnerProfile:
        stored = self._call("set_curriculum_and_assessment", username, curriculum, assessment)
        self._sync_cache(username, stored)
        return stored

    def set_goal_inference(self, username: str, inference: GoalParserInference) -> LearnerProfile:
        stored = self._call("set_goal_inference", username, inference)
        self._sync_cache(username, stored)
        return stored

    def set_curriculum_schedule(
        self,
        username: str,
        schedule: CurriculumSchedule,
        *,
        adjustments: Optional[Dict[str, int]] = None,
    ) -> LearnerProfile:
        clone = schedule.model_copy(deep=True)
        resolved_tz = clone.timezone or self._extract_timezone(username)
        clone.timezone = _normalise_timezone(resolved_tz) or "UTC"
        clone.slice = None
        stored = self._call("set_curriculum_schedule", username, clone, adjustments=adjustments)
        self._sync_cache(username, stored)
        return stored

    def update_schedule_item(
        self,
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
        profile = self.get(username)
        if profile is None or profile.curriculum_schedule is None:
            raise LookupError(f"No curriculum schedule configured for '{username}'.")
        schedule = profile.curriculum_schedule
        updated_items: list[SequencedWorkItem] = []
        target_found = False
        for entry in schedule.items:
            if entry.item_id != item_id:
                updated_items.append(entry)
                continue
            target_found = True
            updates: dict[str, Any] = {}
            if status:
                updates["launch_status"] = status
            if last_launched_at is not None:
                updates["last_launched_at"] = last_launched_at
            if last_completed_at is not None:
                updates["last_completed_at"] = last_completed_at
            if clear_active_session:
                updates["active_session_id"] = None
            elif active_session_id is not None:
                updates["active_session_id"] = active_session_id
            if milestone_progress is not None:
                updates["milestone_progress"] = milestone_progress.model_copy(deep=True)
            elif status and status != "completed" and entry.kind == "milestone":
                updates["milestone_progress"] = None
            updated_items.append(entry.model_copy(update=updates, deep=True))
        if not target_found:
            raise LookupError(f"Schedule item '{item_id}' not found for '{username}'.")

        updated_schedule = schedule.model_copy(update={"items": updated_items}, deep=True)
        stored = self._call(
            "set_curriculum_schedule",
            username,
            updated_schedule,
            adjustments=profile.schedule_adjustments,
        )
        self._sync_cache(username, stored)
        return stored

    def record_milestone_completion(self, username: str, completion: MilestoneCompletion) -> LearnerProfile:
        stored = self._call("record_milestone_completion", username, completion)
        self._sync_cache(username, stored)
        return stored

    def apply_schedule_adjustment(self, username: str, item_id: str, target_offset: int) -> LearnerProfile:
        stored = self._call("apply_schedule_adjustment", username, item_id, target_offset)
        self._sync_cache(username, stored)
        return stored

    def update_schedule_adjustments(self, username: str, adjustments: Dict[str, int]) -> LearnerProfile:
        stored = self._call("update_schedule_adjustments", username, adjustments)
        self._sync_cache(username, stored)
        return stored

    def recent_telemetry_events(self, username: str, limit: int = 50):
        return self._call("recent_telemetry_events", username, limit=limit)

    def apply_assessment_result(
        self,
        username: str,
        result: AssessmentGradingResult,
        elo_snapshot: Dict[str, int],
    ) -> LearnerProfile:
        stored = self._call("apply_assessment_result", username, result, elo_snapshot)
        self._sync_cache(username, stored)
        return stored

    def update_assessment_status(self, username: str, status: str) -> LearnerProfile:
        stored = self._call("update_assessment_status", username, status)
        self._sync_cache(username, stored)
        return stored

    def delete(self, username: str) -> bool:
        deleted = self._call("delete", username)
        if deleted:
            schedule_cache.invalidate(username)
            try:
                self._pending_resync.discard(_normalize_username(username))
            except ValueError:
                pass
        return deleted

    def _sanitize_profile(self, username: str, profile: LearnerProfile) -> LearnerProfile:
        sanitized = profile
        if profile.elo_category_plan and profile.elo_category_plan.categories:
            normalized_plan, changed = _dedupe_elo_plan(profile.elo_category_plan)
            if changed:
                try:
                    sanitized = self._call("set_elo_category_plan", username, normalized_plan)
                    profile = sanitized
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to persist sanitized ELO plan for %s", username)
        tracks = getattr(profile, "foundation_tracks", []) or []
        if tracks:
            deduped_tracks, changed = _dedupe_foundation_tracks(tracks)
            if changed:
                if profile.goal_inference:
                    inference = profile.goal_inference.model_copy(update={"tracks": deduped_tracks})
                    try:
                        sanitized = self._call("set_goal_inference", username, inference)
                        profile = sanitized
                    except Exception:  # noqa: BLE001
                        logger.exception("Failed to persist sanitized goal inference for %s", username)
                else:
                    sanitized = profile.model_copy(update={"foundation_tracks": deduped_tracks})
        return sanitized

    def _extract_timezone(self, username: str) -> Optional[str]:
        if self._mode == "legacy":
            profile = self._legacy_store.get(username)
        elif self._mode == "hybrid":
            try:
                profile = self._db_store.get(username)
            except Exception:  # noqa: BLE001
                profile = self._legacy_store.get(username)
        else:
            profile = self._db_store.get(username)
        return profile.timezone if profile else None


profile_store = LearnerProfileStore()

__all__ = [
    "AssessmentGradingResult",
    "AssessmentTask",
    "CurriculumModule",
    "CurriculumPlan",
    "CurriculumSchedule",
    "ScheduleSliceMetadata",
    "ScheduleWarning",
    "EloCategoryDefinition",
    "EloCategoryPlan",
    "EloRubricBand",
    "MilestonePrerequisite",
    "MilestoneProject",
    "MilestoneGuidance",
    "MilestoneBrief",
    "MilestoneProgress",
    "MilestoneCompletion",
    "LearnerProfile",
    "LearnerProfileStore",
    "slice_schedule",
    "SequencedWorkItem",
    "OnboardingAssessment",
    "MemoryRecord",
    "profile_store",
]
