# Phase 17 – Foundational Validation & Horizon Expansion

**Completion date:** October 14, 2025  
**Owner:** Backend & macOS client swarm

## Goals
- Clamp goal-parser outputs so every foundation track and module publishes a strictly positive `suggested_weeks` value with automated regression coverage.
- Expand onboarding assessment generation/tests so every stored ELO category receives concept and coding diagnostics before grading.
- Extend the curriculum sequencer beyond three months, layering spaced refreshers, telemetry, and pacing heuristics that respect long-range learning cadence.

## Delivered
- Hardened goal-parser sanitisation (`backend/app/goal_parser.py`) to coerce track/module durations to positive week counts, added fallback heuristics, and refreshed tests to guard the behaviour (`backend/tests/test_goal_parser.py`).
- Updated onboarding assessment coverage to dedupe category inputs, pull augmented categories from foundation augmentation, and exercised new cases in tests so every stored category receives concept + code tasks (`backend/app/onboarding_assessment.py`, `backend/tests/test_onboarding_assessment.py`).
- Reworked the curriculum sequencer to generate multi-month horizons with spaced refresh/quiz cycles, new schedule metadata (sessions per week, projected minutes, long-range counts), and richer telemetry payloads (`backend/app/curriculum_sequencer.py`, `backend/app/profile_routes.py`, `backend/app/tools.py`, `backend/app/agent_models.py`).
- Surfaced the extended metadata in the macOS client (model updates in `Models/EloPlan.swift`, decoding tests, and refreshed `CurriculumScheduleView` outlook copy) so the dashboard highlights long-range pacing and focus categories.
- Recorded Phase 17 in the roadmap snapshots (`docs/phase-17-foundational-validation.md`).

## Validation & Testing
- `uv run ruff check`
- `uv run pytest`
- `swift test`
- `xcodebuild -project ArcadiaCoach.xcodeproj -scheme ArcadiaCoach -configuration Debug -sdk macosx build`

## Follow-ups
- Instrument production dashboards with the new long-range telemetry fields (weekly minutes, refresh counts) to inspect adoption and pacing pressure.
- Expand spaced refresher authoring so milestone briefs can trigger their own long-range items (Phase 18 dependency).
- Revisit the macOS decoding warnings in `BackendService` once the Swift 6 concurrency refactor lands (tracking under Phase 27).
