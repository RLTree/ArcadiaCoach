# Arcadia Coach – Render Deployment Quickstart

This guide shows how to deploy the Path 2 stack—FastAPI ChatKit backend plus MCP widget server—on https://arcadiacoach.com using Render Web Services. The macOS client continues to talk only to your custom backend; OpenAI’s Agent Builder is not required.

---

## 1. Prepare Credentials

Collect these secrets before provisioning services:

- `OPENAI_API_KEY` – project/org key with Agents + Responses access
- Optional overrides:
  - `ARCADIA_AGENT_MODEL` (default `gpt-5`)
  - `ARCADIA_AGENT_REASONING` (`minimal|low|medium|high`, default `medium`)
  - `ARCADIA_AGENT_ENABLE_WEB` (`true`/`false`)
- MCP settings:
  - `ARCADIA_MCP_URL` (to be populated after MCP deploy)
  - `ARCADIA_MCP_LABEL` (default `Arcadia_Coach_Widgets`)
  - `ARCADIA_MCP_REQUIRE_APPROVAL` (default `never`)

---

## 2. Deploy the MCP Widget Server (Render Web Service)

1. Push the repo (or a fork) to GitHub so Render can pull it.
2. In Render, create a **Web Service**:
   - Repository: `ArcadiaCoach`
   - Root Directory: `mcp_server`
   - Runtime: Python 3.12
   - Build Command: `uv sync`
   - Start Command: `uv run python server.py --host 0.0.0.0 --port $PORT`
3. Environment variables:
   - `ENVIRONMENT=production` (optional)
4. Deploy and note the public URL, e.g. `https://arcadia-mcp.onrender.com`.
5. Update your secrets with:

   ```
   ARCADIA_MCP_URL=https://arcadia-mcp.onrender.com/mcp
   ```

6. Validate the deployment:

   ```bash
   curl https://arcadia-mcp.onrender.com/health
   ```

   You should see `{"status":"ok","server":"arcadia-mcp"}`.

---

## 3. Deploy the FastAPI Backend (Render Web Service)

1. Create another **Web Service** in Render:
   - Repository: `ArcadiaCoach`
   - Root Directory: `backend`
   - Runtime: Python 3.12
   - Build Command: `uv sync`
   - Start Command: `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`
2. Add environment variables:

   | Key | Value |
   | --- | --- |
   | `OPENAI_API_KEY` | `<your OpenAI key>` |
   | `ARCADIA_AGENT_MODEL` | `gpt-5` (or preferred model) |
   | `ARCADIA_AGENT_REASONING` | `medium` |
   | `ARCADIA_AGENT_ENABLE_WEB` | `false` |
   | `ARCADIA_MCP_URL` | `https://arcadia-mcp.onrender.com/mcp` |
   | `ARCADIA_MCP_LABEL` | `Arcadia_Coach_Widgets` |
   | `ARCADIA_MCP_REQUIRE_APPROVAL` | `never` |

3. Deploy the service. After the health check passes, visit:

   ```
   https://arcadiacoach.onrender.com/healthz
   ```

   Expected output: `{"status":"ok","mode":"custom-chatkit"}`.

4. Smoke-test the lesson route:

   ```bash
   curl -X POST https://arcadiacoach.onrender.com/api/session/lesson \
        -H "Content-Type: application/json" \
        -d '{"topic":"transformers","session_id":"render-test"}'
   ```

   You should receive a JSON payload shaped like `EndLearn`.

---

## 4. Wire Up `arcadiacoach.com`

1. In Render, open the backend service → **Settings → Custom Domains**.
2. Add `arcadiacoach.com` (and `www.arcadiacoach.com` if desired).
3. Render provides A/ALIAS records. In your DNS provider, point the domain to Render’s IPs.
4. After SSL is provisioned, confirm:

   ```
   https://arcadiacoach.com/healthz
   ```

5. If you require a domain key (OpenAI allow-list), generate it in the OpenAI dashboard and store it as `ARCADIA_DOMAIN_KEY`. The macOS app will read it from Settings → ChatKit Backend.

---

## 5. Configure the macOS Client

1. Build and run the app from Xcode.
2. In **Settings → ChatKit Backend**:
   - Backend base URL: `https://arcadiacoach.com/`
   - Domain key: paste your OpenAI domain key if the backend enforces it.
3. Return to **Home** and trigger lesson/quiz/milestone. The app now calls Render-hosted endpoints:
   - `POST https://arcadiacoach.com/api/session/lesson`
   - `POST https://arcadiacoach.com/api/session/quiz`
   - `POST https://arcadiacoach.com/api/session/milestone`
   - `POST https://arcadiacoach.com/api/session/chat`

> For the ChatKit widget embedded in the “Agent Chat” tab, ensure the Render domain is allow-listed in OpenAI so static assets and SSE streams aren’t blocked.

---

## 6. Maintenance Tips

- Backend logs in Render show detailed errors from the `/api/session/*` routes; 502 responses typically indicate an upstream OpenAI failure or misconfigured env var.
- To rotate secrets, update the Render environment variables and redeploy.
- Keep `uv.lock` under source control so Render uses consistent dependencies.
- If you change the MCP server URL, remember to update `ARCADIA_MCP_URL` on the backend service.

With these two Render services live, the macOS client stays in sync with the Path 2 architecture—no direct calls to api.openai.com from the app, and all agent orchestration happens inside your controlled backend. 🚀
