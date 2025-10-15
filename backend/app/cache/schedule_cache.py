"""Simple in-memory cache for learner curriculum schedules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not normalized:
        raise ValueError("Username cannot be empty when caching schedules.")
    return normalized


@dataclass
class _ScheduleEntry:
    schedule: Any
    cached_at: datetime


class ScheduleCache:
    """Process-local cache for curriculum schedules."""

    def __init__(self) -> None:
        self._entries: Dict[str, _ScheduleEntry] = {}

    def get(self, username: str) -> Optional[Any]:
        key = _normalize_username(username)
        entry = self._entries.get(key)
        if entry is None:
            return None
        schedule = entry.schedule
        if hasattr(schedule, "model_copy"):
            return schedule.model_copy(deep=True)  # type: ignore[no-any-return]
        return schedule

    def set(self, username: str, schedule: Any) -> None:
        key = _normalize_username(username)
        payload = schedule
        if hasattr(schedule, "model_copy"):
            payload = schedule.model_copy(deep=True)
        self._entries[key] = _ScheduleEntry(
            schedule=payload,
            cached_at=datetime.now(timezone.utc),
        )

    def invalidate(self, username: str) -> None:
        key = _normalize_username(username)
        self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()


schedule_cache = ScheduleCache()

__all__ = ["ScheduleCache", "schedule_cache"]
