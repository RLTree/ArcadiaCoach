# Phase 29 – Milestone Experience & Telemetry

**Completed:** October 16, 2025  
**Owners:** Backend + macOS Client

## Summary
- Enriched milestone schedule payloads with `milestone_guidance` (state, badges, next actions, warnings) and expanded briefs (kickoff steps, coaching prompts) so the agent, dashboard, and MCP widgets share actionable guidance.
- Persisted schedule launch and milestone completion telemetry by registering a backend listener that stores events in `persistence_audit_events`, exposing the new `GET /api/profile/{username}/telemetry` endpoint for the macOS client.
- Updated the dashboard schedule view to render guidance chips, in-progress warnings, and milestone alert panels fed by the telemetry feed; the MCP milestone widget now surfaces kickoff/coaching details alongside the checklist.
- Extended Python + Swift tests (`uv run pytest`, `swift test`) to cover telemetry persistence and decoding of the new milestone fields.

## Testing
- `uv run pytest`
- `swift test`

## Follow-ups
- Capture additional telemetry event types (e.g., schedule refresh failures) and surface them in the dashboard alert panel.
- Add UI snapshot coverage for the new milestone alert states and guidance chips to prevent regressions.
- Evaluate streaming telemetry (Render dashboards) once the persistence migration alerting work (Phase 34+) begins.
