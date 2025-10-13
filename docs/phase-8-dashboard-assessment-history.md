# Phase 8 – Dashboard Assessment History (October 13, 2025)

## Scope Recap
- Surface assessment history and grading artifacts on the learner dashboard.
- Expose current ELO snapshots alongside assessment status cues across the dashboard and chat sidebar.
- Highlight the most recent onboarding or reassessment activity with explicit timestamps so readiness is unambiguous.

## Backend Updates
- `GET /api/profile/{username}` now includes `assessment_submissions` (latest 12) so the client can display grading history without additional round-trips.
- `LearnerProfilePayload` and related Swift models were extended to carry submission metadata, grading payloads, and timestamps.
- Payload sorting is handled server side to ensure newest-first ordering for UI consumption.
- Added compatibility shims so the client gracefully handles legacy profiles that lack `assessment_submissions`, preventing onboarding flows from breaking while older caches are still present.

## macOS Client Updates
- `AppViewModel` tracks `assessmentHistory`, exposes computed readiness helpers, and keeps history aligned with the latest grading events.
- Dashboard (`HomeView`) adds:
  - A readiness summary card with status badge, last submission/grading timestamps, and recent feedback.
  - A condensed history list (latest six submissions) with grading/score highlights.
  - Clarified ELO section with calibration timestamp or pending messaging.
- Chat sidebar (`ChatPanel`) now mirrors the readiness card, shows the latest two submissions, and reuses the ELO snapshot so learners have the same context while chatting.

## Follow-ups / Open Items
1. Add UI regression tests to confirm readiness states render correctly for each status (pending/in-progress/awaiting grading/ready).
2. Instrument telemetry for history card interactions and grading status transitions (ties into Phases 13 & 17 observability goals).
3. Monitor payload size for `assessment_submissions`; consider pagination if learners accumulate large histories post Phase 12 reassessments.
4. Remove the Swift legacy decode path once persistence migration guarantees the new schema across environments (tracked for the data layer phases).

## Validation Checklist
1. `uv run ruff check` and `swift test` (or build via Xcode) — ensure the new Swift models compile.
2. Run the backend locally (`uv run uvicorn app.main:app …`) and hit `GET /api/profile/{username}` to confirm the new `assessment_submissions` array appears.
3. Launch the macOS app, sign in with a learner that has graded assessments, and verify:
   - Dashboard status card shows accurate timestamps/score.
   - History list renders latest entries with correct status colours.
   - Chat sidebar mirrors the same status and ELO snapshot context.
