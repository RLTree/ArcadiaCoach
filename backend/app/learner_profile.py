"""Learner profile models and lightweight persistence."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Literal, Optional

from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .assessment_result import AssessmentGradingResult

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_PATH = DATA_DIR / "learner_profiles.json"

DEFAULT_VECTOR_STORE_ID = "vs_68e81d741f388191acdaabce2f92b7d5"
MAX_MEMORY_RECORDS = 150


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
    """Minimal persistence layer for learner profiles."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = RLock()
        self._profiles: Dict[str, LearnerProfile] = {}
        self._load()

    def get(self, username: str) -> Optional[LearnerProfile]:
        username = username.lower()
        with self._lock:
            profile = self._profiles.get(username)
            return profile.model_copy(deep=True) if profile else None

    def upsert(self, profile: LearnerProfile) -> LearnerProfile:
        normalized = profile.username.lower()
        with self._lock:
            profile.last_updated = datetime.now(timezone.utc)
            self._profiles[normalized] = profile.model_copy(deep=True)
            self._persist_locked()
            return self._profiles[normalized].model_copy(deep=True)

    def apply_metadata(self, username: str, metadata: Dict[str, Any]) -> LearnerProfile:
        normalized = username.lower()
        with self._lock:
            profile = self._profiles.get(normalized)
            if profile is None:
                profile = LearnerProfile(username=username)
            updated = False

            updated |= self._set_if_changed(profile, "goal", metadata.get("goal"))
            updated |= self._set_if_changed(profile, "use_case", metadata.get("use_case"))
            updated |= self._set_if_changed(profile, "strengths", metadata.get("strengths"))

            tags_payload = metadata.get("knowledge_tags")
            if isinstance(tags_payload, Iterable) and not isinstance(tags_payload, (str, bytes)):
                tags = {
                    tag.strip()
                    for tag in tags_payload
                    if isinstance(tag, str) and tag.strip()
                }
                if tags:
                    combined = {tag.lower(): tag for tag in profile.knowledge_tags}
                    for tag in tags:
                        combined[tag.lower()] = tag
                    profile.knowledge_tags = list(combined.values())
                    updated = True

            if session_id := metadata.get("session_id"):
                if isinstance(session_id, str) and session_id not in profile.recent_sessions:
                    profile.recent_sessions = (profile.recent_sessions + [session_id])[-10:]
                    updated = True

            if elo := metadata.get("elo"):
                if isinstance(elo, dict) and elo:
                    incoming = {
                        key: int(value)
                        for key, value in elo.items()
                        if isinstance(key, str) and isinstance(value, (int, float))
                    }
                    if incoming:
                        profile.elo_snapshot.update(incoming)
                        updated = True

            timezone_value = metadata.get("timezone")
            if isinstance(timezone_value, str):
                normalized_tz = self._normalise_timezone(timezone_value)
                if normalized_tz and profile.timezone != normalized_tz:
                    profile.timezone = normalized_tz
                    updated = True

            if updated:
                profile.last_updated = datetime.now(timezone.utc)
                self._profiles[normalized] = profile.model_copy(deep=True)
                self._persist_locked()
            return profile.model_copy(deep=True)

    def append_memory(self, username: str, note_id: str, note: str, tags: Iterable[str]) -> LearnerProfile:
        normalized = username.lower()
        with self._lock:
            profile = self._profiles.get(normalized)
            if profile is None:
                profile = LearnerProfile(username=username)
            record = MemoryRecord(
                note_id=note_id,
                note=note,
                tags=[tag for tag in (tag.strip() for tag in tags) if tag],
            )
            profile.memory_records.append(record)
            if len(profile.memory_records) > MAX_MEMORY_RECORDS:
                profile.memory_records = profile.memory_records[-MAX_MEMORY_RECORDS:]
            profile.last_updated = datetime.now(timezone.utc)
            self._profiles[normalized] = profile.model_copy(deep=True)
            self._persist_locked()
            return profile.model_copy(deep=True)

    def set_elo_category_plan(self, username: str, plan: EloCategoryPlan) -> LearnerProfile:
        normalized = username.lower()
        with self._lock:
            profile = self._profiles.get(normalized)
            if profile is None:
                profile = LearnerProfile(username=username)
            snapshot = profile.elo_snapshot
            updated_snapshot: Dict[str, int] = {}
            for category in plan.categories:
                rating: Optional[int] = None
                if category.key in snapshot:
                    rating = snapshot[category.key]
                else:
                    label_rating = next(
                        (value for key, value in snapshot.items() if key.lower() == category.label.lower()),
                        None,
                    )
                    rating = label_rating
                if rating is None:
                    rating = int(category.starting_rating)
                updated_snapshot[category.key] = int(rating)

            profile.elo_category_plan = plan.model_copy(deep=True)
            profile.elo_snapshot = updated_snapshot
            profile.last_updated = datetime.now(timezone.utc)
            self._profiles[normalized] = profile.model_copy(deep=True)
            self._persist_locked()
            return self._profiles[normalized].model_copy(deep=True)

    def set_curriculum_and_assessment(
        self,
        username: str,
        curriculum: CurriculumPlan,
        assessment: OnboardingAssessment,
    ) -> LearnerProfile:
        normalized = username.lower()
        with self._lock:
            profile = self._profiles.get(normalized)
            if profile is None:
                profile = LearnerProfile(username=username)
            profile.curriculum_plan = curriculum.model_copy(deep=True)
            profile.onboarding_assessment = assessment.model_copy(deep=True)
            profile.curriculum_schedule = None
            profile.schedule_adjustments = {}
            profile.last_updated = datetime.now(timezone.utc)
            self._profiles[normalized] = profile.model_copy(deep=True)
            self._persist_locked()
            return self._profiles[normalized].model_copy(deep=True)

    def set_goal_inference(self, username: str, inference: GoalParserInference) -> LearnerProfile:
        normalized = username.lower()
        with self._lock:
            profile = self._profiles.get(normalized)
            if profile is None:
                profile = LearnerProfile(username=username)
            profile.goal_inference = inference.model_copy(deep=True)
            profile.foundation_tracks = [track.model_copy(deep=True) for track in inference.tracks]
            profile.last_updated = datetime.now(timezone.utc)
            self._profiles[normalized] = profile.model_copy(deep=True)
            self._persist_locked()
            return self._profiles[normalized].model_copy(deep=True)

    def set_curriculum_schedule(
        self,
        username: str,
        schedule: CurriculumSchedule,
        *,
        adjustments: Optional[Dict[str, int]] = None,
    ) -> LearnerProfile:
        normalized = username.lower()
        with self._lock:
            profile = self._profiles.get(normalized)
            if profile is None:
                raise LookupError(f"Learner profile '{username}' does not exist.")
            resolved_tz = schedule.timezone or profile.timezone
            normalised_tz = self._normalise_timezone(resolved_tz) if resolved_tz else None
            if normalised_tz is None:
                normalised_tz = "UTC"
            schedule.timezone = normalised_tz
            if profile.timezone != normalised_tz:
                profile.timezone = normalised_tz
            profile.curriculum_schedule = schedule.model_copy(deep=True)
            if adjustments is not None:
                allowed_ids = {item.item_id for item in schedule.items}
                sanitized = {
                    item_id: max(int(offset), 0)
                    for item_id, offset in adjustments.items()
                    if isinstance(item_id, str) and item_id in allowed_ids
                }
                profile.schedule_adjustments = sanitized
            else:
                allowed_ids = {item.item_id for item in schedule.items}
                profile.schedule_adjustments = {
                    item_id: offset
                    for item_id, offset in profile.schedule_adjustments.items()
                    if item_id in allowed_ids
                }
            profile.last_updated = datetime.now(timezone.utc)
            self._profiles[normalized] = profile.model_copy(deep=True)
            self._persist_locked()
            return self._profiles[normalized].model_copy(deep=True)

    def apply_schedule_adjustment(self, username: str, item_id: str, target_offset: int) -> LearnerProfile:
        normalized = username.lower()
        if not item_id:
            raise ValueError("Schedule item id cannot be empty.")
        with self._lock:
            profile = self._profiles.get(normalized)
            if profile is None:
                raise LookupError(f"Learner profile '{username}' does not exist.")
            adjustments = dict(profile.schedule_adjustments)
            adjustments[item_id] = max(int(target_offset), 0)
            profile.schedule_adjustments = adjustments
            profile.last_updated = datetime.now(timezone.utc)
            self._profiles[normalized] = profile.model_copy(deep=True)
            self._persist_locked()
            return self._profiles[normalized].model_copy(deep=True)

    def update_schedule_adjustments(self, username: str, adjustments: Dict[str, int]) -> LearnerProfile:
        normalized = username.lower()
        with self._lock:
            profile = self._profiles.get(normalized)
            if profile is None:
                raise LookupError(f"Learner profile '{username}' does not exist.")
            sanitized = {
                item_id: max(int(offset), 0)
                for item_id, offset in adjustments.items()
                if isinstance(item_id, str)
            }
            profile.schedule_adjustments = sanitized
            profile.last_updated = datetime.now(timezone.utc)
            self._profiles[normalized] = profile.model_copy(deep=True)
            self._persist_locked()
            return self._profiles[normalized].model_copy(deep=True)

    def apply_assessment_result(
        self,
        username: str,
        result: AssessmentGradingResult,
        elo_snapshot: Dict[str, int],
    ) -> LearnerProfile:
        from .curriculum_foundations import ensure_foundational_curriculum

        normalized = username.lower()
        with self._lock:
            profile = self._profiles.get(normalized)
            if profile is None:
                raise LookupError(f"Learner profile '{username}' does not exist.")
            profile.onboarding_assessment_result = result.model_copy(deep=True)
            if profile.onboarding_assessment is not None:
                profile.onboarding_assessment.status = "completed"  # type: ignore[assignment]
            if elo_snapshot:
                sanitized = {
                    key: max(int(value), 0)
                    for key, value in elo_snapshot.items()
                    if isinstance(key, str)
                }
                if sanitized:
                    profile.elo_snapshot = dict(sanitized)
            if profile.curriculum_plan:
                categories = profile.elo_category_plan.categories if profile.elo_category_plan else []
                augmented_categories, augmented_curriculum = ensure_foundational_curriculum(
                    goal=profile.goal or "",
                    plan=profile.curriculum_plan,
                    categories=categories,
                    assessment_result=result,
                    goal_inference=profile.goal_inference,
                )
                if profile.elo_category_plan:
                    updated_plan = profile.elo_category_plan.model_copy(deep=True)
                    updated_plan.categories = augmented_categories
                    profile.elo_category_plan = updated_plan
                else:
                    profile.elo_category_plan = EloCategoryPlan(categories=augmented_categories)
                profile.curriculum_plan = augmented_curriculum
                for category in augmented_categories:
                    profile.elo_snapshot.setdefault(category.key, int(category.starting_rating))
            profile.last_updated = datetime.now(timezone.utc)
            self._profiles[normalized] = profile.model_copy(deep=True)
            self._persist_locked()
            return self._profiles[normalized].model_copy(deep=True)

    def update_assessment_status(self, username: str, status: str) -> LearnerProfile:
        normalized = username.lower()
        allowed = {"pending", "in_progress", "completed"}
        if status not in allowed:
            raise ValueError(f"Unsupported onboarding assessment status: {status}")
        with self._lock:
            profile = self._profiles.get(normalized)
            if profile is None:
                raise LookupError(f"Learner profile '{username}' does not exist.")
            if profile.onboarding_assessment is None:
                raise LookupError(f"Assessment for '{username}' has not been generated.")
            profile.onboarding_assessment.status = status  # type: ignore[assignment]
            profile.last_updated = datetime.now(timezone.utc)
            self._profiles[normalized] = profile.model_copy(deep=True)
            self._persist_locked()
            return self._profiles[normalized].model_copy(deep=True)

    def delete(self, username: str) -> bool:
        normalized = username.lower()
        with self._lock:
            removed = self._profiles.pop(normalized, None)
            if removed:
                self._persist_locked()
                logger.info("Removed learner profile for %s", normalized)
                return True
            return False

    def _set_if_changed(self, profile: LearnerProfile, attr: str, raw_value: Any) -> bool:
        if not isinstance(raw_value, str):
            return False
        trimmed = raw_value.strip()
        if trimmed and getattr(profile, attr) != trimmed:
            setattr(profile, attr, trimmed)
            return True
        return False

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("Failed to load learner profiles: %s", exc)
            return
        if isinstance(data, dict):
            records = data.values()
        elif isinstance(data, list):
            records = data
        else:
            logger.warning("Unexpected learner profile payload type: %s", type(data))
            return

        for payload in records:
            try:
                profile = LearnerProfile.model_validate(payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping invalid learner profile payload: %s", exc)
                continue
            if profile.curriculum_schedule and not profile.curriculum_schedule.timezone:
                fallback_tz = profile.timezone or "UTC"
                profile.curriculum_schedule.timezone = fallback_tz
            self._profiles[profile.username.lower()] = profile

    def _persist_locked(self) -> None:
        dump = {
            username: profile.model_dump(mode="json")
            for username, profile in self._profiles.items()
        }
        try:
            self._path.write_text(json.dumps(dump, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            logger.exception("Failed to persist learner profiles to %s", self._path)

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


profile_store = LearnerProfileStore(DATA_PATH)

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
