# Phase 19 – Persistence Migration (Work in Progress)

_Status: in development (October 15, 2025)_

This phase introduces PostgreSQL as the system of record for Arcadia Coach. The legacy JSON stores located under `backend/app/data/` remain readable for backfill but are no longer written during runtime.

## What landed in this iteration

- Added SQLAlchemy + Alembic to the backend runtime and surfaced helpers in `app/db/`.
- Implemented ORM models and repositories for learner profiles, curriculum schedules, memory, assessment submissions, and attachment metadata.
- Replaced the JSON-backed stores with database-backed facades while keeping their public interface stable for existing routes and services.
- Created initial Alembic migration `20241015_01_initial_persistence.py` to provision all new tables and indexes.
- Added a `scripts/backfill_json_stores.py` command that imports historical learner profiles, submissions, and pending attachments into PostgreSQL.
- Updated the assessment submission regression suite to run against SQLite for local testing.

## Local setup

1. Ensure `ARCADIA_DATABASE_URL` is set (see `AGENTS.md` for Render credentials or configure a local Postgres/SQLite URI).
2. Install new dependencies and run migrations:

   ```bash
   cd backend
   uv sync
   uv run alembic upgrade head
   ```

3. Optional: backfill legacy JSON stores after the migration completes:

   ```bash
   cd backend
   uv run python -m scripts.backfill_json_stores
   ```

   Override the default paths with `--profiles`, `--submissions`, or `--attachments` if the JSON files live elsewhere.

## Testing matrix

- Unit tests: `uv run pytest tests/test_assessment_submission_store.py`
- Smoke test (database connectivity): launch the backend locally with `uv run uvicorn app.main:app --reload` to ensure the new repositories initialize without errors.

## Follow-ups

- Wire Alembic migrations into CI so schema drift is caught automatically.
- Extend repository coverage to handle vector memory uploads once Phase 20 begins.
- Harden the backfill script with idempotent resume support and checksum logging before production execution.
- Introduce monitoring for connection pool metrics (see Phase 33) once production traffic migrates.
