import SwiftUI

struct DashboardResourcesSection: View {
    @EnvironmentObject private var appVM: AppViewModel

    let needsOnboarding: Bool
    let onRunOnboarding: () -> Void
    private let clipboard: ClipboardManaging = AppClipboardManager.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if let curriculum = appVM.curriculumPlan {
                CurriculumOutlineView(plan: curriculum)
                    .transition(.opacity)
            } else {
                Text("Curriculum outline unavailable. Run onboarding to generate your personalised roadmap.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .selectableContent()
                if needsOnboarding {
                    Button {
                        onRunOnboarding()
                    } label: {
                        Label("Run onboarding", systemImage: "person.fill.badge.plus")
                    }
                    .buttonStyle(.borderedProminent)
                }
            }

        if let plan = appVM.goalInference {
            FoundationTracksCard(
                tracks: plan.tracks,
                goalSummary: plan.summary,
                targetOutcomes: plan.targetOutcomes
            )
                .transition(.opacity)
        }

            if let summary = appVM.curriculumPlan?.overview, !summary.isEmpty {
                Text(summary)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .selectableContent()
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .selectableContent()
        .contextMenu {
            Button("Copy resources overview") {
                clipboard.copy(resourcesSummary())
            }
        }
    }

    private func resourcesSummary() -> String {
        var lines: [String] = []
        if let curriculum = appVM.curriculumPlan {
            lines.append("Curriculum outline available: \(curriculum.modules.count) modules")
        } else {
            lines.append("Curriculum outline unavailable")
        }
        if let inference = appVM.goalInference {
            lines.append("Goal parser tracks: \(inference.tracks.count)")
            if let summary = inference.summary, !summary.isEmpty {
                lines.append("Goal summary: \(summary)")
            }
            if !inference.targetOutcomes.isEmpty {
                let outcomes = inference.targetOutcomes.joined(separator: ", ")
                lines.append("Target outcomes: \(outcomes)")
            }
        }
        if let overview = appVM.curriculumPlan?.overview, !overview.isEmpty {
            lines.append("Overview: \(overview)")
        }
        return lines.joined(separator: "\n")
    }
}

struct DashboardSessionsSection: View {
    @EnvironmentObject private var settings: AppSettings
    @EnvironmentObject private var appVM: AppViewModel

    @ObservedObject var session: SessionViewModel
    let needsOnboarding: Bool
    @Binding var sessionContentExpanded: Bool
    let onRunOnboarding: () -> Void
    let onClearSessionContent: () -> Void
    private let clipboard: ClipboardManaging = AppClipboardManager.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            sessionControls
            sessionContentSection
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .selectableContent()
        .contextMenu {
            Button("Copy session recap") {
                clipboard.copy(sessionSummary())
            }
        }
    }

    @ViewBuilder
    private var sessionControls: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let lastEvent = session.lastEventDescription, !lastEvent.isEmpty {
                Text(lastEvent)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .selectableContent()
            }
            if appVM.requiresAssessment {
                Text("Complete the onboarding assessment to unlock lessons, quizzes, and milestones.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .selectableContent()
            }
            if needsOnboarding {
                Button {
                    onRunOnboarding()
                } label: {
                    Label("Finish onboarding to enable sessions", systemImage: "exclamationmark.circle")
                }
                .buttonStyle(.bordered)
            }
            Text("Launch lessons, quizzes, and milestones directly from your curriculum schedule.")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .selectableContent()
            if settings.minimalMode {
                GlassButton(title: "Focus Timer", systemName: "timer") {
                    logSessionAction("focus_timer")
                    NotificationCenter.default.post(name: .resetFocusTimer, object: nil)
                }
                .disabled(session.activeAction != nil)
            }
        }
    }

    @ViewBuilder
    private var sessionContentSection: some View {
        let hasLesson = appVM.latestLesson != nil
        let hasQuiz = appVM.latestQuiz != nil
        let hasMilestone = appVM.latestMilestone != nil
        if !(hasLesson || hasQuiz || hasMilestone) {
            VStack(alignment: .leading, spacing: 8) {
                Text("No session content cached yet.")
                    .foregroundStyle(.secondary)
                Text("Open the schedule tab to start a lesson, quiz, or milestone.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(20)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
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
            .selectableContent()
        }
    }

    private func logSessionAction(_ action: String) {
        TelemetryReporter.shared.record(
            event: "session_action_triggered",
            metadata: [
                "action": action,
                "source_section": DashboardSection.sessions.rawValue
            ]
        )
    }

    private func sessionSummary() -> String {
        var lines: [String] = []
        if let lastEvent = session.lastEventDescription, !lastEvent.isEmpty {
            lines.append("Last session event: \(lastEvent)")
        }
        if appVM.requiresAssessment {
            lines.append("Assessment required before sessions can start")
        }
        if let lesson = appVM.latestLesson {
            lines.append("Latest lesson: \(lesson.display)")
        }
        if let quiz = appVM.latestQuiz {
            lines.append("Latest quiz summary available")
        }
        if let milestone = appVM.latestMilestone {
            lines.append("Latest milestone: \(milestone.display)")
        }
        return lines.joined(separator: "\n")
    }
}
