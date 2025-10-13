# Phase 9 – Feedback Drilldowns & Learner Insights (October 13, 2025)

## Scope Recap
- Provide rich grading drilldowns for assessment history entries (rubrics, attachments, ELO deltas).
- Connect grading insights to the active curriculum and milestone roadmap so learners know where to focus next.
- Offer quick navigation from dashboard and chat surfaces back to detailed graded submissions.
- Ensure agent-delivered lesson/quiz/milestone widgets render reliably inside the macOS client.

## Backend Updates
- Extended `AssessmentCategoryOutcome` and payload serializers with `starting_rating` and `rating_delta` so ELO deltas are explicitly exposed to clients.
- Normalised submission metadata into a first-class `attachments` array (`AssessmentSubmissionAttachmentPayload`) with heuristics for JSON manifests and legacy key-value hints, enabling attachment references in the UI.
- Updated `/api/profile/{username}` responses (and tool payloads) to include the new outcome fields and parsed attachments, keeping automated grading compatible with the richer schema.
- Augmented regression tests to cover attachment parsing and to assert the new rating deltas persist end-to-end.

## macOS Client Updates
- Added the inline `AssessmentSubmissionDetailView` (embedded in `Views/HomeView.swift`) to present full grading drilldowns: attachment manifests, rubric notes, per-category ELO deltas, curriculum module ties, and task-level feedback.
- Wired dashboard history rows and chat sidebar summaries with quick-detail buttons that open the new drilldown view using the shared `AppViewModel.focus(on:)` API.
- Extended models (`AssessmentSubmissionRecord`, `AssessmentCategoryOutcome`, etc.) with attachment metadata, rating deltas, and safe decoding defaults for legacy payloads.
- Introduced a “Latest Session Content” section on the dashboard (collapsible) that renders the most recent lesson, quiz, or milestone envelope so structured widgets are visible immediately after agent actions.
- Captured lesson/quiz/milestone envelopes in `AppViewModel` via new `recordLesson/recordQuiz/recordMilestone` helpers, ensuring the UI stays in sync across tabs.

## Follow-ups / Open Items
1. Automate assessment attachments end-to-end (API field, upload flow, client picker, agent ingestion) – completed in Phase 10.
2. Add unit coverage around the new `AssessmentSubmissionDetailView` once UI snapshot testing infrastructure is ready (tracked for Phase 21 automation work and Phase 23 QA).
3. Surface attachment previews (file icons or inline snippets) whenever metadata provides MIME type hints.
4. Expand curriculum linkage to include milestone backlog entries after the milestone roadmap API lands (Phase 15 dependency).
5. Evaluate pagination for submissions if attachment manifests significantly increase payload size; current cap remains the latest 12 submissions.

## Validation Checklist
1. `uv run pytest backend/tests/test_assessment_submission_store.py`
2. `swift test`
3. Manual sanity:
   - (Until Phase 10 automates attachments) trigger a fresh onboarding assessment submission with mock metadata containing an `attachments` array; confirm `/api/profile/{username}` returns parsed attachment objects with non-zero `rating_delta` values.
   - In the macOS app, load the dashboard and open the history detail; verify attachments, rubric notes, and curriculum suggestions appear, and ELO deltas match backend values.
   - From the chat sidebar, click a recent graded submission and confirm the drilldown sheet opens with identical content.
   - Launch a lesson, quiz, and milestone from the dashboard; ensure each widget envelope is rendered in the “Latest Session Content” disclosure and can be cleared via the new action.
