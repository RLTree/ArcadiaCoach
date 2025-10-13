import SwiftUI

@MainActor
final class AppViewModel: ObservableObject {
    @Published var game = GameState()
    @Published var lastEnvelope: WidgetEnvelope?
    @Published var busy: Bool = false
    @Published var error: String?
    @Published var eloPlan: EloCategoryPlan?
    @Published var curriculumPlan: OnboardingCurriculumPlan?
    @Published var onboardingAssessment: OnboardingAssessment?
    @Published var assessmentResult: AssessmentGradingResult?
    // Phase 8 – Track submission/grading history for dashboard + chat surfaces.
    @Published var assessmentHistory: [AssessmentSubmissionRecord] = []
    @Published var assessmentResponses: [String:String] = [:]
    @Published var pendingAssessmentAttachments: [AssessmentSubmissionRecord.Attachment] = []
    @Published var showingAssessmentFlow: Bool = false
    @Published var focusedSubmission: AssessmentSubmissionRecord?
    @Published var latestLesson: EndLearn?
    @Published var latestQuiz: EndQuiz?
    @Published var latestMilestone: EndMilestone?

    func applyElo(updated: [String:Int], delta: [String:Int]) {
        game.elo = updated
        alignEloSnapshotWithPlan()
        let gained = GameState.xpGain(from: delta)
        game.xp += gained
        game.level = GameState.levelFromXP(game.xp)
    }

    func loadProfile(baseURL: String, username: String) async {
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty else { return }
        guard let trimmedBase = BackendService.trimmed(url: baseURL) else { return }
        do {
            let snapshot = try await BackendService.fetchProfile(baseURL: trimmedBase, username: trimmedUsername)
            syncProfile(with: snapshot)
            error = nil
        } catch let serviceError as BackendServiceError {
            if case let .transportFailure(status, _) = serviceError, status == 404 {
                eloPlan = nil
                curriculumPlan = nil
                onboardingAssessment = nil
                assessmentResult = nil
                assessmentHistory = []
                error = nil
            } else {
                error = serviceError.localizedDescription
            }
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
        }
    }

    func ensureOnboardingPlan(
        baseURL: String,
        username: String,
        goal: String,
        useCase: String,
        strengths: String,
        force: Bool = false
    ) async throws {
        busy = true
        defer { busy = false }
        let snapshot = try await BackendService.ensureOnboardingPlan(
            baseURL: baseURL,
            username: username,
            goal: goal,
            useCase: useCase,
            strengths: strengths,
            force: force
        )
        syncProfile(with: snapshot)
        error = nil
        if requiresAssessment {
            showingAssessmentFlow = true
        }
    }

    func response(for taskId: String) -> String {
        assessmentResponses[taskId] ?? ""
    }

    func setResponse(_ value: String, for taskId: String) {
        assessmentResponses[taskId] = value
    }

    func insertStarter(for task: OnboardingAssessmentTask) {
        if let starter = task.starterCode, !starter.isEmpty {
            assessmentResponses[task.taskId] = starter
        }
    }

    func recordLesson(_ lesson: EndLearn) {
        latestLesson = lesson
        lastEnvelope = WidgetEnvelope(display: lesson.display, widgets: lesson.widgets, citations: lesson.citations)
    }

    func recordQuiz(_ quiz: EndQuiz) {
        latestQuiz = quiz
    }

    func recordMilestone(_ milestone: EndMilestone) {
        latestMilestone = milestone
        lastEnvelope = WidgetEnvelope(display: milestone.display, widgets: milestone.widgets, citations: nil)
    }

    func clearSessionContent() {
        latestLesson = nil
        latestQuiz = nil
        latestMilestone = nil
        lastEnvelope = nil
    }

    func focus(on submission: AssessmentSubmissionRecord) {
        focusedSubmission = submission
    }

    func focusSubmission(by id: String) {
        focusedSubmission = assessmentHistory.first { $0.submissionId == id }
    }

    func dismissSubmissionFocus() {
        focusedSubmission = nil
    }

    func isAssessmentTaskAnswered(_ task: OnboardingAssessmentTask) -> Bool {
        let trimmed = response(for: task.taskId).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return false }
        if task.taskType == .code, let starter = task.starterCode, !starter.isEmpty {
            let starterTrimmed = starter.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed == starterTrimmed {
                return false
            }
        }
        return true
    }

    func updateAssessmentStatus(
        to status: OnboardingAssessment.Status,
        baseURL: String,
        username: String
    ) async {
        do {
            let updated = try await BackendService.updateOnboardingAssessmentStatus(
                baseURL: baseURL,
                username: username,
                status: status
            )
            onboardingAssessment = updated
            error = nil
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
        }
    }

    func submitAndCompleteAssessment(
        baseURL: String,
        username: String
    ) async -> Bool {
        guard let assessment = onboardingAssessment else { return false }
        guard let responses = makeSubmissionItems(for: assessment) else {
            error = "Complete every prompt before submitting the assessment."
            return false
        }
        error = nil
        do {
            let submission = try await BackendService.submitAssessmentResponses(
                baseURL: baseURL,
                username: username,
                responses: responses,
                metadata: submissionMetadata()
            )
            assessmentResult = submission.grading
            let updated = try await BackendService.updateOnboardingAssessmentStatus(
                baseURL: baseURL,
                username: username,
                status: .completed
            )
            onboardingAssessment = updated
            assessmentResponses.removeAll()
            showingAssessmentFlow = false
            pendingAssessmentAttachments.removeAll()
            await loadProfile(baseURL: baseURL, username: username)
            error = nil
            return true
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
            return false
        }
    }

    func refreshPendingAssessmentAttachments(
        baseURL: String,
        username: String
    ) async {
        guard let trimmedBase = BackendService.trimmed(url: baseURL) else {
            pendingAssessmentAttachments = []
            return
        }
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty else {
            pendingAssessmentAttachments = []
            return
        }
        do {
            let attachments = try await BackendService.listAssessmentAttachments(
                baseURL: trimmedBase,
                username: trimmedUsername
            )
            pendingAssessmentAttachments = attachments
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
        }
    }

    @discardableResult
    func uploadAssessmentAttachmentFile(
        baseURL: String,
        username: String,
        fileURL: URL,
        description: String? = nil
    ) async -> Bool {
        do {
            _ = try await BackendService.uploadAssessmentAttachment(
                baseURL: baseURL,
                username: username,
                fileURL: fileURL,
                description: description
            )
            await refreshPendingAssessmentAttachments(baseURL: baseURL, username: username)
            return true
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
            return false
        }
    }

    @discardableResult
    func addAssessmentAttachmentLink(
        baseURL: String,
        username: String,
        name: String?,
        url: String,
        description: String?
    ) async -> Bool {
        do {
            _ = try await BackendService.createAssessmentAttachmentLink(
                baseURL: baseURL,
                username: username,
                name: name,
                url: url,
                description: description
            )
            await refreshPendingAssessmentAttachments(baseURL: baseURL, username: username)
            return true
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
            return false
        }
    }

    @discardableResult
    func removeAssessmentAttachment(
        baseURL: String,
        username: String,
        attachmentId: String
    ) async -> Bool {
        do {
            try await BackendService.deleteAssessmentAttachment(
                baseURL: baseURL,
                username: username,
                attachmentId: attachmentId
            )
            await refreshPendingAssessmentAttachments(baseURL: baseURL, username: username)
            return true
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
            return false
        }
    }

    func openAssessmentFlow() {
        showingAssessmentFlow = true
    }

    func closeAssessmentFlow() {
        showingAssessmentFlow = false
    }

    func resetAfterDeveloperClear() {
        game = GameState()
        busy = false
        error = nil
        eloPlan = nil
        curriculumPlan = nil
        onboardingAssessment = nil
        assessmentResult = nil
        assessmentHistory = []
        assessmentResponses.removeAll()
        showingAssessmentFlow = false
        focusedSubmission = nil
        clearSessionContent()
        pendingAssessmentAttachments.removeAll()
    }

    var requiresAssessment: Bool {
        guard let bundle = onboardingAssessment else { return false }
        return bundle.status != .completed
    }

    var awaitingAssessmentResults: Bool {
        if let pending = assessmentHistory.first, pending.grading == nil {
            return true
        }
        guard let bundle = onboardingAssessment else { return false }
        if bundle.status == .completed {
            return assessmentResult == nil
        }
        return false
    }

    enum AssessmentReadinessStatus {
        case notGenerated
        case pendingStart
        case inProgress
        case awaitingGrading
        case ready
    }

    var assessmentReadinessStatus: AssessmentReadinessStatus {
        if assessmentHistory.first(where: { $0.grading == nil }) != nil {
            return .awaitingGrading
        }
        if let onboarding = onboardingAssessment {
            switch onboarding.status {
            case .pending:
                return .pendingStart
            case .inProgress:
                return .inProgress
            case .completed:
                return .ready
            }
        }
        if !assessmentHistory.isEmpty {
            return .ready
        }
        return .notGenerated
    }

    var latestAssessmentSubmission: AssessmentSubmissionRecord? {
        assessmentHistory.first
    }

    var latestGradedAssessment: AssessmentSubmissionRecord? {
        assessmentHistory.first(where: { $0.grading != nil })
    }

    var latestAssessmentGradeTimestamp: Date? {
        latestGradedAssessment?.grading?.evaluatedAt
    }

    var latestAssessmentSubmittedAt: Date? {
        latestAssessmentSubmission?.submittedAt
    }

    var categoryLabelMap: [String:String] {
        guard let plan = eloPlan else { return [:] }
        return Dictionary(uniqueKeysWithValues: plan.categories.map { ($0.key, $0.label) })
    }

    func label(for categoryKey: String) -> String {
        categoryLabelMap[categoryKey] ?? categoryKey
    }

    var modulesByCategory: [String:[OnboardingCurriculumModule]] {
        guard let modules = curriculumPlan?.modules else { return [:] }
        return Dictionary(grouping: modules, by: { $0.categoryKey })
    }

    private func alignEloSnapshotWithPlan() {
        guard let plan = eloPlan else { return }
        var aligned: [String:Int] = [:]
        for category in plan.categories {
            let current = game.elo[category.key] ?? category.startingRating
            aligned[category.key] = current
        }
        game.elo = aligned
    }

    private func syncProfile(with snapshot: LearnerProfileSnapshot) {
        game.elo = Dictionary(uniqueKeysWithValues: snapshot.skillRatings.map { ($0.category, $0.rating) })
        eloPlan = snapshot.eloCategoryPlan
        curriculumPlan = snapshot.curriculumPlan
        onboardingAssessment = snapshot.onboardingAssessment
        assessmentResult = snapshot.onboardingAssessmentResult
        assessmentHistory = snapshot.assessmentSubmissions.sorted { $0.submittedAt > $1.submittedAt }
        if let currentFocusId = focusedSubmission?.submissionId {
            focusedSubmission = assessmentHistory.first { $0.submissionId == currentFocusId }
        }
        alignEloSnapshotWithPlan()
        pruneAssessmentResponses()
    }

    private func pruneAssessmentResponses() {
        guard let assessment = onboardingAssessment else {
            assessmentResponses.removeAll()
            return
        }
        let validIds = Set(assessment.tasks.map { $0.taskId })
        assessmentResponses = assessmentResponses.filter { validIds.contains($0.key) }
    }

    private func makeSubmissionItems(for assessment: OnboardingAssessment) -> [BackendService.AssessmentSubmissionUploadItem]? {
        var items: [BackendService.AssessmentSubmissionUploadItem] = []
        for task in assessment.tasks {
            let trimmed = response(for: task.taskId).trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { return nil }
            if task.taskType == .code, let starter = task.starterCode, !starter.isEmpty {
                let starterTrimmed = starter.trimmingCharacters(in: .whitespacesAndNewlines)
                if trimmed == starterTrimmed {
                    return nil
                }
            }
            items.append(.init(taskId: task.taskId, response: trimmed))
        }
        return items
    }

    private func submissionMetadata() -> [String: String] {
        var metadata: [String: String] = ["platform": "macOS"]
        if let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String, !version.isEmpty {
            metadata["client_version"] = version
        }
        if let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String, !build.isEmpty {
            metadata["build"] = build
        }
        return metadata
    }
}

extension AppViewModel.AssessmentReadinessStatus {
    var displayText: String {
        switch self {
        case .awaitingGrading:
            return "Awaiting grading"
        case .pendingStart:
            return "Not started"
        case .inProgress:
            return "In progress"
        case .ready:
            return "Ready"
        case .notGenerated:
            return "Not generated"
        }
    }

    var systemImageName: String {
        switch self {
        case .awaitingGrading:
            return "hourglass"
        case .pendingStart:
            return "square.and.pencil"
        case .inProgress:
            return "play.circle"
        case .ready:
            return "checkmark.circle"
        case .notGenerated:
            return "questionmark.circle"
        }
    }

    var tintColor: Color {
        switch self {
        case .awaitingGrading:
            return .orange
        case .pendingStart:
            return .orange
        case .inProgress:
            return .blue
        case .ready:
            return .green
        case .notGenerated:
            return .secondary
        }
    }
}
