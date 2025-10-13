# Phase 6 – Frontend Chat & Accessibility Enhancements

- **Date:** October 12, 2025
- **Owner:** Codex (Phase 6 thread)

## Summary

- Upgraded the macOS Agent Chat panel with per-session memory, web-search control, reasoning effort picker, and inline attachment workflow (attachments now render alongside the message they belong to).
- Persisted chat transcripts locally via `ChatHistoryStore` so learners can revisit previous runs from a sidebar preview.
- Enabled file uploads in the native client, forwarding metadata to the backend agent context and persisting them per session so follow-up messages can reuse the same files.
- Added backend overrides so `/api/session/chat` respects per-request web/effort flags and attachment lists.
- Surfaced default chat preferences in Settings (web search + reasoning effort) and wired them into the client experience.

## Implementation Highlights

### macOS Client

- `Views/ChatPanel.swift` now renders a two-column layout with a "Previous Sessions" sidebar (Phase 6 breadcrumb in-file) and a richer `ArcadiaChatbotView` instance.
- `ArcadiaChatbotView` gained interactive reasoning chips, a toggleable web-search control, and an attachment section with upload/remove affordances; message bubbles now display the files sent with that turn.
- `AgentChatViewModel` orchestrates attachments, preference overrides, and transcript persistence (with inline `ChatHistoryStore` definitions marked via the Phase 6 breadcrumb).
- `SettingsView` includes an "Agent Chat Preferences" section that stores defaults in `AppSettings` (`chatWebSearchEnabled`, `chatReasoningLevel`).

### Backend

- `/api/session/chat` (FastAPI) accepts optional `web_enabled`, `reasoning_level`, and `attachments` fields, augments prompts with the same guardrails used by the hosted ChatKit server, and retains uploaded attachments across turns.
- Requests now map reasoning effort to the model family (`minimal`→`gpt-5-nano`, `low`→`gpt-5-mini`, `medium`→`gpt-5`, `high`→`gpt-5-codex`) so the toggle matches production ChatKit behavior.
- `BackendService.sendChat` encodes the new payload fields; `BackendService.uploadChatAttachment` handles multipart uploads to `/api/chatkit/upload` and returns a `ChatAttachment`.

### Persistence & Tests

- Inlined the Phase 6 chat attachment/transcript models inside `AgentChatViewModel` to keep the Xcode target in sync; `ChatHistoryStore` remains the persistence surface and is now deduping attachments by file id.
- Extended `AgentChatViewModelTests` to cover preference persistence and attachment storage.
- Updated `Package.swift` target sources to include the new models/services.

## Verification

1. **Unit tests:** `swift test` (passes with the new test coverage).
2. **Manual QA:**
   - Launch the macOS app, open Agent Chat, and confirm the sidebar records messages after sending a prompt.
   - Toggle "Web search" and reasoning effort chips; verify the state persists across restarts and is reflected in Settings defaults.
   - Use "Add file" to upload a ≤5 MiB document; confirm the attachment renders beneath the outgoing message and the backend retains it for follow-up turns (watch `/api/session/chat` logs for `attachments`).
   - Ensure Settings → Agent Chat Preferences updates defaults used by new chat sessions.

## Follow-Ups

- Phase 11 should migrate chat history out of `UserDefaults` into the planned durable datastore.
- Monitor upload throughput; consider progress/error toasts in Phase 7 if learners attach multiple files.
- Align widget-rendered chat (`WidgetArcadiaChatbotView`) with the new attachment UI once MCP widgets emit attachment metadata.
