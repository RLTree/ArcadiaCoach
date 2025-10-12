"""Lightweight persistence for onboarding assessment submissions (Phase 4)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Dict, Iterable, List, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .agent_models import (
    AssessmentSubmissionPayload,
    AssessmentTaskResponsePayload,
)


logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_PATH = DATA_DIR / "assessment_submissions.json"


class AssessmentTaskResponse(BaseModel):
    task_id: str
    response: str
    category_key: str
    task_type: Literal["concept_check", "code"]
    word_count: int = Field(default=0, ge=0)


class AssessmentSubmission(BaseModel):
    submission_id: str
    username: str
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    responses: List[AssessmentTaskResponse] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)


def _word_count(value: str) -> int:
    tokens = [token for token in value.strip().split() if token]
    return len(tokens)


class AssessmentSubmissionStore:
    """JSON-backed submission log for developer debugging."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = RLock()
        self._entries: Dict[str, List[AssessmentSubmission]] = {}
        self._load()

    def record(
        self,
        username: str,
        responses: Iterable[AssessmentTaskResponse],
        metadata: Dict[str, str] | None = None,
    ) -> AssessmentSubmission:
        normalized = username.lower().strip()
        if not normalized:
            raise ValueError("Username cannot be empty when recording submissions.")

        submission = AssessmentSubmission(
            submission_id=uuid4().hex,
            username=normalized,
            submitted_at=datetime.now(timezone.utc),
            responses=[response.model_copy(deep=True) for response in responses],
            metadata=dict(metadata or {}),
        )
        for response in submission.responses:
            response.word_count = _word_count(response.response)

        with self._lock:
            bucket = self._entries.setdefault(normalized, [])
            bucket.append(submission.model_copy(deep=True))
            self._persist_locked()
            logger.info("Stored onboarding submission %s for %s", submission.submission_id, normalized)
            return submission

    def list_user(self, username: str) -> List[AssessmentSubmission]:
        normalized = username.lower().strip()
        if not normalized:
            return []
        with self._lock:
            entries = self._entries.get(normalized, [])
            return [entry.model_copy(deep=True) for entry in sorted(entries, key=lambda e: e.submitted_at, reverse=True)]

    def list_all(self) -> List[AssessmentSubmission]:
        with self._lock:
            collected: List[AssessmentSubmission] = []
            for entries in self._entries.values():
                collected.extend(entry.model_copy(deep=True) for entry in entries)
            collected.sort(key=lambda entry: entry.submitted_at, reverse=True)
            return collected

    def delete_user(self, username: str) -> None:
        normalized = username.lower().strip()
        if not normalized:
            return
        with self._lock:
            removed = self._entries.pop(normalized, None)
            if removed:
                self._persist_locked()
                logger.info("Cleared %d submissions for %s", len(removed), normalized)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("Unable to load assessment submissions: %s", exc)
            return
        if not isinstance(data, dict):
            logger.warning("Skipping malformed submissions payload (expected dict).")
            return
        for username, entries in data.items():
            if not isinstance(entries, list):
                continue
            bucket: List[AssessmentSubmission] = []
            for payload in entries:
                try:
                    submission = AssessmentSubmission.model_validate(payload)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Skipping invalid submission payload for %s: %s", username, exc)
                    continue
                bucket.append(submission)
            if bucket:
                self._entries[username] = bucket

    def _persist_locked(self) -> None:
        dump = {
            username: [entry.model_dump(mode="json") for entry in entries]
            for username, entries in self._entries.items()
        }
        try:
            self._path.write_text(json.dumps(dump, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            logger.exception("Failed to persist assessment submissions to %s", self._path)


def submission_payload(submission: AssessmentSubmission) -> AssessmentSubmissionPayload:
    return AssessmentSubmissionPayload(
        submission_id=submission.submission_id,
        username=submission.username,
        submitted_at=submission.submitted_at,
        metadata=dict(submission.metadata),
        responses=[
            AssessmentTaskResponsePayload(
                task_id=response.task_id,
                response=response.response,
                category_key=response.category_key,
                task_type=response.task_type,
                word_count=response.word_count,
            )
            for response in submission.responses
        ],
    )


submission_store = AssessmentSubmissionStore(DATA_PATH)

__all__ = [
    "AssessmentSubmission",
    "AssessmentSubmissionStore",
    "AssessmentTaskResponse",
    "submission_payload",
    "submission_store",
]
