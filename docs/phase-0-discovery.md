# Phase 0 – Discovery Refresh (Completed on October 12, 2025)

This document captures the current state of the Arcadia Coach app after Phase 1 upgrades and summarises the findings required to launch Phase 2.

## 1. Onboarding & Data Flow

- **Client capture:** `Views/OnboardingView.swift` now gathers `arcadiaUsername`, backend URL, OpenAI API key, long-term goal, use-case, and strengths. Values persist in `AppSettings` via `@AppStorage`.
- **Profile sync:** `HomeView` and `ChatPanel` push profile metadata into `SessionViewModel` / `AgentChatViewModel`, which include it with every backend request. The macOS client disables lesson/quiz/milestone buttons until username + backend are set.
- **Backend intake:** `backend/app/session_routes.py` wraps each request in `_run_structured`, merges metadata, writes it into `LearnerProfileStore`, and forwards it inside `ArcadiaAgentContext.request_context`.
- **Persistence:** `backend/app/learner_profile.py` stores learner profiles (`goal`, `use_case`, `strengths`, knowledge tags, memory records) in `backend/app/data/learner_profiles.json` (JSON file stub for now). `backend/app/vector_memory.py` records notes tied to the OpenAI vector store `vs_68e81d741f388191acdaabce2f92b7d5`.
- **Open questions:** We still persist to JSON; long-term plan is to migrate to a durable DB (tracked in Phase 7). No dedicated API endpoint exists for the client to read profiles outside agent calls.

## 2. Lesson & Quiz Widget Catalogue

- **Lesson blueprints:** `mcp_server/server.py` exposes `lesson_catalog` via static templates for `transformers`, `diffusion-models`, `rlhf`, plus a `general` fallback. Each blueprint returns `Card`, `List`, and `StatRow` widgets.
- **Quiz recap:** `quiz_results` generates recap cards, stat rows, and drill lists but currently uses placeholder scoring (Δ Coding Elo +18 etc.).
- **Milestones:** `milestone_update` returns celebratory cards/suggested quests; content is static and not tailored to learner goals yet.
- **Focus sprint:** not yet customised; remains as provided by MCP template.
- **Gap:** No existing widget delivers multi-question assessments or embedded code editors—the Phase 3 engine will need new MCP or backend-generated widgets.

## 3. Current ELO Categories

- `Models/GameState.swift` initialises learner ELO ratings for the following categories: `Python`, `NumPy`, `PyTorch`, `Tokenization`, `RAG`, `Eval`, `LLM-Ops`. XP and level progression are derived from `GameState.xpGain` / `levelFromXP`.
- ELO updates are applied in `ViewModels/AppViewModel.applyElo`, with quizzes currently supplying the only delta. Assignments/milestones do not yet feed ELO.
- Phase 2 must revisit this list to align categories with learner goals, add descriptive metadata, and decide which categories remain or expand.

## 4. Backend ↔ Swift Messaging Review

- **Metadata forwarding:** Lessons, quizzes, milestones, and chat requests include `username`, `goal`, `use_case`, and `strengths` metadata. Session IDs are stable per username (`SessionViewModel` hashing) and per chat instance (`AgentChatViewModel`).
- **Profile writes:** Metadata is persisted via `LearnerProfileStore.apply_metadata`. However, there is no direct path for the macOS app to fetch the latest profile outside of the agent results.
- **Assignments & daily refreshers:** `AssignmentView` still relies on the last widget envelope; there is no dedicated endpoint for daily refresher generation or for agent-triggered assessments yet.
- **Vector memory:** Memory notes are stored locally and logged, but there is no retrieval call for surfacing historical notes; future phases will need a read API/tool.

## Recommendations for Phase 2

1. Define how learner goals translate into ELO categories (taxonomy, weighting, user-facing labels) and update both Swift and backend models accordingly.
2. Plan the assessment blueprint structure (question banks, coding prompts, scoring rubrics) so Phase 3 can implement generation + UI.
3. Decide on early database migration strategy (Phase 7) to avoid rewriting storage hooks later; current JSON approach is fine for prototypes but not multi-user.
4. Document any new MCP widget requirements (code editor, response collection) to guide design work before implementation.
