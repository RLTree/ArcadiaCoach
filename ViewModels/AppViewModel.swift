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
    @Published var assessmentResponses: [String:String] = [:]
    @Published var showingAssessmentFlow: Bool = false

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

    func openAssessmentFlow() {
        showingAssessmentFlow = true
    }

    func closeAssessmentFlow() {
        showingAssessmentFlow = false
    }

    var requiresAssessment: Bool {
        guard let bundle = onboardingAssessment else { return false }
        return bundle.status != .completed
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

}
