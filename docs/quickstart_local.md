# Arcadia Coach – Local Quickstart

This guide walks you through running the entire Path 2 stack on your Mac so the Arcadia Coach app talks to the local FastAPI backend and Model Context Protocol (MCP) widget server. No Agent Builder resources are required—you supply the OpenAI agent ID and API key via environment variables.

---

## 1. Prerequisites

- macOS 13+ with Xcode 15.4+ (for building the SwiftUI client)
- Python 3.11 or 3.12 with [uv](https://github.com/astral-sh/uv) installed (`pip install uv`)
- OpenAI account with access to the Agents + Responses APIs

Workspace layout (from repo root):

```text
ArcadiaCoach/
├─ backend/          # FastAPI + ChatKit server
├─ mcp_server/       # Arcadia MCP widget provider
└─ ArcadiaCoach.xcodeproj / Views / ViewModels / ...
```

---

## 2. Configure Environment Variables

Create `backend/.env` with the following values:

```env
OPENAI_API_KEY=sk-...
ARCADIA_AGENT_MODEL=gpt-5
ARCADIA_AGENT_REASONING=medium   # minimal | low | medium | high
ARCADIA_AGENT_ENABLE_WEB=false   # or true if your agent should default to web search
ARCADIA_MCP_URL=http://127.0.0.1:8001/mcp
ARCADIA_MCP_LABEL=Arcadia_Coach_Widgets
ARCADIA_MCP_REQUIRE_APPROVAL=never
```

> Tip: if you prefer to keep secrets outside the repo, export them in your shell session instead of using `.env`.

---

## 3. Start the MCP Widget Server

The MCP server feeds lesson/quiz/milestone widgets to the agent.

```bash
cd mcp_server
uv sync
uv run python server.py --host 127.0.0.1 --port 8001
```

Verify it responds:

```bash
curl http://127.0.0.1:8001/health
# -> {"status":"ok","server":"arcadia-mcp"}
```

Leave this terminal running.

---

## 4. Start the FastAPI Backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Smoke-test the REST endpoints:

```bash
curl -X POST http://127.0.0.1:8000/api/session/lesson \
     -H "Content-Type: application/json" \
     -d '{"topic":"transformers","session_id":"local-test"}'
```

You should receive a JSON payload shaped like `EndLearn`.

---

## 5. Configure the macOS Client

1. Open `ArcadiaCoach.xcodeproj` in Xcode.
2. Select the **ArcadiaCoach** scheme, build & run.
3. In **Settings → ChatKit Backend**, set:
   - `Backend base URL`: `http://127.0.0.1:8000/`
   - `Domain key`: leave blank for local testing.
4. Return to **Home**, dismiss onboarding, and press **Start Lesson/Quiz/Milestone**. Each action should call the backend and render widgets. The Agent Chat tab now proxies through `/api/session/chat`.

> If buttons spin forever, check the backend log for HTTP 401/502 errors—usually missing env vars or an incorrect agent ID.

---

## 6. Development Workflow

- Backend linting: `cd backend && uv run ruff check`
- Swift unit tests via SwiftPM: `swift test`
- Reset backend session cache from the UI by re-saving the backend URL or via the `Reset` logic in `SessionViewModel`.

With this setup, you can iterate on both the FastAPI routes and SwiftUI client locally without touching the OpenAI Agent Builder. All agent orchestration is centralized in the backend.🎯
