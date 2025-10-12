"""Learner profile models and lightweight persistence."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Literal, Optional

from pydantic import BaseModel, Field


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


class CurriculumPlan(BaseModel):
    """Curriculum outline generated during onboarding."""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overview: str = ""
    success_criteria: List[str] = Field(default_factory=list)
    modules: List[CurriculumModule] = Field(default_factory=list)


class AssessmentTask(BaseModel):
    """Assessment task delivered during onboarding assessment."""
    task_id: str
    category_key: str
    title: str
    task_type: Literal["concept_check", "code"]
    prompt: str
    guidance: str
    rubric: List[str] = Field(default_factory=list)
    expected_minutes: int = Field(default=20, ge=1)
    starter_code: Optional[str] = None
    answer_key: Optional[str] = None


class OnboardingAssessment(BaseModel):
    """Personalised assessment bundle generated for onboarding."""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal["pending", "in_progress", "completed"] = "pending"
    tasks: List[AssessmentTask] = Field(default_factory=list)


class LearnerProfile(BaseModel):
    username: str
    goal: str = ""
    use_case: str = ""
    strengths: str = ""
    knowledge_tags: List[str] = Field(default_factory=list)
    recent_sessions: List[str] = Field(default_factory=list)
    memory_records: List[MemoryRecord] = Field(default_factory=list)
    memory_index_id: str = Field(default=DEFAULT_VECTOR_STORE_ID)
    elo_snapshot: Dict[str, int] = Field(default_factory=dict)
    elo_category_plan: Optional[EloCategoryPlan] = None
    curriculum_plan: Optional[CurriculumPlan] = None
    onboarding_assessment: Optional[OnboardingAssessment] = None
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


profile_store = LearnerProfileStore(DATA_PATH)

__all__ = [
    "AssessmentTask",
    "CurriculumModule",
    "CurriculumPlan",
    "EloCategoryDefinition",
    "EloCategoryPlan",
    "EloRubricBand",
    "LearnerProfile",
    "LearnerProfileStore",
    "OnboardingAssessment",
    "MemoryRecord",
    "profile_store",
]
