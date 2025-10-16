# Phase 31 – Agent-Authored Milestone Projects

**Completed:** October 16, 2025  
**Owners:** Backend + macOS Client

## Summary
- Added the `milestone_project_author` MCP tool which calls GPT‑5 via the Responses API to craft bespoke milestone briefs. The service enforces a strict JSON schema, configurable model/reasoning settings, and exposes a REST shortcut (`POST /author/milestone`) for the backend sequencer.
- Extended the FastAPI backend with an authoring orchestrator that requests agent copy during schedule generation, merges it with deterministic guardrails, and falls back to template briefs on transport/schema failures. Telemetry now records `milestone_author_invoked`, `milestone_author_latency`, and `milestone_author_fallback` events for observability.
- Enriched the learner data model with agent metadata (`rationale`, `authored_at`, `authored_by_model`, `reasoning_effort`, `source`, `warnings`) and surfaced the new copy across the macOS schedule view, including VoiceOver-ready rationale badges and warning callouts.
- Refined milestone presentation: schedule cards now show a concise snapshot with optional expansion for full briefs, and session launch content opens directly on the authored instructions without legacy preambles.

## Testing
- `uv run pytest backend/tests/test_curriculum_sequencer.py`
- `swift test`

## Follow-ups
- Stream the new milestone author telemetry into hosted dashboards once production traffic lands.
- Add qualitative review tooling for authored briefs (spot-check output quality, prompt health).
- Explore incremental caching so identical module/context pairs reuse recent agent copy when appropriate.
