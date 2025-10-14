import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject private var settings: AppSettings
    @EnvironmentObject private var appVM: AppViewModel
    @State private var username: String = ""
    @State private var backendURL: String = ""
    @State private var apiKey: String = ""
    @State private var learningGoal: String = ""
    @State private var learningUseCase: String = ""
    @State private var learningStrengths: String = ""
    @State private var isGeneratingPlan: Bool = false
    @State private var planningError: String?
    @FocusState private var focusedField: Field?

    var onContinue: () -> Void

    enum Field: Hashable {
        case username
        case backend
        case apiKey
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Welcome to Arcadia Coach")
                        .font(.system(size: 30, weight: .bold))
                        .accessibilityAddTraits(.isHeader)
                    Text("Set up your workspace so Arcadia can tailor a long-term curriculum just for you.")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                }

                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Choose a username")
                            .font(.headline)
                        TextField("e.g. swift-trailblazer", text: $username)
                            .textFieldStyle(.roundedBorder)
                            .autocorrectionDisabled(true)
                            .focused($focusedField, equals: Field.username)
                        Text("Arcadia uses this name to remember your goals, progress, and ELO.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Connect your backend")
                            .font(.headline)
                        TextField("Backend base URL", text: $backendURL)
                            .textFieldStyle(.roundedBorder)
                            .autocorrectionDisabled(true)
                            .focused($focusedField, equals: Field.backend)
                        Text("This is the Arcadia Coach backend or Render URL that powers sessions.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Add your OpenAI API key")
                            .font(.headline)
                        SecureField("sk-...", text: $apiKey)
                            .textFieldStyle(.roundedBorder)
                            .autocorrectionDisabled(true)
                            .focused($focusedField, equals: Field.apiKey)
                        Text("Stored locally for the backend to authenticate with OpenAI.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }

                    VStack(alignment: .leading, spacing: 12) {
                        Text("Shape your learning path")
                            .font(.headline)
                        labeledTextEditor(
                            title: "Long-term learning goal",
                            text: $learningGoal,
                            placeholder: "Example: Become a staff-level ML engineer within 18 months by mastering production RAG systems and evaluation."
                        )
                        labeledTextEditor(
                            title: "How you’ll use coding",
                            text: $learningUseCase,
                            placeholder: "Example: Apply Python + PyTorch to build accessibility-focused co-pilots for neurodivergent students."
                        )
                        labeledTextEditor(
                            title: "Current strengths & experience",
                            text: $learningStrengths,
                            placeholder: "Example: 3 years of SwiftUI + Combine, strong at accessibility reviews, rebuilding Python fundamentals."
                        )
                        Text("Arcadia combines this profile with spaced refreshers and memory prompts tuned for AuDHD-friendly pacing.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(20)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16))

                VStack(alignment: .leading, spacing: 8) {
                    Label("Motion stays minimal and sounds muted unless you opt in.", systemImage: "eye.trianglebadge.exclamationmark")
                    Label("You’ll review goals with Arcadia right after signing in.", systemImage: "sparkles")
                }
                .font(.footnote)
                .foregroundStyle(.secondary)

                HStack(spacing: 16) {
                    Spacer()
                    GlassButton(
                        title: "Enter Arcadia",
                        systemName: "arrow.right.circle.fill",
                        isBusy: isGeneratingPlan,
                        isDisabled: !canContinue,
                        action: saveAndContinue
                    )
                    Spacer()
                }

                if let planningError {
                    Text(planningError)
                        .font(.footnote)
                        .foregroundStyle(.red)
                } else if isGeneratingPlan {
                    ProgressView("Arcadia is preparing your onboarding plan…")
                        .padding(.top, 8)
                }
            }
            .padding(28)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .scrollIndicators(.automatic)
        .onAppear(perform: preloadSettings)
    }

    private var canContinue: Bool {
        !username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !backendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !learningGoal.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func preloadSettings() {
        username = settings.arcadiaUsername
        backendURL = settings.chatkitBackendURL
        apiKey = settings.openaiApiKey
        learningGoal = settings.learnerGoal
        learningUseCase = settings.learnerUseCase
        learningStrengths = settings.learnerStrengths
        if settings.learnerTimezone.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            settings.learnerTimezone = TimeZone.current.identifier
        }
        if settings.arcadiaUsername.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            focusedField = Field.username
        } else if settings.chatkitBackendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            focusedField = Field.backend
        } else if settings.openaiApiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            focusedField = Field.apiKey
        }
    }

    private func saveAndContinue() {
        settings.arcadiaUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        settings.chatkitBackendURL = backendURL.trimmingCharacters(in: .whitespacesAndNewlines)
        settings.openaiApiKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        settings.learnerGoal = learningGoal.trimmingCharacters(in: .whitespacesAndNewlines)
        settings.learnerUseCase = learningUseCase.trimmingCharacters(in: .whitespacesAndNewlines)
        settings.learnerStrengths = learningStrengths.trimmingCharacters(in: .whitespacesAndNewlines)
        if settings.learnerTimezone.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            settings.learnerTimezone = TimeZone.current.identifier
        }

        let username = settings.arcadiaUsername
        let backend = settings.chatkitBackendURL
        let goal = settings.learnerGoal
        let useCase = settings.learnerUseCase
        let strengths = settings.learnerStrengths

        isGeneratingPlan = true
        planningError = nil
        Task {
            do {
                try await appVM.ensureOnboardingPlan(
                    baseURL: backend,
                    username: username,
                    goal: goal,
                    useCase: useCase,
                    strengths: strengths,
                    timezone: settings.learnerTimezone
                )
                onContinue()
            } catch {
                let nsError = error as NSError
                if let serviceError = error as? BackendServiceError {
                    planningError = serviceError.localizedDescription
                } else if !nsError.localizedDescription.isEmpty {
                    planningError = nsError.localizedDescription
                } else {
                    planningError = String(describing: error)
                }
            }
            isGeneratingPlan = false
        }
    }

    @ViewBuilder
    private func labeledTextEditor(
        title: String,
        text: Binding<String>,
        placeholder: String,
        minimumHeight: CGFloat = 96
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.subheadline)
                .bold()
            Text(placeholder)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .padding(.bottom, 2)
            ZStack(alignment: .topLeading) {
                if text.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text("Tap to add your response…")
                        .font(.callout)
                        .foregroundStyle(.tertiary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 10)
                }
                TextEditor(text: text)
                    .font(.body)
                    .frame(minHeight: minimumHeight)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 10)
                    .background(Color.clear)
            }
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color.primary.opacity(0.02))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Color.secondary.opacity(0.2))
            )
        }
    }
}
