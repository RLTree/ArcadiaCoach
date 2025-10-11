import SwiftUI
import Combine

struct HomeView: View {
    @EnvironmentObject var settings: AppSettings
    @EnvironmentObject var appVM: AppViewModel
    @StateObject var session = SessionViewModel()
    @State private var showOnboarding = false

    private var topElo: [WidgetStatItem] {
        appVM.game.elo
            .sorted { $0.value > $1.value }
            .prefix(3)
            .map { .init(label: $0.key, value: String($0.value)) }
    }

    var body: some View {
        ZStack {
            VStack(spacing: 18) {
                header
                if !settings.minimalMode {
                    WidgetStatRowView(props: .init(items: topElo))
                        .environmentObject(settings)
                }
                sessionControls
                contentTabs
            }
            .padding(24)
            .onAppear {
                showOnboarding = settings.chatkitBackendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
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
            Task { await session.reset(for: newValue) }
            if !newValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                showOnboarding = false
            }
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
                    isDisabled: session.activeAction != nil && session.activeAction != .lesson
                ) {
                    Task { await session.loadLesson(backendURL: settings.chatkitBackendURL, topic: "transformers") }
                }
                GlassButton(
                    title: "Start Quiz",
                    systemName: "gamecontroller.fill",
                    isBusy: session.activeAction == .quiz,
                    isDisabled: session.activeAction != nil && session.activeAction != .quiz
                ) {
                    Task { await session.loadQuiz(backendURL: settings.chatkitBackendURL, topic: "pytorch") }
                }
                GlassButton(
                    title: "Milestone",
                    systemName: "flag.checkered",
                    isBusy: session.activeAction == .milestone,
                    isDisabled: session.activeAction != nil && session.activeAction != .milestone
                ) {
                    Task { await session.loadMilestone(backendURL: settings.chatkitBackendURL, topic: "roadmap") }
                }
                if settings.minimalMode {
                    GlassButton(title: "Focus", systemName: "timer") {
                        NotificationCenter.default.post(name: .resetFocusTimer, object: nil)
                    }
                }
            }
            .disabled(settings.chatkitBackendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            .accessibilityElement(children: .contain)

            if let lastEvent = session.lastEventDescription, !lastEvent.isEmpty {
                Text(lastEvent)
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

    private func delta(from old: [String:Int], to new: [String:Int]) -> [String:Int] {
        var diff: [String:Int] = [:]
        for (key, value) in new {
            diff[key] = value - (old[key] ?? 1100)
        }
        return diff
    }
}
