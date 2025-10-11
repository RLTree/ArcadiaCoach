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
        if trimmedBackendURL.isEmpty {
            return "Set your ChatKit backend URL in Settings to enable the custom server."
        }
        if normalizedChatkitURL == nil {
            return "Backend URL looks invalid. Use a full URL like https://localhost:8000/chatkit."
        }
        if trimmedDomainKey.isEmpty {
            return "Add your ChatKit domain key in Settings. ChatKit blocks custom backends until the domain is allow-listed."
        }
        return nil
    }

    private var advancedConfiguration: AdvancedChatKitConfiguration? {
        guard let apiURL = normalizedChatkitURL else { return nil }
        let domainKey = trimmedDomainKey
        return AdvancedChatKitConfiguration(
            agentId: nil,
            token: nil,
            apiURL: apiURL.absoluteString,
            domainKey: domainKey.isEmpty ? nil : domainKey,
            uploadURL: normalizedUploadURL
        )
    }

    private var normalizedChatkitURL: URL? {
        normalizedChatkitURL(from: trimmedBackendURL)
    }

    private var normalizedUploadURL: String? {
        normalizedUploadURL(from: trimmedBackendURL)
    }

    private var trimmedBackendURL: String {
        settings.chatkitBackendURL.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var trimmedDomainKey: String {
        settings.chatkitDomainKey.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func normalizedChatkitURL(from value: String) -> URL? {
        guard !value.isEmpty, var components = URLComponents(string: value) else { return nil }
        var segments = pathSegments(from: components.path)
        segments = ensureSuffix(segments, suffix: ["chatkit"])
        components.path = buildPath(from: segments)
        return components.url
    }

    private func normalizedUploadURL(from value: String) -> String? {
        guard !value.isEmpty, var components = URLComponents(string: value) else { return nil }
        var segments = pathSegments(from: components.path)
        segments = ensureSuffix(segments, suffix: ["api", "chatkit", "upload"])
        components.path = buildPath(from: segments)
        return components.url?.absoluteString
    }

    private func pathSegments(from path: String) -> [String] {
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard !trimmed.isEmpty else { return [] }
        return trimmed.split(separator: "/").map(String.init)
    }

    private func ensureSuffix(_ segments: [String], suffix: [String]) -> [String] {
        var current = segments
        var matchCount = min(current.count, suffix.count)
        while matchCount > 0 {
            let tail = Array(current.suffix(matchCount))
            let expected = Array(suffix.prefix(matchCount))
            if tail == expected {
                break
            }
            matchCount -= 1
        }
        current.append(contentsOf: suffix.dropFirst(matchCount))
        return current
    }

    private func buildPath(from segments: [String]) -> String {
        guard !segments.isEmpty else { return "/chatkit" } // default path when no base provided
        return "/" + segments.joined(separator: "/")
    }
}
