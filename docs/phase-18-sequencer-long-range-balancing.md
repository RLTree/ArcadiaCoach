# Phase 18 – Sequencer Long-Range Balancing

**Completion date:** October 15, 2025  
**Owner:** Backend swarm

## Goals
- Distribute long-range refresher work evenly across priority categories.
- Prevent early schedule streaks that fixate on a single category and guarantee broad exposure in the first 6–8 weeks.
- Emit telemetry that surfaces category mix, streaks, and first appearances so we can monitor balance before rollout.

## Delivered
- Rebalanced module ordering with chunk-level guardrails that limit consecutive category runs and ensure the opening weeks include at least three distinct categories.
- Reworked the long-range refresher injector to iterate categories in a round-robin cycle, respecting consecutive caps while preserving prerequisite ordering.
- Introduced `_summarize_distribution` telemetry, emitting `long_range_distribution` events with per-category counts, longest streaks, window coverage, and first-week appearances.
- Added regression coverage for near-term category mix, long-range streak caps, and telemetry payload validation.
- Updated the Phase roadmap (`AGENTS.md`) and docs to reflect the new balancing instrumentation.

## Validation & Testing
- `uv run ruff check`
- `uv run pytest`
- `swift test`
- `xcodebuild -project ArcadiaCoach.xcodeproj -scheme ArcadiaCoach -configuration Debug -sdk macosx build`

## Follow-ups
- Monitor `long_range_distribution` telemetry in staging and tune category streak caps if we observe regression toward single-track runs.
- Extend the smoothing heuristics if future modules introduce cross-category prerequisites that reduce flexibility.
- Coordinate with Phase 19 milestone work so milestone unlocks also feed into the long-range distribution summary.
