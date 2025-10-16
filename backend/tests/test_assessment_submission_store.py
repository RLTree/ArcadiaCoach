"""Tests for assessment submission persistence and developer endpoints."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import assessment_attachments, assessment_submission, curriculum_sequencer, developer_routes, onboarding_routes, profile_routes, session_routes
from app.assessment_result import AssessmentCategoryOutcome, AssessmentGradingResult, RubricCriterionResult, TaskGradingResult
from app.assessment_submission import AssessmentSubmissionStore, AssessmentTaskResponse, submission_payload
from app.assessment_attachments import AssessmentAttachmentStore
from app.config import get_settings
from app.db.base import Base
from app.db.session import dispose_engine, get_engine
from app.learner_profile import (
    AssessmentTask,
    CurriculumModule,
    CurriculumPlan,
    EloCategoryDefinition,
    EloCategoryPlan,
    EloRubricBand,
    LearnerProfile,
    LearnerProfileStore,
    OnboardingAssessment,
    CurriculumSchedule,
    SequencedWorkItem,
)
from app.main import app


def _setup_db(tmp_path: Path) -> None:
    db_path = tmp_path / "arcadia.db"
    os.environ["ARCADIA_DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["ARCADIA_PERSISTENCE_MODE"] = "database"
    get_settings.cache_clear()
    dispose_engine()
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _attachment_store(root: Path) -> AssessmentAttachmentStore:
    files_dir = root / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    return AssessmentAttachmentStore(files_dir)


def test_submission_store_round_trip(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    store = AssessmentSubmissionStore()
    profile_store = LearnerProfileStore()
    profile_store.upsert(LearnerProfile(username="Learner-One"))
    response = AssessmentTaskResponse(
        task_id="concept-1",
        response="Describe how async context managers work in Python.",
        category_key="backend-foundations",
        task_type="concept_check",
    )

    created = store.record(
        "Learner-One",
        [response],
        metadata={
            "client_version": "dev",
            "attachments": json.dumps([
                {"name": "solution.py", "url": "https://files.example/solution.py"},
                "notes.txt",
            ]),
        },
    )
    assert created.username == "learner-one"
    assert created.responses[0].word_count == 8

    grading = AssessmentGradingResult(
        submission_id=created.submission_id,
        overall_feedback="Solid explanation with clear understanding of async context managers.",
        strengths=["Highlights asynchronous lock usage."],
        focus_areas=["Discuss cancellation handling in more depth."],
        task_results=[
            TaskGradingResult(
                task_id="concept-1",
                category_key="backend-foundations",
                task_type="concept_check",
                score=0.8,
                confidence="medium",
                feedback="Addresses the primary concurrency risks and mitigation strategies.",
                strengths=["Connects explanation to practical mitigation."],
                improvements=["Include an explicit example of state reset."],
                rubric=[
                    RubricCriterionResult(
                        criterion="Identifies the issue",
                        met=True,
                        notes="Calls out shared state hazards.",
                    ),
                ],
            )
        ],
        category_outcomes=[
            AssessmentCategoryOutcome(
                category_key="backend-foundations",
                average_score=0.8,
                initial_rating=1240,
                starting_rating=1100,
                rating_delta=140,
                rationale="Starting rating 1100 adjusted upward based on rubric alignment.",
            )
        ],
    )
    updated = store.apply_grading("Learner-One", created.submission_id, grading)
    assert updated.grading is not None
    assert updated.grading.overall_feedback.startswith("Solid explanation")
    payload = submission_payload(updated)
    assert payload.attachments[0].name == "solution.py"
    assert payload.attachments[0].url == "https://files.example/solution.py"
    assert payload.attachments[1].name == "notes.txt"
    assert payload.grading.category_outcomes[0].starting_rating == 1100
    assert payload.grading.category_outcomes[0].rating_delta == 140

    items = store.list_user("learner-one")
    assert len(items) == 1

    store.delete_user("learner-one")
    assert store.list_user("learner-one") == []


def test_submission_endpoints_and_developer_reset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_db(tmp_path)

    profile_store = LearnerProfileStore()
    submission_store = AssessmentSubmissionStore()
    attachment_store = _attachment_store(tmp_path / "attachments")

    monkeypatch.setattr(onboarding_routes, "profile_store", profile_store, raising=False)
    monkeypatch.setattr(profile_routes, "profile_store", profile_store, raising=False)
    monkeypatch.setattr(session_routes, "profile_store", profile_store, raising=False)
    monkeypatch.setattr(developer_routes, "profile_store", profile_store, raising=False)
    monkeypatch.setattr(curriculum_sequencer, "profile_store", profile_store, raising=False)
    monkeypatch.setattr(onboarding_routes, "submission_store", submission_store, raising=False)
    monkeypatch.setattr(developer_routes, "submission_store", submission_store, raising=False)
    monkeypatch.setattr(assessment_submission, "submission_store", submission_store, raising=False)
    monkeypatch.setattr(onboarding_routes, "attachment_store", attachment_store, raising=False)
    monkeypatch.setattr(developer_routes, "attachment_store", attachment_store, raising=False)
    monkeypatch.setattr(assessment_attachments, "attachment_store", attachment_store, raising=False)

    async def _fake_grade_submission(settings, profile, submission, tasks):
        return (
            AssessmentGradingResult(
                submission_id=submission.submission_id,
                overall_feedback="Great progress on the assessment. Concept mastery is evident; expand error handling in code.",
                strengths=[
                    "Concept response highlights concrete race-condition mitigation.",
                    "Code solution demonstrates retry loop structure.",
                ],
                focus_areas=["Introduce exponential backoff to your retry snippet."],
                task_results=[
                    TaskGradingResult(
                        task_id="concept-1",
                        category_key="backend-foundations",
                        task_type="concept_check",
                        score=0.9,
                        confidence="high",
                        feedback="Excellent description with actionable mitigation detail.",
                        strengths=["Addresses shared-state race condition."],
                        improvements=["Mention cancellation safeguards for completeness."],
                        rubric=[
                            RubricCriterionResult(
                                criterion="Identifies the issue",
                                met=True,
                                notes="Explains the race condition clearly.",
                            ),
                            RubricCriterionResult(
                                criterion="Provides mitigation",
                                met=True,
                                notes="Suggests lock around shared state.",
                            ),
                        ],
                    ),
                    TaskGradingResult(
                        task_id="code-1",
                        category_key="backend-foundations",
                        task_type="code",
                        score=0.7,
                        confidence="medium",
                        feedback="Implements retries but lacks jitter or error capture.",
                        strengths=["Uses a bounded retry loop."],
                        improvements=["Add exception handling and backoff delay."],
                        rubric=[],
                    ),
                ],
                category_outcomes=[
                AssessmentCategoryOutcome(
                    category_key="backend-foundations",
                    average_score=0.8,
                    initial_rating=1232,
                    starting_rating=1100,
                    rating_delta=132,
                    rationale="Starting rating 1100 adjusted by +132 after averaging task scores.",
                )
            ],
        ),
        {"backend-foundations": 1232},
        )

    monkeypatch.setattr(onboarding_routes, "grade_submission", _fake_grade_submission, raising=False)

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
    profile.elo_category_plan = EloCategoryPlan(
        categories=[
            EloCategoryDefinition(
                key="backend-foundations",
                label="Backend Foundations",
                description="Solidify backend resilience and async discipline.",
                focus_areas=["async patterns", "observability"],
                weight=1.0,
                rubric=[
                    EloRubricBand(level="Developing", descriptor="Working toward async mastery."),
                    EloRubricBand(level="Proficient", descriptor="Comfortable with async flows and retries."),
                ],
                starting_rating=1100,
            )
        ]
    )
    profile.curriculum_plan = CurriculumPlan(
        overview="Backend sequencing starter.",
        success_criteria=["Ship reliable retry workflows."],
        modules=[
            CurriculumModule(
                module_id="backend-retries",
                category_key="backend-foundations",
                title="Async Retry Tuning",
                summary="Harden asynchronous retry flows with observability.",
                objectives=["Implement jitter backoff", "Capture structured logs"],
                activities=["Code review retries", "Add metrics hooks"],
                deliverables=["Retry helper module"],
                estimated_minutes=60,
            )
        ],
    )
    profile.elo_snapshot = {"backend-foundations": 1100}
    profile_store.upsert(profile)

    client = TestClient(app)

    file_bytes = b"%PDF-1.4\n%Arcadia test\n"
    upload = client.post(
        "/api/onboarding/tester/assessment/attachments/files",
        data={"description": "Uploaded reference"},
        files={"file": ("analysis.pdf", file_bytes, "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    uploaded_file = upload.json()
    assert uploaded_file["attachment_id"]
    assert uploaded_file["name"] == "analysis.pdf"
    assert uploaded_file["description"] == "Uploaded reference"
    assert uploaded_file["size_bytes"] == len(file_bytes)

    link_resp = client.post(
        "/api/onboarding/tester/assessment/attachments/links",
        json={"url": "https://files.example/design-notes", "name": "Design Notes"},
    )
    assert link_resp.status_code == 201, link_resp.text
    link_attachment = link_resp.json()
    assert link_attachment["kind"] == "link"
    assert link_attachment["url"] == "https://files.example/design-notes"

    pending = client.get("/api/onboarding/tester/assessment/attachments")
    assert pending.status_code == 200
    pending_items = pending.json()
    assert len(pending_items) == 2

    submission_payload = {
        "responses": [
            {"task_id": "concept-1", "response": "Async tasks must guard shared state with locks."},
            {"task_id": "code-1", "response": "for attempt in range(3):\n    print(attempt)"},
        ],
        "metadata": {
            "client_version": "dev-main",
        },
    }

    create = client.post("/api/onboarding/tester/assessment/submissions", json=submission_payload)
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["username"] == "tester"
    assert len(body["responses"]) == 2
    assert body["responses"][0]["word_count"] > 0
    assert body["grading"]["overall_feedback"].startswith("Great progress")
    assert body["grading"]["category_outcomes"][0]["initial_rating"] == 1232
    assert body["grading"]["category_outcomes"][0]["starting_rating"] == 1100
    assert body["grading"]["category_outcomes"][0]["rating_delta"] == 132
    assert len(body["attachments"]) == 2
    file_attachment = next(item for item in body["attachments"] if item["kind"] == "file")
    assert file_attachment["name"] == "analysis.pdf"
    assert file_attachment["url"].endswith(f"/{uploaded_file['attachment_id']}/download")
    assert file_attachment["size_bytes"] == len(file_bytes)
    link_attachment = next(item for item in body["attachments"] if item["kind"] == "link")
    assert link_attachment["url"] == "https://files.example/design-notes"

    refreshed_profile = profile_store.get("tester")
    assert refreshed_profile is not None
    assert refreshed_profile.onboarding_assessment_result is not None
    assert refreshed_profile.elo_snapshot["backend-foundations"] == 1232
    assert "python-foundations" in refreshed_profile.elo_snapshot
    assert "project-delivery" in refreshed_profile.elo_snapshot
    assert refreshed_profile.onboarding_assessment is not None
    assert refreshed_profile.onboarding_assessment.status == "completed"
    assert refreshed_profile.curriculum_schedule is not None
    assert refreshed_profile.curriculum_schedule.items, "Schedule should contain sequenced work items."

    grading_fetch = client.get("/api/onboarding/tester/assessment/result")
    assert grading_fetch.status_code == 200
    assert grading_fetch.json()["focus_areas"][0].startswith("Introduce exponential backoff")

    listing = client.get("/api/developer/submissions", params={"username": "tester"})
    assert listing.status_code == 200
    records = listing.json()
    assert len(records) == 1
    assert records[0]["metadata"]["client_version"] == "dev-main"
    assert records[0]["grading"]["task_results"][0]["score"] == pytest.approx(0.9)
    assert len(records[0]["attachments"]) == 2

    # Pending attachments should be cleared after submission.
    cleared = client.get("/api/onboarding/tester/assessment/attachments")
    assert cleared.status_code == 200
    assert cleared.json() == []

    download = client.get(f"/api/onboarding/tester/assessment/attachments/{uploaded_file['attachment_id']}/download")
    assert download.status_code == 200
    assert download.content == file_bytes
    assert download.headers["content-type"] == "application/pdf"

    reset = client.post("/api/developer/reset", json={"username": "tester"})
    assert reset.status_code == 204
    assert profile_store.get("tester") is None
    assert submission_store.list_user("tester") == []


def test_developer_auto_complete_schedule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_db(tmp_path)

    profile_store = LearnerProfileStore()
    monkeypatch.setattr(developer_routes, "profile_store", profile_store, raising=False)

    profile_store.upsert(LearnerProfile(username="developer"))

    schedule = CurriculumSchedule(
        generated_at=datetime.now(timezone.utc),
        time_horizon_days=14,
        timezone="UTC",
        items=[
            SequencedWorkItem(
                item_id="lesson-1",
                category_key="backend",
                kind="lesson",
                title="Backend Lesson",
                summary="Learn retry strategies.",
                objectives=["Understand retry policies"],
                prerequisites=[],
                recommended_minutes=45,
                recommended_day_offset=0,
                focus_reason=None,
                expected_outcome=None,
                effort_level="moderate",
            ),
            SequencedWorkItem(
                item_id="quiz-1",
                category_key="backend",
                kind="quiz",
                title="Backend Quiz",
                summary="Check retry mastery.",
                objectives=[],
                prerequisites=["lesson-1"],
                recommended_minutes=20,
                recommended_day_offset=1,
                focus_reason=None,
                expected_outcome=None,
                effort_level="light",
                launch_status="in_progress",
            ),
            SequencedWorkItem(
                item_id="milestone-1",
                category_key="backend",
                kind="milestone",
                title="Backend Milestone",
                summary="Apply retries in a project.",
                objectives=[],
                prerequisites=["lesson-1", "quiz-1"],
                recommended_minutes=90,
                recommended_day_offset=2,
                focus_reason=None,
                expected_outcome=None,
                effort_level="focus",
            ),
        ],
    )
    profile_store.set_curriculum_schedule("developer", schedule)

    client = TestClient(app)
    response = client.post("/api/developer/auto-complete", json={"username": "developer"})
    assert response.status_code == 200, response.text
    body = response.json()
    statuses = {item["item_id"]: item["launch_status"] for item in body["items"]}
    assert statuses["lesson-1"] == "completed"
    assert statuses["quiz-1"] == "completed"
    assert statuses["milestone-1"] == "pending"
