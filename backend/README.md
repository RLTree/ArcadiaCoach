# Arcadia Coach Backend

This FastAPI service hosts Arcadia Coach’s custom ChatKit integration. It mounts the ChatKit Python SDK server that hands conversations to the OpenAI Agents SDK agent, and it exposes helper endpoints (file upload, health checks) that the macOS client calls.

## Features

- `POST /chatkit` streams ChatKit turns through the Arcadia Coach agent graph.
- `POST /api/chatkit/upload` handles file uploads from the ChatKit widget and forwards file metadata to the agent.
- `GET /healthz` lightweight health probe for load balancers and uptime monitors.

## Requirements

- Python 3.10+
- An OpenAI API key (stored in `OPENAI_API_KEY`) so the server can call the OpenAI Responses API.

## Setup

```bash
cd backend
uv sync          # creates .venv and uv.lock
uv run uvicorn app.main:app --reload
```

Fill in an `.env` file (or export values in your shell):

```
OPENAI_API_KEY=sk-...
# Hosted MCP defaults to the local FastMCP service at http://127.0.0.1:8001/mcp.
# Override these if you host the widget tools elsewhere.
ARCADIA_MCP_URL=http://127.0.0.1:8001/mcp
ARCADIA_MCP_LABEL=Arcadia_Coach_Widgets
ARCADIA_MCP_REQUIRE_APPROVAL=never
```

> The service reads configuration from environment variables at startup. Use your favourite secret manager for production deployments.

### Required environment variables

- `OPENAI_API_KEY` – API key with access to the OpenAI Responses/Agents APIs.
- `ARCADIA_MCP_URL` – Fully-qualified MCP endpoint (e.g. `https://<your-mcp-service>/mcp`).
- `ARCADIA_MCP_LABEL` – Friendly label passed to the MCP tool configuration.
- `ARCADIA_MCP_REQUIRE_APPROVAL` – Guardrail approval strategy (e.g. `never`).
- `ARCADIA_AGENT_ID` / other agent identifiers – if your deployment references specific agent IDs, set them here as well.
- `CHATKIT_DOMAIN_KEY` (client-side) – make sure the macOS app stores the domain key returned from the OpenAI domain allow-list so ChatKit trusts your Render domain.

## Run the service

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Set the macOS app’s “ChatKit backend URL” to `http://localhost:8000` (or the address where your server is reachable).

### Run the widget MCP server

Arcadia Coach expects a hosted MCP server that serves lesson, quiz, milestone, and focus sprint widgets—this repository ships one under `mcp_server/`. Start it alongside the backend:

```bash
cd ../mcp_server
uv sync
uv run python server.py
```

By default the backend points at `http://127.0.0.1:8001/mcp` (see `ARCADIA_MCP_URL`). If you host the MCP service elsewhere (for example on a public domain for ChatKit), update the environment variables accordingly.

### Deploy to Render

The repository ships a [`render.yaml`](../render.yaml) blueprint that spins up two Render services:

- **arcadia-coach-backend** – the ChatKit Python SDK + Agents SDK bridge (FastAPI).
- **arcadia-coach-mcp** – the MCP widget server that streams cards/lists/stat rows.

Steps:

1. Commit your changes and push to a Git repository that Render can access.
2. In Render, choose **Blueprint Deploy**, point it at `render.yaml`, and supply the required environment variables when prompted. Set `OPENAI_API_KEY` and update `ARCADIA_MCP_URL` after the MCP service goes live.
3. After the MCP service deploys, copy its public URL (for example `https://arcadia-coach-mcp.onrender.com/mcp`) and, if the hostname differs from the default in `render.yaml`, update the `ARCADIA_MCP_URL` environment variable on the backend service.
4. Add both service domains to your ChatKit domain allowlist and use the returned domain key inside the macOS Settings panel if required.

Once deployed, point the macOS app’s ChatKit backend URL at the Render backend domain (e.g. `https://arcadia-coach-backend.onrender.com`).

## Docker (optional)

A simple container image can be built with:

```bash
docker build -t arcadia-chatkit-backend .
```

Then run with:

```bash
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  -e ARCADIA_MCP_URL=http://127.0.0.1:8001/mcp \
  -e ARCADIA_MCP_LABEL=Arcadia_Coach_Widgets \
  -e ARCADIA_MCP_REQUIRE_APPROVAL=never \
  arcadia-chatkit-backend
```

## Endpoints

| Method | Path                     | Description                                                 |
|--------|--------------------------|-------------------------------------------------------------|
| POST   | `/chatkit`               | Stream ChatKit turns through the Arcadia Coach agent.       |
| POST   | `/api/chatkit/upload`    | Accept file uploads from the ChatKit widget.                |
| GET    | `/healthz`               | Health probe.                                               |
| GET    | `/mcp/health`            | (When forwarded) Upstream MCP health probe.                 |

## Testing

Use `httpie` or `curl` to sanity-check the API:

```bash
http :8000/healthz
```

You should see `{"status": "ok", "mode": "custom-chatkit"}`. The macOS client calls `/chatkit` directly once you configure the backend URL in Settings.

### Debugging tips

- Backend logs now print the resolved MCP URL and whether the OpenAI API key is configured at startup. Inspect Render’s logs after each deploy to confirm environment variables are loading.
- The MCP service expects streamable HTTP requests. To test from the command line:
  ```bash
  curl https://<mcp-host>/mcp \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: <session-id>" \
  -d '{"jsonrpc":"2.0","id":"tools","method":"tools.list","params":{}}'
  ```
  Start the session with an `initialize` call to obtain the `Mcp-Session-Id`, then reuse it for subsequent requests.
- Run the macOS client from Xcode 26.1 beta 2 and monitor Console.app (subsystem `com.arcadiacoach.app`) to capture widget registration errors or agent call failures.
- Add your backend and MCP domains to the OpenAI ChatKit domain allow-list and supply the generated domain key in the macOS Settings panel; without a domain key the embedded widget will not render.
- Confirm App Transport Security (ATS) permits outbound requests to `cdn.openai.com`, your Render domains, and any other API hosts. Update `Info.plist` with `NSAllowsArbitraryLoads` or per-domain exceptions if needed.
