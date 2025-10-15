"""Structured attachment storage for onboarding assessment submissions (Phase 10)."""

from __future__ import annotations

import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional, cast
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from .db.models import AssessmentAttachmentModel, LearnerProfileModel
from .db.session import session_scope

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
FILES_DIR = DATA_DIR / "assessment_attachments"

FILES_DIR.mkdir(parents=True, exist_ok=True)

ID_PREFIX = "att"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_username(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username cannot be empty.",
        )
    return normalized


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value)
    return cleaned.strip("._") or "file"


class PendingAssessmentAttachment(BaseModel):
    attachment_id: str
    username: str
    kind: Literal["file", "link", "note"]
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    stored_path: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)

    def as_payload(self) -> Dict[str, Optional[str | int]]:
        return {
            "attachment_id": self.attachment_id,
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "url": self.url,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "stored_path": self.stored_path,
            "created_at": self.created_at,
        }


class AssessmentAttachmentStore:
    """Database-backed attachment registry for onboarding assessment submissions."""

    def __init__(self, files_dir: Path) -> None:
        self._files_dir = files_dir

    def list_pending(self, username: str) -> List[PendingAssessmentAttachment]:
        normalized = _normalize_username(username)
        with session_scope(commit=False) as session:
            learner = self._get_learner(session, normalized, required=False)
            if learner is None:
                return []
            stmt = (
                select(AssessmentAttachmentModel)
                .where(
                    AssessmentAttachmentModel.learner_id == learner.id,
                    AssessmentAttachmentModel.is_consumed.is_(False),
                )
                .order_by(AssessmentAttachmentModel.created_at.asc())
            )
            rows = session.execute(stmt).scalars().all()
        return [self._model_to_pending(row, normalized) for row in rows]

    def add_file(
        self,
        username: str,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
        description: Optional[str] = None,
    ) -> PendingAssessmentAttachment:
        normalized = _normalize_username(username)
        effective_name = filename or "attachment"
        safe_filename = _safe_component(effective_name)
        blob = bytes(content)
        if not blob:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is empty.",
            )

        attachment_id = f"{ID_PREFIX}_{uuid4().hex[:10]}"
        user_dir = self._files_dir / _safe_component(normalized)
        user_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{attachment_id}_{safe_filename}"
        stored_path = user_dir / stored_name
        try:
            with stored_path.open("wb") as handle:
                handle.write(blob)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to persist attachment.",
            ) from exc

        relative_path = os.path.relpath(stored_path, self._files_dir)
        with session_scope() as session:
            learner = self._get_learner(session, normalized)
            model = AssessmentAttachmentModel(
                attachment_id=attachment_id,
                learner_id=learner.id,
                kind="file",
                name=effective_name,
                description=(description or "").strip() or None,
                url=None,
                content_type=content_type or "application/octet-stream",
                size_bytes=len(blob),
                stored_path=relative_path,
                source="structured",
                created_at=_now(),
                is_consumed=False,
            )
            session.add(model)
            session.flush()
        logger.info("Stored assessment attachment %s for %s", attachment_id, normalized)
        return self._model_to_pending(model, normalized)

    def add_link(
        self,
        username: str,
        name: str,
        url: str,
        description: Optional[str] = None,
    ) -> PendingAssessmentAttachment:
        normalized = _normalize_username(username)
        trimmed_url = url.strip()
        if not trimmed_url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="URL cannot be empty.",
            )
        trimmed_name = name.strip() or trimmed_url
        attachment_id = f"{ID_PREFIX}_{uuid4().hex[:10]}"
        with session_scope() as session:
            learner = self._get_learner(session, normalized)
            model = AssessmentAttachmentModel(
                attachment_id=attachment_id,
                learner_id=learner.id,
                kind="link",
                name=trimmed_name,
                description=(description or "").strip() or None,
                url=trimmed_url,
                content_type=None,
                size_bytes=None,
                stored_path=None,
                source="structured",
                created_at=_now(),
                is_consumed=False,
            )
            session.add(model)
            session.flush()
        logger.info("Registered link attachment %s for %s", attachment_id, normalized)
        return self._model_to_pending(model, normalized)

    def delete(self, username: str, attachment_id: str) -> None:
        normalized = _normalize_username(username)
        trimmed = attachment_id.strip()
        if not trimmed:
            return
        with session_scope() as session:
            model = self._find_attachment(session, normalized, trimmed)
            if model is None:
                return
            stored_path = model.stored_path
            session.delete(model)
            session.flush()
        if stored_path:
            candidate = (self._files_dir / stored_path).resolve()
            if candidate.exists():
                try:
                    candidate.unlink()
                except OSError:
                    logger.warning("Failed to delete attachment file %s", candidate)
        logger.info("Removed pending attachment %s for %s", trimmed, normalized)

    def consume(self, username: str) -> List[PendingAssessmentAttachment]:
        normalized = _normalize_username(username)
        with session_scope() as session:
            learner = self._get_learner(session, normalized, required=False)
            if learner is None:
                return []
            stmt = (
                select(AssessmentAttachmentModel)
                .where(
                    AssessmentAttachmentModel.learner_id == learner.id,
                    AssessmentAttachmentModel.is_consumed.is_(False),
                )
                .order_by(AssessmentAttachmentModel.created_at.asc())
            )
            rows = session.execute(stmt).scalars().all()
            if not rows:
                return []
            for row in rows:
                row.is_consumed = True
            session.flush()
        logger.info("Consuming %d pending attachments for %s", len(rows), normalized)
        return [self._model_to_pending(row, normalized) for row in rows]

    def restore(self, attachments: Iterable[PendingAssessmentAttachment]) -> None:
        items = [attachment.model_copy(deep=True) for attachment in attachments]
        if not items:
            return
        with session_scope() as session:
            for attachment in items:
                normalized = _normalize_username(attachment.username)
                learner = self._get_learner(session, normalized)
                model = self._find_attachment(session, normalized, attachment.attachment_id)
                if model is None:
                    model = AssessmentAttachmentModel(
                        attachment_id=attachment.attachment_id,
                        learner_id=learner.id,
                        kind=attachment.kind,
                        name=attachment.name,
                        description=attachment.description,
                        url=attachment.url,
                        content_type=attachment.content_type,
                        size_bytes=attachment.size_bytes,
                        stored_path=attachment.stored_path,
                        source="structured",
                        created_at=attachment.created_at,
                        is_consumed=False,
                    )
                    session.add(model)
                else:
                    model.kind = attachment.kind
                    model.name = attachment.name
                    model.description = attachment.description
                    model.url = attachment.url
                    model.content_type = attachment.content_type
                    model.size_bytes = attachment.size_bytes
                    model.stored_path = attachment.stored_path
                    model.created_at = attachment.created_at
                    model.is_consumed = False
            session.flush()

    def resolve_stored_path(self, stored_path: str) -> Path:
        candidate = (self._files_dir / stored_path).resolve()
        base = self._files_dir.resolve()
        if not str(candidate).startswith(str(base)):
            raise ValueError(f"Invalid attachment path: {stored_path}")
        if not candidate.exists():
            raise FileNotFoundError(stored_path)
        return candidate

    def purge_user(self, username: str) -> None:
        normalized = _normalize_username(username)
        with session_scope() as session:
            learner = self._get_learner(session, normalized, required=False)
            if learner:
                session.execute(
                    delete(AssessmentAttachmentModel).where(AssessmentAttachmentModel.learner_id == learner.id)
                )
        user_dir = self._files_dir / _safe_component(normalized)
        if user_dir.exists():
            shutil.rmtree(user_dir, ignore_errors=True)
            logger.info("Removed attachment directory for %s", normalized)

    def load_file(self, username: str, attachment_id: str) -> Path:
        normalized = _normalize_username(username)
        trimmed = attachment_id.strip()
        if not trimmed:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")
        with session_scope(commit=False) as session:
            model = self._find_attachment(session, normalized, trimmed)
            stored_path = model.stored_path if model else None
        if stored_path:
            candidate = (self._files_dir / stored_path).resolve()
            if candidate.exists():
                return candidate
        archived_path = self._files_dir / _safe_component(normalized) / f"{trimmed}_archive"
        if archived_path.exists():
            return archived_path
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_learner(
        self,
        session,
        username: str,
        *,
        required: bool = True,
    ) -> Optional[LearnerProfileModel]:
        stmt = select(LearnerProfileModel).where(LearnerProfileModel.username == username)
        learner = session.execute(stmt).scalar_one_or_none()
        if learner is None and required:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Learner profile '{username}' does not exist.",
            )
        return learner

    def _find_attachment(self, session, username: str, attachment_id: str) -> Optional[AssessmentAttachmentModel]:
        learner = self._get_learner(session, username, required=False)
        if learner is None:
            return None
        stmt = (
            select(AssessmentAttachmentModel)
            .where(
                AssessmentAttachmentModel.learner_id == learner.id,
                AssessmentAttachmentModel.attachment_id == attachment_id,
            )
        )
        return session.execute(stmt).scalar_one_or_none()

    def _model_to_pending(
        self,
        model: AssessmentAttachmentModel,
        username: str,
    ) -> PendingAssessmentAttachment:
        return PendingAssessmentAttachment(
            attachment_id=model.attachment_id,
            username=username,
            kind=cast(Literal["file", "link", "note"], model.kind),
            name=model.name,
            description=model.description,
            url=model.url,
            content_type=model.content_type,
            size_bytes=model.size_bytes,
            stored_path=model.stored_path,
            created_at=model.created_at,
        )


attachment_store = AssessmentAttachmentStore(FILES_DIR)

__all__ = [
    "PendingAssessmentAttachment",
    "AssessmentAttachmentStore",
    "attachment_store",
]
