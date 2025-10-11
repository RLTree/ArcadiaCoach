import SwiftUI
import Foundation

struct ChatPanel: View {
    @EnvironmentObject private var settings: AppSettings
    private let widgetBase64 = WidgetResource.arcadiaChatbotWidgetBase64()

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Agent Chat")
                .font(.title2)
                .bold()
            if let message = configurationMessage {
                Text(message)
                    .font(.body)
                    .foregroundStyle(.secondary)
            } else if let config = advancedConfiguration {
                AdvancedChatKitView(
                    configuration: config,
                    widgetBase64: widgetBase64
                )
                .frame(minHeight: 420)
                if let apiURL = config.apiURL {
                    Text("Connected to \(apiURL).")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text("Unable to configure ChatKit. Double-check your settings.")
                    .font(.body)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
    }

    private var configurationMessage: String? {
        if settings.chatkitBackendURL.isEmpty {
            return "Set your ChatKit backend URL in Settings to enable the custom server."
        }
        if normalizedChatkitURL == nil {
            return "Backend URL looks invalid. Use a full URL like https://localhost:8000/chatkit."
        }
        return nil
    }

    private var advancedConfiguration: AdvancedChatKitConfiguration? {
        guard let apiURL = normalizedChatkitURL else { return nil }
        return AdvancedChatKitConfiguration(
            agentId: nil,
            token: nil,
            apiURL: apiURL.absoluteString,
            domainKey: settings.chatkitDomainKey.isEmpty ? nil : settings.chatkitDomainKey,
            uploadURL: normalizedUploadURL
        )
    }

    private var normalizedChatkitURL: URL? {
        normalizedChatkitURL(from: settings.chatkitBackendURL)
    }

    private var normalizedUploadURL: String? {
        normalizedUploadURL(from: settings.chatkitBackendURL)
    }

    private func normalizedChatkitURL(from value: String) -> URL? {
        guard !value.isEmpty, var components = URLComponents(string: value) else { return nil }
        var path = components.path
        if path.isEmpty || path == "/" {
            path = "/chatkit"
        } else if !path.hasSuffix("/chatkit") {
            path = path.hasSuffix("/") ? path + "chatkit" : path + "/chatkit"
        }
        components.path = path
        return components.url
    }

    private func normalizedUploadURL(from value: String) -> String? {
        guard !value.isEmpty, var components = URLComponents(string: value) else { return nil }
        var path = components.path
        if path.isEmpty || path == "/" {
            path = "/api/chatkit/upload"
        } else if !path.hasSuffix("/api/chatkit/upload") {
            path = path.hasSuffix("/") ? path + "api/chatkit/upload" : path + "/api/chatkit/upload"
        }
        components.path = path
        return components.url?.absoluteString
    }
}
