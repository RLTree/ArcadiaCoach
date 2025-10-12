<!-- Status will be flipped to “completed” once user sign-off is captured for Phase 5 -->

# Phase 5 – Automated Grading & Initial Ratings *(awaiting sign-off)*

## Backend
- Added `backend/app/assessment_grading.py` to orchestrate grading runs through the Arcadia agent. It normalises rubric data, requests structured JSON (feedback + scores), and falls back gracefully if the agent call fails.
- Extended `assessment_submission` storage with grading payloads (`grading` field plus `apply_grading` helper) so developer dashboards surface agent feedback beside submissions.
- `LearnerProfileStore.apply_assessment_result` persists the latest grading report, marks the onboarding assessment as completed, and seeds `elo_snapshot` with per-category ratings computed from task scores.
- New endpoint `GET /api/onboarding/{username}/assessment/result` returns the stored grading payload so the macOS client can render a post-assessment briefing.
- `LearnerProfilePayload` / `LearnerProfile` now expose `onboarding_assessment_result`; agent profile tools inherit the same snapshot for follow-up coaching.
- Normalised OpenAI reasoning effort inputs to avoid `typing.Union` instantiation errors during grading runs.

## API / Data Shapes
- `POST /api/onboarding/{username}/assessment/submissions` now returns the enriched submission payload (agent feedback, strengths/gaps, category outcomes) after the grading run completes.
- Developer submissions feed (`GET /api/developer/submissions`) includes the same grading bundle for quick inspection.
- `AssessmentGradingPayload` introduces `task_results[]` (score, strengths, improvements, rubric notes) and `category_outcomes[]` (average score, initial rating, rationale).

## macOS Client
- Added `AssessmentGradingResult` models, plumbed through `BackendService` and `AppViewModel`, and taught the dashboard to block ELO stats with a centered “Waiting for assessment results…” spinner until grading completes.
- Developer Submissions dashboard now shows the agent’s overall feedback and per-category outcomes for each stored submission.

## Testing
- Added grading-aware coverage to `backend/tests/test_assessment_submission_store.py` (store persistence + FastAPI endpoints). Agent grading is monkeypatched to deterministic results; asserts cover ELO snapshot seeding and the new `/assessment/result` endpoint.
- Smoke checklist (manual):
  1. Boot backend (`uv sync && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`) with OpenAI key configured.
  2. Submit an onboarding assessment via the macOS client (or `curl`) and confirm the UI surfaces the returned briefing + updated ratings.
  3. Hit `/api/developer/submissions` to verify grading metadata is persisted, then trigger `/api/developer/reset` to clear state.

## Follow-ups
- Tune the grading prompt once we review real learner submissions (adjust score weighting vs. rubric depth, capture code-specific heuristics).
- Add integration tests that exercise the grading fallback branch and rating interpolation as more categories/tasks are introduced.
- Document the grading prompt schema under `docs/agents/` if we start customising per-category rubrics.
