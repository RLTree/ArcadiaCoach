# Path 2 Cutover – Backend-First Agents

This guide documents the remaining steps to complete the Path 2 migration: the macOS client now talks exclusively to the custom FastAPI backend, which in turn proxies all agent work to OpenAI. Users no longer paste agent IDs or API keys into the desktop app.

## What Changed
- `AgentService` and Keychain storage were removed from the macOS client; lesson/quiz/milestone/chat flows now call REST endpoints on the backend (`/api/session/...`).
- The settings UI only asks for the ChatKit backend URL and optional domain key. The agent ID field and OpenAI API key inputs were deleted.
- The FastAPI app exposes four new routes:
  - `POST /api/session/lesson`
  - `POST /api/session/quiz`
  - `POST /api/session/milestone`
  - `POST /api/session/chat`
- Backend configuration is read from environment variables so the model defaults never reach the client.

## Backend Checklist
1. Populate the new env vars (see `backend/app/config.py`):
   - `OPENAI_API_KEY` – project or org key with Agents access.
   - `ARCADIA_AGENT_MODEL` – default model fallback (e.g. `gpt-5`).
   - `ARCADIA_AGENT_REASONING` – optional reasoning level (`minimal`, `low`, `medium`, `high`).
   - `ARCADIA_AGENT_ENABLE_WEB` – `"true"` to allow web search by default.
2. Redeploy the FastAPI service. The new routes depend on these variables; missing values return `502` to the client.
3. Verify health:
   - `uv run uvicorn app.main:app --reload`
   - `curl -X POST http://localhost:8000/api/session/lesson -d '{"topic":"transformers","session_id":"local-test"}'`

## macOS Client Checklist
1. Launch the app and open **Settings → ChatKit Backend**.
2. Enter the full backend URL (e.g. `https://arcadiacoach.onrender.com/`) and save. Domain key is optional.
3. Quit and relaunch the app (or use the new **Session Reset** button once added) to flush cached sessions.
4. Validate flows: lesson, quiz, milestone buttons plus the mini-chat widget should now hit the backend.

## Data Migration Notes
- Legacy `agentId` values stored in `UserDefaults` are no longer read. They can be purged with `defaults delete com.arcadiacoach.app agentId` if desired.
- The backend maintains in-memory session state keyed by `session_id`. Resetting a session from the app clears that cache via `/api/session/reset`.

## Troubleshooting
- A blank Settings page usually means the backend URL wasn’t saved; check `~/Library/Containers/com.arcadiacoach.app/Data/Library/Preferences` for `chatkitBackendURL`.
- `502` errors from the backend indicate either a missing `OPENAI_API_KEY` or malformed agent output. Inspect the FastAPI logs for details about the failing request.
- If ChatKit still fails to render, confirm the domain allow-list is updated and that the new REST routes return JSON matching `EndLearn`, `EndQuiz`, `EndMilestone`, and `WidgetEnvelope`.
