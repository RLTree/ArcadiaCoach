import SwiftUI
import WebKit

struct AdvancedChatKitConfiguration: Codable, Equatable {
    var agentId: String
    var token: String?
    var apiURL: String?
    var domainKey: String?
}

struct AdvancedChatKitView: NSViewRepresentable {
    var configuration: AdvancedChatKitConfiguration
    var widgetBase64: String

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.setValue(false, forKey: "drawsBackground")
        if let html = loadHTML(widgetBase64: widgetBase64, configuration: configuration) {
            webView.loadHTMLString(html, baseURL: nil)
        }
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        if let script = try? configurationScript(configuration) {
            webView.evaluateJavaScript(script, completionHandler: nil)
        }
    }

    private func loadHTML(widgetBase64: String, configuration: AdvancedChatKitConfiguration) -> String? {
        guard let url = Bundle.main.url(forResource: "advanced_chatkit", withExtension: "html", subdirectory: "Resources/ChatKit") ?? Bundle.main.url(forResource: "advanced_chatkit", withExtension: "html") else {
            return nil
        }
        guard var html = try? String(contentsOf: url) else { return nil }
        html = html.replacingOccurrences(of: "%WIDGET_BASE64%", with: widgetBase64)
        let configBase64 = (try? configurationData(configuration).base64EncodedString()) ?? ""
        html = html.replacingOccurrences(of: "%CHATKIT_CONFIG_BASE64%", with: configBase64)
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
        let escaped = escapeForJavaScript(base64)
        return "window.arcadiaChatKitMount && window.arcadiaChatKitMount(JSON.parse(atob(\"\(escaped)\")));"
    }

    private func escapeForJavaScript(_ value: String) -> String {
        return value
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
            .replacingOccurrences(of: "'", with: "\\'")
            .replacingOccurrences(of: "\n", with: "\\n")
    }
}
