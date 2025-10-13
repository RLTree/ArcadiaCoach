"""Structured attachment storage for onboarding assessment submissions (Phase 10)."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Dict, Iterable, List, Literal, Optional
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
FILES_DIR = DATA_DIR / "assessment_attachments"
METADATA_PATH = DATA_DIR / "assessment_attachments.json"

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
    """JSON-backed attachment registry for onboarding assessment submissions."""

    def __init__(self, metadata_path: Path, files_dir: Path) -> None:
        self._metadata_path = metadata_path
        self._files_dir = files_dir
        self._lock = RLock()
        self._pending: Dict[str, List[PendingAssessmentAttachment]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_pending(self, username: str) -> List[PendingAssessmentAttachment]:
        normalized = _normalize_username(username)
        with self._lock:
            entries = self._pending.get(normalized, [])
            return [entry.model_copy(deep=True) for entry in sorted(entries, key=lambda e: e.created_at)]

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
        size_bytes = len(blob)
        if size_bytes == 0:
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

        entry = PendingAssessmentAttachment(
            attachment_id=attachment_id,
            username=normalized,
            kind="file",
            name=effective_name,
            description=(description or "").strip() or None,
            content_type=content_type or "application/octet-stream",
            size_bytes=size_bytes,
            stored_path=os.path.relpath(stored_path, self._files_dir),
        )
        with self._lock:
            bucket = self._pending.setdefault(normalized, [])
            bucket.append(entry)
            self._persist_locked()
        logger.info("Stored assessment attachment %s for %s", attachment_id, normalized)
        return entry.model_copy(deep=True)

    def add_link(
        self,
        username: str,
        name: str,
        url: str,
        description: Optional[str] = None,
    ) -> PendingAssessmentAttachment:
        normalized = _normalize_username(username)
        trimmed_name = name.strip() or url.strip()
        trimmed_url = url.strip()
        if not trimmed_url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="URL cannot be empty.",
            )
        attachment_id = f"{ID_PREFIX}_{uuid4().hex[:10]}"
        entry = PendingAssessmentAttachment(
            attachment_id=attachment_id,
            username=normalized,
            kind="link",
            name=trimmed_name,
            url=trimmed_url,
            description=(description or "").strip() or None,
        )
        with self._lock:
            bucket = self._pending.setdefault(normalized, [])
            bucket.append(entry)
            self._persist_locked()
        logger.info("Registered link attachment %s for %s", attachment_id, normalized)
        return entry.model_copy(deep=True)

    def delete(self, username: str, attachment_id: str) -> None:
        normalized = _normalize_username(username)
        trimmed = attachment_id.strip()
        if not trimmed:
            return
        with self._lock:
            bucket = self._pending.get(normalized)
            if not bucket:
                return
            remaining: List[PendingAssessmentAttachment] = []
            removed: Optional[PendingAssessmentAttachment] = None
            for entry in bucket:
                if entry.attachment_id == trimmed:
                    removed = entry
                else:
                    remaining.append(entry)
            if removed is None:
                return
            if remaining:
                self._pending[normalized] = remaining
            else:
                self._pending.pop(normalized, None)
            self._persist_locked()
        logger.info("Removed pending attachment %s for %s", trimmed, normalized)

    def consume(self, username: str) -> List[PendingAssessmentAttachment]:
        normalized = _normalize_username(username)
        with self._lock:
            bucket = self._pending.pop(normalized, [])
            self._persist_locked()
        if bucket:
            logger.info("Consuming %d pending attachments for %s", len(bucket), normalized)
        return [entry.model_copy(deep=True) for entry in bucket]

    def restore(self, attachments: Iterable[PendingAssessmentAttachment]) -> None:
        items = [attachment.model_copy(deep=True) for attachment in attachments]
        if not items:
            return
        with self._lock:
            for attachment in items:
                bucket = self._pending.setdefault(attachment.username, [])
                bucket = [entry for entry in bucket if entry.attachment_id != attachment.attachment_id]
                bucket.append(attachment)
                bucket.sort(key=lambda entry: entry.created_at)
                self._pending[attachment.username] = bucket
            self._persist_locked()

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
        with self._lock:
            removed = self._pending.pop(normalized, None)
            if removed is not None:
                self._persist_locked()
        user_dir = self._files_dir / _safe_component(normalized)
        if user_dir.exists():
            shutil.rmtree(user_dir, ignore_errors=True)
            logger.info("Removed attachment directory for %s", normalized)

    def load_file(self, username: str, attachment_id: str) -> Path:
        normalized = _normalize_username(username)
        trimmed = attachment_id.strip()
        if not trimmed:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")
        with self._lock:
            bucket = self._pending.get(normalized, [])
            for entry in bucket:
                if entry.attachment_id == trimmed and entry.kind == "file":
                    if entry.stored_path is None:
                        break
                    path = self._files_dir / entry.stored_path
                    if path.exists():
                        return path
                    break
        # If not pending, attempt to resolve saved file on disk (for archival submissions).
        archived_path = self._files_dir / _safe_component(normalized) / f"{trimmed}_archive"
        if archived_path.exists():
            return archived_path
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._metadata_path.exists():
            return
        try:
            payload = json.loads(self._metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("Unable to load assessment attachments metadata: %s", exc)
            return
        if not isinstance(payload, dict):
            logger.warning("Skipping malformed attachments payload (expected dict).")
            return
        for username, entries in payload.items():
            if not isinstance(entries, list):
                continue
            bucket: List[PendingAssessmentAttachment] = []
            for item in entries:
                try:
                    attachment = PendingAssessmentAttachment.model_validate(item)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Skipping invalid attachment for %s: %s", username, exc)
                    continue
                bucket.append(attachment)
            if bucket:
                self._pending[username] = bucket

    def _persist_locked(self) -> None:
        dump = {
            username: [entry.model_dump(mode="json") for entry in entries]
            for username, entries in self._pending.items()
        }
        try:
            self._metadata_path.write_text(json.dumps(dump, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            logger.exception("Failed to persist attachments metadata to %s", self._metadata_path)


attachment_store = AssessmentAttachmentStore(METADATA_PATH, FILES_DIR)

__all__ = [
    "PendingAssessmentAttachment",
    "AssessmentAttachmentStore",
    "attachment_store",
]
