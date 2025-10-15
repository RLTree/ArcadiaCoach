# Phase 25 – Clipboard & Selection Support

**Status:** Completed October 15, 2025  
**Owner:** Arcadia Coach macOS client team  

## Goals
- Enable Command+C and related text selection shortcuts across chat, lesson, assessment, and widget surfaces.
- Provide consistent copy affordances (context menus + clipboard helpers) so learners can quickly capture agent guidance.
- Harden regression coverage around clipboard behaviour ahead of future SwiftUI refactors.

## Implementation Summary
- Added `AppClipboardManager` wrapper around `NSPasteboard` so views share a single copy utility with test injection.
- Introduced `selectableContent(_:)` view modifier (macOS 12+) that enables `.textSelection(.enabled)` while keeping styling intact.
- Updated chat experiences (`ArcadiaChatbotView`, `ChatPanel`) with selectable bubbles, metadata badges, transcript previews, and copy context menus for messages, attachments, and transcript summaries.
- Enabled selection and copy affordances for lesson content and widget components (`WidgetCardView`, `WidgetListView`, `WidgetStatRowView`, cited text blocks, MCP chatbot widgets).
- Expanded assessment detail surfaces with selectable text, per-section context menus, and shared clipboard usage for attachments, feedback summaries, category impacts, and task drilldowns.
- Resolved the AttributeGraph recursion loop by scoping selection modifiers to leaf views and centralising clipboard access through `AppClipboardManager`.

## Testing
- `swift test`
- Manual VoiceOver sweep to confirm selection-enabled text remains grouped correctly in chat, lesson, and assessment detail panes.
- Manual verification of Command+C/Ctrl+C and context menu copy actions across chat transcripts, lesson decks, widget cards, and assessment drilldowns.

## Follow-ups
- Extend clipboard/context menu coverage to future milestone briefs (Phase 27) and lesson deck components (Phase 29) once those surfaces ship.
- Monitor schedule-driven launches (Phase 26) for additional copy targets (e.g., schedule cards, launch confirmations) and add telemetry hooks if learners signal friction.
- Continue listening for feedback on other high-friction surfaces and expand context menus where learners need quicker exports.
