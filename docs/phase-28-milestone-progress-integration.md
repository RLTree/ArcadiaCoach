# Phase 28 – Milestone Progress Integration

**Completed:** October 16, 2025  
**Owners:** Backend + macOS Client

## Summary
- Persist milestone completion history in Postgres and the legacy JSON store, exposing it through learner profile and schedule payloads, with ELO nudges and telemetry instrumentation.  
- Updated curriculum sequencing to prioritise categories lacking recent milestone completions, preserved milestone progress on schedule regeneration, and surfaced completion context in rationale entries and events.  
- Enhanced the macOS client with decoding, AppViewModel state, and dashboard UI to display recent milestone wins, keeping schedules and caches in sync with backend milestone history.

## Testing
- `uv run pytest tests/test_schedule_refresh.py tests/test_curriculum_sequencer.py`
- `swift test`

## Follow-ups
- Extend milestone completion payloads to include agent-authored coaching prompts once Milestone Experience & Telemetry (Phase 29) lands.  
- Add UI snapshot coverage for the milestone history section and consider telemetry for milestone completion view engagement.
