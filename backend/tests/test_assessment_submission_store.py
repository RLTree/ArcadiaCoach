"""Tests for assessment submission persistence and developer endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import assessment_submission, developer_routes, onboarding_routes, profile_routes, session_routes
from app.assessment_submission import AssessmentSubmissionStore, AssessmentTaskResponse
from app.learner_profile import AssessmentTask, LearnerProfile, LearnerProfileStore, OnboardingAssessment
from app.main import app


def _store(path: Path) -> AssessmentSubmissionStore:
    return AssessmentSubmissionStore(path)


def test_submission_store_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path / "submissions.json")
    response = AssessmentTaskResponse(
        task_id="concept-1",
        response="Describe how async context managers work in Python.",
        category_key="backend-foundations",
        task_type="concept_check",
    )

    created = store.record("Learner-One", [response], metadata={"client_version": "dev"})
    assert created.username == "learner-one"
    assert created.responses[0].word_count == 8

    items = store.list_user("learner-one")
    assert len(items) == 1

    store.delete_user("learner-one")
    assert store.list_user("learner-one") == []


def test_submission_endpoints_and_developer_reset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile_path = tmp_path / "profiles.json"
    submissions_path = tmp_path / "submissions.json"

    profile_store = LearnerProfileStore(profile_path)
    submission_store = AssessmentSubmissionStore(submissions_path)

    monkeypatch.setattr(onboarding_routes, "profile_store", profile_store, raising=False)
    monkeypatch.setattr(profile_routes, "profile_store", profile_store, raising=False)
    monkeypatch.setattr(session_routes, "profile_store", profile_store, raising=False)
    monkeypatch.setattr(developer_routes, "profile_store", profile_store, raising=False)
    monkeypatch.setattr(onboarding_routes, "submission_store", submission_store, raising=False)
    monkeypatch.setattr(developer_routes, "submission_store", submission_store, raising=False)
    monkeypatch.setattr(assessment_submission, "submission_store", submission_store, raising=False)

    profile = LearnerProfile(
        username="tester",
        onboarding_assessment=OnboardingAssessment(
            tasks=[
                AssessmentTask(
                    task_id="concept-1",
                    category_key="backend-foundations",
                    title="Explain async pitfalls",
                    task_type="concept_check",
                    prompt="Describe a race condition you recently fixed.",
                    guidance="Highlight how you diagnosed the issue.",
                    rubric=["Identifies the issue", "Provides mitigation"],
                    expected_minutes=12,
                ),
                AssessmentTask(
                    task_id="code-1",
                    category_key="backend-foundations",
                    title="Implement retry logic",
                    task_type="code",
                    prompt="Write Python code that retries a request up to 3 times.",
                    guidance="Keep the snippet under 30 lines.",
                    rubric=["Implements loop", "Handles errors"],
                    expected_minutes=18,
                    starter_code="",
                ),
            ]
        ),
    )
    profile_store.upsert(profile)

    client = TestClient(app)

    submission_payload = {
        "responses": [
            {"task_id": "concept-1", "response": "Async tasks must guard shared state with locks."},
            {"task_id": "code-1", "response": "for attempt in range(3):\n    print(attempt)"},
        ],
        "metadata": {"client_version": "dev-main"},
    }

    create = client.post("/api/onboarding/tester/assessment/submissions", json=submission_payload)
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["username"] == "tester"
    assert len(body["responses"]) == 2
    assert body["responses"][0]["word_count"] > 0

    listing = client.get("/api/developer/submissions", params={"username": "tester"})
    assert listing.status_code == 200
    records = listing.json()
    assert len(records) == 1
    assert records[0]["metadata"]["client_version"] == "dev-main"

    reset = client.post("/api/developer/reset", json={"username": "tester"})
    assert reset.status_code == 204
    assert profile_store.get("tester") is None
    assert submission_store.list_user("tester") == []
