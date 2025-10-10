import SwiftUI
import WebKit

struct ChatPanel: View {
    @EnvironmentObject private var settings: AppSettings
    @State private var clientSecret: String?
    @State private var sessionId: String?
    @State private var loadMessage: String?
    @State private var isLoading = false

    private var activeSecret: String? {
        if let secret = clientSecret { return secret }
        return settings.chatkitClientToken.isEmpty ? nil : settings.chatkitClientToken
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Agent Chat")
                .font(.title2)
                .bold()
            if isLoading {
                ProgressView("Connecting to ChatKit…")
            }
            if let loadMessage {
                Text(loadMessage)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            if let secret = activeSecret, !secret.isEmpty {
                ChatKitWebView(token: secret, agentId: settings.agentId)
                    .accessibilityLabel("Interactive agent chat")
            } else {
                chatKitInstructions
            }
        }
        .padding(12)
        .task(id: settings.chatkitBackendURL) {
            await ensureToken()
        }
    }

    private var chatKitInstructions: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Connect ChatKit")
                .font(.headline)
            if settings.chatkitBackendURL.isEmpty {
                Text("Set a ChatKit backend URL in Settings or paste a client token manually.")
                    .font(.body)
                    .foregroundStyle(.secondary)
            } else {
                Text("Fetching a token from \(settings.chatkitBackendURL)…")
                    .font(.body)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
    }

    @MainActor
    private func ensureToken() async {
        guard settings.chatkitClientToken.isEmpty else { return }
        guard !settings.chatkitBackendURL.isEmpty else { return }
        guard let url = URL(string: settings.chatkitBackendURL) else {
            loadMessage = "Invalid backend URL."
            return
        }
        isLoading = true
        do {
            let response = try await ChatKitTokenService.fetch(baseURL: url, deviceId: settings.chatkitDeviceId)
            clientSecret = response.client_secret
            sessionId = response.session_id
            if let expiry = response.expires_at {
                loadMessage = "Session \(response.session_id) expires \(expiry.formatted())."
            } else {
                loadMessage = "Received ChatKit client token."
            }
        } catch {
            loadMessage = "Failed to fetch token: \(error.localizedDescription)"
        }
        isLoading = false
    }
}

private struct ChatKitWebView: NSViewRepresentable {
    var token: String
    var agentId: String

    func makeNSView(context: Context) -> WKWebView {
        let webView = WKWebView(frame: .zero)
        webView.configuration.preferences.javaScriptEnabled = true
        webView.loadHTMLString(html, baseURL: nil)
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        let script = "window.updateChatKit?.(\"\(jsEscaped(token))\", \"\(jsEscaped(agentId))\");"
        webView.evaluateJavaScript(script, completionHandler: nil)
    }

    private var html: String {
        """
        <!DOCTYPE html>
        <html lang=\"en\">
        <head>
          <meta charset=\"utf-8\" />
          <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
          <style>
            body { margin: 0; background-color: transparent; font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; }
            #chatkit-root { height: 100vh; width: 100%; }
            openai-chatkit { height: 100%; width: 100%; }
          </style>
          <script type=\"module\">
            import ChatKit from \"https://cdn.platform.openai.com/deployments/chatkit/chatkit.js\";
            let chatkit;
            async function mount(token, agentId) {
              if (!chatkit) {
                chatkit = await ChatKit.create({
                  element: document.querySelector('#chatkit-root'),
                  api: { clientToken: token },
                  layout: { autoFocus: false },
                  theme: { mode: 'light' }
                });
              }
              chatkit.setOptions({ api: { clientToken: token }, agent: agentId ? { id: agentId } : undefined });
            }
            window.updateChatKit = mount;
            window.addEventListener('DOMContentLoaded', () => {
              mount('\(jsEscaped(token))', '\(jsEscaped(agentId))');
            });
          </script>
        </head>
        <body>
          <div id=\"chatkit-root\"></div>
        </body>
        </html>
        """
    }

    private func jsEscaped(_ value: String) -> String {
        value
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
            .replacingOccurrences(of: "\n", with: "\\n")
            .replacingOccurrences(of: "'", with: "\\'")
    }
}
