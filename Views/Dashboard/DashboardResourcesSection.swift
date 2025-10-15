import SwiftUI

struct DashboardResourcesSection: View {
    @EnvironmentObject private var settings: AppSettings
    @EnvironmentObject private var appVM: AppViewModel

    @ObservedObject var session: SessionViewModel
    let needsOnboarding: Bool
    @Binding var sessionContentExpanded: Bool
    let onRunOnboarding: () -> Void
    let onStartLesson: () async -> Void
    let onStartQuiz: () async -> Void
    let onStartMilestone: () async -> Void
    let onClearSessionContent: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if let curriculum = appVM.curriculumPlan {
                CurriculumOutlineView(plan: curriculum)
                    .transition(.opacity)
            }
            sessionControls
            sessionContentSection
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var disabledSessionActions: Bool {
        needsOnboarding || session.activeAction != nil || appVM.requiresAssessment
    }

    @ViewBuilder
    private var sessionControls: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                GlassButton(
                    title: "Start Lesson",
                    systemName: "book.fill",
                    isBusy: session.activeAction == .lesson,
                    isDisabled: disabledSessionActions
                ) {
                    logSessionAction("lesson")
                    Task { await onStartLesson() }
                }
                GlassButton(
                    title: "Start Quiz",
                    systemName: "gamecontroller.fill",
                    isBusy: session.activeAction == .quiz,
                    isDisabled: disabledSessionActions
                ) {
                    logSessionAction("quiz")
                    Task { await onStartQuiz() }
                }
                GlassButton(
                    title: "Milestone",
                    systemName: "flag.checkered",
                    isBusy: session.activeAction == .milestone,
                    isDisabled: disabledSessionActions
                ) {
                    logSessionAction("milestone")
                    Task { await onStartMilestone() }
                }
                if settings.minimalMode {
                    GlassButton(title: "Focus", systemName: "timer") {
                        logSessionAction("focus_timer")
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
            if needsOnboarding {
                Button {
                    onRunOnboarding()
                } label: {
                    Label("Finish onboarding to enable sessions", systemImage: "exclamationmark.circle")
                }
                .buttonStyle(.bordered)
            }
        }
    }

    @ViewBuilder
    private var sessionContentSection: some View {
        let hasLesson = appVM.latestLesson != nil
        let hasQuiz = appVM.latestQuiz != nil
        let hasMilestone = appVM.latestMilestone != nil
        if !(hasLesson || hasQuiz || hasMilestone) {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 12) {
                DisclosureGroup(isExpanded: $sessionContentExpanded) {
                    VStack(alignment: .leading, spacing: 18) {
                        if let lesson = appVM.latestLesson {
                            LessonView(
                                envelope: WidgetEnvelope(
                                    display: lesson.display,
                                    widgets: lesson.widgets,
                                    citations: lesson.citations
                                )
                            )
                            .environmentObject(settings)
                            .frame(maxWidth: .infinity)
                        }
                        if let quiz = appVM.latestQuiz {
                            QuizSummaryView(elo: quiz.elo, widgets: quiz.widgets, last: quiz.last_quiz)
                                .environmentObject(settings)
                                .environmentObject(appVM)
                                .frame(maxWidth: .infinity)
                        }
                        if let milestone = appVM.latestMilestone {
                            MilestoneView(content: milestone)
                                .environmentObject(settings)
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .padding(.top, 8)
                } label: {
                    HStack {
                        Label("Latest Session Content", systemImage: "sparkles")
                            .font(.headline)
                        Spacer()
                        Text(sessionContentExpanded ? "Hide" : "Show")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Button {
                    onClearSessionContent()
                    sessionContentExpanded = false
                } label: {
                    Label("Clear cached content", systemImage: "xmark.circle")
                        .font(.caption)
                }
                .buttonStyle(.link)
                .accessibilityLabel("Clear cached lesson, quiz, and milestone content")
            }
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
        }
    }

    private func logSessionAction(_ action: String) {
        TelemetryReporter.shared.record(
            event: "session_action_triggered",
            metadata: [
                "action": action,
                "source_section": DashboardSection.resources.rawValue
            ]
        )
    }
}
