import Foundation
import SwiftUI

@MainActor
final class DeveloperToolsViewModel: ObservableObject {
    @Published var submissions: [AssessmentSubmissionRecord] = []
    @Published var isLoadingSubmissions = false
    @Published var resetInFlight = false
    @Published var lastError: String?
    @Published var lastResetAt: Date?

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
        } catch {
            let nsError = error as NSError
            lastError = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
        }
    }
}
