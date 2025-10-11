import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var settings: AppSettings
    @StateObject private var diagnostics = ChatKitDiagnosticsViewModel()
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
                if diagnostics.isRunning {
                    ProgressView("Running ChatKit diagnostics…")
                }
                ForEach(diagnostics.results) { result in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: result.iconName)
                            .foregroundStyle(result.tintColor)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(result.title).bold()
                            Text(result.message)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 2)
                }
                if let lastRun = diagnostics.lastRunAt {
                    Text("Last run on \(lastRun.formatted(date: .numeric, time: .standard)).")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Button("Run ChatKit Diagnostics") {
                    Task {
                        await diagnostics.run(with: settings)
                    }
                }
                if diagnostics.results.isEmpty {
                    Text("Run diagnostics to validate your backend URL, domain key, and widget bundle before launching ChatKit.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
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

@MainActor
final class ChatKitDiagnosticsViewModel: ObservableObject {
    enum Status {
        case success
        case warning
        case failure
    }

    struct DiagnosticResult: Identifiable {
        let id = UUID()
        let title: String
        let message: String
        let status: Status

        var iconName: String {
            switch status {
            case .success:
                return "checkmark.circle.fill"
            case .warning:
                return "exclamationmark.triangle.fill"
            case .failure:
                return "xmark.octagon.fill"
            }
        }

        var tintColor: Color {
            switch status {
            case .success:
                return .green
            case .warning:
                return .yellow
            case .failure:
                return .red
            }
        }
    }

    @Published private(set) var results: [DiagnosticResult] = []
    @Published private(set) var isRunning = false
    @Published private(set) var lastRunAt: Date?

    func run(with settings: AppSettings) async {
        if isRunning { return }
        isRunning = true
        results = []
        defer {
            isRunning = false
            lastRunAt = Date()
        }

        let backend = settings.chatkitBackendURL.trimmingCharacters(in: .whitespacesAndNewlines)
        let domainKey = settings.chatkitDomainKey.trimmingCharacters(in: .whitespacesAndNewlines)

        var newResults: [DiagnosticResult] = []

        newResults.append(evaluateDomainKey(domainKey))
        newResults.append(evaluateBackendURL(backend))

        if let backendURL = normalizedChatkitURL(from: backend) {
            newResults.append(await evaluateHealthEndpoint(for: backendURL))
        } else {
            newResults.append(
                DiagnosticResult(
                    title: "Backend Health Check",
                    message: "Skipped because the backend URL could not be normalised.",
                    status: .warning
                )
            )
        }

        if WidgetResource.isArcadiaWidgetBundled {
            newResults.append(
                DiagnosticResult(
                    title: "ArcadiaChatbot Widget",
                    message: "Bundled widget detected. Verify it stays in sync with the backend stream.",
                    status: .warning
                )
            )
        } else {
            newResults.append(
                DiagnosticResult(
                    title: "ArcadiaChatbot Widget",
                    message: "No bundled widget found — the backend will stream the Arcadia chatbot UI on demand.",
                    status: .success
                )
            )
        }

        if let inlineDiagnostics = ChatKitResource.inlineModuleDiagnostics() {
            if inlineDiagnostics.isFallbackStub {
                newResults.append(
                    DiagnosticResult(
                        title: "ChatKit Inline Fallback",
                        message: "Inline module stub detected (size \(inlineDiagnostics.byteCount) bytes). Replace `Resources/ChatKit/chatkit.inline.mjs` with the official ChatKit bundle to run offline or behind strict firewalls.",
                        status: .warning
                    )
                )
            } else {
                newResults.append(
                    DiagnosticResult(
                        title: "ChatKit Inline Fallback",
                        message: "Inline module ready (size \(inlineDiagnostics.byteCount) bytes). ChatKit will load locally if CDN access fails.",
                        status: .success
                    )
                )
            }
        } else {
            newResults.append(
                DiagnosticResult(
                    title: "ChatKit Inline Fallback",
                    message: "No inline ChatKit bundle found. Provide `Resources/ChatKit/chatkit.inline.mjs` when CDN access is blocked.",
                    status: .warning
                )
            )
        }

        results = newResults
    }

    private func evaluateDomainKey(_ domainKey: String) -> DiagnosticResult {
        if domainKey.isEmpty {
            return DiagnosticResult(
                title: "ChatKit Domain Key",
                message: "Add the domain key from OpenAI’s allow-list (for example `domain_pk_…`). Without it ChatKit will block custom backends.",
                status: .failure
            )
        }
        if domainKey.hasPrefix("domain_pk_") && domainKey.count > 20 {
            return DiagnosticResult(
                title: "ChatKit Domain Key",
                message: "Domain key saved. Confirm it matches `domain_pk_68e9a8cac6808190bbd92778730ea51b0dd821b29e8e5cd0` from your OpenAI dashboard.",
                status: .success
            )
        }
        return DiagnosticResult(
            title: "ChatKit Domain Key",
            message: "Domain key looks unusual. Double-check the value in Settings → ChatKit Backend.",
            status: .warning
        )
    }

    private func evaluateBackendURL(_ backend: String) -> DiagnosticResult {
        if backend.isEmpty {
            return DiagnosticResult(
                title: "ChatKit Backend URL",
                message: "Set the backend base URL (for example `https://staging.arcadia.dev`).",
                status: .failure
            )
        }
        guard let url = normalizedChatkitURL(from: backend) else {
            return DiagnosticResult(
                title: "ChatKit Backend URL",
                message: "Unable to normalise the backend URL. Use a full URL such as https://localhost:8000.",
                status: .failure
            )
        }
        return DiagnosticResult(
            title: "ChatKit Backend URL",
            message: "Backend URL looks valid. ChatKit will call \(url.absoluteString).",
            status: .success
        )
    }

    private func evaluateHealthEndpoint(for chatkitURL: URL) async -> DiagnosticResult {
        guard var components = URLComponents(url: chatkitURL, resolvingAgainstBaseURL: false) else {
            return DiagnosticResult(
                title: "Backend Health Check",
                message: "Unable to construct health check path from backend URL.",
                status: .failure
            )
        }
        components.path = "/healthz"
        guard let healthURL = components.url else {
            return DiagnosticResult(
                title: "Backend Health Check",
                message: "Failed to build /healthz URL for diagnostics.",
                status: .failure
            )
        }

        var request = URLRequest(url: healthURL)
        request.timeoutInterval = 6

        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 6
        configuration.timeoutIntervalForResource = 6
        let session = URLSession(configuration: configuration)

        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                return DiagnosticResult(
                    title: "Backend Health Check",
                    message: "Received unexpected response from \(healthURL.absoluteString).",
                    status: .warning
                )
            }
            guard (200...299).contains(httpResponse.statusCode) else {
                return DiagnosticResult(
                    title: "Backend Health Check",
                    message: "Backend responded with status \(httpResponse.statusCode). Confirm CORS and domain allow-list configuration.",
                    status: .failure
                )
            }
            if let summary = parseHealthSummary(from: data) {
                return DiagnosticResult(
                    title: "Backend Health Check",
                    message: summary,
                    status: .success
                )
            }
            return DiagnosticResult(
                title: "Backend Health Check",
                message: "Health endpoint responded with HTTP \(httpResponse.statusCode).",
                status: .success
            )
        } catch {
            return DiagnosticResult(
                title: "Backend Health Check",
                message: "Health check failed: \(error.localizedDescription)",
                status: .failure
            )
        }
    }

    private func parseHealthSummary(from data: Data) -> String? {
        guard
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let status = object["status"] as? String
        else {
            return nil
        }
        if let mode = object["mode"] as? String {
            return "Health endpoint OK (`status=\(status)`, `mode=\(mode)`)."
        }
        return "Health endpoint OK (`status=\(status)`)."
    }

    private func normalizedChatkitURL(from value: String) -> URL? {
        guard !value.isEmpty, var components = URLComponents(string: value) else { return nil }
        var segments = pathSegments(from: components.path)
        segments = ensureSuffix(segments, suffix: ["chatkit"])
        components.path = buildPath(from: segments)
        return components.url
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
        guard !segments.isEmpty else { return "/chatkit" }
        return "/" + segments.joined(separator: "/")
    }
}
