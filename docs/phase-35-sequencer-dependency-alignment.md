# Phase 35 – Sequencer Dependency Alignment

**Status:** Completed October 17, 2025

## Summary
- Introduced a Sequencer Advisor agent that reprioritises curriculum slices when milestone requirements are at risk, while keeping deterministic guardrails in place.
- Propagated dependency metadata across backend persistence, APIs, and the Swift client so learners can see why specific lessons or quizzes were scheduled ahead of milestones.
- Hardened milestone gating by surfacing unlock targets directly in dashboard UI, updated rationale history, and new telemetry for advisor usage and dependency pressure.

## Key Changes
1. **Backend**
   - Added `sequencer_advisor.py` and new settings (`ARCADIA_SEQUENCER_ADVISOR_*`).
   - Enhanced `CurriculumSequencer` with requirement pressure scoring, dependency target aggregation, advisored ordering, and new telemetry events (`sequencer_advisor_*`, `sequencer_dependency_target`).
   - Enriched persistence (`CurriculumSchedule`, `SequencedWorkItem`, `MilestoneQueueEntry`) with dependency payloads and advisor summary metadata; shipped Alembic migration `20241017_02_sequencer_advisor_metadata`.
2. **Swift Client**
   - Extended models (`DependencyTarget`, `SequencerAdvisorSummary`) and dashboard rendering to highlight unlock targets and advisor cues.
   - Updated backend decoding tests to assert the new fields.
3. **Docs & Telemetry**
   - Documented the phase deliverables, new environment variables, and follow-up instrumentation expectations.

## Testing
- `uv run ruff check`
- `uv run pytest`
- `swift test`

## Follow-ups
- Stage adviser latency & dependency-target telemetry in observability dashboards for trend monitoring.
- Extend chat/session launch flows to surface dependency targets when the advisor reshuffles upcoming work.
- Capture learner feedback on the new unlock messaging to calibrate copy and ordering heuristics for multi-milestone scenarios.
