"""Tests for hybrid persistence resync behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.learner_profile import LearnerProfile, LearnerProfileStore, _normalize_username


class _FakeDBStore:
    def __init__(self) -> None:
        self.raise_errors = True
        self.storage: dict[str, LearnerProfile] = {}

    def get(self, username: str) -> LearnerProfile | None:
        if self.raise_errors:
            raise RuntimeError("db unavailable")
        profile = self.storage.get(_normalize_username(username))
        return profile.model_copy(deep=True) if profile else None

    def upsert(self, profile: LearnerProfile) -> LearnerProfile:
        if self.raise_errors:
            raise RuntimeError("db unavailable")
        self.storage[_normalize_username(profile.username)] = profile.model_copy(deep=True)
        return profile

    def apply_metadata(self, username: str, metadata: dict[str, object]) -> LearnerProfile:
        if self.raise_errors:
            raise RuntimeError("db unavailable")
        key = _normalize_username(username)
        existing = self.storage.get(key, LearnerProfile(username=key))
        update: dict[str, object] = {}
        if "goal" in metadata:
            update["goal"] = metadata["goal"]
        if "use_case" in metadata:
            update["use_case"] = metadata["use_case"]
        if "strengths" in metadata:
            update["strengths"] = metadata["strengths"]
        updated = existing.model_copy(update=update)
        self.storage[key] = updated
        return updated

    def set_curriculum_schedule(self, username: str, schedule, **kwargs) -> LearnerProfile:
        if self.raise_errors:
            raise RuntimeError("db unavailable")
        profile = self.storage.get(_normalize_username(username))
        if profile:
            profile = profile.model_copy(update={"curriculum_schedule": schedule})
            self.storage[_normalize_username(username)] = profile
            return profile
        return LearnerProfile(username=username, curriculum_schedule=schedule)

    def set_elo_category_plan(self, username: str, plan) -> LearnerProfile:
        if self.raise_errors:
            raise RuntimeError("db unavailable")
        profile = self.storage.get(_normalize_username(username))
        if profile:
            profile = profile.model_copy(update={"elo_category_plan": plan})
            self.storage[_normalize_username(username)] = profile
            return profile
        return LearnerProfile(username=username, elo_category_plan=plan)

    def set_goal_inference(self, username: str, inference) -> LearnerProfile:
        if self.raise_errors:
            raise RuntimeError("db unavailable")
        profile = self.storage.get(_normalize_username(username))
        if profile:
            profile = profile.model_copy(update={"goal_inference": inference})
            self.storage[_normalize_username(username)] = profile
            return profile
        return LearnerProfile(username=username, goal_inference=inference)

    def delete(self, username: str) -> bool:
        if self.raise_errors:
            raise RuntimeError("db unavailable")
        return self.storage.pop(_normalize_username(username), None) is not None


@pytest.fixture()
def hybrid_store(tmp_path: Path) -> LearnerProfileStore:
    store = LearnerProfileStore(tmp_path / "legacy.json")
    store._mode = "hybrid"  # type: ignore[attr-defined]
    fake_db = _FakeDBStore()
    store._db_store = fake_db  # type: ignore[attr-defined]
    return store


def test_resync_copies_legacy_changes_when_database_recovers(hybrid_store: LearnerProfileStore) -> None:
    store = hybrid_store
    fake_db: _FakeDBStore = store._db_store  # type: ignore[assignment]

    profile = LearnerProfile(username="resync-user")
    fake_db.raise_errors = True

    stored = store.upsert(profile)
    assert stored.username == "resync-user"
    assert fake_db.storage == {}

    store.apply_metadata("resync-user", {"goal": "Ship API"})
    legacy = store._legacy_store.get("resync-user")  # type: ignore[attr-defined]
    assert legacy is not None
    assert legacy.goal == "Ship API"

    normalized = _normalize_username("resync-user")
    assert normalized in store._pending_resync  # type: ignore[attr-defined]

    fake_db.raise_errors = False

    fetched = store.get("resync-user")
    assert fetched is not None
    assert fetched.goal == "Ship API"
    assert normalized not in store._pending_resync  # type: ignore[attr-defined]
    assert fake_db.storage[normalized].goal == "Ship API"
