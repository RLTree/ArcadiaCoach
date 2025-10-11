# ChatKit widgets in WKWebView

OpenAI ChatKit renders widgets that are streamed from the server. This document captures the architecture, common failure modes, and the debugging checklist we now follow when a widget does not appear inside the macOS client’s `WKWebView`.

## Architecture overview

- The backend creates widgets with `chatkit.widgets` factories. When the agent wants to surface UI, it yields events from `stream_widget(...)`. No base64 transport or manual registration is required.
- The ChatKit JavaScript SDK (or the `<openai-chatkit>` web component) receives Server-Sent Events and renders the widgets automatically. There is no `widgets.register()` API.
- A blank panel usually means the SSE stream never delivered a `thread.item.added` event that contains the widget, or that the stream failed because of CORS, authentication, or WKWebView security limits.

## Server-side checklist

1. **Instrument streaming**  
   `backend/app/chat_server.py` now logs start, per-event, and completion messages so Console.app quickly shows whether `stream_widget` ran to completion. Example log prefix: “Streaming Arcadia chatbot widget…”.
2. **Validate widget models**  
   If a widget fails validation, log the error and send a simple `Text` widget explaining the problem. (Add this when we see validation failures.)
3. **Minimal repro tool**  
   Add helper tasks that stream a trivial widget (for example `Text(id="diagnostic", value="Widget test successful!")`) so we can rule out complex layouts.

## WKWebView integration guidelines

- Load HTML with an HTTPS base URL via `loadHTMLString(_:baseURL:)`. `file://` origins break the SSE handshake.
- Ensure `WKAppBoundDomains` includes our ChatKit domain (`api.openai.com`) and the custom backend domain. Set `limitsNavigationsToAppBoundDomains = true`.
- Install a console bridge early (`AdvancedChatKitView.consoleBridgeScript`) so JavaScript errors surface in macOS logs.
- Add listeners for `chatkit.error`, `thread.item.added`, and other high-value events. They now log to the console, which forwards through the bridge.
- Watch for CORS or auth failures in Safari’s Web Inspector (`webView.isInspectable = true` on macOS 13.3+).

## Debug workflow

1. Trigger the widget from the macOS client.
2. Tail backend logs. Confirm `Streaming Arcadia chatbot widget…` followed by “Completed widget stream… events=1”. If not, fix the server.
3. Open Safari Web Inspector, check the Network tab for `text/event-stream` responses. Any CORS, 401, or 403 errors must be fixed before continuing.
4. Review Console.app (`subsystem: com.arcadiacoach.app`). Look for the new debug listeners or JS error events.
5. If Safari renders correctly but WKWebView does not, double-check App-Bound Domains, CSP headers, and that the WKWebView base URL is HTTPS.
6. When localStorage persistence matters, copy it into `UserDefaults` before the app closes and restore it during app launch.

## Recommended instrumentation hooks

Add these snippets if additional diagnostics are needed:

```javascript
const chatkit = document.querySelector('openai-chatkit');
chatkit.addEventListener('chatkit.error', ({ detail }) => {
  console.error('[ChatKit Error]', detail.error);
});
chatkit.addEventListener('chatkit.log', ({ detail }) => {
  console.debug('[ChatKit Log]', detail.name, detail.data);
});
```

```python
async for event in stream_widget(...):
    logger.debug("Emitting widget event %s", event)
    yield event
```

With these hooks in place we can observe every stage of the widget lifecycle and quickly narrow down WKWebView-specific problems.
