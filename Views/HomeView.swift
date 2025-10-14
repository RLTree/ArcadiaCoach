import SwiftUI
import Combine

struct HomeView: View {
    private enum MainTab: Hashable {
        case dashboard
        case assessment
        case chat
        case settings
    }

    @EnvironmentObject var settings: AppSettings
    @EnvironmentObject var appVM: AppViewModel
    @StateObject var session = SessionViewModel()
    @State private var showOnboarding = false
    @State private var selectedTab: MainTab = .dashboard
    @State private var sessionContentExpanded = false

    private var assessmentTabBadge: String? {
        appVM.requiresAssessment ? "!" : nil
    }

    private var focusedSubmissionBinding: Binding<AssessmentSubmissionRecord?> {
        Binding(
            get: { appVM.focusedSubmission },
            set: { newValue in
                if let submission = newValue {
                    appVM.focus(on: submission)
                } else {
                    appVM.dismissSubmissionFocus()
                }
            }
        )
    }

    private var allEloItems: [WidgetStatItem] {
        let labels = categoryLabels
        return appVM.game.elo
            .sorted { $0.value > $1.value }
            .map { .init(label: labels[$0.key] ?? $0.key, value: String($0.value)) }
    }

    private var categoryLabels: [String:String] {
        guard let plan = appVM.eloPlan else { return [:] }
        return Dictionary(uniqueKeysWithValues: plan.categories.map { ($0.key, $0.label) })
    }

    var body: some View {
        ZStack(alignment: .center) {
            Color(nsColor: .windowBackgroundColor)
                .ignoresSafeArea()

            TabView(selection: $selectedTab) {
                dashboardTab
                    .tabItem { Label("Dashboard", systemImage: "rectangle.grid.2x2") }
                    .tag(MainTab.dashboard)

                assessmentTab
                    .tabItem {
                        Label("Assessment", systemImage: "checklist")
                    }
                    .tag(MainTab.assessment)
                    .badge(assessmentTabBadge)

                ChatPanel()
                    .environmentObject(settings)
                    .environmentObject(appVM)
                    .tabItem { Label("Agent Chat", systemImage: "bubble.left.and.bubble.right") }
                    .tag(MainTab.chat)

                SettingsView()
                    .environmentObject(settings)
                    .tabItem { Label("Settings", systemImage: "gearshape") }
                    .tag(MainTab.settings)
            }
            .onAppear {
                selectedTab = appVM.requiresAssessment ? .assessment : .dashboard
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
                onboardingOverlay
            }
        }
        .onReceive(session.$lesson.compactMap { $0 }) { lesson in
            appVM.recordLesson(lesson)
            sessionContentExpanded = true
        }
        .onReceive(session.$quiz.compactMap { $0 }) { quiz in
            let before = appVM.game.elo
            appVM.applyElo(updated: quiz.elo, delta: delta(from: before, to: quiz.elo))
            appVM.recordQuiz(quiz)
            sessionContentExpanded = true
        }
        .onReceive(session.$milestone.compactMap { $0 }) { milestone in
            appVM.recordMilestone(milestone)
            sessionContentExpanded = true
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
        .onChange(of: settings.learnerTimezone) { _ in
            refreshLearnerProfile()
        }
        .onChange(of: appVM.requiresAssessment) { required in
            if required {
                selectedTab = .assessment
            }
        }
        .alert(item: $session.lastError) { error in
            Alert(
                title: Text("\(error.action.rawValue) failed"),
                message: Text(error.message),
                dismissButton: .default(Text("OK"))
            )
        }
        .onReceive(NotificationCenter.default.publisher(for: .developerResetCompleted)) { _ in
            selectedTab = .assessment
            showOnboarding = true
        }
        .onReceive(appVM.$learnerTimezone) { timezone in
            guard let timezone, !timezone.isEmpty else { return }
            if settings.learnerTimezone != timezone {
                settings.learnerTimezone = timezone
            }
            session.updateProfile(
                goal: settings.learnerGoal,
                useCase: settings.learnerUseCase,
                strengths: settings.learnerStrengths,
                timezone: timezone
            )
        }
        .sheet(
            item: focusedSubmissionBinding
        ) { submission in
            AssessmentSubmissionDetailView(
                submission: submission,
                plan: appVM.eloPlan,
                curriculum: appVM.curriculumPlan
            )
            .environmentObject(settings)
            .environmentObject(appVM)
        }
    }

    @ViewBuilder
    private var onboardingOverlay: some View {
        ZStack {
            Color.black.opacity(0.45).ignoresSafeArea()
            OnboardingView {
                showOnboarding = false
            }
            .frame(maxWidth: 520)
            .background(.bar, in: RoundedRectangle(cornerRadius: 18))
            .padding(40)
        }
        .transition(.opacity)
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
            if !showOnboarding {
                Button {
                    showOnboarding = true
                } label: {
                    Label("Run Onboarding", systemImage: "person.crop.circle.badge.plus")
                        .labelStyle(.titleAndIcon)
                }
                .buttonStyle(.bordered)
                .accessibilityLabel("Re-run onboarding setup")
            }
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

    private var dashboardTab: some View {
        ZStack {
            Color(nsColor: .windowBackgroundColor)
                .ignoresSafeArea()

            if appVM.awaitingAssessmentResults {
                VStack(spacing: 12) {
                    ProgressView()
                        .controlSize(.large)
                    Text("Waiting for assessment results…")
                        .font(.headline)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView(.vertical, showsIndicators: true) {
                    VStack(spacing: 18) {
                        header
                        assessmentSummaryCard
                        if appVM.requiresAssessment, let bundle = appVM.onboardingAssessment {
                            assessmentBanner(status: bundle.status)
                        }
                        if let result = appVM.assessmentResult ?? appVM.latestGradedAssessment?.grading {
                            assessmentResultsCard(result: result)
                        }
                        assessmentHistorySection
                        if !settings.minimalMode && !allEloItems.isEmpty {
                            VStack(alignment: .leading, spacing: 8) {
                                Label("Current ELO Ratings", systemImage: "chart.bar")
                                    .font(.subheadline.bold())
                                    .foregroundStyle(.primary)
                                if let stamp = appVM.latestAssessmentGradeTimestamp {
                                    Text("Calibrated \(stamp.formatted(date: .abbreviated, time: .shortened))")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                } else if let pending = appVM.latestAssessmentSubmittedAt {
                                    Text("Awaiting grading for submission on \(pending.formatted(date: .abbreviated, time: .shortened))")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                WidgetStatRowView(props: .init(items: allEloItems))
                                    .environmentObject(settings)
                            }
                        }
                        if let plan = appVM.eloPlan, !plan.categories.isEmpty {
                            EloPlanSummaryView(plan: plan)
                                .transition(.opacity)
                        }
                        if !appVM.foundationTracks.isEmpty {
                            FoundationTracksCard(
                                tracks: appVM.foundationTracks,
                                goalSummary: appVM.goalInference?.summary,
                                targetOutcomes: appVM.goalInference?.targetOutcomes ?? []
                            )
                            .transition(.opacity)
                        }
                        if let curriculum = appVM.curriculumPlan {
                            CurriculumOutlineView(plan: curriculum)
                                .transition(.opacity)
                        }
                        if let schedule = appVM.curriculumSchedule, !schedule.items.isEmpty {
                            CurriculumScheduleView(
                                schedule: schedule,
                                categoryLabels: categoryLabels,
                                isRefreshing: appVM.scheduleRefreshing,
                                adjustingItemId: appVM.adjustingScheduleItemId,
                                refreshAction: refreshSchedule,
                                adjustAction: deferSchedule
                            )
                            .transition(.opacity)
                        }
                        sessionControls
                        sessionContentSection
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(24)
                }
            }
        }
    }

    private var assessmentTab: some View {
        Group {
            if appVM.requiresAssessment {
                OnboardingAssessmentFlow()
                    .environmentObject(settings)
                    .environmentObject(appVM)
                    .padding(.vertical, 20)
            } else if appVM.onboardingAssessment == nil {
                VStack(spacing: 16) {
                    Text("Onboarding assessment not ready")
                        .font(.title2.bold())
                    Text("Run the onboarding flow to generate your personalised curriculum and assessment bundle.")
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                    Button("Run Onboarding") {
                        showOnboarding = true
                    }
                    .buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                VStack(spacing: 16) {
                    Text("Onboarding assessment completed")
                        .font(.title2.bold())
                    Text("Review your grading summary and curriculum on the Dashboard tab, or reopen the assessment from there if you need to revisit your responses.")
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(nsColor: .windowBackgroundColor).ignoresSafeArea())
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
            strengths: settings.learnerStrengths,
            timezone: settings.learnerTimezone
        )
        Task {
            await appVM.loadProfile(
                baseURL: settings.chatkitBackendURL,
                username: settings.arcadiaUsername
            )
        }
    }

    private func refreshSchedule() {
        Task {
            await appVM.refreshCurriculumSchedule(
                baseURL: settings.chatkitBackendURL,
                username: settings.arcadiaUsername
            )
        }
    }

    private func deferSchedule(item: SequencedWorkItem, days: Int) {
        Task {
            await appVM.deferScheduleItem(
                baseURL: settings.chatkitBackendURL,
                username: settings.arcadiaUsername,
                item: item,
                days: days,
                reason: "manual_defer_\(days)"
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

    @ViewBuilder
    private var assessmentSummaryCard: some View {
        let pendingSubmission = appVM.assessmentHistory.first { $0.grading == nil }
        let readiness = appVM.assessmentReadinessStatus
        let statusText = readiness.displayText
        let statusIcon = readiness.systemImageName
        let statusColor = readiness.tintColor

        let submissionLabel = appVM.latestAssessmentSubmittedAt?
            .formatted(date: .abbreviated, time: .shortened) ?? "No submissions yet"

        let gradingLabel: String = {
            if let pendingSubmission {
                return "Pending since \(pendingSubmission.submittedAt.formatted(date: .abbreviated, time: .shortened))"
            }
            if let gradedAt = appVM.latestAssessmentGradeTimestamp {
                if let average = appVM.latestGradedAssessment?.averageScoreLabel {
                    return "\(average) average • \(gradedAt.formatted(date: .abbreviated, time: .shortened))"
                }
                return gradedAt.formatted(date: .abbreviated, time: .shortened)
            }
            return "No grading yet"
        }()

        let latestFeedback = appVM.latestGradedAssessment?.grading?.overallFeedback
            .trimmingCharacters(in: .whitespacesAndNewlines)

        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center) {
                Label("Assessment Status", systemImage: "checkmark.seal")
                    .labelStyle(.titleAndIcon)
                    .font(.title3.weight(.semibold))
                Spacer()
                Label(statusText, systemImage: statusIcon)
                    .font(.footnote.weight(.semibold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(statusColor.opacity(0.18), in: Capsule())
                    .foregroundStyle(statusColor)
            }

            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label("Last submission", systemImage: "tray.and.arrow.down.fill")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(.primary)
                    Spacer()
                    Text(submissionLabel)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                HStack {
                    Label("Last grading", systemImage: "chart.bar.fill")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(.primary)
                    Spacer()
                    Text(gradingLabel)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }

            if let feedback = latestFeedback, !feedback.isEmpty {
                Divider()
                Text("Latest feedback: \(feedback)")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
    }

    @ViewBuilder
    private var assessmentHistorySection: some View {
        let history = Array(appVM.assessmentHistory.prefix(6))
        if history.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Label("Assessment History", systemImage: "clock.arrow.circlepath")
                        .labelStyle(.titleAndIcon)
                        .font(.headline)
                    Spacer()
                    Text("Newest first")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(history.enumerated()), id: \.element.id) { index, submission in
                        assessmentHistoryRow(for: submission, index: index + 1)
                        if index < history.count - 1 {
                            Divider().padding(.vertical, 10)
                        }
                    }
                }

                if appVM.assessmentHistory.count > history.count {
                    Text("Showing latest \(history.count) of \(appVM.assessmentHistory.count) submissions.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
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
                    appVM.clearSessionContent()
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

    @ViewBuilder
    private func assessmentHistoryRow(for submission: AssessmentSubmissionRecord, index: Int) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text("#\(index) · \(submission.submittedAt.formatted(date: .abbreviated, time: .shortened))")
                    .font(.subheadline.weight(.semibold))
                Spacer()
                let isPending = submission.grading == nil
                let badgeForeground: Color = isPending ? .orange : .green
                Text(submission.statusLabel)
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(badgeForeground.opacity(0.18), in: Capsule())
                    .foregroundStyle(badgeForeground)
            }

            HStack(spacing: 12) {
                Label("\(submission.answeredCount) prompts", systemImage: "list.bullet.rectangle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let average = submission.averageScoreLabel, submission.grading != nil {
                    Label("\(average) average", systemImage: "percent")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let gradedAt = submission.gradedAt {
                    Label("Graded \(gradedAt.formatted(date: .abbreviated, time: .shortened))", systemImage: "clock")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if submission.hasAttachments {
                    Label("\(submission.attachments.count) attachment\(submission.attachments.count == 1 ? "" : "s")", systemImage: "paperclip")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let outcomes = submission.grading?.categoryOutcomes {
                    let totalDelta = outcomes.reduce(0) { $0 + $1.ratingDelta }
                    if totalDelta != 0 {
                        let label = totalDelta > 0 ? "+\(totalDelta)" : "\(totalDelta)"
                        Label("ΔELO \(label)", systemImage: totalDelta > 0 ? "arrow.up" : "arrow.down")
                            .font(.caption)
                            .foregroundStyle(totalDelta > 0 ? .green : .orange)
                    }
                }
            }

            if let grading = submission.grading {
                if !grading.overallFeedback.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text(grading.overallFeedback)
                        .font(.footnote)
                        .foregroundStyle(.primary)
                        .lineLimit(3)
                }
                let strengths = grading.strengths.prefix(2).joined(separator: ", ")
                if !strengths.isEmpty {
                    Text("Strengths: \(strengths)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                let focus = grading.focusAreas.prefix(2).joined(separator: ", ")
                if !focus.isEmpty {
                    Text("Focus next: \(focus)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text("Arcadia Coach is grading this submission.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack {
                Spacer()
                Button {
                    appVM.focus(on: submission)
                } label: {
                    Label("View details", systemImage: "arrow.right.circle")
                        .font(.caption.weight(.semibold))
                }
                .buttonStyle(.bordered)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func assessmentResultsCard(result: AssessmentGradingResult) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top) {
                Label("Assessment Results", systemImage: "chart.bar.doc.horizontal")
                    .labelStyle(.titleAndIcon)
                    .font(.title3.weight(.semibold))
                Spacer()
                Text(result.evaluatedAt.formatted(date: .abbreviated, time: .shortened))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Text(result.overallFeedback)
                .font(.body)

            if !result.strengths.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Strengths")
                        .font(.subheadline.bold())
                    ForEach(result.strengths, id: \.self) { item in
                        Text("• \(item)")
                            .font(.footnote)
                    }
                }
            }

            if !result.focusAreas.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Focus Next")
                        .font(.subheadline.bold())
                    ForEach(result.focusAreas, id: \.self) { item in
                        Text("• \(item)")
                            .font(.footnote)
                    }
                }
            }

            if !result.categoryOutcomes.isEmpty {
                let columns = [GridItem(.adaptive(minimum: 160), spacing: 12, alignment: .top)]
                LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
                    ForEach(result.categoryOutcomes) { outcome in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(categoryLabels[outcome.categoryKey] ?? outcome.categoryKey)
                                .font(.headline)
                            Text("Rating \(outcome.initialRating)")
                                .font(.subheadline)
                            Text("Avg score \(Int((outcome.averageScore * 100).rounded()))%")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            if let rationale = outcome.rationale, !rationale.isEmpty {
                                Text(rationale)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 12))
                    }
                }
            }

            if !result.taskResults.isEmpty {
                DisclosureGroup("Task-by-task notes") {
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(result.taskResults) { task in
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(task.taskId)
                                        .font(.subheadline.bold())
                                    Spacer()
                                    Text("Score \(Int((task.score * 100).rounded()))% · \(task.confidence.rawValue.capitalized)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Text(task.feedback)
                                    .font(.footnote)
                                if !task.strengths.isEmpty {
                                    Text("Strengths: \(task.strengths.joined(separator: ", "))")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                if !task.improvements.isEmpty {
                                    Text("Improve: \(task.improvements.joined(separator: ", "))")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .padding(10)
                            .background(Color.primary.opacity(0.03), in: RoundedRectangle(cornerRadius: 10))
                        }
                    }
                    .padding(.top, 6)
                }
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
        .accessibilityElement(children: .contain)
    }
}

private struct FoundationTracksCard: View {
    var tracks: [FoundationTrackModel]
    var goalSummary: String?
    var targetOutcomes: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                Label("Foundation Tracks", systemImage: "target")
                    .font(.headline)
                Spacer()
            }
            if let trimmedSummary = goalSummary?.trimmingCharacters(in: .whitespacesAndNewlines),
               !trimmedSummary.isEmpty {
                Text(trimmedSummary)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            if !targetOutcomes.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Target outcomes")
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                    ForEach(targetOutcomes, id: \.self) { outcome in
                        HStack(alignment: .top, spacing: 6) {
                            Text("•")
                            Text(outcome)
                        }
                        .font(.caption)
                    }
                }
            }
            ForEach(tracks) { track in
                let technologies = track.technologies.joined(separator: ", ")
                let focusAreas = track.focusAreas.joined(separator: ", ")
                VStack(alignment: .leading, spacing: 6) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(track.label)
                            .font(.subheadline.weight(.semibold))
                        Spacer()
                        Text(track.priority.replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.caption.bold())
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(priorityColor(for: track.priority).opacity(0.18))
                            .foregroundStyle(priorityColor(for: track.priority))
                            .clipShape(Capsule())
                    }
                    if !technologies.isEmpty {
                        Text("Technologies: \(technologies)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if !focusAreas.isEmpty {
                        Text("Focus areas: \(focusAreas)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if let weeks = track.suggestedWeeks {
                        Text("Suggested duration: \(weeks) week\(weeks == 1 ? "" : "s")")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                    if let notes = track.notes?.trimmingCharacters(in: .whitespacesAndNewlines),
                       !notes.isEmpty {
                        Text(notes)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.primary.opacity(0.04))
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
        )
    }

    private func priorityColor(for priority: String) -> Color {
        switch priority.lowercased() {
        case "now":
            return .red
        case "up_next", "up-next":
            return .orange
        case "later":
            return .blue
        default:
            return .accentColor
        }
    }
}

struct AssessmentSubmissionDetailView: View {
    @EnvironmentObject private var appVM: AppViewModel
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var settings: AppSettings

    let submission: AssessmentSubmissionRecord
    let plan: EloCategoryPlan?
    let curriculum: OnboardingCurriculumPlan?

    private var grading: AssessmentGradingResult? { submission.grading }

    private var categoryOutcomes: [AssessmentCategoryOutcome] {
        grading?.categoryOutcomes ?? []
    }

    private var blockedOutcomes: [AssessmentCategoryOutcome] {
        categoryOutcomes.filter { $0.ratingDelta <= 0 }
    }

    private var totalDelta: Int {
        categoryOutcomes.reduce(0) { $0 + $1.ratingDelta }
    }

    private var moduleLookup: [String:[OnboardingCurriculumModule]] {
        if appVM.modulesByCategory.isEmpty, let curriculum {
            return Dictionary(grouping: curriculum.modules, by: { $0.categoryKey })
        }
        return appVM.modulesByCategory
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    headerSection
                    attachmentsSection
                    responsesSection
                    gradingOverviewSection
                    categoryImpactSection
                    taskDrilldownsSection
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(24)
            }
            .background(Color(nsColor: .windowBackgroundColor).ignoresSafeArea())
            .navigationTitle(titleLabel)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .frame(minWidth: 720, minHeight: 640)
    }

    private var titleLabel: String {
        submission.submittedAt.formatted(date: .abbreviated, time: .shortened)
    }

    @ViewBuilder
    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Text(submission.statusLabel)
                    .font(.title3.bold())
                Spacer()
                if let gradedAt = submission.gradedAt {
                    Text("Graded \(gradedAt.formatted(date: .abbreviated, time: .shortened))")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                } else {
                    Text("Grading in progress")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            }

            HStack(alignment: .center, spacing: 16) {
                Label("Submitted \(submission.submittedAt.formatted(date: .abbreviated, time: .shortened))", systemImage: "tray.and.arrow.down")
                    .font(.callout)
                Label("\(submission.answeredCount) prompts", systemImage: "list.bullet.rectangle")
                    .font(.callout)
                if let average = submission.averageScoreLabel {
                    Label("Average \(average)", systemImage: "percent")
                        .font(.callout)
                }
                if totalDelta != 0 {
                    let deltaLabel = totalDelta > 0 ? "+\(totalDelta)" : "\(totalDelta)"
                    Label("ΔELO \(deltaLabel)", systemImage: totalDelta > 0 ? "arrow.up" : "arrow.down")
                        .font(.callout)
                        .foregroundStyle(totalDelta > 0 ? .green : .orange)
                }
            }
            .foregroundStyle(.secondary)

            if !blockedOutcomes.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Label("Blocked categories", systemImage: "exclamationmark.octagon")
                        .font(.headline)
                        .foregroundStyle(.orange)
                    ForEach(blockedOutcomes) { outcome in
                        Text("• \(appVM.label(for: outcome.categoryKey)) needs more work (Δ\(outcome.ratingDelta))")
                            .font(.callout)
                    }
                }
            }
        }
        .padding(20)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
    }

    @ViewBuilder
    private var attachmentsSection: some View {
        if submission.attachments.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 12) {
                Label("Attachments", systemImage: "paperclip")
                    .font(.headline)
                    ForEach(submission.attachments) { attachment in
                        HStack(alignment: .top, spacing: 12) {
                            Image(systemName: icon(for: attachment.kind))
                                .foregroundStyle(.secondary)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(attachment.name)
                                    .font(.callout.weight(.semibold))
                                if let size = attachment.sizeLabel {
                                    Text(size)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                if let description = attachment.description, !description.isEmpty {
                                    Text(description)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                if let destination = attachment.resolvedURL(baseURL: settings.chatkitBackendURL) {
                                    Link("Open", destination: destination)
                                        .font(.caption)
                                }
                                if let source = attachment.source, !source.isEmpty {
                                    Text("Source: \(source)")
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                            }
                        }
                    }
                    .padding(.vertical, 6)
                }
            }
            .padding(20)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
        }
    }

    @ViewBuilder
    private var responsesSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Learner Responses", systemImage: "square.and.pencil")
                .font(.headline)
            ForEach(submission.responses) { response in
                DisclosureGroup {
                    ScrollView {
                        Text(response.response)
                            .font(.body.monospaced())
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .textSelection(.enabled)
                            .padding(.vertical, 4)
                    }
                    .frame(maxHeight: 200)
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(response.taskId)
                            .font(.subheadline.weight(.semibold))
                        Text(response.preview.isEmpty ? "(No response)" : response.preview)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding(20)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
    }

    @ViewBuilder
    private var gradingOverviewSection: some View {
        if let grading {
            VStack(alignment: .leading, spacing: 12) {
                Label("Feedback Summary", systemImage: "text.bubble")
                    .font(.headline)
                Text(grading.overallFeedback)
                    .font(.body)
                if !grading.strengths.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Strengths")
                            .font(.subheadline.bold())
                        ForEach(grading.strengths, id: \.self) { item in
                            Text("• \(item)")
                                .font(.callout)
                        }
                    }
                }
                if !grading.focusAreas.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Focus next")
                            .font(.subheadline.bold())
                        ForEach(grading.focusAreas, id: \.self) { item in
                            Text("• \(item)")
                                .font(.callout)
                        }
                    }
                }
            }
            .padding(20)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
        }
    }

    @ViewBuilder
    private var categoryImpactSection: some View {
        if !categoryOutcomes.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                Label("Category Impact", systemImage: "chart.bar")
                    .font(.headline)
                ForEach(categoryOutcomes, content: categoryImpactRow)
            }
            .padding(20)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
        }
    }

    @ViewBuilder
    private var taskDrilldownsSection: some View {
        if let grading, !grading.taskResults.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                Label("Task Drilldowns", systemImage: "doc.text.magnifyingglass")
                    .font(.headline)
                ForEach(grading.taskResults) { task in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(alignment: .firstTextBaseline) {
                            Text(task.taskId)
                                .font(.subheadline.weight(.semibold))
                            Spacer()
                            Text("Score \(Int((task.score * 100).rounded()))%")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(task.confidence.rawValue.capitalized)
                                .font(.caption)
                                .foregroundStyle(.tertiary)
                        }
                        Text(task.feedback)
                            .font(.callout)
                        if !task.strengths.isEmpty {
                            Text("Strengths: \(task.strengths.joined(separator: ", "))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        if !task.improvements.isEmpty {
                            Text("Improve: \(task.improvements.joined(separator: ", "))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        if !task.rubric.isEmpty {
                            DisclosureGroup("Rubric feedback") {
                                VStack(alignment: .leading, spacing: 4) {
                                    ForEach(task.rubric, id: \.criterion) { rubric in
                                        HStack(alignment: .top, spacing: 6) {
                                            Image(systemName: rubric.met ? "checkmark.circle.fill" : "xmark.circle")
                                                .foregroundStyle(rubric.met ? .green : .orange)
                                                .imageScale(.small)
                                            VStack(alignment: .leading, spacing: 2) {
                                                Text(rubric.criterion)
                                                    .font(.caption.weight(.semibold))
                                                if let notes = rubric.notes, !notes.isEmpty {
                                                    Text(notes)
                                                        .font(.caption)
                                                        .foregroundStyle(.secondary)
                                                }
                                            }
                                        }
                                    }
                                }
                                .padding(.top, 4)
                            }
                            .font(.caption)
                        }
                    }
                    .padding(12)
                    .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
                }
            }
            .padding(20)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
        }
    }

    private func icon(for kind: AssessmentSubmissionRecord.Attachment.Kind) -> String {
        switch kind {
        case .file:
            return "doc"
        case .link:
            return "link"
        case .note:
            return "note.text"
        }
    }

    @ViewBuilder
    private func categoryImpactRow(for outcome: AssessmentCategoryOutcome) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(appVM.label(for: outcome.categoryKey))
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Text("Rating \(outcome.initialRating)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if outcome.ratingDelta != 0 {
                    let deltaLabel = outcome.ratingDelta > 0 ? "+\(outcome.ratingDelta)" : "\(outcome.ratingDelta)"
                    Text(deltaLabel)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(outcome.ratingDelta > 0 ? .green : .orange)
                }
            }

            if let rationale = outcome.rationale, !rationale.isEmpty {
                Text(rationale)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let category = plan?.categories.first(where: { $0.key == outcome.categoryKey }), !category.focusAreas.isEmpty {
                Text("Focus areas: \(category.focusAreas.joined(separator: ", "))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let modules = moduleLookup[outcome.categoryKey], !modules.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Suggested modules")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    ForEach(modules.prefix(3)) { module in
                        Text("• \(module.title)")
                            .font(.caption)
                    }
                }
            }
        }
        .padding(12)
        .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
    }
}
