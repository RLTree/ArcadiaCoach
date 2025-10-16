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
    @State private var dashboardSection: DashboardSection = .elo
    @State private var showCompletionSheet = false
    @State private var pendingCompletionItem: SequencedWorkItem?
    @State private var completionNotes: String = ""
    @State private var completionLinksText: String = ""
    @State private var selectedAttachmentIds: Set<String> = []

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

    private var shouldShowAssessmentTab: Bool {
        appVM.requiresAssessment
    }

    var body: some View {
        ZStack(alignment: .center) {
            Color(nsColor: .windowBackgroundColor)
                .ignoresSafeArea()

            TabView(selection: $selectedTab) {
                dashboardTab
                    .tabItem { Label("Dashboard", systemImage: "rectangle.grid.2x2") }
                    .tag(MainTab.dashboard)

                if shouldShowAssessmentTab {
                    assessmentTab
                        .tabItem {
                            Label("Assessment", systemImage: "checklist")
                        }
                        .tag(MainTab.assessment)
                        .badge(assessmentTabBadge)
                }

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
                let storedSection = DashboardSection(rawValue: settings.dashboardSection) ?? .elo
                if dashboardSection != storedSection {
                    dashboardSection = storedSection
                }
                TelemetryReporter.shared.record(
                    event: "dashboard_tab_selected",
                    metadata: [
                        "tab": storedSection.rawValue,
                        "initial": "true"
                    ]
                )
                appVM.updateLastSeenAssessmentSubmissionId(settings.lastSeenAssessmentSubmissionId)
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
        .sheet(isPresented: $showCompletionSheet, onDismiss: {
            pendingCompletionItem = nil
            selectedAttachmentIds.removeAll()
        }) {
            MilestoneCompletionSheet(
                item: pendingCompletionItem,
                notes: $completionNotes,
                linksText: $completionLinksText,
                attachments: appVM.pendingAssessmentAttachments,
                selectedAttachmentIds: $selectedAttachmentIds,
                onCancel: {
                    showCompletionSheet = false
                    pendingCompletionItem = nil
                    completionNotes = ""
                    completionLinksText = ""
                    selectedAttachmentIds.removeAll()
                },
                onSubmit: {
                    guard let item = pendingCompletionItem else {
                        showCompletionSheet = false
                        return
                    }
                    let submission = makeCompletionSubmission()
                    showCompletionSheet = false
                    pendingCompletionItem = nil
                    completionNotes = ""
                    completionLinksText = ""
                    selectedAttachmentIds.removeAll()
                    submitScheduleCompletion(item: item, completion: submission)
                }
            )
            .environmentObject(appVM)
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
        .onChange(of: dashboardSection) { newValue in
            settings.dashboardSection = newValue.rawValue
            TelemetryReporter.shared.record(
                event: "dashboard_tab_selected",
                metadata: ["tab": newValue.rawValue]
            )
            if newValue == .assessments {
                let seenId = appVM.markAssessmentResultsAsSeen() ?? ""
                if settings.lastSeenAssessmentSubmissionId != seenId {
                    settings.lastSeenAssessmentSubmissionId = seenId
                }
            }
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
        .onChange(of: settings.lastSeenAssessmentSubmissionId) { newValue in
            appVM.updateLastSeenAssessmentSubmissionId(newValue)
        }
        .onChange(of: appVM.requiresAssessment) { required in
            if required {
                selectedTab = .assessment
            } else {
                if selectedTab == .assessment {
                    selectedTab = .dashboard
                }
                if selectedTab == .dashboard {
                    dashboardSection = .assessments
                }
            }
        }
        .onChange(of: appVM.awaitingAssessmentResults) { awaiting in
            if !awaiting, selectedTab == .dashboard {
                dashboardSection = .assessments
            }
        }
        .onChange(of: appVM.hasUnseenAssessmentResults) { hasUnseen in
            if hasUnseen && dashboardSection == .assessments {
                let seenId = appVM.markAssessmentResultsAsSeen() ?? ""
                if settings.lastSeenAssessmentSubmissionId != seenId {
                    settings.lastSeenAssessmentSubmissionId = seenId
                }
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
            selectedTab = appVM.requiresAssessment ? .assessment : .dashboard
            showOnboarding = true
            settings.lastSeenAssessmentSubmissionId = ""
            appVM.updateLastSeenAssessmentSubmissionId(nil)
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

    private var dashboardTab: some View {
        ZStack {
            Color(nsColor: .windowBackgroundColor)
                .ignoresSafeArea()

            ScrollView(.vertical, showsIndicators: true) {
                VStack(alignment: .leading, spacing: 20) {
                    header
                    assessmentResultsNudge
                    dashboardSegmentedPicker
                    selectedDashboardSection
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(24)
            }
        }
    }

    @ViewBuilder
    private var assessmentResultsNudge: some View {
        if appVM.hasUnseenAssessmentResults && dashboardSection != .assessments {
            Button {
                presentAssessmentResults(from: "nudge")
            } label: {
                HStack(alignment: .center, spacing: 14) {
                    Image(systemName: "sparkles")
                        .font(.title2.weight(.semibold))
                        .foregroundStyle(Color.accentColor)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("New grading available")
                            .font(.headline.weight(.semibold))
                        Text("Review the latest feedback and ELO updates.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 14)
                .padding(.horizontal, 18)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.plain)
            .background(
                RoundedRectangle(cornerRadius: 18)
                    .fill(Color.accentColor.opacity(0.12))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18)
                    .stroke(Color.accentColor.opacity(0.28), lineWidth: 1)
            )
            .accessibilityHint("Opens the Assessments section to view recent grading.")
            .transition(.opacity)
        }
    }

    private var dashboardSegmentedPicker: some View {
        Picker("Dashboard Section", selection: $dashboardSection) {
            ForEach(DashboardSection.allCases) { section in
                Label(section.label, systemImage: section.systemImage)
                    .tag(section)
            }
        }
        .pickerStyle(.segmented)
        .accessibilityLabel("Dashboard section selector")
    }

    @ViewBuilder
    private var selectedDashboardSection: some View {
        switch dashboardSection {
        case .elo:
            DashboardEloSection(
                eloItems: allEloItems,
                latestAssessmentGradeTimestamp: appVM.latestAssessmentGradeTimestamp,
                latestSubmissionTimestamp: appVM.latestAssessmentSubmittedAt
            )
            .transition(.opacity)
        case .schedule:
            DashboardScheduleSection(
                schedule: appVM.curriculumSchedule,
                categoryLabels: categoryLabels,
                milestoneCompletions: appVM.milestoneCompletions,
                telemetryEvents: appVM.telemetryEvents,
                isRefreshing: appVM.scheduleRefreshing,
                isLoadingNextSlice: appVM.loadingScheduleSlice,
                adjustingItemId: appVM.adjustingScheduleItemId,
                launchingItemId: appVM.launchingScheduleItemId,
                completingItemId: appVM.completingScheduleItemId,
                refreshAction: refreshSchedule,
                adjustAction: deferSchedule,
                loadMoreAction: loadMoreSchedule,
                launchAction: { item, force in launchSchedule(item: item, force: force) },
                completeAction: { item in completeSchedule(item: item) }
            )
            .transition(.opacity)
        case .sessions:
            DashboardSessionsSection(
                session: session,
                needsOnboarding: needsOnboarding,
                sessionContentExpanded: $sessionContentExpanded,
                onRunOnboarding: { showOnboarding = true },
                onClearSessionContent: {
                    appVM.clearSessionContent()
                }
            )
            .transition(.opacity)
        case .assessments:
            DashboardAssessmentsSection(
                awaitingAssessmentResults: appVM.awaitingAssessmentResults,
                requiresAssessment: appVM.requiresAssessment,
                hasUnseenResults: appVM.hasUnseenAssessmentResults,
                categoryLabels: categoryLabels,
                onRunOnboarding: { showOnboarding = true },
                onOpenAssessmentFlow: openAssessmentTab
            )
            .transition(.opacity)
        case .resources:
            DashboardResourcesSection(
                needsOnboarding: needsOnboarding,
                onRunOnboarding: { showOnboarding = true }
            )
            .transition(.opacity)
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

    private func presentAssessmentResults(from source: String) {
        var metadata: [String:String] = ["source": source]
        TelemetryReporter.shared.record(event: "assessment_results_nudge_tapped", metadata: metadata)
        withAnimation(.easeInOut) {
            dashboardSection = .assessments
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

    private func openAssessmentTab() {
        guard appVM.requiresAssessment else { return }
        TelemetryReporter.shared.record(
            event: "assessment_tab_selected",
            metadata: ["source": "dashboard"]
        )
        withAnimation(.easeInOut) {
            selectedTab = .assessment
        }
        appVM.openAssessmentFlow()
    }

    private func loadMoreSchedule() {
        Task {
            let span = appVM.curriculumSchedule?.slice?.daySpan
            await appVM.loadNextScheduleSlice(
                baseURL: settings.chatkitBackendURL,
                username: settings.arcadiaUsername,
                daySpan: span
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

    private func launchSchedule(item: SequencedWorkItem, force: Bool) {
        Task { @MainActor in
            guard let base = BackendService.trimmed(url: settings.chatkitBackendURL) else {
                appVM.error = BackendServiceError.missingBackend.localizedDescription
                return
            }
            let username = settings.arcadiaUsername.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !username.isEmpty else {
                appVM.error = BackendServiceError.invalidURL.localizedDescription
                return
            }
        session.lastError = nil
        do {
            let response = try await appVM.launchScheduleItem(
                baseURL: base,
                username: username,
                    item: item,
                    sessionId: session.sessionId,
                    force: force
                )
                session.applyLaunchResponse(response)
                if response.content.lesson != nil || response.content.quiz != nil || response.content.milestone != nil {
                    sessionContentExpanded = true
                }
            } catch let serviceError as BackendServiceError {
                appVM.error = serviceError.localizedDescription
            } catch {
                let nsError = error as NSError
                appVM.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
            }
        }
    }

    private func completeSchedule(item: SequencedWorkItem) {
        if item.kind == .milestone {
            pendingCompletionItem = item
            completionNotes = ""
            completionLinksText = ""
            selectedAttachmentIds = []
            showCompletionSheet = true
            Task { @MainActor in
                await preloadCompletionAttachments()
            }
        } else {
            submitScheduleCompletion(item: item, completion: .empty)
        }
    }

    private func preloadCompletionAttachments() async {
        guard let base = BackendService.trimmed(url: settings.chatkitBackendURL) else { return }
        let username = settings.arcadiaUsername.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !username.isEmpty else { return }
        await appVM.refreshPendingAssessmentAttachments(baseURL: base, username: username)
    }

    private func makeCompletionSubmission() -> ScheduleCompletionSubmission {
        let trimmedNotes = completionNotes.trimmingCharacters(in: .whitespacesAndNewlines)
        let notesValue = trimmedNotes.isEmpty ? nil : trimmedNotes
        let links = completionLinksText
            .split(separator: "\n")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        let attachmentIds = Array(selectedAttachmentIds)
        return ScheduleCompletionSubmission(notes: notesValue, externalLinks: links, attachmentIds: attachmentIds)
    }

    private func submitScheduleCompletion(item: SequencedWorkItem, completion: ScheduleCompletionSubmission) {
        Task { @MainActor in
            guard let base = BackendService.trimmed(url: settings.chatkitBackendURL) else {
                appVM.error = BackendServiceError.missingBackend.localizedDescription
                return
            }
            let username = settings.arcadiaUsername.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !username.isEmpty else {
                appVM.error = BackendServiceError.invalidURL.localizedDescription
                return
            }
            session.lastError = nil
            do {
                try await appVM.completeScheduleItem(
                    baseURL: base,
                    username: username,
                    item: item,
                    sessionId: session.sessionId,
                    completion: completion
                )
                session.lastEventDescription = "Marked \"\(item.title)\" complete."
            } catch let serviceError as BackendServiceError {
                appVM.error = serviceError.localizedDescription
            } catch {
                let nsError = error as NSError
                appVM.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
            }
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

    private let clipboard: ClipboardManaging = AppClipboardManager.shared

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
        .selectableContent()
        .contextMenu {
            Button("Copy Status") {
                clipboard.copy(submission.statusLabel)
            }
            Button("Copy Summary Line") {
                let summary = "Submitted \(submission.submittedAt.formatted(date: .abbreviated, time: .shortened)) • \(submission.answeredCount) prompts"
                clipboard.copy(summary)
            }
        }
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
                    .selectableContent()
                    .contextMenu {
                        Button("Copy Name") {
                            clipboard.copy(attachment.name)
                        }
                        if let size = attachment.sizeLabel {
                            Button("Copy Size") {
                                clipboard.copy(size)
                            }
                        }
                        if let description = attachment.description, !description.isEmpty {
                            Button("Copy Description") {
                                clipboard.copy(description)
                            }
                        }
                    }
                }
            }
            .padding(20)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
            .selectableContent()
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
        .selectableContent()
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
            .selectableContent()
            .contextMenu {
                Button("Copy Feedback") {
                    clipboard.copy(grading.overallFeedback)
                }
                if !grading.strengths.isEmpty {
                    let strengths = grading.strengths.joined(separator: "\n")
                    Button("Copy Strengths") {
                        clipboard.copy(strengths)
                    }
                }
                if !grading.focusAreas.isEmpty {
                    let focus = grading.focusAreas.joined(separator: "\n")
                    Button("Copy Focus Areas") {
                        clipboard.copy(focus)
                    }
                }
            }
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
            .selectableContent()
            .contextMenu {
                Button("Copy Category Impact") {
                    let lines = categoryOutcomes.map { outcome in
                        "\(appVM.label(for: outcome.categoryKey)): \(outcome.ratingDelta)"
                    }
                    clipboard.copy(lines.joined(separator: "\n"))
                }
            }
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
                    .selectableContent()
                    .contextMenu {
                        Button("Copy Feedback") {
                            clipboard.copy(task.feedback)
                        }
                        Button("Copy Summary") {
                            let summary = "\(task.taskId) – \(Int((task.score * 100).rounded()))% (\(task.confidence.rawValue))"
                            clipboard.copy(summary)
                        }
                    }
                }
            }
            .padding(20)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
            .selectableContent()
            .contextMenu {
                let lines = grading.taskResults.map { task in
                    "\(task.taskId): \(Int((task.score * 100).rounded()))%"
                }
                Button("Copy All Task Scores") {
                    clipboard.copy(lines.joined(separator: "\n"))
                }
            }
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
        .selectableContent()
        .contextMenu {
            let label = appVM.label(for: outcome.categoryKey)
            Button("Copy Category") {
                clipboard.copy(label)
            }
            if let rationale = outcome.rationale, !rationale.isEmpty {
                Button("Copy Rationale") {
                    clipboard.copy(rationale)
                }
            }
        }
    }
}

struct MilestoneCompletionSheet: View {
    let item: SequencedWorkItem?
    @Binding var notes: String
    @Binding var linksText: String
    let attachments: [AssessmentSubmissionRecord.Attachment]
    @Binding var selectedAttachmentIds: Set<String>
    let onCancel: () -> Void
    let onSubmit: () -> Void

    private func isSelected(_ attachment: AssessmentSubmissionRecord.Attachment) -> Bool {
        guard let identifier = attachment.attachmentId else { return false }
        return selectedAttachmentIds.contains(identifier)
    }

    private func toggleAttachment(_ attachment: AssessmentSubmissionRecord.Attachment, enabled: Bool) {
        guard let identifier = attachment.attachmentId else { return }
        if enabled {
            selectedAttachmentIds.insert(identifier)
        } else {
            selectedAttachmentIds.remove(identifier)
        }
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Reflection") {
                    ZStack(alignment: .topLeading) {
                        if notes.isEmpty {
                            Text("Summarise what you delivered, decisions you made, and any blockers.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .padding(.top, 8)
                        }
                        TextEditor(text: $notes)
                            .frame(minHeight: 120)
                    }
                }

                Section("External Links") {
                    TextEditor(text: $linksText)
                        .frame(minHeight: 80)
                    Text("Enter one link per line (e.g. repository, demo, documentation).")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Section("Attachments") {
                    if attachments.isEmpty {
                        Text("No uploaded attachments yet. Use the assessment attachment manager to add files or links.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    } else {
                        ForEach(attachments) { attachment in
                            let identifier = attachment.attachmentId
                            Toggle(isOn: Binding(
                                get: { isSelected(attachment) },
                                set: { newValue in toggleAttachment(attachment, enabled: newValue) }
                            )) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(attachment.name)
                                        .font(.subheadline)
                                    if let description = attachment.description, !description.isEmpty {
                                        Text(description)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    if let size = attachment.sizeLabel {
                                        Text(size)
                                            .font(.caption2)
                                            .foregroundStyle(.tertiary)
                                    }
                                }
                            }
                            .disabled(identifier == nil)
                        }
                        Text("Selected attachments will be linked to this milestone submission.")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle(item?.title ?? "Milestone Progress")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel", action: onCancel)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Mark Complete", action: onSubmit)
                        .disabled(item == nil)
                }
            }
        }
        .frame(minWidth: 520, minHeight: 460)
    }
}
