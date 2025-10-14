# Phase 15 – Adaptive Curriculum Evolution

**Completion date:** October 14, 2025  
**Owner:** Backend & macOS cross-functional swarm

## Goals
- Expand the curriculum sequencer to plan beyond the prior two-week horizon while respecting learner pacing signals.
- Surface per-category effort allocations and rationale history so learners understand how deferrals and assessment outcomes influence the roadmap.
- Present the pacing model and changelog directly inside the macOS dashboard.

## Delivered
- Extended the sequencer with pacing heuristics that translate recurring deferrals into lighter weekly cadences, space sessions across multi-month horizons, and insert reinforcement sprints for every module.
- Introduced foundation-aware curriculum augmentation that layers Python, data, math, ML, and delivery tracks based on learner goals and assessment performance, expanding both ELO categories and modules when gaps surface.
- Persisted `category_allocations`, `pacing_overview`, and `rationale_history` on curriculum schedules, including structured deferral metrics and narrative adjustment notes.
- Updated FastAPI schedule payloads and agents tooling to emit the new pacing metadata, with tests covering serialization via `_schedule_payload`.
- Refreshed the macOS dashboard schedule view with a pacing plan breakdown, deferral pressure badges, and a changelog timeline sourced from the new rationale history.
- Added regression coverage (`test_curriculum_sequencer_prioritises_low_scores`, `testCurriculumScheduleDecodesPacingMetadata`) to lock in the new sequencing logic and Swift decoding path.

## Validation & Testing
- `uv run pytest` inside `backend/`
- `swift test` from the repository root
- Manual dashboard review: trigger a schedule refresh, confirm pacing plan and changelog render with localized timestamps.

## Follow-ups
- Stream the new pacing metrics into telemetry dashboards (sessions per week, deferral pressure trends) to monitor real-world cadence shifts.
- Allow learners to tune preferred sessions per week directly from the macOS client, feeding the value back into the sequencer.
- Expose schedule rationale history inside chat transcripts so explanations stay visible during coaching conversations.
