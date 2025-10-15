from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict

from pydantic import ValidationError

from sqlalchemy import select

from app.db.base import Base
from app.db.models import AssessmentAttachmentModel, AssessmentSubmissionModel, LearnerProfileModel
from app.db.session import get_engine, session_scope
from app.learner_profile import LearnerProfile
from app.repositories.learner_profiles import learner_profiles
from app.assessment_submission import AssessmentSubmission
from app.assessment_attachments import PendingAssessmentAttachment


logger = logging.getLogger("backfill")

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data"


def _ensure_database() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)


def _load_json(path: Path) -> Dict[str, object] | list[object]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def backfill_profiles(path: Path) -> int:
    if not path.exists():
        logger.info("No legacy profiles found at %s", path)
        return 0
    payload = _load_json(path)
    records = payload.values() if isinstance(payload, dict) else payload
    imported = 0
    with session_scope() as session:
        for entry in records:
            try:
                profile = LearnerProfile.model_validate(entry)
            except ValidationError as exc:
                logger.warning("Skipping invalid profile payload: %s", exc)
                continue
            learner_profiles.upsert(session, profile)
            imported += 1
    logger.info("Imported %d learner profiles", imported)
    return imported


def backfill_submissions(path: Path) -> int:
    if not path.exists():
        logger.info("No legacy submissions found at %s", path)
        return 0
    payload = _load_json(path)
    if not isinstance(payload, dict):
        logger.warning("Legacy submission payload was not a mapping; skipping")
        return 0

    imported = 0
    with session_scope() as session:
        for username, entries in payload.items():
            if not isinstance(entries, list):
                continue
            learner = session.execute(
                select(LearnerProfileModel).where(LearnerProfileModel.username == username.lower().strip())
            ).scalar_one_or_none()
            if learner is None:
                logger.warning("Skipping submissions for %s; profile not found", username)
                continue
            for entry in entries:
                try:
                    submission = AssessmentSubmission.model_validate(entry)
                except ValidationError as exc:
                    logger.warning("Skipping invalid submission for %s: %s", username, exc)
                    continue
                exists = session.execute(
                    select(AssessmentSubmissionModel).where(
                        AssessmentSubmissionModel.submission_id == submission.submission_id
                    )
                ).scalar_one_or_none()
                if exists:
                    continue
                model = AssessmentSubmissionModel(
                    learner_id=learner.id,
                    submission_id=submission.submission_id,
                    submitted_at=submission.submitted_at,
                    responses=[response.model_dump(mode="json") for response in submission.responses],
                    attachments=[attachment.model_dump(mode="json") for attachment in submission.attachments],
                    metadata_payload=dict(submission.metadata),
                    grading=submission.grading.model_dump(mode="json") if submission.grading else None,
                )
                session.add(model)
                imported += 1
    logger.info("Imported %d assessment submissions", imported)
    return imported


def backfill_attachments(path: Path) -> int:
    if not path.exists():
        logger.info("No legacy attachments found at %s", path)
        return 0
    payload = _load_json(path)
    if not isinstance(payload, dict):
        logger.warning("Legacy attachment payload was not a mapping; skipping")
        return 0

    imported = 0
    with session_scope() as session:
        for username, entries in payload.items():
            if not isinstance(entries, list):
                continue
            learner = session.execute(
                select(LearnerProfileModel).where(LearnerProfileModel.username == username.lower().strip())
            ).scalar_one_or_none()
            if learner is None:
                logger.warning("Skipping attachments for %s; profile not found", username)
                continue
            for entry in entries:
                try:
                    attachment = PendingAssessmentAttachment.model_validate(entry)
                except ValidationError as exc:
                    logger.warning("Skipping invalid attachment for %s: %s", username, exc)
                    continue
                exists = session.execute(
                    select(AssessmentAttachmentModel).where(
                        AssessmentAttachmentModel.attachment_id == attachment.attachment_id
                    )
                ).scalar_one_or_none()
                if exists:
                    continue
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
                    source="legacy-json",
                    created_at=attachment.created_at,
                    is_consumed=False,
                )
                session.add(model)
                imported += 1
    logger.info("Imported %d pending attachments", imported)
    return imported


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill legacy JSON stores into PostgreSQL.")
    parser.add_argument("--profiles", type=Path, default=DATA_DIR / "learner_profiles.json")
    parser.add_argument("--submissions", type=Path, default=DATA_DIR / "assessment_submissions.json")
    parser.add_argument("--attachments", type=Path, default=DATA_DIR / "assessment_attachments.json")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    _ensure_database()
    total_profiles = backfill_profiles(args.profiles)
    total_submissions = backfill_submissions(args.submissions)
    total_attachments = backfill_attachments(args.attachments)
    logger.info(
        "Backfill completed: %d profiles, %d submissions, %d attachments",
        total_profiles,
        total_submissions,
        total_attachments,
    )


if __name__ == "__main__":
    main()
