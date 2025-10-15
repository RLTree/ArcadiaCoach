# Phase 26 – Schedule-Driven Session Launch

## Summary
- Added launch metadata to curriculum schedules (`launch_status`, `last_launched_at`, `last_completed_at`, `active_session_id`) with a new Alembic migration so in-progress work persists across refreshes.
- Introduced `/api/session/schedule/launch` and `/api/session/schedule/complete` to drive lesson/quiz/milestone delivery directly from schedule items, including milestone lock checks, telemetry, and error handling.
- Expanded the Swift models and `BackendService` to consume the new payloads and exposed launch/complete helpers for the macOS client.
- Revamped the Dashboard schedule UI with status pills, start/resume/complete controls, milestone confirmation dialogs, and progress indicators while removing the legacy “Start Lesson/Quiz/Milestone” buttons.
- Updated session handling (`AppViewModel`, `SessionViewModel`) so launched content records centrally, updates ELO, and refreshes cached lesson/quiz/milestone views.

## Testing
- `uv run ruff check`
- `uv run pytest`
- `swift test`
- Manual schedule launch/complete flows (lessons, quizzes, milestones) with and without milestone locks and slice pagination.

## Follow-ups
- Add end-to-end API tests for schedule launch/complete routes (including force overrides) and milestone lock telemetry assertions.
- Extend Swift UI test coverage to verify status pills, confirmation dialogs, and `Mark complete` behaviour across light/dark themes.
- Stream new launch/completion telemetry into the production dashboards and monitor for stuck `in_progress` items that never complete.
