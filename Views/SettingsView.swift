import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var settings: AppSettings
    @EnvironmentObject var appVM: AppViewModel
    @StateObject private var diagnostics = ChatKitDiagnosticsViewModel()
    @StateObject private var developerTools = DeveloperToolsViewModel()
    @State private var apiKey: String = ""
    @State private var backendURL: String = ""
   @State private var domainKey: String = ""
   @State private var learnerGoal: String = ""
   @State private var learnerUseCase: String = ""
   @State private var showDeveloperDashboard = false
   @State private var showDeveloperResetConfirmation = false
    private let reasoningOptions = ArcadiaChatbotProps.defaultLevels

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                SettingsSection(title: "OpenAI API") {
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

                SettingsSection(title: "ChatKit Backend") {
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

                SettingsSection(title: "Agent Chat Preferences") {
                    Toggle("Enable web search by default", isOn: $settings.chatWebSearchEnabled)
                    Picker("Default reasoning effort", selection: $settings.chatReasoningLevel) {
                        ForEach(reasoningOptions, id: \.value) { option in
                            Text(option.label).tag(option.value)
                        }
                    }
                    .pickerStyle(.segmented)
                    Text("These defaults apply whenever you open Agent Chat. You can still adjust them during a session.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                SettingsSection(title: "Learner Profile") {
                    TextEditor(text: $learnerGoal)
                        .frame(minHeight: 100)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.secondary.opacity(0.2))
                        )
                        .overlay(alignment: .topLeading) {
                            if learnerGoal.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                                Text("Long-term learning goal")
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                                    .padding(6)
                            }
                        }
                    TextEditor(text: $learnerUseCase)
                        .frame(minHeight: 80)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.secondary.opacity(0.2))
                        )
                        .overlay(alignment: .topLeading) {
                            if learnerUseCase.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                                Text("How you plan to use coding (domain, projects, context)")
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                                    .padding(6)
                            }
                        }
                    Button("Save Learner Profile") {
                        settings.learnerGoal = learnerGoal.trimmingCharacters(in: .whitespacesAndNewlines)
                        settings.learnerUseCase = learnerUseCase.trimmingCharacters(in: .whitespacesAndNewlines)
                    }
                    Text("Arcadia personalises lessons, quizzes, and refreshers using this profile.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                SettingsSection(title: "Accessibility") {
                    Toggle("Reduce motion", isOn: $settings.reduceMotion)
                    Toggle("High contrast", isOn: $settings.highContrast)
                    Toggle("Mute sounds", isOn: $settings.muteSounds)
                    Toggle("Minimal mode", isOn: $settings.minimalMode)
                    Stepper("Font scale: \(String(format: "%.2f", settings.fontScale))×", value: $settings.fontScale, in: 0.9...1.6, step: 0.05)
                }

                SettingsSection(title: "Focus mode") {
                    Stepper("Session minutes: \(settings.sessionMinutes)", value: $settings.sessionMinutes, in: 10...60, step: 5)
                    Stepper("Tasks per chunk: \(settings.focusChunks)", value: $settings.focusChunks, in: 1...6)
                }

                SettingsSection(title: "Developer Tools") {
                    VStack(alignment: .leading, spacing: 10) {
                        Button {
                            Task {
                                await developerTools.normalizeEloPlan(
                                    baseURL: settings.chatkitBackendURL,
                                    settings: settings,
                                    appVM: appVM
                                )
                            }
                        } label: {
                            if developerTools.normalizeInFlight {
                                ProgressView()
                                    .controlSize(.small)
                            } else {
                                Label("Normalise ELO Categories", systemImage: "wand.and.stars")
                            }
                        }
                        .buttonStyle(.bordered)
                        .disabled(developerTools.normalizeInFlight)
                        if let normalizedAt = developerTools.lastNormalizedAt {
                            Text("Last normalised on \(normalizedAt.formatted(date: .numeric, time: .standard)).")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        if let planError = developerTools.planError, !planError.isEmpty {
                            Text(planError)
                                .font(.caption)
                                .foregroundStyle(.red)
                        } else {
                            Text("Fetches the current ELO plan, removes duplicate categories, and updates the backend immediately.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        Button {
                            Task {
                                await developerTools.autoCompleteSchedule(
                                    baseURL: settings.chatkitBackendURL,
                                    settings: settings,
                                    appVM: appVM
                                )
                            }
                        } label: {
                            if developerTools.autoCompleteInFlight {
                                ProgressView()
                                    .controlSize(.small)
                            } else {
                                Label("Auto-complete Lessons & Quizzes", systemImage: "checkmark.circle")
                            }
                        }
                        .buttonStyle(.bordered)
                        .disabled(developerTools.autoCompleteInFlight)
                        if let message = developerTools.autoCompleteMessage {
                            Text(message)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        } else {
                            Text("Marks all pending lessons/quizzes as completed to fast-forward schedule testing (milestones stay locked).")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        Button {
                            showDeveloperResetConfirmation = true
                        } label: {
                            if developerTools.resetInFlight {
                                ProgressView()
                                    .controlSize(.small)
                            } else {
                                Label("Developer Reset", systemImage: "arrow.counterclockwise.circle.fill")
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.red)
                        .disabled(developerTools.resetInFlight)
                        if let resetAt = developerTools.lastResetAt {
                            Text("Last reset on \(resetAt.formatted(date: .numeric, time: .standard)).")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Button("View Assessment Submissions") {
                            showDeveloperDashboard = true
                        }
                        .buttonStyle(.bordered)
                        .disabled(developerTools.isLoadingSubmissions && showDeveloperDashboard)
                        if developerTools.isLoadingSubmissions {
                            ProgressView("Refreshing submissions…")
                                .controlSize(.small)
                        }
                        if let error = developerTools.lastError, !error.isEmpty {
                            Text(error)
                                .font(.caption)
                                .foregroundStyle(.red)
                        } else {
                            Text("Reset clears the learner profile, onboarding assessment bundle, and local responses while keeping your OpenAI key and backend settings intact.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                SettingsSection(title: "Diagnostics") {
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
            .frame(maxWidth: 640, alignment: .leading)
            .padding(24)
        }
        .onAppear {
            apiKey = settings.openaiApiKey
            backendURL = settings.chatkitBackendURL
            domainKey = settings.chatkitDomainKey
            learnerGoal = settings.learnerGoal
            learnerUseCase = settings.learnerUseCase
            // strengths handled implicitly by future assessments
        }
        .sheet(isPresented: $showDeveloperDashboard) {
            DeveloperSubmissionDashboard(
                viewModel: developerTools,
                baseURL: settings.chatkitBackendURL,
                currentUsername: settings.arcadiaUsername
            )
        }
        .confirmationDialog(
            "Developer Reset",
            isPresented: $showDeveloperResetConfirmation,
            titleVisibility: .visible
        ) {
            Button("Reset learner data", role: .destructive) {
                Task {
                    await developerTools.performDeveloperReset(
                        baseURL: settings.chatkitBackendURL,
                        settings: settings,
                        appVM: appVM
                    )
                }
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("This clears the learner profile, curriculum, and assessment submissions. Your backend URL and API key remain saved locally.")
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

private struct SettingsSection<Content: View>: View {
    let title: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.title3)
                .bold()
            VStack(alignment: .leading, spacing: 12) {
                content
            }
            .padding(16)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
        }
    }
}
