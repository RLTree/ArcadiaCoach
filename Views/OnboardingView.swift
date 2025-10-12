import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject private var settings: AppSettings
    @State private var username: String = ""
    @State private var backendURL: String = ""
    @State private var apiKey: String = ""
    @State private var learningGoal: String = ""
    @State private var learningUseCase: String = ""
    @State private var learningStrengths: String = ""
    @FocusState private var focusedField: Field?

    var onContinue: () -> Void

    enum Field: Hashable {
        case username
        case backend
        case apiKey
    }

    var body: some View {
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
                        placeholder: "Describe the skills, milestones, or roles you’re aiming for over the next 6–12 months."
                    )
                    labeledTextEditor(
                        title: "How you’ll use coding",
                        text: $learningUseCase,
                        placeholder: "Share the domain, projects, or day-to-day work you plan to support with coding."
                    )
                    labeledTextEditor(
                        title: "Current strengths & supports",
                        text: $learningStrengths,
                        placeholder: "List prior knowledge, tools you’re comfortable with, and any accessibility needs that help you learn."
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
                    isBusy: false,
                    isDisabled: !canContinue,
                    action: saveAndContinue
                )
                Spacer()
            }
        }
        .padding(28)
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
        onContinue()
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
            ZStack(alignment: .topLeading) {
                if text.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text(placeholder)
                        .font(.body)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 8)
                }
                TextEditor(text: text)
                    .font(.body)
                    .frame(minHeight: minimumHeight)
                    .padding(4)
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
