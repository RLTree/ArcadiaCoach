# Phase 33 – Milestone Unlock UX & Notifications

**Completed:** October 17, 2025  
**Owners:** Backend + macOS Client

## Summary
- Introduced the Requirement Advisor service that enriches milestone prerequisites with calibrated rating targets and rationale, storing advisor metadata alongside schedule items.
- Added milestone queue modelling to curriculum schedules and API payloads so the macOS client can render a dedicated milestone dashboard with readiness badges, requirement progress, and launch controls.
- Normalised milestone completion persistence to carry project status/evaluation metadata across Postgres and legacy stores and updated schedule serialization to expose per-requirement progress snapshots.
- Implemented per-milestone macOS notifications (leveraging `UNUserNotificationCenter`) that trigger when requirements are satisfied, with user-friendly queue visuals and accessibility improvements.
- Hardened developer unlock tooling: the Boost ELO workflow now auto-completes prerequisite lessons/quizzes, preserves calibrated requirements, and refreshes telemetry so QA can immediately verify milestone readiness.
- Patched the forced milestone launch path to build a static milestone envelope when bypassing the agent, ensuring QA/dev overrides no longer crash when briefs omit optional fields.

## Testing
- `uv run pytest`
- `swift test`

## Follow-ups
- Monitor advisor telemetry to tune weighting heuristics.
- Extend the milestone queue UI with quick links to milestone briefs and completion history once user feedback lands.
- Consider persisting notification opt-in preferences and exposing them under Settings.
- Capture regression coverage for developer override workflows (Boost ELO, forced launch) whenever milestone schemas change.
