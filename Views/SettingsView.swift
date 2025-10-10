import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var settings: AppSettings
    @State private var apiKey: String = KeychainHelper.get("OPENAI_API_KEY") ?? ""
    @State private var clientToken: String = ""
    @State private var backendURL: String = ""
    @State private var domainKey: String = ""
    @State private var deviceId: String = ""
    @State private var fetchStatus: String?
    @State private var isFetchingToken: Bool = false

    var body: some View {
        Form {
            Section("Accounts") {
                SecureField("OpenAI API Key", text: $apiKey)
                    .textContentType(.password)
                    .accessibilityLabel("OpenAI API Key")
                Button("Save Key") {
                    KeychainHelper.set(apiKey, for: "OPENAI_API_KEY")
                }
                TextField("Agent ID", text: $settings.agentId)
            }
            Section("ChatKit Backend") {
                TextField("Backend base URL", text: $backendURL)
                SecureField("Domain key", text: $domainKey)
                TextField("Device ID", text: $deviceId)
                Button(action: fetchChatKitToken) {
                    if isFetchingToken {
                        ProgressView()
                    } else {
                        Text("Fetch token from backend")
                    }
                }
                .disabled(backendURL.isEmpty || isFetchingToken)
                if let fetchStatus {
                    Text(fetchStatus)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                SecureField("Override client token (optional)", text: $clientToken)
                    .textContentType(.password)
                Button("Save ChatKit Token") {
                    settings.chatkitClientToken = clientToken
                }
                Button("Save Backend Settings") {
                    settings.chatkitBackendURL = backendURL
                    settings.chatkitDeviceId = deviceId
                    settings.chatkitDomainKey = domainKey
                }
                Text("Arcadia Coach now always uses the web-based ChatKit experience. Provide either a domain key or a short-lived client token to connect.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Section("Accessibility") {
                Toggle("Reduce motion", isOn: $settings.reduceMotion)
                Toggle("High contrast", isOn: $settings.highContrast)
                Toggle("Mute sounds", isOn: $settings.muteSounds)
                Toggle("Minimal mode", isOn: $settings.minimalMode)
                Stepper("Font scale: \(String(format: "%.2f", settings.fontScale))×", value: $settings.fontScale, in: 0.9...1.6, step: 0.05)
            }
            Section("Focus mode") {
                Stepper("Session minutes: \(settings.sessionMinutes)", value: $settings.sessionMinutes, in: 10...60, step: 5)
                Stepper("Tasks per chunk: \(settings.focusChunks)", value: $settings.focusChunks, in: 1...6)
            }
            Section("Diagnostics") {
                if settings.agentId.isEmpty {
                    Text("Add an Agent ID to unlock lesson and quiz requests.").foregroundStyle(.secondary)
                }
                if settings.chatkitBackendURL.isEmpty {
                    Text("Configure a ChatKit backend URL to fetch domain-backed sessions.").foregroundStyle(.secondary)
                }
                if settings.chatkitDomainKey.isEmpty && settings.chatkitClientToken.isEmpty {
                    Text("Provide either a domain key or an override client token so ChatKit can connect.").foregroundStyle(.secondary)
                }
            }
        }
        .padding()
        .onAppear {
            clientToken = settings.chatkitClientToken
            backendURL = settings.chatkitBackendURL
            deviceId = settings.chatkitDeviceId
            domainKey = settings.chatkitDomainKey
        }
    }

    private func fetchChatKitToken() {
        guard let url = URL(string: backendURL) else {
            fetchStatus = "Invalid backend URL."
            return
        }
        isFetchingToken = true
        fetchStatus = nil
        Task {
            do {
                let response = try await ChatKitTokenService.fetch(baseURL: url, deviceId: deviceId)
                settings.chatkitClientToken = response.client_secret
                settings.chatkitBackendURL = backendURL
                settings.chatkitDeviceId = deviceId
                fetchStatus = "Token fetched (expires \(response.expires_at?.formatted() ?? "soon"))."
                clientToken = response.client_secret
            } catch {
                fetchStatus = "Fetch failed: \(error.localizedDescription)"
            }
            isFetchingToken = false
        }
    }
}
