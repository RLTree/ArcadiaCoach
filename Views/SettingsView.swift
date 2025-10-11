import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var settings: AppSettings
    @State private var backendURL: String = ""
    @State private var domainKey: String = ""

    var body: some View {
        Form {
            Section("ChatKit Backend") {
                TextField("Backend base URL", text: $backendURL)
                    .disableAutocorrection(true)
                SecureField("Domain key (optional)", text: $domainKey)
                Button("Save Backend Settings") {
                    settings.chatkitBackendURL = backendURL
                    settings.chatkitDomainKey = domainKey
                }
                Text("Arcadia Coach connects directly to your ChatKit Python server. Provide a domain key only if your backend requires it.")
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
            backendURL = settings.chatkitBackendURL
            domainKey = settings.chatkitDomainKey
        }
    }
}
