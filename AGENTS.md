# Repository Guidelines

## Project Structure & Module Organization
- `backend/`: FastAPI entrypoint (`app/`), agent tooling, curriculum sequencer, and upload/grading services. Treat this as the source of truth for agent orchestration, REST APIs, and persistence helpers.
- `mcp_server/`: FastMCP-compatible widget service that streams lesson/quiz/milestone/focus sprint envelopes to the agent. Run this locally when developing widget payloads.
- `Resources/`, `Views/`, `ViewModels/`, `Services/`, `Models/`, `Tests/`: macOS SwiftUI client. Widgets live under `Resources/Widgets/`, shared assets stay in `Resources/`, and unit tests belong in `Tests/`.
- `docs/`: Phase snapshots, runbooks, and troubleshooting guides (kept in lockstep with the roadmap).
- `openai-agents-python/`, `openai-chatkit-advanced-samples/`: upstream SDK examples referenced during prototyping—do not modify unless syncing from upstream.
- Root-level config (`prompts-agents-maintenance.md`, `render.yaml`, `Package.swift`, etc.) describes deployment, prompt hygiene, and Swift package settings.

## Build, Test, and Development Commands
- Backend: `cd backend && uv sync && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- MCP widgets: `cd mcp_server && uv sync && uv run python server.py --host 127.0.0.1 --port 8001`.
- Backend lint/tests: `cd backend && uv run ruff check && uv run pytest`.
- macOS client: `open ArcadiaCoach.xcodeproj` → build/run the **ArcadiaCoach** scheme (Debug for development, Release for distribution).
- Swift unit tests: run `swift test` from the repository root so model + view-model coverage executes.
- Always open `ArcadiaCoach.xcodeproj` and build the **ArcadiaCoach** scheme before shipping changes; `swift test` can pass while an actual Xcode build fails due to UI or integration issues, so treat the full app build as part of the standard test matrix.

## Coding Style & Naming Conventions
- Python: Black/PEP 8, 4-space indents, snake_case. Keep docstrings concise and run `uv run ruff check` plus `uv run pytest` before pushing.
- Swift: 4-space indents, UpperCamelCase types, lowerCamelCase members. Widget JSON assets stay in PascalCase (e.g., `ArcadiaChatbot.widget`).
- TypeScript/JS (sample integrations): Prettier defaults with camelCase functions/variables and PascalCase components. Treat `openai-*` sample folders as read-only unless explicitly prototyping.

## Testing Guidelines
- Backend: add pytest coverage under `backend/tests/` (use `test_<feature>.py` naming). Every new service (e.g., curriculum sequencer, assessment storage) needs happy path + failure mode tests.
- Swift: group tests by feature (`Tests/<FeatureName>Tests.swift`) and cover onboarding, assessment delivery, dashboard history, and chat continuity.
- Aim for ≥80 % coverage on new modules; document any gaps in PR descriptions and open follow-up tasks when deferring tests.

## Commit & Pull Request Guidelines
- Commit messages follow `<scope>: <imperative summary>` (e.g., `backend: add curriculum sequencer`). Keep commits focused; include migration or data backfill notes in the body when relevant.
- Pull Requests require a concise summary, explicit testing checklist (`uv run …`, `swift test`, screenshots for UI), and links to roadmap phases or issues. Request reviews from backend and client owners when touching both stacks.

---

# Arcadia Coach Agent Overview

Arcadia Coach runs on the custom FastAPI backend + OpenAI Agents SDK (Path 2) with MCP widgets and vector-backed memory. Keep this section current with production configuration and local workflows.

## Current Production Agent

| Field | Value |
|-------|-------|
| Agent Name | Arcadia Coach |
| Agent ID | (stored in Render env var `ARCADIA_AGENT_ID`) |
| Supported Models | `gpt-5`, `gpt-5-codex`, `gpt-5-mini`, `gpt-5-nano` (fallbacks default to `gpt-5`) |
| Default Model | `gpt-5` (`ARCADIA_AGENT_MODEL`) |
| Reasoning Effort | `medium` (`ARCADIA_AGENT_REASONING`; prompt overlay upgrades per turn) |
| Web Search | Off by default (`ARCADIA_AGENT_ENABLE_WEB=false`); toggled per chat turn in the macOS client |

## Tools

The agent is configured with:

| Tool | Purpose |
|------|---------|
| `HostedMCPTool` (`Arcadia_Coach_Widgets`) | Serves lesson/quiz/milestone/focus sprint widgets |
| `FileSearchTool` | Queries Arcadia’s vector store (summary decks, docs) |
| `WebSearchTool` | Optional web context when `webEnabled=true` |
| `progress_start` / `progress_advance` | Multi-step progress overlay inside lessons/quizzes |
| `learner_profile_get` / `learner_profile_update` | Retrieve and persist learner profile fields |
| `learner_memory_write` | Append structured memory into the learner vector store |
| `elo_update` / `learner_elo_category_plan_set` | Maintain ELO snapshots and category plans

Hosted MCP calls are proxied through the backend (see `backend/app/arcadia_agent.py` and `backend/app/tools.py`).

MCP endpoint: `https://mcp.arcadiacoach.com/mcp` (Render service). It exposes:

- `lesson_catalog`
- `quiz_results`
- `milestone_update`
- `focus_sprint`

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Responses/Agents API key |
| `ARCADIA_AGENT_MODEL` | Default agent model (string literal from `SUPPORTED_MODELS`) |
| `ARCADIA_AGENT_REASONING` | Reasoning effort literal: `minimal` / `low` / `medium` / `high` |
| `ARCADIA_AGENT_ENABLE_WEB` | Toggle web search default (macOS UI can override per turn) |
| `ARCADIA_DATABASE_URL` | PostgreSQL connection string (required for Phase 19+). |
| `ARCADIA_DATABASE_POOL_SIZE` | Optional SQLAlchemy pool size (defaults to 10). |
| `ARCADIA_DATABASE_MAX_OVERFLOW` | Optional overflow connection limit (defaults to 10). |
| `ARCADIA_DATABASE_ECHO` | Set `true` to log SQL statements locally. |
| `ARCADIA_DB_MIGRATION_TIMEOUT` | Seconds the migration runner waits for the database before failing (default `60`). |
| `ARCADIA_DB_MIGRATION_POLL_INTERVAL` | Seconds between readiness probes during migrations (default `3`). |
| `ARCADIA_DB_MIGRATION_REVISION` | Optional Alembic revision override for the migration runner (default `head`). |
| `ARCADIA_DB_TELEMETRY_INTERVAL` | Minimum seconds between database pool telemetry events (set to `0` to log every checkout/checkin). |
| `ARCADIA_PERSISTENCE_MODE` | Selects the active persistence backend: `database` (default), `legacy`, or `hybrid` fallback. |
| `ARCADIA_MCP_URL` | MCP server URL (local dev defaults to `http://127.0.0.1:8001/mcp`) |
| `ARCADIA_MCP_LABEL` | Label shown in the tool config (default `Arcadia_Coach_Widgets`) |
| `ARCADIA_MCP_REQUIRE_APPROVAL` | MCP approval strategy (default `never`) |
| `ARCADIA_DEBUG_ENDPOINTS` | `true` to expose debugging routes in non-production builds |

## Local Debugging Checklist

1. Export env vars (or create `backend/.env`):
   ```bash
   export OPENAI_API_KEY=sk-...
   export ARCADIA_MCP_URL=http://127.0.0.1:8001/mcp   # if running MCP locally
   export ARCADIA_AGENT_MODEL=gpt-5
   ```
2. Start the MCP server:
   ```bash
   cd mcp_server
   uv run python server.py --host 127.0.0.1 --port 8001
   ```
3. Apply database migrations (first run and whenever schema changes land):
   ```bash
   cd backend
   python -m scripts.run_migrations
   ```
   _Need a specific revision?_ Use `uv run alembic upgrade <revision>` instead. Backfill legacy data with `uv run python -m scripts.backfill_json_stores` if needed.
4. Start the backend:
   ```bash
   cd backend
   uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
5. Test the agent directly:
   ```python
   from agents import Runner, RunConfig, ModelSettings
   from backend.app.arcadia_agent import ArcadiaAgentContext, get_arcadia_agent

   agent = get_arcadia_agent("gpt-5", False)
   context = ArcadiaAgentContext.model_construct(thread=..., store=..., request_context={})
   Runner.run_sync(agent, "learn transformers", context=context,
                   run_config=RunConfig(model_settings=ModelSettings()))
   ```
6. On the macOS Dashboard, use the **Upcoming Schedule** refresh button to hit `GET /api/profile/<username>/schedule?refresh=true` and confirm cadence notes/day offsets match the backend response.
7. (Optional) Snapshot pool health for on-call handoffs:
   ```bash
   cd backend
   python -m scripts.db_metrics
   ```

**Hosted-only limitation:** The production backend runs at `https://chat.arcadiacoach.com`, and the MCP server lives at `https://mcp.arcadiacoach.com` (tool base URL `https://mcp.arcadiacoach.com/mcp`). Because OpenAI requires the domain to be pre-approved, we cannot exercise the full stack against localhost; all integration tests must target the hosted endpoints.

## Widgets

- `Resources/Widgets/ArcadiaChatbot.widget` powers the ChatKit embed (served via `ChatPanel`).
- MCP widgets return `Card`, `List`, `StatRow`, and other envelope types. The backend normalises props before returning to Swift to keep widget schemas stable across releases.

Keep this section up to date as agent configuration changes (new tools, model upgrades, etc.).

---

# Arcadia Coach Vision & Goals

Arcadia Coach is being upgraded into an adaptive, goal-driven coding mentor for AuDHD learners. The app must:

- Onboard each learner with a username + OpenAI key, then capture their long-term coding goals, intended use-cases, current strengths, and accessibility needs via an agent-led conversation.
- Let the agent decide when it needs more context before designing a long-term curriculum, and generate lessons, assignments, quizzes, and milestone projects that stay aligned with those goals.
- Maintain persistent memory of goals, knowledge state, completed work, and next steps; agents default to web-enabled GPT‑5 / GPT‑5‑codex with high reasoning for content creation, grading, and support.
- Deliver thorough, presentation-style, AuDHD-friendly lessons and interactive assessments entirely inside the app; quizzes and assignments are graded in-app and feed the player’s ELO ratings.
- Run daily science-backed refreshers and mini comprehension checks before new material.
- Keep the milestone system gated by ELO thresholds: milestones unlock once users demonstrate proficiency, contribute to—but do not solely drive—ELO progression, and provide clear success criteria while being executed outside the app (with in-app coaching).
- Present a sleek macOS UI with sidebar navigation (ELO dashboard by category, chatbot, settings, help) and support milestone/project tracking.

All upgrades must preserve these goals while improving agent orchestration, memory, and experience cohesion.

---

# Implementation Roadmap

Use the roadmap below to scope future tasks. When a phase is “completed”, new threads should snapshot the resulting state before moving on.

1. **Phase 0 – Discovery Refresh** ✅ *(completed October 12, 2025; see `docs/phase-0-discovery.md`)*
   - Map current onboarding data flow.
   - Catalogue existing lesson/quiz widgets.
   - Document present ELO categories.
   - Confirm backend ↔ Swift messaging gaps for profile + session metadata.
2. **Phase 1 – Goal Intake & Profile Memory** ✅ *(completed October 12, 2025; see `docs/phase-1-goal-intake.md`)*
   - Harden the new profile capture.
   - Persist learner goals/use-case/strengths.
   - Expose profile/memory agent tools seeded with vector store `vs_68e81d741f388191acdaabce2f92b7d5`.
3. **Phase 2 – ELO Category Planning** ✅ *(completed October 12, 2025; see `docs/phase-2-elo-category-planning.md`)*
   - Enable the agent to call `learner_elo_category_plan_set` and persist goal-aligned skill categories with weights + rubrics.
   - Sync category plans into learner profiles and expose `/api/profile/{username}` + `/api/profile/{username}/elo-plan` for the client.
   - Update the macOS app to fetch and display the stored plan (Home dashboard + quiz summaries) before assessments begin.
4. **Phase 3 – Onboarding Assessment Engine** ✅ *(completed October 12, 2025; see `docs/phase-3-onboarding-assessment.md`)*
   - Trigger automatic curriculum planning immediately after onboarding completes, without requiring a manual chat turn.
   - Derive the learner’s ELO category plan directly from the generated curriculum and persist it for client use.
   - Generate and cache a personalised assessment (conceptual + coding tasks per category) once the plan exists.
   - Build MCP widgets + SwiftUI flows for multi-question delivery with embedded code editor.
   - Capture user responses locally and block assessment launch until curriculum + categories are ready.
   - Resize the macOS assessment overlay to fit smaller viewports and only count coding prompts as answered after edits beyond starter code.
5. **Phase 4 – Submission Loop & Developer Reset** ✅ *(completed October 12, 2025; see `docs/phase-4-submission-loop.md`)*
   - Add the developer-facing reset control that clears learner profile + local assessment state (preserves stored OpenAI key and backend settings).
   - Expose a manual submission endpoint + storage path for completed assessment responses.
   - Provide a lightweight dashboard view to inspect stored submissions for debugging.
6. **Phase 5 – Automated Grading & Initial Ratings** ✅ *(completed October 12, 2025; see `docs/phase-5-automated-grading.md`)*
   - Wire automated grading into the onboarding submission loop, persist rubric-aligned feedback, and seed initial ELO ratings from the resulting scores.
   - Surface grading summaries to the macOS dashboard (with a loading gate while grading runs) and mirror the data in developer tooling for inspection.
   - Follow-ups: tune the grading prompt after analysing real submissions, add integration tests that cover the fallback path and rating interpolation, and document the grading schema for future prompt work.
7. **Phase 6 – Frontend Chat & Accessibility Enhancements** ✅ *(completed October 13, 2025; see `docs/phase-6-frontend-chat-accessibility.md`)*
   - Deliver the upgraded Agent Chat panel with per-model capability picker, reasoning effort controls, attachment rendering, and a persisted transcript sidebar.
   - Harden attachment policies (full files for GPT-5/Mini, images-only for GPT-5 Codex) while keeping web search available per model selection.
   - Follow-up: move the “read attachments before responding” guidance into the chat prompt so `file_search` is always invoked when files are present (tracked under Phase 33).
8. **Phase 7 – Chat Continuity & Prompt Hardening** ✅ *(completed October 13, 2025; see `docs/phase-7-chat-continuity.md`)*
   - Centralise prompt overlays so GPT-5/Mini always run `file_search` on attachments, GPT-5 Codex leans on inline previews, and web-enabled turns call `web_search` with Markdown hyperlink citations.
   - Add session resume support in the macOS client (active transcript tracking, sidebar ordering, resume button) without resetting backend threads.
   - Render chat bubbles with Markdown-aware text so citations and links are clickable inside the app.
   - Follow-ups: add automated tests to confirm `file_search`/`web_search` tool invocation sequences, track hyperlink rendering inside MCP widgets, capture telemetry on tool success rates (see Phases 24 & 27), and decouple reasoning effort selection from model selection so users can mix any reasoning tier with any supported model.
9. **Phase 8 – Dashboard Assessment History** ✅ *(completed October 13, 2025; see `docs/phase-8-dashboard-assessment-history.md`)*
   - Add dashboard readiness summary, submission history list, and calibrated ELO callouts, mirrored in the chat sidebar for continuity.
   - Extend backend profile payloads and Swift models with assessment submission history plus legacy-safe decoding to avoid regressions during rollout.
   - Follow-ups: add UI regression tests for readiness states, instrument telemetry on history/grade status transitions, monitor payload growth (introduce pagination if needed), and remove the legacy decode shim once the persistence migration standardises the schema (Phases 24–25).
10. **Phase 9 – Feedback Drilldowns & Learner Insights** ✅ *(completed October 13, 2025; see `docs/phase-9-feedback-drilldowns.md`)*
    - Delivered detailed submission drilldowns with rubric notes, attachment manifests, and category ELO deltas in both dashboard and chat surfaces.
    - Normalised assessment submissions to include parsed attachments and explicit rating deltas across backend APIs and client models.
    - Captured the latest lesson/quiz/milestone envelopes so learners can revisit content immediately after agent actions.
   - Follow-ups: add UI coverage for the new detail view (Phase 29) and expand curriculum tie-ins alongside the milestone roadmap (Phase 22).
   
11. **Phase 10 – Assessment Attachment UX & Agent Ingestion** ✅ *(completed October 13, 2025; see `docs/phase-10-assessment-attachment-ux-agent-ingestion.md`)*
    - Replaced the metadata workaround with a structured `attachments` array on submissions, populated from the new attachment store (legacy metadata remains a fallback parser).
    - Shipped the full upload pipeline: REST endpoints, on-disk persistence, developer reset purge, and a macOS attachment manager (file picker + link entry) that auto-populates submissions.
    - Surfaced structured attachments across profile/developer APIs and piped attachment descriptors into grading payloads so the agent can ingest learner-provided context.
    - Extended regression coverage for upload/link/delete flows, download endpoints, and submission payloads to guard the new storage/ingestion path.
    - Follow-ups: add inline previews for common attachment types, capture ingestion telemetry, harden storage encryption ahead of the persistence migration, and resolve Swift 6 concurrency warnings raised by shared formatters (see follow-up assignments under Phases 18–21, 25, 26, and the new Known Corrections entry).
12. **Phase 11 – Curriculum Sequencer Foundations** ✅ *(completed October 13, 2025; see `docs/phase-11-curriculum-sequencer-foundations.md`)*
    - Delivered a deterministic sequencing service that prioritises lessons, quizzes, and a milestone using learner goals, ELO snapshots, curriculum modules, and assessment deltas.
    - Persisted schedules on learner profiles, surfaced them via `GET /api/profile/{username}/schedule`, and added a dashboard refresh control backed by the new endpoint.
    - Normalised shared schedule models/tests so both backend and macOS client decode the same schema; follow up with telemetry and chat consumption work during Phase 12.
    - Follow-ups: instrument schedule generation telemetry, add failure fallbacks, and pipe schedule summaries into the chat overlay (tracked in Phase 12 and Phase 13).
13. **Phase 12 – Sequencer Telemetry & Reliability Hardening** ✅ *(completed October 14, 2025; see `docs/phase-12-sequencer-telemetry.md`)*
    - Instrumented schedule generation and refresh paths with structured telemetry (duration, item count, horizon, status) and a reusable logger/listener helper.
    - Added resilient fallbacks: failed refreshes now reuse the previous schedule, mark it `is_stale`, and surface warning metadata to both API and SwiftUI.
    - Triggered automatic schedule regeneration immediately after onboarding grading and updated the agent prompt so Chat answers reference `curriculum_schedule` data.
    - Expanded regression coverage for telemetry fan-out, fallback warnings, and post-grading schedule creation.
    - **Follow-ups:** Stream telemetry into production observability once the persistence migration lands and finish the richer citation UX (tracked under Phase 26).
14. **Phase 13 – Adaptive Curriculum MVP** ✅ *(completed October 14, 2025; see `docs/phase-13-adaptive-curriculum-mvp.md`)*
    - Regenerated curriculum schedules immediately after onboarding so every learner leaves planning with a populated 2–3 week roadmap.
    - Persisted learner `schedule_adjustments`, surfaced `user_adjusted` flags in schedule payloads, and taught the sequencer to honour deferrals on refresh.
    - Added the `/api/profile/{username}/schedule/adjust` endpoint, dashboard reschedule controls, and telemetry covering adjustment requests and applied deltas.
    - Hardened schedule refresh performance by short-circuiting identical regenerations so the backend skips redundant writes.
    - **Follow-ups:** Localise schedule output to the learner’s timezone (Phase 14), monitor `schedule_generation` telemetry for unexpected spikes, and extend UI affordances for pulling work forward.
15. **Phase 14 – Schedule Localization & Time Semantics** ✅ *(completed October 14, 2025; see `docs/phase-14-schedule-localization.md`)*
    - Persisted learner timezone context end-to-end (onboarding, client metadata, backend profiles) so scheduling logic always knows the correct locale.
    - Localised curriculum schedules across APIs, chat prompts, and SwiftUI with DST-aware dates and timezone abbreviations.
    - Added the `current_time` agent tool and prompt guidance so Arcadia Coach can report precise, localised timestamps without asking the learner.
    - Refreshed dashboard schedule views to show per-item local timestamps that mirror the agent’s schedule summaries.
    - **Follow-ups:** Instrument `current_time` usage and localisation telemetry, expose a user-facing timezone override, and extend localisation to exported artefacts (milestone briefs, summaries).
16. **Phase 16 – Adaptive Foundations & Assessment Overhaul** ✅ *(completed October 14, 2025; see `docs/phase-16-adaptive-foundations.md`)*
    - Stand up a dedicated *Goal Parser Agent* that ingests the learner’s long-term goals, strengths, and context, then infers the complete stack of prerequisite languages, frameworks, libraries, and tooling (e.g., Python, SQL, Pandas, CUDA, SwiftUI) needed to achieve that vision.
    - Maintain a living curriculum module library (templates are modular building blocks, not rigid scripts) so the agent can assemble, adapt, or synthesize beginner-to-expert progressions for each inferred technology—duplicating, remixing, or authoring new modules whenever the library lacks coverage.
    - Redesign the onboarding assessment into a longer, multi-section evaluation (conceptual, coding, data manipulation, architecture, tooling) so the agent has broad coverage to baseline current knowledge and confidence.
    - Generate dynamic ELO category plans that grow beyond five categories, with the agent weighting new foundational categories whenever the learner indicates gaps (“I don’t know”) or the assessment scores reveal missing fundamentals.
    - Update schedule and module sequencing logic to deliver multi-month roadmaps that revisit foundations until mastery thresholds are hit, with reinforcement lessons tied directly to the agent’s goal-to-foundation mapping.
    - **Follow-ups:** instrument telemetry that shows which goal-parser inferences and foundation tracks are activated per learner, add low-friction tooling to author new module templates, and explore adaptive assessment shortening once mid-course mastery is demonstrated.
17. **Phase 17 – Foundational Validation & Horizon Expansion** ✅ *(completed October 14, 2025; see `docs/phase-17-foundational-validation.md`)*
    - Clamped goal-parser outputs so every track and recommended module emits a strictly positive `suggested_weeks`, with validation mirrored in Swift decoding.
    - Guaranteed onboarding assessment coverage for every stored ELO category (concept + code + scenario), adding regression tests and lightweight defaults for template gaps.
    - Extended the curriculum sequencer to plan multi-month horizons and emit additional pacing metadata (sessions/week, projected weekly minutes, long-range counts) consumed by the macOS client.
    - Logged horizon telemetry (duration, category allocations, refresh cadence) to observe load and deferral pressure across the extended roadmap.
    - **Follow-ups:** surface extended-horizon summaries inside chat and dashboard once telemetry confirms the cadence is stable, and stream the new telemetry into production observability (coordinate with the updated Phases 20 & 22).
18. **Phase 18 – Sequencer Long-Range Balancing** ✅ *(completed October 15, 2025; see `docs/phase-18-sequencer-long-range-balancing.md`)*  
    - Reordered module chunk sequencing with guardrails that cap consecutive streaks and ensure the opening 6–8 weeks represent at least three categories.  
    - Enforced dependency-aware curriculum ordering so prerequisite modules always precede dependent work before applying priority-based mixing.  
    - Split oversized lessons/quizzes/milestones into ≤120-minute parts so long-form content stretches over additional sessions instead of being trimmed.  
    - Reworked `_inject_long_range_refreshers` into a round-robin cycle so long-range lessons and quizzes rotate across priority categories while respecting prerequisite ordering.  
    - Added `_summarize_distribution` telemetry and emit `long_range_distribution` with per-category counts, longest runs, first-week appearances, and near-term coverage.  
    - Backfilled regression coverage for near-term mixing, long-range streak caps, and telemetry payloads, then refreshed roadmap/doc snapshots to highlight the balancing instrumentation.  
    - **Follow-ups:** Monitor the new telemetry in staging, adjust streak caps if imbalance resurfaces, and feed milestone unlock signals into the distribution summary during Phase 20.

19. **Phase 19 – Persistence Migration – Data Layer** ✅ *(completed October 15, 2025; see `docs/phase-19-persistence-migration.md`)*  
    - Replaced the JSON-backed stores with SQLAlchemy repositories and Alembic migrations so learner profiles, submissions, schedules, and attachments now live in PostgreSQL.  
    - Added connection management helpers, pooling defaults, and a `backfill_json_stores.py` utility to migrate historical data safely.  
    - Documented new database env vars, developer workflow updates, and Render rollout steps so teammates can apply migrations consistently.  
    - **Follow-ups:** automate Alembic migrations within the deployment pipeline, add database health/telemetry dashboards, and harden rollback tooling (tracked under Phases 21 and 35).

20. **Phase 20 – Persistence Migration – Client Integration** ✅ *(completed October 15, 2025; see `docs/phase-20-persistence-migration-client.md`)*  
    - Added persistence-mode switching (`database` / `legacy` / `hybrid`) so phased rollouts can fail over safely.  
    - Delivered schedule pagination + caching for backend APIs, the macOS client, and agent tooling to reduce payload size.  
    - Updated Swift models and telemetry to handle slice-aware refresh flows with offline caches.  
    - **Follow-ups:** finish ELO category deduplication and schedule slice adoption telemetry (tracked in Phase 22) and extend slice support to MCP widgets (Phase 24).

21. **Phase 21 – Persistence Migration – Automation & Observability**
    - Add Render deploy hooks or workers that run Alembic migrations automatically and block deploys on schema drift.
    - Stand up database monitoring (connections, slow queries, storage, vacuum stats) and route alerts into the existing telemetry stack.
    - Cement disaster-recovery playbooks: validate backups, rehearse failover, and document rollback steps for the new PostgreSQL store.
22. **Phase 22 – ELO Integrity & Responsiveness**
    - Enforce unique ELO category labels/keys by deduplicating goal-parser outputs, merging focus areas, and adding regression tests plus telemetry alerts for collisions.
    - Complete schedule slice adoption across backend tools, macOS UI, and agent prompts; minimise payload size and surface latency dashboards.
    - Optimise client-side caching/telemetry batching to reduce schedule refresh lag and capture responsiveness metrics for future tuning.
    - Harden persistence fallbacks so hybrid mode auto-recovers from database outages without exposing stale or duplicate categories.
23. **Phase 23 – Milestone Brief Foundations**
    - Generate detailed milestone briefs (objectives, deliverables, success parameters) that live entirely in-app.
    - Clarify which work must happen outside the app while capturing progress notes and artefacts back into Arcadia.
    - Ensure briefs surface prerequisite lessons/quizzes and ELO dependencies before milestones unlock.
24. **Phase 24 – Milestone Progress Integration**
    - Feed milestone completion data into the sequencer so future lessons/quizzes adjust automatically.
    - Display milestone status and outstanding deliverables across dashboard, chat, and MCP widgets using the new slice endpoints.
    - Extend paginated schedule delivery to MCP widgets and chat overlays to keep milestone context lightweight.
25. **Phase 25 – Lesson Deck Foundations**
    - Render lessons as presentation-style decks with narrative slides, inline code/examples, and citations to supporting papers/docs.
    - Establish shared deck components and export formats so both chat and dashboard views reuse the same content.
    - Ensure lessons remain self-contained so learners can progress without leaving the app while still offering optional deep-dive links.
26. **Phase 26 – Lesson Comprehension & Knowledge Checks**
    - Bundle comprehension checks at the end of each lesson and sync outcomes into the sequencer and ELO model.
    - Add lightweight progress indicators and reminders so learners know when to complete follow-up checks.
    - Resolve outstanding Swift concurrency warnings tied to shared formatters introduced by the new lesson components.
27. **Phase 27 – Attachment Experience Enhancements**
    - Extend attachment presentation with inline previews/captions and map `file_search` IDs to human-readable filenames and titles.
    - Harden upload/preview flows for large artifacts with resumable transfers and checksum validation.
    - Document attachment lifecycle policies ahead of persistence migration completion.
28. **Phase 28 – Citation UX & Linking**
    - Refresh the agent + client rendering pipeline so Markdown citations consistently show richer metadata across chat, lessons, and dashboard views.
    - Surface backend citation metadata in UI chip components with quick-open/download affordances.
    - Add regression coverage ensuring citation targets remain accessible after persistence migration.
29. **Phase 29 – Interactive Quiz Runner**
    - Build an in-app quiz runner with interactive question types, attempt tracking, and immediate feedback loops.
    - Instrument quizzes so outcomes are stored alongside attempt metadata for follow-up analysis.
    - Ensure accessibility and offline considerations are met for the new quiz surfaces.
30. **Phase 30 – Assessment Review & Feedback Loop**
    - Provide review surfaces so learners can revisit answers, rationales, and references across attempts.
    - Route quiz outcomes into ELO updates and adaptive curriculum adjustments with clearer explanations of rating changes.
    - Capture telemetry on assessment retries to inform future sequencing heuristics.
31. **Phase 31 – Reassessment & Refresh Cadence**
    - Schedule periodic reassessments and surface their status alongside historical submissions.
    - Adapt refresher frequency based on recent grading outcomes and learner momentum.
    - Define thresholds for triggering reassessment vs. lightweight check-ins.
32. **Phase 32 – Developer Code Tooling Enhancements**
    - Add code-entry affordances (syntax highlighting, editor shortcuts) and evaluate optional lint/run hooks for in-app prompts.
    - Ensure accessibility preferences (font sizing, colour choices) are respected in the coding surface.
    - Provide developer-oriented toggles for sandboxed execution once backend support exists.
33. **Phase 33 – API Reliability & Test Coverage**
    - Expand automated tests for profile, assessment, and submission endpoints (happy path, retries, and grading fallbacks).
    - Add contract tests for assessment history payloads, including legacy compatibility verification.
    - Integrate the new telemetry signals into CI to guard against tool invocation regressions and attachment ingestion failures.
34. **Phase 34 – Evaluation & Benchmarking Framework**
    - Validate GPT-graded outcomes against representative human reviews and build a replayable evaluation harness.
    - Curate ground-truth datasets across lesson types and surface scorecards to the team.
    - Track model drift and regression deltas, feeding results into adaptive curriculum decisions.
35. **Phase 35 – Adaptive Safety & Prompt Hardening**
    - Tune grading and response prompts (language, scoring thresholds, guardrails) using insights from the evaluation framework.
    - Revisit default model/web-search settings, codify safety policies, and document escalation paths for risky content.
    - Align tooling with OpenAI policy updates and ensure guardrail prompts are centrally versioned.
36. **Phase 36 – QA & Release Readiness**
    - Run full-stack QA passes covering onboarding, curriculum sequencing, reassessments, and chat flows.
    - Implement a preflight checklist for the Render deploy (env vars, secrets, migrations, observability hooks).
    - Capture release notes and rollback procedures.
37. **Phase 37 – Agent Operations Uplift**
    - Build observability dashboards for agent tool usage, grading latency, and token consumption.
    - Harden configuration syncing across dev/staging/prod and document operational runbooks.
    - Add telemetry for automatic `file_search`/`web_search` success and link to alerting.
## Known Corrections & References

### SwiftUI overlay sizing and scroll behaviour (added October 12, 2025)
- **What went wrong:** The onboarding assessment overlay enforced a tall fixed frame, so on shorter displays the system clipped content instead of allowing the inner `ScrollView` to scroll. Progress also counted untouched starter code as valid responses.
- **Correct approach:** Compute modal width/height from the available viewport (via `GeometryReader`) and cap the scrollable region rather than forcing a minimum larger than the window. For code prompts, compare the learner’s response against the starter snippet and only mark the task answered after additional edits.
- **Action for future work:** When introducing new overlays or starter snippets, ensure sizing logic bounds the content to the viewport and treat template text as unanswered until modified.

### Agents function_tool strict schema (added October 12, 2025)
- **What went wrong:** We assumed that returning Pydantic models with `ConfigDict(extra="forbid")` would satisfy the OpenAI Agents `function_tool` strict JSON-schema requirements. Render deploys failed because the generated schema still contained `additionalProperties`, triggering `agents.exceptions.UserError`.
- **Correct approach:** When defining new agent tools with complex parameter schemas, explicitly set `@function_tool(strict_mode=False)` or design parameter models that yield compliant schemas. Review the Structured Outputs/Agents documentation before introducing or modifying tools that return complex payloads: https://platform.openai.com/docs/guides/structured-outputs.
- **Action for future work:** Before starting any phase or task that adds/modifies agent tools, read the linked docs and ensure strict-mode compatibility or intentionally disable strict mode with an accompanying justification.

### GPT-5 Codex tool support (added October 13, 2025)
- **What went wrong:** We treated `gpt-5-codex` as a limited-offline model that could not perform web search and rejected all attachments, leading to unnecessary 400 errors and weak answers.
- **Correct approach:** Codex supports web search but only accepts image uploads; other GPT-5 variants support the full attachment set. Pass the correct capability flags from the client and ensure prompts steer the agent to call `file_search` when files are available.
- **Action for future work:** Whenever we onboard a new model, verify its supported tools in OpenAI’s release notes before hard-coding capability constraints.

### MCP route registration & tool invocation (added October 12, 2025)
- **What went wrong:** We defined the `/mcp` OPTIONS/HEAD routes outside `create_proxy_app`, so FastAPI never registered them. OpenAI’s agent bootstrap saw 405/307 responses and the backend bubbled 424 errors. We also briefly used the non-existent JSON-RPC method `call_tool`.
- **Correct approach:** Register all MCP proxy routes inside `create_proxy_app`, ensure the proxy rewrites the path to `mcp.settings.streamable_http_path` (with trailing slash), and invoke tools with `tools/call` plus `params={"name": ..., "arguments": {...}}`.
- **Action for future work:** When adding proxy routes or middleware, confirm they’re attached during app construction and validate with `curl` (`initialize`, `tools/list`, `tools/call`) before relying on the OpenAI-side integration.

### ReasoningEffort enum usage (added October 12, 2025)
- **What went wrong:** We attempted to instantiate `ReasoningEffort(...)`, which fails because the OpenAI SDK exposes it as a typing `Union`/`Literal`. This caused grading runs to drop into the fallback branch.
- **Correct approach:** Pass the string literal directly (or cast) instead of calling the class constructor, e.g. `cast(ReasoningEffort, effort)`.
- **Action for future work:** Update any new agent tool wiring to pass raw string literals for reasoning effort tiers and add regression tests for the grading pipeline.

### Curriculum session sizing (added October 15, 2025)
- **What went wrong:** Sequencer heuristics produced single sessions exceeding 9 hours because reinforcement and deep-dive modules inherited long estimated durations.
- **Correct approach:** The sequencer now splits every oversized lesson/quiz/milestone into ≤120-minute parts, chaining prerequisites across parts so the learner receives the full content across multiple sessions.
- **Action for future work:** When authoring new curriculum modules, include realistic `estimated_minutes` values and ensure future phases (e.g., milestone guidance) respect the session-splitting helper rather than bypassing it.
- **Action for future work:** Whenever we upgrade the OpenAI SDK, confirm enum-like types remain string literals and avoid invoking them like classes. Review the type hints before wiring new agents.

### Web search enforcement & Markdown citations (added October 13, 2025)
- **What went wrong:** With web search toggled on, the agent still skipped `web_search` and returned plain-text source mentions, leaving learners without fresh context or clickable references.
- **Correct approach:** The prompt overlay must require `web_search` whenever the feature is enabled and instruct the model to format citations as Markdown hyperlinks; the client must render Markdown so links are clickable.
- **Action for future work:** When modifying prompts or chat presentation, confirm both tool invocation requirements and Markdown rendering remain intact, and add telemetry to detect regressions.

### Legacy profile payload compatibility (added October 13, 2025)
- **What went wrong:** Adding `assessment_submissions` to the learner profile payload caused older cached responses to fail decoding on macOS, blocking onboarding.
- **Correct approach:** Provide backward-compatible decoders (Swift + backend shim) that treat the new field as optional until persistence migration guarantees the updated schema everywhere.
- **Action for future work:** Remove the compatibility shim only after the persistence migration phases land and add contract tests (Phases 25–26) to guard against similar regressions.

### SwiftPM deployment targets & Swift 6 concurrency diagnostics (added October 13, 2025)
- **What went wrong:** Raising the deployment target to macOS 15 without updating the SwiftPM tools version triggered manifest failures, and Swift 6 surfaced concurrency warnings for shared `ISO8601DateFormatter` instances and other singletons.
- **Correct approach:** Bump `swift-tools-version` to 6.0 when targeting macOS 15+, and isolate shared Foundation formatters/registries behind `@MainActor` or Sendable-safe wrappers to satisfy Swift 6 diagnostics.
- **Action for future work:** Complete the formatter refactor during Phase 29’s reliability work so no `@MainActor` globals leak into Sendable contexts.

### Schedule refresh query encoding (added October 13, 2025)
- **What went wrong:** The macOS dashboard refresh button percent-encoded the entire `schedule?refresh=true` path segment, so the backend received `/schedule%3Frefresh%3Dtrue` and returned 404s instead of regenerating schedules.
- **Correct approach:** Build schedule URLs with `URLComponents`, keeping the path untouched and adding `refresh=true` as a proper query item.
- **Action for future work:** Whenever new API calls are added to the client, prefer `URLComponents` for path/query composition and cover them with integration tests so encoded routes are caught before release.

### Agent schedule prompt alignment (added October 14, 2025)
- **What went wrong:** Even after generating schedules, Arcadia Coach kept asking learners for calendar exports because the system prompt never told it to read `curriculum_schedule`.
- **Correct approach:** Update the prompt to instruct the agent to consume `curriculum_schedule`, sort items by `recommended_day_offset`, and translate offsets into dated summaries when answering scheduling questions.
- **Action for future work:** Whenever we adjust profile payloads or scheduling data, double-check the prompt overlay so the agent explicitly references the new fields and time semantics.

### Schedule regeneration short-circuit (added October 14, 2025)
- **What went wrong:** Refreshing a schedule immediately after deferring an item rewrote the unchanged profile JSON, so the request stalled behind a multi-minute disk write on Render.
- **Correct approach:** Detect unchanged sequencer output, skip persistence when no fields differ, and emit telemetry with `status="unchanged"` so we can monitor redundant refreshes.
- **Action for future work:** Extend the short-circuit to future persistence migrations and alert if `schedule_generation` repeatedly reports large `duration_ms` despite unchanged payloads.

### Foundation coverage gaps in curriculum (added October 14, 2025)
- **What went wrong:** The adaptive curriculum assumed learners already had broad Python/data foundations, so onboarding plans after low assessment scores still generated only ~13 items without introducing prerequisite languages, libraries, or extended assessment coverage.
- **Correct approach:** Expand the foundation module library, allow dynamic ELO categories, and regenerate schedules with multi-month scaffolding whenever the learner’s goals or assessment results indicate missing fundamentals.
- **Action for future work:** As part of Phase 16, ship telemetry that tracks which foundation tracks are activated per learner and add authoring tools so we can continue extending the module catalog without code changes.

### Current time tool & timezone propagation (added October 14, 2025)
- **What went wrong:** The agent defaulted to UTC when reporting timestamps, even after we localised schedules, because it lacked a clock tool and the backend wasn’t forwarding learner timezone metadata.
- **Correct approach:** Introduce a `current_time` function tool, update prompts to call it, and ensure the macOS client/backend pass the learner’s timezone with every chat turn.
- **Action for future work:** Monitor tool usage, surface telemetry for localisation mismatches, and add a client-facing timezone override control.

### Sequencer long-range refresh imbalance (added October 14, 2025)
- **What went wrong:** `_inject_long_range_refreshers` let the highest-priority category monopolise long-range lessons/quizzes, leaving peers like Systems & Architecture without reinforcement for months.
- **Correct approach:** Distribute refreshers across all high-priority categories with per-category completion checks and pacing guardrails, then verify balance through new regression tests and telemetry.
- **Action for future work:** Addressed in Phase 18 – Sequencer Long-Range Balancing; monitor the new `long_range_distribution` telemetry and expand smoothing heuristics if imbalance reappears.

### Alembic migrations require `psycopg` driver hint (added October 15, 2025)
- **What went wrong:** Render pre-deploys failed (`ModuleNotFoundError: psycopg2`) because SQLAlchemy defaulted to the legacy `psycopg2` driver while the project depends on `psycopg[binary]`.
- **Correct approach:** Use a connection URL prefixed with `postgresql+psycopg://` (and keep the dependency pinned) so Alembic loads the correct driver during migrations.
- **Action for future work:** When provisioning new environments or rotating secrets, double-check the driver prefix in `ARCADIA_DATABASE_URL`, and document migration CLI usage (`uv run --active alembic …`) to avoid environment mismatches.
