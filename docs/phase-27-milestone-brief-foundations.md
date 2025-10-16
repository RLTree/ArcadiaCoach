# Phase 27 – Milestone Brief Foundations

**Completed:** October 16, 2025  
**Owners:** Backend + macOS Client  

## Summary
- Added structured milestone briefs (objectives, deliverables, success criteria, external work, capture prompts, prerequisite status) to the curriculum sequencer and schedule payloads.  
- Persisted milestone briefs/progress in both SQLite legacy storage and the Postgres-backed repositories, introducing an Alembic migration for `milestone_brief` / `milestone_progress`.  
- Updated session launch routes, MCP milestone tool, and the macOS client schedule view to render briefs, respect prerequisite locks, and collect learner progress notes/attachments via the new completion sheet.  
- Extended automated coverage (pytest + Swift unit tests) to assert milestone briefs split correctly, progress persists, and schedule completion telemetry marks `progress_recorded`.  

## Testing
- `uv run pytest`  
- `swift test`  

## Follow-ups
- Improve milestone copy and kickoff prompts so the brief offers concrete “first steps” guidance (see Phase 29 – Milestone Experience & Telemetry).  
- Stream milestone completion telemetry into production dashboards and expand UI coverage for locked/unlocked states.  
- Audit attachment reuse during milestone completion (surface names, previews) and fold results into the Attachment Experience Enhancements phase.  

