import SwiftUI
import Combine

struct HomeView: View {
    @EnvironmentObject var settings: AppSettings
    @EnvironmentObject var appVM: AppViewModel
    @StateObject var session = SessionViewModel()
    @State private var showOnboarding = false

    private var topElo: [WidgetStatItem] {
        let labels = categoryLabels
        return appVM.game.elo
            .sorted { $0.value > $1.value }
            .prefix(3)
            .map { .init(label: labels[$0.key] ?? $0.key, value: String($0.value)) }
    }

    private var categoryLabels: [String:String] {
        guard let plan = appVM.eloPlan else { return [:] }
        return Dictionary(uniqueKeysWithValues: plan.categories.map { ($0.key, $0.label) })
    }

    var body: some View {
        ZStack {
            VStack(spacing: 18) {
                header
                if appVM.requiresAssessment, let bundle = appVM.onboardingAssessment {
                    assessmentBanner(status: bundle.status)
                }
                if !settings.minimalMode {
                    WidgetStatRowView(props: .init(items: topElo))
                        .environmentObject(settings)
                }
                if let plan = appVM.eloPlan, !plan.categories.isEmpty {
                    EloPlanSummaryView(plan: plan)
                        .transition(.opacity)
                }
                if let curriculum = appVM.curriculumPlan {
                    CurriculumOutlineView(plan: curriculum)
                        .transition(.opacity)
                }
                sessionControls
                contentTabs
            }
            .padding(24)
            .onAppear {
                showOnboarding = needsOnboarding
                refreshLearnerProfile()
                Task {
                    await session.applyUserContext(
                        username: settings.arcadiaUsername,
                        backendURL: settings.chatkitBackendURL
                    )
                }
            }
            if showOnboarding {
                Color.black.opacity(0.4).ignoresSafeArea()
                OnboardingView {
                    showOnboarding = false
                }
                .frame(maxWidth: 520)
                .background(.bar, in: RoundedRectangle(cornerRadius: 18))
                .padding(40)
            }
            if appVM.showingAssessmentFlow, appVM.requiresAssessment {
                Color.black.opacity(0.45).ignoresSafeArea()
                OnboardingAssessmentFlow()
                    .environmentObject(settings)
                    .environmentObject(appVM)
                    .background(.bar, in: RoundedRectangle(cornerRadius: 20))
                    .padding(32)
            }
        }
        .onReceive(session.$lesson.compactMap { $0 }) { lesson in
            appVM.lastEnvelope = .init(display: lesson.display, widgets: lesson.widgets, citations: lesson.citations)
        }
        .onReceive(session.$quiz.compactMap { $0 }) { quiz in
            let before = appVM.game.elo
            appVM.applyElo(updated: quiz.elo, delta: delta(from: before, to: quiz.elo))
        }
        .onReceive(session.$milestone.compactMap { $0 }) { milestone in
            appVM.lastEnvelope = .init(display: milestone.display, widgets: milestone.widgets, citations: nil)
        }
        .onChange(of: settings.chatkitBackendURL) { newValue in
            Task {
                await session.reset(for: newValue)
                await session.applyUserContext(
                    username: settings.arcadiaUsername,
                    backendURL: newValue
                )
            }
            showOnboarding = needsOnboarding
            refreshLearnerProfile()
        }
        .onChange(of: settings.openaiApiKey) { _ in
            showOnboarding = needsOnboarding
        }
        .onChange(of: settings.arcadiaUsername) { _ in
            showOnboarding = needsOnboarding
            Task {
                await session.applyUserContext(
                    username: settings.arcadiaUsername,
                    backendURL: settings.chatkitBackendURL
                )
            }
        }
        .onChange(of: settings.learnerGoal) { _ in
            refreshLearnerProfile()
        }
        .onChange(of: settings.learnerUseCase) { _ in
            refreshLearnerProfile()
        }
        .onChange(of: settings.learnerStrengths) { _ in
            refreshLearnerProfile()
        }
        .alert(item: $session.lastError) { error in
            Alert(
                title: Text("\(error.action.rawValue) failed"),
                message: Text(error.message),
                dismissButton: .default(Text("OK"))
            )
        }
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 6) {
                Text("Arcadia Coach")
                    .font(.system(size: 32, weight: .bold))
                    .foregroundStyle(Color("Brand"))
                    .accessibilityAddTraits(.isHeader)
                if let usernameLabel {
                    Text(usernameLabel)
                        .font(.title3)
                        .foregroundStyle(.secondary)
                }
                Text("Level \(appVM.game.level) • XP \(appVM.game.xp) • Streak \(appVM.game.streak)")
                    .font(.title3)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if !settings.minimalMode {
                VStack(alignment: .trailing, spacing: 6) {
                    Text("Chunks per session: \(settings.focusChunks)")
                    Text("Duration: \(settings.sessionMinutes) min")
                }
                .font(.footnote)
                .foregroundStyle(.secondary)
            }
        }
    }

    private var sessionControls: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                GlassButton(
                    title: "Start Lesson",
                    systemName: "book.fill",
                    isBusy: session.activeAction == .lesson,
                    isDisabled: (session.activeAction != nil && session.activeAction != .lesson) || appVM.requiresAssessment
                ) {
                    Task { await session.loadLesson(backendURL: settings.chatkitBackendURL, topic: "transformers") }
                }
                GlassButton(
                    title: "Start Quiz",
                    systemName: "gamecontroller.fill",
                    isBusy: session.activeAction == .quiz,
                    isDisabled: (session.activeAction != nil && session.activeAction != .quiz) || appVM.requiresAssessment
                ) {
                    Task { await session.loadQuiz(backendURL: settings.chatkitBackendURL, topic: "pytorch") }
                }
                GlassButton(
                    title: "Milestone",
                    systemName: "flag.checkered",
                    isBusy: session.activeAction == .milestone,
                    isDisabled: (session.activeAction != nil && session.activeAction != .milestone) || appVM.requiresAssessment
                ) {
                    Task { await session.loadMilestone(backendURL: settings.chatkitBackendURL, topic: "roadmap") }
                }
                if settings.minimalMode {
                    GlassButton(title: "Focus", systemName: "timer") {
                        NotificationCenter.default.post(name: .resetFocusTimer, object: nil)
                    }
                }
            }
            .disabled(
                settings.chatkitBackendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                settings.arcadiaUsername.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            )
            .accessibilityElement(children: .contain)

            if let lastEvent = session.lastEventDescription, !lastEvent.isEmpty {
                Text(lastEvent)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            if appVM.requiresAssessment {
                Text("Complete the onboarding assessment to unlock lessons, quizzes, and milestones.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var contentTabs: some View {
        TabView {
            if let lesson = session.lesson {
                LessonView(envelope: .init(display: lesson.display, widgets: lesson.widgets, citations: lesson.citations))
                    .environmentObject(settings)
                    .tabItem { Text("Lesson") }
            }
            if let quiz = session.quiz {
                QuizSummaryView(elo: quiz.elo, widgets: quiz.widgets, last: quiz.last_quiz)
                    .environmentObject(settings)
                    .tabItem { Text("Quiz") }
            }
            if let milestone = session.milestone {
                MilestoneView(content: milestone)
                    .environmentObject(settings)
                    .tabItem { Text("Milestone") }
            }
            if let envelope = appVM.lastEnvelope, !settings.minimalMode {
                AssignmentView(envelope: envelope)
                    .environmentObject(settings)
                    .tabItem { Text("Assignments") }
            }
            ChatPanel()
                .environmentObject(settings)
                .tabItem { Text("Agent Chat") }
            SettingsView()
                .environmentObject(settings)
                .tabItem { Text("Settings") }
        }
        .tabViewStyle(.automatic)
        .frame(maxHeight: .infinity)
    }

    private var needsOnboarding: Bool {
        settings.arcadiaUsername.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
        settings.chatkitBackendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
        settings.openaiApiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var usernameLabel: String? {
        let trimmed = settings.arcadiaUsername.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : "Signed in as \(trimmed)"
    }

    private func delta(from old: [String:Int], to new: [String:Int]) -> [String:Int] {
        var diff: [String:Int] = [:]
        for (key, value) in new {
            diff[key] = value - (old[key] ?? 1100)
        }
        return diff
    }

    private func refreshLearnerProfile() {
        session.updateProfile(
            goal: settings.learnerGoal,
            useCase: settings.learnerUseCase,
            strengths: settings.learnerStrengths
        )
        Task {
            await appVM.loadProfile(
                baseURL: settings.chatkitBackendURL,
                username: settings.arcadiaUsername
            )
        }
    }

    @ViewBuilder
    private func assessmentBanner(status: OnboardingAssessment.Status) -> some View {
        HStack(alignment: .center, spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Onboarding assessment pending")
                    .font(.headline)
                Text(status == .inProgress ? "Pick up where you left off to finish calibration." : "Complete the initial assessment so Arcadia can calibrate your curriculum.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button("Resume") {
                appVM.openAssessmentFlow()
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(16)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16))
    }
}
