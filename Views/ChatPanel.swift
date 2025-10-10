import SwiftUI
import Foundation

struct ChatPanel: View {
    @EnvironmentObject private var settings: AppSettings
    @State private var advancedSession: ChatKitSessionResponse?
    @State private var advancedStatus: String?
    @State private var advancedLoading: Bool = false
    private let widgetBase64 = WidgetResource.miniChatbotWidgetBase64()

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Agent Chat")
                .font(.title2)
                .bold()
            if settings.agentId.isEmpty {
                Text("Add an Agent ID in Settings to enable the advanced ChatKit experience.")
                    .font(.body)
                    .foregroundStyle(.secondary)
            } else if directConnectionConfiguration == nil && settings.chatkitBackendURL.isEmpty {
                Text("Set your ChatKit backend URL in Settings to issue tokens for ChatKit.")
                    .font(.body)
                    .foregroundStyle(.secondary)
            } else if directConnectionConfiguration != nil && settings.chatkitDomainKey.isEmpty {
                Text("Provide a domain key in Settings to connect directly to your ChatKit backend.")
                    .font(.body)
                    .foregroundStyle(.secondary)
            } else if advancedLoading {
                ProgressView("Fetching ChatKit token…")
            } else if let config = advancedConfiguration {
                AdvancedChatKitView(
                    configuration: config,
                    widgetBase64: widgetBase64
                )
                .frame(minHeight: 420)
                if let expiry = advancedSession?.expires_at, config.apiURL == nil {
                    Text("Token expires \(expiry.formatted(date: .omitted, time: .shortened)).")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                } else if let apiURL = config.apiURL {
                    Text("Connected to \(apiURL) using domain key authentication.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text(advancedStatus ?? "Unable to fetch ChatKit token.")
                    .font(.body)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .onChange(of: settings.agentId) { _ in
            advancedSession = nil
        }
        .task(id: advancedTaskKey) {
            await loadAdvancedSession()
        }
    }

    private var advancedTaskKey: String {
        [settings.chatkitBackendURL, settings.agentId, settings.chatkitDeviceId, settings.chatkitDomainKey].joined(separator: "|")
    }

    private var directConnectionConfiguration: AdvancedChatKitConfiguration? {
        guard !settings.chatkitBackendURL.isEmpty, !settings.chatkitDomainKey.isEmpty else {
            return nil
        }
        guard let apiURL = normalizedChatkitURL(from: settings.chatkitBackendURL) else {
            return nil
        }
        return AdvancedChatKitConfiguration(
            agentId: settings.agentId,
            token: nil,
            apiURL: apiURL.absoluteString,
            domainKey: settings.chatkitDomainKey
        )
    }

    private var tokenBasedConfiguration: AdvancedChatKitConfiguration? {
        if let session = advancedSession {
            return AdvancedChatKitConfiguration(
                agentId: settings.agentId,
                token: session.client_secret,
                apiURL: nil,
                domainKey: nil
            )
        }
        if !settings.chatkitClientToken.isEmpty {
            return AdvancedChatKitConfiguration(
                agentId: settings.agentId,
                token: settings.chatkitClientToken,
                apiURL: nil,
                domainKey: nil
            )
        }
        return nil
    }

    private var advancedConfiguration: AdvancedChatKitConfiguration? {
        directConnectionConfiguration ?? tokenBasedConfiguration
    }

    private func normalizedChatkitURL(from value: String) -> URL? {
        guard var components = URLComponents(string: value) else { return nil }
        var path = components.path
        if path.isEmpty || path == "/" {
            path = "/chatkit"
        } else if !path.hasSuffix("/chatkit") {
            if path.hasSuffix("/") {
                path += "chatkit"
            } else {
                path += "/chatkit"
            }
        }
        components.path = path
        return components.url
    }

    @MainActor
    private func loadAdvancedSession() async {
        guard !settings.agentId.isEmpty else { return }

        if directConnectionConfiguration != nil {
            advancedSession = nil
            advancedStatus = nil
            return
        }

        guard let baseURL = URL(string: settings.chatkitBackendURL) else {
            advancedStatus = "Invalid backend URL."
            return
        }
        advancedLoading = true
        defer { advancedLoading = false }
        do {
            let session = try await ChatKitTokenService.fetch(baseURL: baseURL, deviceId: settings.chatkitDeviceId)
            advancedSession = session
            advancedStatus = nil
        } catch {
            advancedStatus = error.localizedDescription
        }
    }
}
