# Phase 24 – Assessment Surface Lifecycle

**Completed:** October 15, 2025  
**Owner:** Arcadia Coach macOS client  

## Highlights
- Removed the dedicated **Assessment** tab once onboarding calibration finishes; the tab now reappears only when `AppViewModel.requiresAssessment` flips true (new bundle, developer reset, or resumed work in progress).
- Added a dashboard nudge (“New grading available”) that routes learners to the Assessments section, wired through `presentAssessmentResults` and tracked via `assessment_results_nudge_tapped` telemetry.
- Introduced `AssessmentResultTracker`, a pure model utility that powers unseen-result detection; `AppViewModel` exposes a published `hasUnseenAssessmentResults`, persists the last reviewed submission in `AppSettings.lastSeenAssessmentSubmissionId`, and emits `assessment_results_unseen` / `assessment_results_seen` events with ISO8601 metadata.
- Updated `DashboardAssessmentsSection` to hide the “Open assessment” button post-calibration, reinforce the onboarding relaunch affordance, and highlight recent grading when the unseen state is true.
- Strengthened state transitions in `HomeView`: conditional tab rendering, animated routing to Assessments when the nudge fires, automatic acknowledgement when the Assessments section is opened, and telemetry for manual tab selection (`assessment_tab_selected`).

## Verification
- `swift test`
- `uv run pytest`

## Follow-ups
1. Monitor the new telemetry series in staging; wire alerts once `assessment_results_unseen` shows unhealthy backlogs.
2. Explore surfacing the latest graded submission inline (auto-expanding detail view) when the unseen flag clears, per Phase 33 UI polish goals.
3. Evaluate persisting the `Run Onboarding` overlay dismissal reason so developer resets can optionally skip the reminder when testing multiple learners in succession.
