# Phase 22 – ELO Integrity & Responsiveness

_Snapshot date: October 15, 2025_

## Highlights

- Deduplicated ELO category payloads across the toolchain (labels now canonicalise keys) and surfaced `elo_category_collision` telemetry whenever the goal parser emits overlapping entries.
- Trimmed `learner_profile_get` responses by supporting schedule slices end-to-end and added a `schedule_slice` telemetry event for latency tracking.
- Expanded the macOS dashboard with a "Load more sessions" control, smarter schedule caching, deduped category/track tiles, and debounced telemetry to cut duplicate slice events.
- Hardened hybrid persistence by automatically resyncing legacy profiles back into Postgres after transient failures.

## Backend Updates

- Normalised ELO category definitions inside `learner_elo_category_plan_set`, merging focus areas, rubric bands, and weights before persisting. Collisions emit structured telemetry and are covered by `tests/test_elo_category_dedup.py`.
- Added duplicate track sanitisation for the goal parser so foundation tracks stay aligned with the merged categories. `tests/test_goal_parser.py` now validates the merge heuristics.
- Canonicalised category keys using label-first slugs and deduped foundation tracks on read so legacy profiles no longer surface duplicate tiles. `backend/tests/test_profile_elo_plan.py` exercises the new POST route.
- Extended `learner_profile_get` with optional `start_day`, `day_span`, and `page_token` arguments. The function now slices schedules via `slice_schedule` and the agent instructions prompt GPT to fetch additional pages when `slice.has_more` is true.
- Instrumented `GET /api/profile/{username}/schedule` with the new `schedule_slice` telemetry event (duration, pagination payload, and cache hints). Regression coverage lives in `tests/test_schedule_refresh.py`.
- Introduced automatic resync for hybrid persistence: when the database path fails, updates land in the legacy store and the username is queued for recovery. Once the DB is available again, the store replays the legacy snapshot back into Postgres and clears the cache. See `backend/tests/test_learner_profile_resync.py` for coverage.

## macOS Client

- `CurriculumScheduleView` now exposes a "Load more sessions" button that drives `AppViewModel.loadNextScheduleSlice`. Loading states, progress indicators, and telemetry were updated to reflect paginated fetches.
- `ScheduleSliceCache` stores slices by start day and keeps an aggregated (start=0) snapshot so slice retries can recover from disk. Cache hits include the new `cacheStartDay` field in telemetry.
- Schedule telemetry is debounced inside `AppViewModel` to avoid duplicate events and now records whether payloads came from cache.

## Testing & Tooling

- Added backend unit tests for category deduplication, goal-parser track merging, schedule slice telemetry, the new ELO plan POST route, and hybrid resync behaviour.
- Extended the Swift test suite with slice caching coverage (`BackendServiceTests.testScheduleSliceCacheStoresByStartDay`) and confirmed the dashboard dedupe helpers via smoke testing.
- Full suites executed post-change: `uv run pytest` and `swift test`.

## Follow-ups

- Expand label matching to handle near-duplicates (e.g., punctuation-only differences) without merging genuinely distinct categories.
- Add automated UI tests that assert a single tile per category label to prevent regressions when new dashboard modules ship.
