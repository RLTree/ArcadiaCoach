"""Tests for ELO plan persistence endpoints."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import dispose_engine, get_engine
from app.learner_profile import LearnerProfile, profile_store
from app.main import app


def _setup_db(tmp_path: Path) -> None:
    db_path = tmp_path / "elo_plan.db"
    os.environ["ARCADIA_DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["ARCADIA_PERSISTENCE_MODE"] = "database"
    dispose_engine()
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _plan_payload() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "generated_at": now,
        "source_goal": "Ship API",
        "strategy_notes": None,
        "categories": [
            {
                "key": "Backend Systems",
                "label": "Backend Systems",
                "description": "Services and runtime reliability.",
                "focus_areas": ["observability", "resilience"],
                "weight": 1.4,
                "rubric": [
                    {"level": "Developing", "descriptor": "Needs scaffolding"},
                ],
                "starting_rating": 1080,
            },
            {
                "key": "backend-systems",
                "label": "Backend Delivery",
                "description": "Runtime delivery.",
                "focus_areas": ["observability", "deployment"],
                "weight": 1.2,
                "rubric": [
                    {"level": "Proficient", "descriptor": "Operates independently"},
                ],
                "starting_rating": 1140,
            },
        ],
    }


@pytest.fixture(autouse=True)
def _reset_store(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    profile_store.delete("dup-user")
    profile_store.upsert(LearnerProfile(username="dup-user"))


def test_post_elo_plan_dedupes_categories() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/profile/dup-user/elo-plan",
        json=_plan_payload(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["categories"]) == 1
    category = body["categories"][0]
    assert sorted(category["focus_areas"]) == ["deployment", "observability", "resilience"]
    assert category["starting_rating"] == 1140
    profile = profile_store.get("dup-user")
    assert profile is not None
    assert profile.elo_category_plan is not None
    assert len(profile.elo_category_plan.categories) == 1
