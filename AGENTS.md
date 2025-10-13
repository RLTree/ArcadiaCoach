# Repository Guidelines

## Project Structure & Module Organization
- `backend/`: FastAPI services (`app/`), configuration (`config.py`), and deployment assets (Dockerfile). Use this for the custom ChatKit server, file uploads, and Arcadia agent orchestration.
- `Resources/`, `Views/`, `ViewModels/`, `Services/`: macOS SwiftUI client. Widget assets (e.g., `Resources/Widgets/ArcadiaChatbot.widget`) live here.
- `advanced-agent/`: Node/TypeScript utilities built on the OpenAI Agents SDK. Run from this directory when prototyping agent workflows.
- `mcp_server/`, `Models/`, `Tests/`: Auxiliary services, data models, and Swift unit tests. Keep cross-cutting assets (icons, entitlements) under `Resources/`.

## Build, Test, and Development Commands
- `uv sync && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` (backend): install deps and start the FastAPI server with live reload.
- `npm install && npm run dev` (advanced-agent): run the TypeScript agent playground.
- `open ArcadiaCoach.xcodeproj` → `⌘B` in Xcode: build the macOS client. Use the “ArcadiaCoach” scheme (Debug for development, Release for distribution).
- `swift test` (from project root): execute Swift unit tests under `Tests/`.

## Coding Style & Naming Conventions
- Python: follow Black/PEP 8 (4-space indents, snake_case). Run `uv run ruff check` before committing.
- Swift: 4-space indents, UpperCamelCase for types, lowerCamelCase for properties/functions. Keep widget JSON assets in PascalCase filenames (e.g., `ArcadiaChatbot.widget`).
- TypeScript: use Prettier defaults (`npm run format`) and camelCase for variables/functions, PascalCase for components.

## Testing Guidelines
- Backend: add pytest or FastAPI route tests under `backend/tests/` (create if missing). Name tests `test_<feature>.py`.
- Swift: group tests by feature (`Tests/<FeatureName>Tests.swift`). Include integration coverage for key flows (lesson, quiz, milestone).
- Target ≥80 % coverage for new modules; document gaps in PR descriptions when unavoidable.

## Commit & Pull Request Guidelines
- Commit messages: `<scope>: <imperative summary>` (e.g., `backend: add file-upload endpoint`). Keep commits focused and include migration notes in the body if needed.
- Pull Requests: provide a concise summary, list testing steps (`uv run …`, `swift test`, screenshots for UI), and link to tracking issues. Request review from both backend and client owners when changes span directories.

---

# Arcadia Coach Agent Overview

Arcadia Coach now runs solely on the custom backend + Agents SDK (Path 2). This section tracks the production agent configuration and how to run it locally.

## Current Production Agent

| Field | Value |
|-------|-------|
| Agent Name | Arcadia Coach |
| Agent ID | (stored in Render env var `ARCADIA_AGENT_ID`) |
| Default Model | `gpt-5` |
| Reasoning Effort | `medium` (`ARCADIA_AGENT_REASONING`) |
| Web Search | Default `false` (`ARCADIA_AGENT_ENABLE_WEB`) |

## Tools

The agent is configured with:

| Tool | Purpose |
|------|---------|
| `HostedMCPTool` (`Arcadia_Coach_Widgets`) | Serves lesson/quiz/milestone/focus sprint widgets |
| `FileSearchTool` | Queries Arcadia’s vector store (summary decks, docs) |
| `WebSearchTool` | Optional web context when `webEnabled=true` |

Additional function tools (Phase 2+) wired through `AGENT_SUPPORT_TOOLS`: `progress_start`, `progress_advance`, `learner_profile_get`, `learner_profile_update`, `learner_memory_write`, `elo_update`, and the new `learner_elo_category_plan_set` for persisting skill plans (see `docs/phase-2-elo-category-planning.md`).

MCP endpoint: `https://mcp.arcadiacoach.com/mcp` (Render service). It exposes:

- `lesson_catalog`
- `quiz_results`
- `milestone_update`
- `focus_sprint`

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Responses/Agents API key |
| `ARCADIA_AGENT_MODEL` | Default model (`gpt-5`, `gpt-5-codex`, etc.) |
| `ARCADIA_AGENT_REASONING` | `minimal` \| `low` \| `medium` \| `high` |
| `ARCADIA_AGENT_ENABLE_WEB` | Toggle web search for the agent |
| `ARCADIA_MCP_URL` | MCP server URL (`https://mcp.arcadiacoach.com/mcp`) |
| `ARCADIA_MCP_LABEL` | `Arcadia_Coach_Widgets` |
| `ARCADIA_MCP_REQUIRE_APPROVAL` | Approval mode (`never`) |

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
3. Start the backend:
   ```bash
   cd backend
   uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
4. Test the agent directly:
   ```python
   from agents import Runner, RunConfig, ModelSettings
   from backend.app.arcadia_agent import ArcadiaAgentContext, get_arcadia_agent

   agent = get_arcadia_agent("gpt-5", False)
   context = ArcadiaAgentContext.model_construct(thread=..., store=..., request_context={})
   Runner.run_sync(agent, "learn transformers", context=context,
                   run_config=RunConfig(model_settings=ModelSettings()))
   ```

**Hosted-only limitation:** The production backend runs at `https://chat.arcadiacoach.com`, and the MCP server lives at `https://mcp.arcadiacoach.com` (tool base URL `https://mcp.arcadiacoach.com/mcp`). Because OpenAI requires the domain to be pre-approved, we cannot exercise the full stack against localhost; all integration tests must target the hosted endpoints.

## Widgets

- `Resources/Widgets/ArcadiaChatbot.widget` powers the ChatKit embed (served via `ChatPanel`).
- MCP widgets return `Card`, `List`, `StatRow` items; the backend normalizes props before returning to Swift.

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
   - Follow-up: move the “read attachments before responding” guidance into the chat prompt so `file_search` is always invoked when files are present (tracked under Phase 21).
8. **Phase 7 – Chat Continuity & Prompt Hardening** ✅ *(completed October 13, 2025; see `docs/phase-7-chat-continuity.md`)*
   - Centralise prompt overlays so GPT-5/Mini always run `file_search` on attachments, GPT-5 Codex leans on inline previews, and web-enabled turns call `web_search` with Markdown hyperlink citations.
   - Add session resume support in the macOS client (active transcript tracking, sidebar ordering, resume button) without resetting backend threads.
   - Render chat bubbles with Markdown-aware text so citations and links are clickable inside the app.
   - Follow-ups: add automated tests to confirm `file_search`/`web_search` tool invocation sequences, track hyperlink rendering inside MCP widgets, and capture telemetry on tool success rates (see Phases 20 & 23).
9. **Phase 8 – Dashboard Assessment History** ✅ *(completed October 13, 2025; see `docs/phase-8-dashboard-assessment-history.md`)*
   - Add dashboard readiness summary, submission history list, and calibrated ELO callouts, mirrored in the chat sidebar for continuity.
   - Extend backend profile payloads and Swift models with assessment submission history plus legacy-safe decoding to avoid regressions during rollout.
   - Follow-ups: add UI regression tests for readiness states, instrument telemetry on history/grade status transitions, monitor payload growth (introduce pagination if needed), and remove the legacy decode shim once the persistence migration standardises the schema (Phases 17–18).
10. **Phase 9 – Feedback Drilldowns & Learner Insights** ✅ *(completed October 13, 2025; see `docs/phase-9-feedback-drilldowns.md`)*
    - Delivered detailed submission drilldowns with rubric notes, attachment manifests, and category ELO deltas in both dashboard and chat surfaces.
    - Normalised assessment submissions to include parsed attachments and explicit rating deltas across backend APIs and client models.
    - Captured the latest lesson/quiz/milestone envelopes so learners can revisit content immediately after agent actions.
    - Follow-ups: add UI coverage for the new detail view (Phase 21) and expand curriculum tie-ins alongside the milestone roadmap (Phase 16).
11. **Phase 10 – Assessment Attachment UX & Agent Ingestion** ✅ *(completed October 13, 2025; see `docs/phase-10-assessment-attachment-ux-agent-ingestion.md`)*
    - Replaced the metadata workaround with a structured `attachments` array on submissions, populated from the new attachment store (legacy metadata remains a fallback parser).
    - Shipped the full upload pipeline: REST endpoints, on-disk persistence, developer reset purge, and a macOS attachment manager (file picker + link entry) that auto-populates submissions.
    - Surfaced structured attachments across profile/developer APIs and piped attachment descriptors into grading payloads so the agent can ingest learner-provided context.
    - Extended regression coverage for upload/link/delete flows, download endpoints, and submission payloads to guard the new storage/ingestion path.
    - Follow-ups: add inline previews for common attachment types, capture ingestion telemetry, harden storage encryption ahead of the persistence migration, and resolve Swift 6 concurrency warnings raised by shared formatters (see follow-up assignments under Phases 14, 18, 21, and the new Known Corrections entry).
12. **Phase 11 – Curriculum Sequencer Foundations**
    - Stand up a sequencing service that consumes current ELO snapshot, goals, and recent assessment results to order upcoming lessons, quizzes, and milestones.
    - Emit structured schedules that the macOS client can cache, including prerequisites and expected effort.
    - Document sequencing inputs/outputs to unblock adaptive curriculum work in later phases.
13. **Phase 12 – Adaptive Curriculum MVP**
    - Plug the sequencing service into the existing curriculum generator to produce a short-term (2–3 week) adaptive roadmap per learner.
    - Ensure ELO deltas and onboarding assessment outcomes feed the sequencer so near-term lessons/quizzes reflect current proficiency.
    - Deliver client updates that visualise the upcoming schedule and allow basic rescheduling/defer actions.
14. **Phase 13 – Adaptive Curriculum Evolution**
    - Extend the curriculum generator to cover multi-month plans with rationale history, surfacing how adjustments relate to learner goals and performance trends.
    - Layer in milestone dependencies and pacing controls so the sequencer can allocate effort across categories intelligently.
    - Add changelog-style explanations in the macOS client so learners understand why the plan evolved.
15. **Phase 14 – Lesson Experience Redesign**
    - Render lessons as presentation-style decks with narrative slides, inline code/examples, and citations to supporting papers/docs.
    - Bundle comprehension checks at the end of each lesson and sync the results into the sequencer and ELO model.
    - Ensure lessons remain self-contained so learners can progress without leaving the app while still offering optional deep-dive links.
    - Extend attachment presentation with inline previews and captions so lesson and assessment feedback surfaces can display uploaded context gracefully.
16. **Phase 15 – Interactive Quiz & Assessment Overhaul**
    - Build an in-app quiz runner with interactive question types, attempt tracking, and immediate feedback.
    - Route quiz outcomes into ELO updates and adaptive curriculum adjustments.
    - Provide review surfaces so learners can revisit answers, rationales, and references.
17. **Phase 16 – Milestone Guidance & Adaptive Roadmapping**
    - Generate detailed milestone briefs (objectives, required deliverables, success parameters) that live entirely in-app.
    - Clarify which work must happen outside the app while capturing progress notes and artifacts back into Arcadia.
    - Feed milestone completion data into the sequencer so future lessons/quizzes adjust automatically.
18. **Phase 17 – Reassessment & Refresh Cadence**
    - Schedule periodic reassessments and surface their status alongside historical submissions.
    - Adapt refresher frequency based on recent grading outcomes and learner momentum.
    - Define thresholds for triggering reassessment vs. lightweight check-ins.
19. **Phase 18 – Persistence Migration (Data Layer)**
    - Introduce a durable database for profiles, assessments, chat transcripts, and submissions.
    - Add repository/service abstractions in the backend to wrap new storage, including migrations for existing JSON data.
    - Establish schema versioning and seed scripts for dev/staging environments, including encryption-at-rest for stored assessment attachments.
20. **Phase 19 – Persistence Migration (Client Integration & Sync)**
    - Update the macOS client and Agents SDK utilities to consume the new persistence APIs.
    - Remove JSON-file assumptions from the app layer and ensure offline/cache behaviours remain stable.
    - Backfill smoke tests to verify legacy decode paths are no longer needed.
21. **Phase 20 – Developer Code Tooling Enhancements**
    - Add code-entry affordances (syntax highlighting, editor shortcuts) and evaluate optional lint/run hooks for in-app prompts.
    - Ensure accessibility preferences (font sizing, colour choices) are respected in the coding surface.
    - Provide developer-oriented toggles for sandboxed execution once backend support exists.
22. **Phase 21 – API Reliability & Test Coverage**
    - Expand automated tests for profile, assessment, and submission endpoints (happy path, retries, and grading fallbacks).
    - Add contract tests for assessment history payloads, including legacy compatibility verification.
    - Resolve Swift 6 concurrency warnings by introducing Sendable-safe formatter/accessor wrappers and covering them with regression tests.
    - Integrate the new telemetry signals into CI to guard against tool invocation regressions and attachment ingestion failures.
23. **Phase 22 – Evaluation & Adaptive Safety**
    - Validate GPT-graded outcomes against representative human reviews and update rubric weights accordingly.
    - Tune the grading prompt (language, scoring thresholds) using data gathered post-Phase 15/16.
    - Default agents to launch with web search enabled (with per-user override) and document the grading prompt schema.
24. **Phase 23 – QA & Release Readiness**
    - Run full-stack QA passes covering onboarding, curriculum sequencing, reassessments, and chat flows.
    - Implement a preflight checklist for the Render deploy (env vars, secrets, migrations, observability hooks).
    - Capture release notes and rollback procedures.
25. **Phase 24 – Agent Operations Uplift**
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
- **Action for future work:** Whenever we upgrade the OpenAI SDK, confirm enum-like types remain string literals and avoid invoking them like classes. Review the type hints before wiring new agents.

### Web search enforcement & Markdown citations (added October 13, 2025)
- **What went wrong:** With web search toggled on, the agent still skipped `web_search` and returned plain-text source mentions, leaving learners without fresh context or clickable references.
- **Correct approach:** The prompt overlay must require `web_search` whenever the feature is enabled and instruct the model to format citations as Markdown hyperlinks; the client must render Markdown so links are clickable.
- **Action for future work:** When modifying prompts or chat presentation, confirm both tool invocation requirements and Markdown rendering remain intact, and add telemetry to detect regressions.

### Legacy profile payload compatibility (added October 13, 2025)
- **What went wrong:** Adding `assessment_submissions` to the learner profile payload caused older cached responses to fail decoding on macOS, blocking onboarding.
- **Correct approach:** Provide backward-compatible decoders (Swift + backend shim) that treat the new field as optional until persistence migration guarantees the updated schema everywhere.
- **Action for future work:** Remove the compatibility shim only after the persistence migration phases land and add contract tests (Phases 17–18) to guard against similar regressions.

### SwiftPM deployment targets & Swift 6 concurrency diagnostics (added October 13, 2025)
- **What went wrong:** Raising the deployment target to macOS 15 without updating the SwiftPM tools version triggered manifest failures, and Swift 6 surfaced concurrency warnings for shared `ISO8601DateFormatter` instances and other singletons.
- **Correct approach:** Bump `swift-tools-version` to 6.0 when targeting macOS 15+, and isolate shared Foundation formatters/registries behind `@MainActor` or Sendable-safe wrappers to satisfy Swift 6 diagnostics.
- **Action for future work:** Complete the formatter refactor during Phase 21’s reliability work so no `@MainActor` globals leak into Sendable contexts.
