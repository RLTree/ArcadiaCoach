# Arcadia Coach Debug Log — 11 Oct 2025

This note captures the problems we are still investigating in the Arcadia Coach desktop app and the concrete steps already taken. The goal is to provide ChatGPT (or any teammate) with the context needed to recommend next actions.

---

## 1. ArcadiaChatbot.widget fails to render inside the macOS client

### Symptoms
- The “Agent Chat” tab shows the shell UI but the embedded ChatKit widget never appears.
- WKWebView loads, but no custom widget card is displayed; no errors surface in the UI.

### Fixes/Instrumentation Attempted
- Updated `Resources/ChatKit/advanced_chatkit.html` to import ChatKit as an ES module, sanitize base64 payloads, and add global `window` error/rejection listeners plus debug logs prefixed with `[ArcadiaChatKit]`.
- Added a JS→Swift console bridge in `Views/Components/AdvancedChatKitView.swift` that forwards `console.log/info/warn/error` from the web view into macOS `OSLog`. This should surface load or runtime errors in Console.app (subsystem `com.arcadiacoach.app`).
- Ensured widget JSON is read correctly by logging file size in `Services/WidgetResource.arcadiaChatbotWidgetBase64()`.

### Current Status
- JS logs now reach Console.app, but the widget remains blank even against the freshly deployed Render backend. Need to capture logs while connected to the cloud stack to confirm whether the ChatKit SDK fails during registration or is receiving malformed configuration.
- Confirm the Render domain is allow-listed in OpenAI and that the macOS Settings → Domain Key field is populated; otherwise ChatKit will quietly refuse to render.
- Validate that App Transport Security allows outbound requests to `cdn.openai.com`, your Render endpoints, and any other API hosts. Missing ATS exceptions can block the widget silently.

---

## 2. Learn / Quiz / Milestone buttons intermittently no-op

### Symptoms
- Clicking “Start Lesson”, “Start Quiz”, or “Milestone” sometimes does nothing; other times the operation hangs without feedback.
- No alerts or spinners were visible prior to instrumentation.

### Fixes/Instrumentation Attempted
- Extended `SessionViewModel` with `activeAction`, `lastEventDescription`, and `lastError`. Buttons now show a spinner via `GlassButton` and display alerts when backend calls fail.
- Added detailed `OSLog` traces in `SessionViewModel` and the new `BackendService` reporting message payloads, missing backend URLs, HTTP failures, and session updates.
- `HomeView` now prints the last successful action beneath the button row for quick visual confirmation.

### Current Status
- UI provides feedback, but buttons remain non-functional against the Render deployment. Must confirm the macOS app saved the new ChatKit backend URL, ensure `OPENAI_API_KEY` is set on the server, and inspect FastAPI session-route logs for HTTP failures.

---

## 3. Backend ChatKit + Agents integration reliability

### Symptoms
- Without proper logs, it was difficult to tell if agent runs failed, if model calls returned 4xx, or if guardrails blocked requests.

- Added logging around the `/api/session/*` routes for request payloads, non-2xx status codes, and decode failures.
- Guardrails now degrade gracefully: if `OPENAI_API_KEY` is absent the server logs a warning and skips guardrail checks instead of crashing.
- `docs/sdk-integration.md` rewritten to reference the official ChatKit Python server docs and Agents SDK quickstarts, clarifying the expected deployment steps.

- Render backend redeployed successfully, but we haven’t yet validated that environment variables (`OPENAI_API_KEY`, `ARCADIA_AGENT_MODEL`, `ARCADIA_MCP_URL`) are populated. Missing or incorrect values would explain both the widget and button failures despite new logging.

---

## 4. MCP widget server deployment hiccups

### Symptoms
- Render deploys failed after introducing unsupported `FastMCP` constructor arguments (`version`, later `host`/`port` on `run()`).

### Fixes/Instrumentation Attempted
- Adjusted `mcp_server/server.py` to match the Model Context Protocol sample: host/port defined at construction, `mcp.run(transport="streamable-http")` used at launch.
- Confirmed the server binds to `$PORT` and exposes `/mcp` + `/health`, ready for Render deployment.

### Current Status
- Render deploy now succeeds. Need to confirm `/mcp/health` on the Render instance returns 200 and that the backend’s `ARCADIA_MCP_URL` points to this new host; otherwise widgets won’t populate.

---

## Next Diagnostic Steps
1. **Collect Console Logs** – Run the app from Xcode 26.1 beta 2, keep Console.app open (filter subsystem `com.arcadiacoach.app`), and reproduce the missing widget and button clicks to capture JS + Swift log output.
2. **Validate Backend Connectivity** – Ensure `uvicorn` is running locally (or via Render) with a populated `OPENAI_API_KEY`; verify the macOS Settings panel points to the reachable URL.
3. **Check MCP Responses** – Call the MCP service (`/mcp/tools/list`, `/mcp/tools/call`) to verify it returns widget envelopes; confirm the backend consumes these successfully.
4. **Verify Domain Key** – Double-check the domain allow-list entry on OpenAI and ensure the client is passing the correct domain key to ChatKit.
5. **Review ATS Settings** – Audit `Info.plist` for `NSAppTransportSecurity` rules permitting `cdn.openai.com` and your backend/MCP domains; add exceptions if the widget still fails after the above steps.

Documenting each outcome in this markdown file will make it easier for ChatGPT or another teammate to pick up the investigation.
