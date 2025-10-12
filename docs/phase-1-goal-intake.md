# Phase 1 – Goal Intake & Profile Memory (Completed on October 12, 2025)

This phase established a persistent learner profile pipeline and enabled Arcadia Coach to remember user intent across sessions.

## What Changed

- **Onboarding intake:** `Views/OnboardingView.swift` now collects username, backend URL, OpenAI API key, long-term learning goal, and coding use-case. Responses are saved to `AppSettings` and validated before entering the app.
- **Settings management:** Added a learner profile section in `Views/SettingsView.swift` so users can adjust long-term goal and use-case later.
- **Client metadata propagation:** `SessionViewModel`, `AgentChatViewModel`, `HomeView`, and `ChatPanel` send the profile metadata with every backend request, ensuring the agent stays aware of the learner’s goals/context.
- **Backend persistence:** Introduced `backend/app/learner_profile.py` (JSON stub store) and `backend/app/vector_memory.py` (note interface) to retain learner goals, sessions, and memory records. Metadata is automatically stored whenever a request arrives.
- **Agent tooling:** Added structured tools in `backend/app/tools.py` (`learner_profile_get`, `learner_profile_update`, `learner_memory_write`) and wired them into the Arcadia agent so it can fetch/update learner data and write long-term memories.
- **Render compatibility fix:** Resolved `function_tool` strict-schema issues by loosening schemas where needed and returning structured payload models.

## Remaining Gaps / Next Steps

- Backend still writes to a JSON file; Phase 7 will migrate to a durable store.
- There is no dedicated REST endpoint yet for clients to query learner profiles outside of agent runs.
- Memory notes are written locally but not retrieved; future phases should expose retrieval to support refreshers.

With these pieces in place we can proceed to Phase 2 (ELO category planning) knowing the system captures and recalls learner goals reliably.
