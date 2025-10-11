import SwiftUI
import WebKit
import OSLog

struct AdvancedChatKitConfiguration: Codable, Equatable {
    var agentId: String?
    var token: String?
    var apiURL: String?
    var domainKey: String?
    var uploadURL: String?
}

struct AdvancedChatKitView: NSViewRepresentable {
    var configuration: AdvancedChatKitConfiguration
    var widgetBase64: String

    private static let logger = Logger(subsystem: "com.arcadiacoach.app", category: "AdvancedChatKit")
    private static let consoleBridgeScript = """
    (function() {
      if (window.__arcadiaConsoleBridgeInstalled) { return; }
      window.__arcadiaConsoleBridgeInstalled = true;
      const handler = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.chatkitLogger;
      if (!handler) { return; }
      const levels = ['log', 'debug', 'info', 'warn', 'error'];
      const normalise = (value) => {
        if (value === undefined) { return 'undefined'; }
        if (value === null) { return 'null'; }
        if (typeof value === 'object') {
          try { return JSON.stringify(value); } catch (_) { return String(value); }
        }
        return String(value);
      };
      levels.forEach((level) => {
        const original = console[level] ? console[level].bind(console) : console.log.bind(console);
        console[level] = function(...args) {
          try {
            handler.postMessage({
              level,
              message: args.map(normalise).join(' ')
            });
          } catch (_) {}
          try {
            original(...args);
          } catch (_) {}
        };
      });
    })();
    """

    final class Coordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate {
        func userContentController(_: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "chatkitLogger" else { return }
            if let payload = message.body as? [String: Any],
               let level = payload["level"] as? String,
               let body = payload["message"] as? String {
                log(level: level, body: body)
            } else {
                let description = String(describing: message.body)
                AdvancedChatKitView.logger.debug("ChatKit JS message: \(description, privacy: .public)")
            }
        }

        func webView(_ webView: WKWebView, didFinish _: WKNavigation!) {
            AdvancedChatKitView.logger.debug("ChatKit web view finished load (isLoading=\(webView.isLoading, privacy: .public))")
        }

        func webView(_: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            let navState = navigation == nil ? "navigation=nil" : "navigation!=nil"
            AdvancedChatKitView.logger.error("ChatKit web view navigation failure (\(navState, privacy: .public)): \(error.localizedDescription, privacy: .public)")
        }

        func webView(_: WKWebView, didFailProvisionalNavigation _: WKNavigation!, withError error: Error) {
            AdvancedChatKitView.logger.error("ChatKit web view provisional load failure: \(error.localizedDescription, privacy: .public)")
        }

        private func log(level: String, body: String) {
            switch level {
            case "error", "fault":
                AdvancedChatKitView.logger.error("ChatKit JS error: \(body, privacy: .public)")
            case "warn":
                AdvancedChatKitView.logger.notice("ChatKit JS warning: \(body, privacy: .public)")
            case "info":
                AdvancedChatKitView.logger.info("ChatKit JS info: \(body, privacy: .public)")
            default:
                AdvancedChatKitView.logger.debug("ChatKit JS \(level): \(body, privacy: .public)")
            }
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeNSView(context: Context) -> WKWebView {
        let webConfiguration = WKWebViewConfiguration()
        let userContentController = webConfiguration.userContentController
        userContentController.add(context.coordinator, name: "chatkitLogger")
        let bridge = WKUserScript(
            source: Self.consoleBridgeScript,
            injectionTime: .atDocumentStart,
            forMainFrameOnly: false
        )
        userContentController.addUserScript(bridge)

        let webView = WKWebView(frame: .zero, configuration: webConfiguration)
        webView.navigationDelegate = context.coordinator
        webView.setValue(false, forKey: "drawsBackground")
        if #available(macOS 13.3, *) {
            webView.isInspectable = true
        }

        let trimmedWidget = widgetBase64.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmedWidget.isEmpty {
            Self.logger.error("ChatKit widget payload is empty; custom widget will not render.")
        } else {
            Self.logger.debug("Preparing ChatKit HTML (widgetBase64Length=\(trimmedWidget.count, privacy: .public))")
        }

        if let html = loadHTML(widgetBase64: trimmedWidget, configuration: configuration) {
            webView.loadHTMLString(html, baseURL: baseURL(for: configuration))
        } else {
            Self.logger.error("Failed to load ChatKit HTML template from bundle.")
        }

        return webView
    }

    func updateNSView(_ webView: WKWebView, context _: Context) {
        do {
            let script = try configurationScript(configuration)
            webView.evaluateJavaScript(script) { _, error in
                if let error {
                    Self.logger.error("Failed to apply ChatKit configuration: \(error.localizedDescription, privacy: .public)")
                } else {
                    Self.logger.debug("Applied ChatKit configuration script successfully.")
                }
            }
        } catch {
            Self.logger.error("Unable to build ChatKit configuration script: \(error.localizedDescription, privacy: .public)")
        }
    }

    static func dismantleNSView(_ webView: WKWebView, coordinator: Coordinator) {
        webView.navigationDelegate = nil
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "chatkitLogger")
        AdvancedChatKitView.logger.debug("ChatKit web view dismantled.")
    }

    private func loadHTML(widgetBase64: String, configuration: AdvancedChatKitConfiguration) -> String? {
        guard let url = Bundle.main.url(
            forResource: "advanced_chatkit",
            withExtension: "html",
            subdirectory: "Resources/ChatKit"
        ) ?? Bundle.main.url(forResource: "advanced_chatkit", withExtension: "html") else {
            return nil
        }
        guard var html = try? String(contentsOf: url) else { return nil }
        let sanitizedWidget = widgetBase64.replacingOccurrences(of: "\n", with: "")
        html = html.replacingOccurrences(of: "%WIDGET_BASE64%", with: sanitizedWidget)
        let configBase64 = (try? configurationData(configuration).base64EncodedString()) ?? ""
        let sanitizedConfig = configBase64.replacingOccurrences(of: "\n", with: "")
        html = html.replacingOccurrences(of: "%CHATKIT_CONFIG_BASE64%", with: sanitizedConfig)
        if let bootstrap = try? configurationScript(configuration) {
            html += "\n<script>\(bootstrap)</script>"
        }
        return html
    }

    private func configurationData(_ configuration: AdvancedChatKitConfiguration) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.withoutEscapingSlashes]
        return try encoder.encode(configuration)
    }

    private func configurationScript(_ configuration: AdvancedChatKitConfiguration) throws -> String {
        let base64 = try configurationData(configuration).base64EncodedString()
        let escaped = escapeForJavaScript(base64.replacingOccurrences(of: "\n", with: ""))
        return "window.arcadiaChatKitMount && window.arcadiaChatKitMount(JSON.parse(atob(\"\(escaped)\")));"
    }

    private func escapeForJavaScript(_ value: String) -> String {
        return value
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
            .replacingOccurrences(of: "'", with: "\\'")
            .replacingOccurrences(of: "\n", with: "\\n")
    }

    private func baseURL(for configuration: AdvancedChatKitConfiguration) -> URL? {
        if let api = configuration.apiURL, let url = URL(string: api) {
            return URL(string: "\(url.scheme ?? "https")://\(url.host ?? "")")
        }
        return URL(string: "https://arcadiacoach.localhost")
    }
}
