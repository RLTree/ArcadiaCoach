"""Lightweight persistence for onboarding assessment submissions (Phases 4-5)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Literal, Optional, Sequence, cast
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from .agent_models import (
    AssessmentCategoryOutcomePayload,
    AssessmentGradingPayload,
    AssessmentRubricEvaluationPayload,
    AssessmentSubmissionAttachmentPayload,
    AssessmentSubmissionPayload,
    AssessmentTaskGradePayload,
    AssessmentTaskResponsePayload,
)
from .assessment_result import AssessmentGradingResult
from .assessment_attachments import PendingAssessmentAttachment
from .db.models import AssessmentSubmissionModel, LearnerProfileModel
from .db.session import session_scope


logger = logging.getLogger(__name__)


class AssessmentTaskResponse(BaseModel):
    task_id: str
    response: str
    category_key: str
    task_type: Literal["concept_check", "code"]
    word_count: int = Field(default=0, ge=0)


class AssessmentSubmissionAttachment(BaseModel):
    attachment_id: str
    kind: Literal["file", "link", "note"] = "file"
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = Field(default=None, ge=0)
    stored_path: Optional[str] = None
    source: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_pending(cls, entry: PendingAssessmentAttachment) -> "AssessmentSubmissionAttachment":
        return cls(
            attachment_id=entry.attachment_id,
            kind=entry.kind,
            name=entry.name,
            description=entry.description,
            url=entry.url if entry.kind != "file" else None,
            content_type=entry.content_type,
            size_bytes=entry.size_bytes,
            stored_path=entry.stored_path,
            source="structured",
            created_at=entry.created_at,
        )

    def to_pending(self, username: str) -> PendingAssessmentAttachment:
        return PendingAssessmentAttachment(
            attachment_id=self.attachment_id,
            username=username.lower().strip(),
            kind=self.kind,
            name=self.name,
            description=self.description,
            url=self.url if self.kind != "file" else None,
            content_type=self.content_type,
            size_bytes=self.size_bytes,
            stored_path=self.stored_path,
            created_at=self.created_at,
        )

    def as_payload(self, username: str) -> AssessmentSubmissionAttachmentPayload:
        download_url: Optional[str] = None
        if self.kind == "file":
            download_url = f"/api/onboarding/{username}/assessment/attachments/{self.attachment_id}/download"
        return AssessmentSubmissionAttachmentPayload(
            attachment_id=self.attachment_id,
            name=self.name,
            kind=self.kind,
            url=self.url or download_url,
            description=self.description,
            source=self.source,
            content_type=self.content_type,
            size_bytes=self.size_bytes,
        )


class AssessmentSubmission(BaseModel):
    submission_id: str
    username: str
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    responses: List[AssessmentTaskResponse] = Field(default_factory=list)
    attachments: List[AssessmentSubmissionAttachment] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)
    grading: Optional[AssessmentGradingResult] = None


def _word_count(value: str) -> int:
    tokens = [token for token in value.strip().split() if token]
    return len(tokens)

_ATTACHMENT_META_KEYS = (
    "attachments",
    "attachment_manifest",
    "attachment_links",
    "submission_attachments",
)


def _parse_attachment_metadata(metadata: Dict[str, str]) -> List[AssessmentSubmissionAttachmentPayload]:
    attachments: List[AssessmentSubmissionAttachmentPayload] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(
        name: str,
        kind: Literal["file", "link", "note"] = "file",
        url: Optional[str] = None,
        description: Optional[str] = None,
        source: Optional[str] = None,
    ) -> None:
        label = name.strip()
        if not label:
            return
        normalized_url = url.strip() if isinstance(url, str) else None
        normalized_description = description.strip() if isinstance(description, str) else None
        key = (label, normalized_url or "", kind)
        if key in seen:
            return
        seen.add(key)
        attachments.append(
            AssessmentSubmissionAttachmentPayload(
                name=label,
                kind=kind,
                url=normalized_url,
                description=normalized_description,
                source=source,
            )
        )

    for key in _ATTACHMENT_META_KEYS:
        raw = metadata.get(key)
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if not value:
            continue
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, list):
            for entry in parsed:
                if isinstance(entry, str):
                    _add(entry, source=key)
                elif isinstance(entry, dict):
                    name = str(entry.get("name") or entry.get("filename") or entry.get("title") or "").strip()
                    url = entry.get("url") or entry.get("href") or entry.get("link")
                    url_value = str(url).strip() if isinstance(url, str) else None
                    description = entry.get("description") or entry.get("notes")
                    kind = str(entry.get("kind") or ("link" if url_value else "file")).lower()
                    if kind not in {"file", "link", "note"}:
                        kind = "link" if url_value else "file"
                    target_name = name or (url_value or "")
                    if target_name:
                        _add(
                            target_name,
                            kind=cast(Literal["file", "link", "note"], kind),
                            url=url_value,
                            description=str(description).strip() if isinstance(description, str) else None,
                            source=key,
                        )
        elif isinstance(parsed, dict):
            for entry_name, entry_value in parsed.items():
                if not isinstance(entry_name, str):
                    continue
                label = entry_name.strip()
                if isinstance(entry_value, str):
                    url_value = entry_value.strip()
                    kind: Literal["file", "link"] = "link" if url_value.startswith(("http://", "https://")) else "file"
                    _add(label or url_value, kind=kind, url=url_value, source=key)
                else:
                    _add(label or str(entry_value), source=key)
        else:
            for part in value.split(","):
                trimmed = part.strip()
                if trimmed:
                    _add(trimmed, source=key)

    for key, raw in metadata.items():
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if not value:
            continue
        lower_key = key.lower()
        if lower_key.startswith(("attachment:", "attachment_", "file:")):
            url_value = value if value.startswith(("http://", "https://")) else None
            kind: Literal["file", "link"] = "link" if url_value else "file"
            _add(value if not url_value else value, kind=kind, url=url_value, source=key)

    return attachments


class AssessmentSubmissionStore:
    """Database-backed submission log for developer debugging."""

    def record(
        self,
        username: str,
        responses: Iterable[AssessmentTaskResponse],
        metadata: Dict[str, str] | None = None,
        attachments: Sequence[AssessmentSubmissionAttachment] | None = None,
    ) -> AssessmentSubmission:
        normalized = username.strip().lower()
        if not normalized:
            raise ValueError("Username cannot be empty when recording submissions.")

        response_models = [response.model_copy(deep=True) for response in responses]
        for response in response_models:
            response.word_count = _word_count(response.response)

        attachment_models = [attachment.model_copy(deep=True) for attachment in attachments or []]
        metadata_payload = {str(key): str(value) for key, value in (metadata or {}).items()}
        submission_id = uuid4().hex
        submitted_at = datetime.now(timezone.utc)

        with session_scope() as session:
            learner = self._get_learner(session, normalized)
            model = AssessmentSubmissionModel(
                learner_id=learner.id,
                submission_id=submission_id,
                submitted_at=submitted_at,
                responses=[response.model_dump(mode="json") for response in response_models],
                attachments=[attachment.model_dump(mode="json") for attachment in attachment_models],
                metadata_payload=metadata_payload,
                grading=None,
            )
            session.add(model)
            session.flush()
            logger.info("Stored onboarding submission %s for %s", submission_id, normalized)
            return self._model_to_domain(model, learner.username or normalized)

    def apply_grading(
        self,
        username: str,
        submission_id: str,
        grading: AssessmentGradingResult,
    ) -> AssessmentSubmission:
        normalized = username.strip().lower()
        if not normalized:
            raise ValueError("Username cannot be empty when applying grading.")
        with session_scope() as session:
            model, learner_username = self._get_submission(session, normalized, submission_id)
            model.grading = grading.model_dump(mode="json")
            session.flush()
            logger.info("Attached grading result to submission %s for %s", submission_id, normalized)
            return self._model_to_domain(model, learner_username)

    def list_user(self, username: str) -> List[AssessmentSubmission]:
        normalized = username.strip().lower()
        if not normalized:
            return []
        with session_scope(commit=False) as session:
            learner = self._get_learner(session, normalized, required=False)
            if learner is None:
                return []
            stmt = (
                select(AssessmentSubmissionModel)
                .options(selectinload(AssessmentSubmissionModel.learner))
                .where(AssessmentSubmissionModel.learner_id == learner.id)
                .order_by(AssessmentSubmissionModel.submitted_at.desc())
            )
            rows = session.execute(stmt).scalars().all()
            return [self._model_to_domain(row, learner.username or normalized) for row in rows]

    def list_all(self) -> List[AssessmentSubmission]:
        with session_scope(commit=False) as session:
            stmt = (
                select(AssessmentSubmissionModel)
                .options(selectinload(AssessmentSubmissionModel.learner))
                .order_by(AssessmentSubmissionModel.submitted_at.desc())
            )
            rows = session.execute(stmt).scalars().all()
            submissions: List[AssessmentSubmission] = []
            for row in rows:
                username = row.learner.username if row.learner else ""
                submissions.append(self._model_to_domain(row, username))
            return submissions

    def delete_user(self, username: str) -> None:
        normalized = username.strip().lower()
        if not normalized:
            return
        with session_scope() as session:
            learner = self._get_learner(session, normalized, required=False)
            if learner is None:
                logger.info("No submissions found for %s", normalized)
                return
            stmt = select(AssessmentSubmissionModel).where(AssessmentSubmissionModel.learner_id == learner.id)
            existing = session.execute(stmt).scalars().all()
            session.execute(
                delete(AssessmentSubmissionModel).where(AssessmentSubmissionModel.learner_id == learner.id)
            )
            logger.info("Cleared %d submissions for %s", len(existing), normalized)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_learner(self, session, username: str, required: bool = True) -> LearnerProfileModel | None:
        stmt = select(LearnerProfileModel).where(LearnerProfileModel.username == username)
        learner = session.execute(stmt).scalar_one_or_none()
        if learner is None and required:
            raise LookupError(f"Learner profile '{username}' does not exist.")
        return learner

    def _get_submission(self, session, username: str, submission_id: str):
        learner = self._get_learner(session, username)
        stmt = (
            select(AssessmentSubmissionModel)
            .options(selectinload(AssessmentSubmissionModel.learner))
            .where(
                AssessmentSubmissionModel.learner_id == learner.id,
                AssessmentSubmissionModel.submission_id == submission_id,
            )
        )
        model = session.execute(stmt).scalar_one_or_none()
        if model is None:
            raise LookupError(f"Submission '{submission_id}' was not found for '{username}'.")
        return model, learner.username or username

    def _model_to_domain(self, model: AssessmentSubmissionModel, username: str) -> AssessmentSubmission:
        responses = []
        for payload in model.responses or []:
            response = AssessmentTaskResponse.model_validate(payload)
            if response.word_count <= 0:
                response.word_count = _word_count(response.response)
            responses.append(response)
        attachments = [
            AssessmentSubmissionAttachment.model_validate(payload)
            for payload in model.attachments or []
        ]
        metadata = {str(key): str(value) for key, value in (model.metadata_payload or {}).items()}
        grading = (
            AssessmentGradingResult.model_validate(model.grading)
            if model.grading
            else None
        )
        return AssessmentSubmission(
            submission_id=model.submission_id,
            username=username,
            submitted_at=model.submitted_at,
            responses=responses,
            attachments=attachments,
            metadata=metadata,
            grading=grading,
        )


def submission_payload(submission: AssessmentSubmission) -> AssessmentSubmissionPayload:
    grading_payload: AssessmentGradingPayload | None = None
    if submission.grading:
        grading = submission.grading
        grading_payload = AssessmentGradingPayload(
            submission_id=grading.submission_id,
            evaluated_at=grading.evaluated_at,
            overall_feedback=grading.overall_feedback,
            strengths=list(grading.strengths),
            focus_areas=list(grading.focus_areas),
            task_results=[
                AssessmentTaskGradePayload(
                    task_id=task.task_id,
                    category_key=task.category_key,
                    task_type=task.task_type,
                    score=task.score,
                    confidence=task.confidence,
                    feedback=task.feedback,
                    strengths=list(task.strengths),
                    improvements=list(task.improvements),
                    rubric=[
                        AssessmentRubricEvaluationPayload(
                            criterion=rubric.criterion,
                            met=rubric.met,
                            notes=rubric.notes,
                            score=rubric.score,
                        )
                        for rubric in task.rubric
                    ],
                )
                for task in grading.task_results
            ],
            category_outcomes=[
                AssessmentCategoryOutcomePayload(
                    category_key=outcome.category_key,
                    average_score=outcome.average_score,
                    initial_rating=outcome.initial_rating,
                    starting_rating=outcome.starting_rating,
                    rating_delta=outcome.rating_delta,
                    rationale=outcome.rationale,
                )
                for outcome in grading.category_outcomes
            ],
        )

    payload_attachments: List[AssessmentSubmissionAttachmentPayload] = []
    seen: set[tuple[str, str, str]] = set()

    def _append(value: AssessmentSubmissionAttachmentPayload) -> None:
        key = (value.name.strip(), (value.url or "").strip(), value.kind)
        if key in seen:
            return
        seen.add(key)
        payload_attachments.append(value)

    for attachment in submission.attachments:
        _append(attachment.as_payload(submission.username))

    for legacy in _parse_attachment_metadata(submission.metadata):
        _append(legacy)

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
        grading=grading_payload,
        attachments=payload_attachments,
    )


submission_store = AssessmentSubmissionStore()

__all__ = [
    "AssessmentGradingResult",
    "AssessmentSubmissionAttachment",
    "AssessmentSubmission",
    "AssessmentSubmissionStore",
    "AssessmentTaskResponse",
    "submission_payload",
    "submission_store",
]
