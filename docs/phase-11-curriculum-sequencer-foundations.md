# Phase 11 – Curriculum Sequencer Foundations

*Completed October 13, 2025*

## Overview
Phase 11 introduces a deterministic curriculum sequencing service that converts the learner’s stored signals into a near-term practice roadmap. The sequencer consumes the learner’s goal, ELO snapshot, onboarding curriculum, and latest assessment results to prioritise upcoming lessons, quizzes, and a milestone. The resulting schedule is persisted on the learner profile and exposed to the macOS client via `/api/profile/{username}/schedule`.

## Inputs Considered
- **Learner intent:** trims the stored goal to surface in scheduling rationales.
- **ELO signals:** uses the latest `elo_snapshot` to bias toward weaker categories.
- **Category plan:** normalises category weights and guarantees each category has at least one learning module (falling back to primer templates when necessary).
- **Curriculum plan:** reuses onboarding modules and their estimated minutes/objectives where available.
- **Assessment outcomes:** folds in average scores, rating deltas, and focus areas to drive prioritisation and cadence notes.

## Output Schema
Schedules are persisted as a `CurriculumSchedule` with:
- `generated_at` timestamp and a rolling `time_horizon_days` (minimum 7, default 14).
- `cadence_notes` summarising total effort, covered days, and key focus areas.
- `items`: ordered `SequencedWorkItem` objects with:
  - `kind`: `lesson`, `quiz`, or `milestone`.
  - `recommended_minutes` and derived `effort_level` (`light`, `moderate`, `focus`).
  - `recommended_day_offset` (0-indexed schedule placement respecting a daily capacity cap).
  - `prerequisites`, `focus_reason`, and `expected_outcome` strings to guide UI presentation.

## Service Behaviour
- Prioritises categories by combining normalised weight, ELO deficit, assessment score gaps, and recent rating deltas.
- Generates lesson + quiz pairs for every module, plus a milestone for the highest-priority category.
- Assigns day offsets while respecting a configurable daily effort budget (`120` minutes by default).
- Resets cached schedules whenever the curriculum or assessment bundle is regenerated.

## API & Persistence Updates
- Added `curriculum_schedule` to `LearnerProfile` persistence and to the profile response payloads.
- Published `GET /api/profile/{username}/schedule` with optional `refresh` query to regenerate schedules on demand.
- Introduced `CurriculumSequencer` service (`backend/app/curriculum_sequencer.py`) and unit tests to keep heuristics regression-safe.

## Validation & Testing
- Run `uv run pytest backend/tests/test_curriculum_sequencer.py` to exercise sequencing heuristics and serialization coverage.
- With the backend running (`uv sync && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`), call `GET /api/profile/<username>/schedule?refresh=true` to generate a schedule after onboarding and inspect cadence notes, prerequisites, and day offsets.
- Launch the macOS client (`open ArcadiaCoach.xcodeproj` → build & run the ArcadiaCoach scheme) and sign in with a learner who has completed onboarding; the Dashboard schedule drawer should now fetch the persisted schedule. Toggle the “Refresh Plan” control to confirm the app issues `/api/profile/<username>/schedule?refresh=true` and reflects updated day offsets or cadence notes.
- Resume a chat session and request “show my upcoming curriculum” to ensure the agent surfaces the new schedule data via the profile payload, verifying widget rendering stays aligned with the backend schema.

## Follow-up Considerations
- Future phases can replace the deterministic heuristics with agent-generated plans while keeping the same persisted schema.
- Sequencer telemetry (tool success rates, regeneration patterns) should land alongside Phase 21 reliability work.
- Milestone generation currently targets only the highest-priority category; expand to multi-category plans once adaptive curriculum phases begin.
