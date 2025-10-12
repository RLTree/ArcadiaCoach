"""Learner profile models and lightweight persistence."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional

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

__all__ = ["LearnerProfile", "LearnerProfileStore", "profile_store", "MemoryRecord"]
