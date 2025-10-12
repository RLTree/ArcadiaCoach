# Phase 3 – Onboarding Assessment Engine *(Completed October 12, 2025)*

This phase automates curriculum planning at the end of onboarding, persists the agent-produced plan, and introduces a guided assessment flow that captures learner responses locally before lessons begin.

## Highlights

- **Backend orchestration (`backend/app/onboarding_assessment.py`):** added structured agent prompts that generate a curriculum outline, ELO categories, and assessment tasks in one run. Results are normalised, fallback tasks are injected when the agent omits a concept/code pair, and the plan is persisted through `LearnerProfileStore`.
- **New REST surface (`/api/onboarding/...`):** macOS clients can trigger planning (`POST /api/onboarding/plan`), fetch curriculum/assessment snapshots, poll status, and update assessment state without additional agent turns.
- **Profile schema upgrades:** `LearnerProfile` now stores `curriculum_plan` and `onboarding_assessment`; tool outputs and REST payloads expose the same structures for clients and agent tools.
- **macOS experience:** onboarding now launches plan generation automatically, displays the curriculum outline on the dashboard, and opens dedicated Dashboard/Assessment tabs. The assessment overlay resizes to the viewport, scrolls independently, and tracks progress without counting untouched starter code.
- **Local response capture:** assessment drafts live in `AppViewModel.assessmentResponses`, never leaving the client. Starter code can still be inserted, but coding prompts only count as answered once the learner edits beyond the starter snippet.

## New/Updated API endpoints

| Method | Path | Notes |
| ------ | ---- | ----- |
| `POST` | `/api/onboarding/plan` | Generates (or refreshes) curriculum + assessment for a learner and returns the full profile snapshot. Optional `force=true` triggers regeneration. |
| `GET` | `/api/onboarding/{username}` | Returns the stored onboarding bundle (404 until generated). |
| `GET` | `/api/onboarding/{username}/status` | Lightweight readiness probe (plan + assessment flags, timestamp). |
| `GET` | `/api/onboarding/{username}/curriculum` | Retrieves the curriculum outline only. |
| `GET` | `/api/onboarding/{username}/assessment` | Retrieves the assessment bundle only. |
| `POST` | `/api/onboarding/{username}/assessment/status` | Updates assessment status (`pending` → `in_progress` → `completed`). |

## Client changes

- `OnboardingView` now collects learner strengths, saves settings, then calls `AppViewModel.ensureOnboardingPlan` to trigger planning before entering the app.
- `AppViewModel` tracks the curriculum plan, assessment bundle, local responses, and assessment presentation state; coding prompts now require edits beyond starter snippets before progress counts.
- `HomeView` presents a gating banner, renders the curriculum outline, and disables lesson/quiz/milestone buttons until the onboarding assessment is completed. Tabs now separate Dashboard, Assessment, Agent Chat, and Settings.
- `OnboardingAssessmentFlow` delivers tasks in a modal overlay that resizes to the viewport with rubric reminders, starter-code insertion, and progress tracking.

## Testing

- `backend/tests/test_onboarding_assessment.py` exercises the new persistence helpers and fallback task coverage.
- `uv run pytest` *(backend)*
- `swift test`
- Manual smoke test checklist:
  1. Launch the macOS app, run onboarding, and confirm the assessment overlay appears after plan generation.
  2. Complete both concept and code tasks, then mark the assessment completed—lesson/quiz buttons unlock afterwards.
  3. Refresh the home dashboard; curriculum modules and ELO plan remain visible.

## Follow-ups

- Consider persisting `assessmentResponses` between launches (e.g., via `AppStorage`) so drafts survive app restarts.
- Update agent instructions (`constants.py`) to explicitly call out the new onboarding tools and fallback expectations before production deploy.
- Expand backend unit coverage to include route-level tests once FastAPI test harness lands in Phase 7.
- Automated grading and initial ratings remain for Phase 4.
- Default web search enablement across agents is tracked under Phase 7.
