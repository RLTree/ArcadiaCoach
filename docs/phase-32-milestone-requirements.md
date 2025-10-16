# Phase 32 – Milestone Requirement Modeling

**Completed:** October 16, 2025  
**Owners:** Backend + macOS Client

## Summary
- Introduced the `MilestoneRequirement` domain model and Alembic migration so curriculum schedule items persist requirement metadata across both Postgres and the legacy JSON store.
- Extended the milestone author workflow and sequencer to request, validate, and merge agent-authored requirements with deterministic fallbacks, emitting telemetry-friendly guidance and gating milestones when the learner’s ratings fall short.
- Updated REST payloads, Swift models, and the dashboard schedule UI to surface requirement badges, highlight unmet thresholds, and display coaching rationale before learners attempt a launch.
- Hardened schedule serialization plus MCP responses so `milestone_requirements` travel through widgets/chat, and expanded pytest + Swift decoding coverage to lock in the new schema.

## Testing
- `uv run pytest backend/tests/test_curriculum_sequencer.py`
- `swift test`

## Follow-ups
- Stream requirement telemetry into the hosted dashboards to monitor unlock pressure and tuning needs.
- Add SwiftUI snapshot coverage for the requirement badges/lock messaging.
- Expose coach-side prompt snippets that nudge learners toward the best rating-raising activities when requirements remain unmet.
