import Foundation
import SwiftUI

@MainActor
final class DeveloperToolsViewModel: ObservableObject {
    @Published var submissions: [AssessmentSubmissionRecord] = []
    @Published var isLoadingSubmissions = false
    @Published var resetInFlight = false
    @Published var lastError: String?
    @Published var lastResetAt: Date?
    @Published var normalizeInFlight = false
    @Published var planError: String?
    @Published var lastNormalizedAt: Date?
    @Published var autoCompleteInFlight = false
    @Published var autoCompleteMessage: String?
    @Published var eloBoostInFlight = false
    @Published var eloBoostMessage: String?

    func refreshSubmissions(baseURL: String, username: String?) async {
        guard !isLoadingSubmissions else { return }
        let trimmedBase = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedBase.isEmpty else {
            submissions = []
            lastError = "Set the ChatKit backend URL before fetching submissions."
            return
        }
        isLoadingSubmissions = true
        defer { isLoadingSubmissions = false }
        do {
            submissions = try await BackendService.fetchAssessmentSubmissions(baseURL: trimmedBase, username: username)
            lastError = nil
        } catch {
            let nsError = error as NSError
            lastError = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
        }
    }

    func performDeveloperReset(
        baseURL: String,
        settings: AppSettings,
        appVM: AppViewModel
    ) async {
        guard !resetInFlight else { return }
        let trimmedBase = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedBase.isEmpty else {
            lastError = "Set the ChatKit backend URL before running the reset."
            return
        }
        let trimmedUsername = settings.arcadiaUsername.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty else {
            lastError = "Add a learner username in Settings before running the reset."
            return
        }
        resetInFlight = true
        defer { resetInFlight = false }
        do {
            try await BackendService.developerReset(baseURL: trimmedBase, username: trimmedUsername)
            lastResetAt = Date()
            submissions = []
            lastError = nil
            settings.arcadiaUsername = ""
            settings.learnerGoal = ""
            settings.learnerUseCase = ""
            settings.learnerStrengths = ""
            appVM.resetAfterDeveloperClear()
            NotificationCenter.default.post(name: .developerResetCompleted, object: nil)
        } catch {
            let nsError = error as NSError
            lastError = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
        }
    }

    func normalizeEloPlan(
        baseURL: String,
        settings: AppSettings,
        appVM: AppViewModel
    ) async {
        guard !normalizeInFlight else { return }
        let trimmedBase = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedBase.isEmpty else {
            planError = "Set the ChatKit backend URL before normalising the ELO plan."
            return
        }
        let trimmedUsername = settings.arcadiaUsername.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty else {
            planError = "Add a learner username in Settings before normalising the ELO plan."
            return
        }
        normalizeInFlight = true
        defer { normalizeInFlight = false }
        do {
            try await BackendService.normalizeEloPlan(baseURL: trimmedBase, username: trimmedUsername)
            lastNormalizedAt = Date()
            planError = nil
            await appVM.loadProfile(baseURL: trimmedBase, username: trimmedUsername)
        } catch {
            let nsError = error as NSError
            planError = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
        }
    }

    func autoCompleteSchedule(
        baseURL: String,
        settings: AppSettings,
        appVM: AppViewModel
    ) async {
        guard !autoCompleteInFlight else { return }
        let trimmedBase = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedBase.isEmpty else {
            lastError = "Set the ChatKit backend URL before auto-completing work."
            return
        }
        let trimmedUsername = settings.arcadiaUsername.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty else {
            lastError = "Add a learner username in Settings before auto-completing work."
            return
        }
        autoCompleteInFlight = true
        defer { autoCompleteInFlight = false }
        do {
            let schedule = try await BackendService.autoCompleteSchedule(
                baseURL: trimmedBase,
                username: trimmedUsername
            )
            appVM.applyDeveloperScheduleOverride(schedule)
            await appVM.refreshTelemetry(baseURL: trimmedBase, username: trimmedUsername)
            autoCompleteMessage = "Completed lessons/quizzes on \(Date().formatted(date: .numeric, time: .standard))."
            lastError = nil
        } catch {
            let nsError = error as NSError
            lastError = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
            autoCompleteMessage = nil
        }
    }

    func boostElo(
        baseURL: String,
        settings: AppSettings,
        appVM: AppViewModel,
        categoryKey: String? = nil,
        targetRating: Int = 1500
    ) async {
        guard !eloBoostInFlight else { return }
        let trimmedBase = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedBase.isEmpty else {
            lastError = "Set the ChatKit backend URL before boosting ratings."
            return
        }
        let trimmedUsername = settings.arcadiaUsername.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty else {
            lastError = "Add a learner username in Settings before boosting ratings."
            return
        }
        eloBoostInFlight = true
        defer { eloBoostInFlight = false }
        do {
            let schedule = try await BackendService.boostElo(
                baseURL: trimmedBase,
                username: trimmedUsername,
                categoryKey: categoryKey,
                targetRating: targetRating,
                completePriorItems: true
            )
            appVM.applyDeveloperScheduleOverride(schedule)
            await appVM.refreshTelemetry(baseURL: trimmedBase, username: trimmedUsername)
            eloBoostMessage = "Boosted ratings to \(targetRating) on \(Date().formatted(date: .numeric, time: .standard))."
            lastError = nil
        } catch {
            let nsError = error as NSError
            lastError = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
            eloBoostMessage = nil
        }
    }
}
