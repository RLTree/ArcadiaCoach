# Phase 20 – Persistence Migration – Client Integration

_Status: in progress (draft October 15, 2025)_

This snapshot captures the first implementation pass for Phase 20. Key highlights:

## Backend updates
- Added `ARCADIA_PERSISTENCE_MODE` configuration with `database`, `legacy`, and `hybrid` modes to enable controlled rollback paths.
- Introduced a process-local schedule cache and `slice_schedule` helper so profile APIs can deliver paginated windows without rehydrating full schedules on every call.
- `/api/profile/{username}/schedule` now accepts `start_day`, `day_span`, and `page_token` query parameters and emits slice metadata alongside schedule items.
- Learner profile repositories gained a JSON-backed legacy implementation used when the mode is `legacy` or when `hybrid` fallback is triggered.
- Regression tests cover schedule slicing, telemetry payloads, and the new persistence fallbacks.

## macOS client updates
- `BackendService.fetchCurriculumSchedule` can request paginated slices and persists responses via the new `ScheduleSliceCache` disk cache.
- `AppViewModel` supports refreshing the full schedule, loading subsequent slices, and falling back to cached slices when offline.
- Schedule telemetry now records slice metadata (`sliceStartDay`, `sliceHasMore`, cache hits) for both refresh and incremental fetch events.

## Agent tooling
- Schedule payloads returned to the agent include slice metadata so tools can reason about paginated windows without fetching the entire horizon.

## Outstanding work
- Wire slice-aware schedule fetching into the SwiftUI surfaces (e.g., load-more affordances).
- Extend MCP widget streaming so long-horizon dashboards reuse the new slice metadata.
- Finalise documentation once deployment rollout steps are rehearsed (Render hooks, staging verification).
