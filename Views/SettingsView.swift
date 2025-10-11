import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var settings: AppSettings
    @State private var apiKey: String = ""
    @State private var backendURL: String = ""
    @State private var domainKey: String = ""

    var body: some View {
        Form {
            Section("OpenAI API") {
                SecureField("OPENAI_API_KEY", text: $apiKey)
                    .textContentType(.password)
                    .autocorrectionDisabled(true)
                Button("Save API Key") {
                    settings.openaiApiKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
                }
                if settings.openaiApiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text("Add your OpenAI API key so the Arcadia backend can authenticate with OpenAI.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                } else {
                    Text("API key saved locally. Update the backend if needed.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            Section("ChatKit Backend") {
                TextField("Backend base URL", text: $backendURL)
                    .disableAutocorrection(true)
                SecureField("Domain key (optional)", text: $domainKey)
                Button("Save Backend Settings") {
                    let trimmedBackend = backendURL.trimmingCharacters(in: .whitespacesAndNewlines)
                    let trimmedDomain = domainKey.trimmingCharacters(in: .whitespacesAndNewlines)
                    settings.chatkitBackendURL = trimmedBackend
                    settings.chatkitDomainKey = trimmedDomain
                    backendURL = trimmedBackend
                    domainKey = trimmedDomain
                }
                Text("Arcadia Coach connects directly to your ChatKit server. Add the domain key from the ChatKit dashboard so custom backends render correctly.")
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
                if settings.chatkitBackendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text("Configure a ChatKit backend URL to fetch domain-backed sessions.").foregroundStyle(.secondary)
                } else {
                    Text("Backend URL saved. Restart sessions from Home to apply changes.").foregroundStyle(.secondary)
                }
            }
        }
        .padding()
        .onAppear {
            apiKey = settings.openaiApiKey
            backendURL = settings.chatkitBackendURL
            domainKey = settings.chatkitDomainKey
        }
    }
}
