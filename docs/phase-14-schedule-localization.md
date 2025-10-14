# Phase 14 – Schedule Localization & Time Semantics (Completed October 14, 2025)

## Summary

- Persist the learner’s timezone across onboarding, chat metadata, and the backend profile store so every schedule and prompt can reference local time automatically.
- Translate `recommended_day_offset` values into concrete calendar dates (with local timezone abbreviations and DST-aware formatting) for API responses, agent prompts, and SwiftUI schedule views.
- Added a `current_time` function tool so Arcadia Coach can retrieve exact timestamps without asking the learner, defaulting to the learner’s timezone when available.
- Render upcoming schedule items in the macOS dashboard with localized date headings and per-item timestamps, mirroring the summarised schedule injected into chat prompts.

## Follow-ups

- Add telemetry around `current_time` usage and schedule summary formatting to catch timezone mismatches in production.
- Provide a user-facing override in Settings so learners can switch timezones without rerunning onboarding.
- Incorporate localized date strings into downloadable/exported artifacts (e.g., milestone briefs) to keep all learner-facing materials consistent.
