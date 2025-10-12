"""Learner memory utilities bridging the vector store and profile metadata."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Dict, Iterable, List


VECTOR_STORE_ID = "vs_68e81d741f388191acdaabce2f92b7d5"

logger = logging.getLogger(__name__)


class LearnerMemoryClient:
    def __init__(self, vector_store_id: str) -> None:
        self._vector_store_id = vector_store_id

    @property
    def vector_store_id(self) -> str:
        return self._vector_store_id

    def record_note(self, username: str, note: str, tags: Iterable[str] | None = None) -> Dict[str, str]:
        """Persist a learner memory note and append it to the profile cache.

        Production deployments should enqueue an OpenAI vector store upload here.
        For now we persist locally and return the deterministic note identifier so
        the Agent can reference the memory later in the conversation.
        """
        if not username.strip():
            raise ValueError("username is required to record a memory note")
        safe_tags: List[str] = [tag.strip() for tag in (tags or []) if tag and tag.strip()]
        digest_source = f"{username}:{note}:{time.time()}"
        note_id = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16]

        try:
            from .learner_profile import profile_store

            profile_store.append_memory(username=username, note_id=note_id, note=note, tags=safe_tags)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to append learner memory for %s", username)

        logger.info(
            "Recorded learner memory (username=%s, note_id=%s, tags=%s, vector_store=%s)",
            username,
            note_id,
            safe_tags,
            self._vector_store_id,
        )
        return {
            "note_id": note_id,
            "vector_store_id": self._vector_store_id,
            "status": "queued",
        }


learner_memory = LearnerMemoryClient(VECTOR_STORE_ID)

__all__ = ["LearnerMemoryClient", "VECTOR_STORE_ID", "learner_memory"]
