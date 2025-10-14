# Phase 13 – Adaptive Curriculum MVP

**Completion date:** October 14, 2025  
**Owner:** Backend & macOS cross-functional swarm

## Goals
- Feed the curriculum sequencer output directly into onboarding so every learner starts with a rolling 2–3 week roadmap.
- Let learners defer scheduled work from the dashboard while keeping the chat view in sync.
- Capture reschedule telemetry and roll learner actions into future schedule refreshes.

## Delivered
- Regenerated the curriculum schedule immediately after onboarding plan creation, wiring sequencer output into the standard flow and logging `schedule_generation_post_onboarding`.
- Added persistent `schedule_adjustments` to learner profiles and taught the sequencer to honour them on every refresh (with `user_adjusted` flags in schedule payloads and telemetry via `schedule_adjustments_applied`).
- Shipped `POST /api/profile/{username}/schedule/adjust`, updating schedules on demand, pruning stale adjustments, and emitting structured `schedule_adjustment` events.
- Extended the macOS dashboard to highlight deferred items, surface a reschedule menu (1/3/7 day pushes), and block duplicate actions while adjustments are in flight.
- Introduced client-side telemetry for reschedule starts/completions/failures and refreshed Swift models/UI to decode and render the new `userAdjusted` state.

## Validation & Testing
- **Backend unit tests:** run `uv run pytest` inside `backend/`. This exercises sequencer adjustments (`test_schedule_generation_respects_adjustments`, `test_schedule_adjustment_endpoint_updates_schedule`) and guards the new telemetry fan-out.
- **API smoke tests:** with the backend running (`uv sync && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`), POST to `/api/onboarding/plan` for a fresh user, then hit `GET /api/profile/<username>/schedule?refresh=true` and `POST /api/profile/<username>/schedule/adjust` to verify the regenerated schedule reflects deferrals.
- **Client workflow:** build/run the macOS app (`open ArcadiaCoach.xcodeproj`) and on the Dashboard use the "Reschedule" menu to defer an item; confirm the pill highlights the adjusted row, the refresh button stays enabled, and the chat surface references the updated offsets.
- **Telemetry review:** tail the backend logs for `schedule_generation_post_onboarding`, `schedule_adjustments_applied`, and `schedule_adjustment` events to confirm adjustments are captured end-to-end.

## Follow-ups
- Allow pull-forward and free-form date selection once milestone dependencies land (Phase 14).
- Track per-category defer trends and feed them into pacing heuristics when the adaptive sequencer evolves (Phase 15).
- Add automated UI coverage for the reschedule menu and adjusted styling, and expand backend coverage to include telemetry fan-out assertions (Phase 24).
