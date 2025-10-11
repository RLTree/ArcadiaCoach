# OpenAI SDK Integration Notes

Updated 11 October 2025.

Arcadia Coach now standardises on the OpenAI ChatKit **Python** SDK and the OpenAI **Agents** SDK for Python. The former `advanced-agent/` TypeScript playground has been removed; use the Python workflows below for both backend and prototyping needs.

## ChatKit Python SDK (backend/)

- The FastAPI backend already subclasses `ChatKitServer` and streams agent runs with `stream_agent_response`. That mirrors the server integration guidance from the official ChatKit Python docs, which recommend implementing `ChatKitServer.respond` and exposing a single POST endpoint (e.g. `/chatkit`). citeturn0search0
- Install or update dependencies inside `backend/` with `uv`:
  ```bash
  cd backend
  uv sync          # creates or refreshes the virtualenv and uv.lock
  uv run uvicorn app.main:app --reload
  ```
  The docs note that ChatKit is delivered as `openai-chatkit`; our `pyproject.toml` already pins it, so `uv sync` will resolve a compatible version automatically. citeturn0search0turn8view0
- For ephemeral environments or CI rebuilds, you can refresh only the Python packages:
  ```bash
  uv pip install --upgrade openai-chatkit openai-agents
  uv pip install --upgrade openai
  ```
  As of 30 September 2025 the latest PyPI release of `openai-agents` is 0.3.3; pinning against that build keeps parity with upstream bug fixes. citeturn4view0
- Keep FastAPI wired exactly as in `backend/app/main.py`: accept the request body, call `server.process(...)`, and stream SSE responses when available. This matches the FastAPI sample in the ChatKit documentation. citeturn0search0

## Agents SDK for Python (backend/ and mcp_server/)

- Follow the official Python quickstart when extending `backend/app/arcadia_agent.py` or adding new orchestration flows. The guide covers setting up a virtual environment, installing `openai-agents`, and defining agents plus runners. citeturn1search0
- Optional capabilities:
  - **Voice / TTS**: install `openai-agents[voice]` and use the voice pipeline helpers when you need narrated outputs. citeturn1search3
  - **Realtime sessions**: the realtime quickstart shows how to run `RealtimeAgent` workflows for audio-first experiences; adapt those patterns if Arcadia Coach adopts realtime classrooms. citeturn1search2
- When adding tools, guardrails, or multi-agent handoffs, prefer SDK constructs (`function_tool`, `handoffs`, `Runner.run`) so the ChatKit server can continue using `Runner.run_streamed` without additional plumbing. citeturn0search0turn1search0

## SwiftUI client (Resources/ChatKit)

- The embedded HTML calls `ChatKit.create(...)`, matching the public JavaScript APIs described in the official ChatKit web integration guide, so the macOS WKWebView stays compatible with upstream releases. citeturn6search3
- `AdvancedChatKitView` mirrors browser console output into macOS log streams; watch the subsystem `com.arcadiacoach.app` in Console.app while testing new widget or action behaviour.

Use this guide as the source of truth when onboarding teammates or upgrading SDK versions. It ties the Python backend, guardrails, and SwiftUI client together with the officially documented workflows so upgrades stay predictable.
