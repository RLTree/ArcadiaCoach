# Phase 7 – Chat Continuity & Prompt Hardening

- **Date:** October 13, 2025
- **Owner:** Codex (Phase 7 thread)

## Summary

- Hardened the Arcadia Coach prompt overlays so GPT-5/GPT-5 Mini runs automatically consult uploaded files via `file_search`, while GPT-5 Codex receives explicit guidance to interpret inline image previews instead of invoking `file_search`.
- Centralised the preference/attachment prompt builder (`apply_preferences_overlay`) so both the ChatKit streaming server and `/api/session/chat` share identical instructions and attachment metadata formatting.
- Added a "Resume" workflow to the macOS Agent Chat sidebar: learners can reopen any stored transcript, continue the exact backend session thread, and see which session is active at a glance.
- Updated chat history models to persist the selected model per transcript, keeping capability enforcement (web search, attachment policy) in sync when a past conversation is resumed.

## Implementation Highlights

### Backend

- Introduced `app/prompt_utils.py` with `apply_preferences_overlay`, producing uniform attachment listings, `file_search`/`web_search` guidance, and reasoning effort reminders across entry points.
- `chat_server.ArcadiaChatServer` now feeds the resolved model name into the overlay so GPT-5/GPT-5 Mini sessions insist on `file_search` before responding, while GPT-5 Codex is told to stay within inline image previews.
- `/api/session/chat` (and related structured endpoints) swapped `_augment_prompt_with_preferences` for the shared helper; prompt text now includes the correct directive for Codex runs and cites OpenAI file identifiers for attachments.
- `constants.INSTRUCTIONS` highlight the attachment rules by model to keep the base agent prompt aligned with the overlay behaviour.
- Added `backend/tests/test_prompt_utils.py` to exercise attachment formatting, GPT-5 file-search enforcement, and Codex guidance.

### macOS Client

- `AgentChatViewModel` now tracks the active transcript id, saves each transcript’s model identifier, and exposes `resumeTranscript` to reload stored messages, reinstate capability guards, and reuse the original session id without hitting the reset endpoint.
- Sidebar summaries in `ChatPanel` flag the active session, remain sorted by `updatedAt`, and surface model/web/reasoning metadata in the transcript preview.
- The preview pane gained a "Resume" button that calls the new view model API, synchronises `AppSettings` (model, web toggle, reasoning level), and repopulates the main chat surface with the restored history.
- `AgentChatViewModelTests` gained `testResumeTranscriptRestoresSessionState` for the Swift side, ensuring resuming rehydrates settings and message history.

## Verification

1. **Python unit tests:** `uv run pytest backend/tests/test_prompt_utils.py`
2. **Swift unit tests:** `swift test`
3. **Manual QA:**
   - Upload a PDF (GPT-5) and confirm the backend logs show a `file_search` call before the assistant replies; repeat with GPT-5 Codex to verify no `file_search` tool execution and that the prompt references image previews.
   - Start a new chat session, send a few messages, switch to another transcript via "Resume", and ensure the chat surface reloads the older conversation while the sidebar marks it Active.
   - With Codex resumed from history, confirm attachments are restricted to images and the web toggle stays enabled.
   - After resuming, send another message and verify `/api/session/chat` keeps the original `session_id` (no reset) and appends to the stored transcript.

## Follow-Ups

- Bubble the active-session badge into `WidgetArcadiaChatbotView` once the SwiftUI surface mirrors the native sidebar.
- Extend Codex guidance with richer image annotation examples if successive runs prove the inline preview insufficient.
- Phase 8 should reuse the new transcript metadata (model, web flag) when presenting assessment dashboards, so learners immediately see which model produced prior grading feedback.
