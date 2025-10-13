# Phase 6 – Frontend Chat & Accessibility Enhancements

- **Date:** October 12, 2025
- **Owner:** Codex (Phase 6 thread)

## Summary

- Upgraded the macOS Agent Chat panel with per-session memory, web-search control, reasoning effort picker, and inline attachment workflow.
- Persisted chat transcripts locally via `ChatHistoryStore` so learners can revisit previous runs from a sidebar preview.
- Enabled file uploads in the native client, forwarding metadata to the backend agent context.
- Added backend overrides so `/api/session/chat` respects per-request web/effort flags and attachment lists.
- Surfaced default chat preferences in Settings (web search + reasoning effort) and wired them into the client experience.

## Implementation Highlights

### macOS Client

- `Views/ChatPanel.swift` now renders a two-column layout with a "Previous Sessions" sidebar (Phase 6 breadcrumb in-file) and a richer `ArcadiaChatbotView` instance.
- `ArcadiaChatbotView` gained interactive reasoning chips, a toggleable web-search control, and an attachment section with upload/remove affordances.
- `AgentChatViewModel` orchestrates attachments, preference overrides, and transcript persistence through the new `ChatHistoryStore` (see Phase 6 breadcrumb).
- `SettingsView` includes an "Agent Chat Preferences" section that stores defaults in `AppSettings` (`chatWebSearchEnabled`, `chatReasoningLevel`).

### Backend

- `/api/session/chat` (FastAPI) accepts optional `web_enabled`, `reasoning_level`, and `attachments` fields and augments prompts with the same guardrails used by the hosted ChatKit server.
- `BackendService.sendChat` encodes the new payload fields; `BackendService.uploadChatAttachment` handles multipart uploads to `/api/chatkit/upload` and returns a `ChatAttachment`.

### Persistence & Tests

- Introduced `Models/ChatAttachment`, `Models/ChatTranscript`, and `Services/ChatHistoryStore` to persist chat history via `UserDefaults`.
- Extended `AgentChatViewModelTests` to cover preference persistence and attachment storage.
- Updated `Package.swift` target sources to include the new models/services.

## Verification

1. **Unit tests:** `swift test` (passes with the new test coverage).
2. **Manual QA:**
   - Launch the macOS app, open Agent Chat, and confirm the sidebar records messages after sending a prompt.
   - Toggle "Web search" and reasoning effort chips; verify the state persists across restarts and is reflected in Settings defaults.
   - Use "Add file" to upload a ≤5 MiB document; confirm the attachment summary appears and the backend receives the `attachments` array (watch server logs).
   - Ensure Settings → Agent Chat Preferences updates defaults used by new chat sessions.

## Follow-Ups

- Phase 11 should migrate chat history out of `UserDefaults` into the planned durable datastore.
- Monitor upload throughput; consider progress/error toasts in Phase 7 if learners attach multiple files.
- Align widget-rendered chat (`WidgetArcadiaChatbotView`) with the new attachment UI once MCP widgets emit attachment metadata.

