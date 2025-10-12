# Phase 2 – ELO Category Planning (Completed on October 12, 2025)

This phase equips Arcadia Coach with dynamic, learner-aligned ELO categories and exposes them to both the agent and macOS client before any onboarding assessment begins.

## What Changed

- **Backend data model:** Added `EloCategoryPlan`, `EloCategoryDefinition`, and `EloRubricBand` to `backend/app/learner_profile.py`, allowing the agent to persist category definitions (label, focus areas, weight, rubric, starting rating) alongside existing learner profiles.
- **Agent tooling:** Introduced `learner_elo_category_plan_set` (strict mode disabled) in `backend/app/tools.py`. The tool normalises category keys, writes the plan to the learner profile store, and returns the refreshed snapshot so GPT runs can immediately use the results.
- **Profile APIs:** New REST endpoints under `/api/profile` expose full learner snapshots and the extracted ELO plan, enabling the macOS app (or future services) to fetch categories without running an agent turn.
- **Plan persistence:** `LearnerProfileStore.set_elo_category_plan` resynchronises stored Elo ratings with the plan, ensuring skill keys stay consistent for future quiz updates.
- **Swift client sync:** `BackendService.fetchProfile` pulls the new plan + ratings, `AppViewModel` caches them, and `HomeView` renders an `EloPlanSummaryView` (with weight percentages, focus areas, and rubric bands) before the learner launches an assessment.
- **UI labelling:** Quiz and dashboard stat rows now map Elo keys to the friendly labels supplied in the plan, preventing slug identifiers from leaking into the UI.

## New Endpoints & Tools

| Type | Identifier | Notes |
| ---- | ---------- | ----- |
| Function tool | `learner_elo_category_plan_set` | Accepts `{username, categories[], source_goal?, strategy_notes?}` and returns the saved plan. Respects Phase 2 key normalisation. |
| REST | `GET /api/profile/{username}` | Returns the full learner profile payload (including `skill_ratings` and `elo_category_plan`). |
| REST | `GET /api/profile/{username}/elo-plan` | Returns only the stored `EloCategoryPlan` (404 when unset). |

## Swift Data Shapes

```swift
struct LearnerProfileSnapshot: Codable {
    var username: String
    var skillRatings: [SkillRating]
    var eloCategoryPlan: EloCategoryPlan?
}

struct EloCategoryPlan: Codable, Hashable {
    var generatedAt: Date
    var sourceGoal: String?
    var strategyNotes: String?
    var categories: [EloCategoryDefinition]
}
```

> Referenced in `AppViewModel.loadProfile` to align in-memory Elo snapshots with the backend plan before quizzes/assessments run.

## Outstanding / Next Phase Hooks

- Agent instructions still need explicit guidance for when to trigger `learner_elo_category_plan_set`. A future prompt tuning pass should add that once the Phase 3 assessment workflows land.
- Plan storage remains JSON-backed; database migration stays scheduled for Phase 7.
- Tests continue to mock network responses. Add backend unit coverage for profile routes when we expand the FastAPI test suite (Phase 7 scope).

## Validation

- `swift test` (Oct 12, 2025) to confirm Swift additions compile via the package target.

With categories now persisted and surfaced, Phase 3 can focus on generating personalised assessment content keyed to these weights and rubrics.
