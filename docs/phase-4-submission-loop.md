# Phase 4 – Submission Loop & Developer Reset (completed October 12, 2025)

## Backend
- Added `backend/app/assessment_submission.py` for JSON-backed storage at `app/data/assessment_submissions.json`.
- New endpoints:
  - `POST /api/onboarding/{username}/assessment/submissions` – saves manual assessment responses with basic validation and word counts.
  - `GET /api/onboarding/{username}/assessment/submissions` – returns ordered submission history for the learner.
  - `GET /api/developer/submissions?username=` – developer feed of stored submissions (optionally filtered).
  - `POST /api/developer/reset` – clears learner profile + stored submissions without touching backend credentials.
- `LearnerProfileStore.delete` and developer router orchestrate profile resets. Tests cover store behaviour and HTTP plumbing (`backend/tests/test_assessment_submission_store.py`).

## macOS Client (SwiftUI)
- `SettingsView` gains a **Developer Tools** section:
  - “Developer Reset” button (confirmation dialog) invokes the backend reset and clears local profile preferences while preserving backend URL and OpenAI key.
  - “View Assessment Submissions” opens `DeveloperSubmissionDashboard`, a lightweight browser backed by `DeveloperToolsViewModel`.
- `OnboardingAssessmentFlow` now submits responses through `BackendService.submitAssessmentResponses` before marking the bundle completed; errors surface inline.
- Added `Models/AssessmentSubmission.swift` plus `DeveloperToolsViewModel` to manage resets/submission fetches.

## Testing
- `uv run pytest backend/tests` – covers submission store + developer endpoints.
- `swift test` – verifies Swift target changes build cleanly.

## Follow-up Notes
- Submission metadata currently captures client version/build/platform; extend as needed for richer analytics.
- Dashboard fetch defaults to the current learner scope; switch to “All Learners” inside the sheet to inspect global history.

