# Phase 12 – Sequencer Telemetry & Reliability Hardening

**Completion date:** October 14, 2025  
**Owner:** Backend / macOS cross-functional swarm

## Goals
- Capture observable metrics for schedule generation so failures and latency spikes surface quickly.
- Keep the learner’s existing schedule available when regeneration fails, instead of surfacing a blank state.
- Feed the generated schedule back into the agent so Chat replies can reference the same plan the dashboard shows.

## Delivered
- Added a structured telemetry helper that fan-outs to listeners and logs JSON payloads (`backend/app/telemetry.py`).  
- Instrumented `generate_schedule_for_user` and the `/api/profile/{username}/schedule` refresh path with success/failure metrics, durations, horizon, and item counts.
- Implemented graceful fallback: if regeneration fails we reuse the previous schedule, mark it `is_stale`, attach warnings, and surface the same message in both API and SwiftUI.
- Wired post-grading auto-regeneration so onboarding completions immediately produce a schedule.
- Extended the agent prompt instructions so Chat summarises the actual `curriculum_schedule`.
- Updated regression coverage (`tests/test_schedule_refresh.py`, `tests/test_assessment_submission_store.py`) to cover telemetry fan-out, fallback warnings, and post-grading schedule creation.

## Follow-ups
- Capture the learner’s timezone (or geo) in the macOS client so the agent can translate offsets into precise calendar dates without manual user input.
- Pipe telemetry into real observability sinks (Datadog/Grafana) once Phases 20–21 introduce persistent storage.
- Explore task-level telemetry (e.g., success ratios for attachments vs. schedule fetches) when we harden Phase 22 developer tooling.
- Ship the improved citation footnotes and interactive attachment links (tracked in the revised roadmap).

