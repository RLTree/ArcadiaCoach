import SwiftUI
import OSLog

@MainActor
final class SessionViewModel: ObservableObject {
    @Published var lesson: EndLearn?
    @Published var quiz: EndQuiz?
    @Published var milestone: EndMilestone?
    @Published var sessionId: String? = UUID().uuidString
    @Published private(set) var activeAction: SessionAction?
    @Published var lastError: SessionActionError?
    @Published var lastEventDescription: String?

    private static let logger = Logger(subsystem: "com.arcadiacoach.app", category: "SessionViewModel")

    func reset(for backendURL: String) async {
        let cacheKey = sessionId ?? "default"
        await BackendService.resetSession(baseURL: backendURL, sessionId: cacheKey)
        sessionId = UUID().uuidString
        lesson = nil
        quiz = nil
        milestone = nil
        lastError = nil
        lastEventDescription = "Session reset at \(Date().formatted(date: .omitted, time: .standard))"
        Self.logger.info("Reset session cache for backend \(backendURL, privacy: .public)")
    }

    func loadLesson(backendURL: String, topic: String) async {
        await perform(action: .lesson, backendURL: backendURL, topic: topic) {
            let output = try await BackendService.loadLesson(
                baseURL: backendURL,
                sessionId: sessionId,
                topic: topic
            )
            lesson = output
            lastEventDescription = "Loaded lesson envelope (\(output.widgets.count) widgets)."
        }
    }

    func loadQuiz(backendURL: String, topic: String) async {
        await perform(action: .quiz, backendURL: backendURL, topic: topic) {
            let output = try await BackendService.loadQuiz(
                baseURL: backendURL,
                sessionId: sessionId,
                topic: topic
            )
            quiz = output
            lastEventDescription = "Loaded quiz results (ELO keys: \(output.elo.keys.joined(separator: ", ")))."
        }
    }

    func loadMilestone(backendURL: String, topic: String) async {
        await perform(action: .milestone, backendURL: backendURL, topic: topic) {
            let output = try await BackendService.loadMilestone(
                baseURL: backendURL,
                sessionId: sessionId,
                topic: topic
            )
            milestone = output
            lastEventDescription = "Loaded milestone update (\(output.widgets.count) widgets)."
        }
    }

    private func perform(
        action: SessionAction,
        backendURL: String,
        topic: String,
        block: () async throws -> Void
    ) async {
        do {
            guard !backendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                throw SessionActionError(
                    action: action,
                    message: "Set the ChatKit backend URL in Settings before launching a \(action.rawValue.lowercased()) flow."
                )
            }
            activeAction = action
            lastError = nil
            Self.logger.debug("Starting \(action.rawValue) action (backend=\(backendURL, privacy: .public), topic=\(topic, privacy: .public))")
            try await block()
            Self.logger.info("\(action.rawValue) action completed successfully.")
        } catch {
            let message = describe(error: error)
            lastError = SessionActionError(action: action, message: message)
            Self.logger.error("\(action.rawValue) action failed: \(message, privacy: .public)")
        }
        activeAction = nil
    }

    private func describe(error: Error) -> String {
        if let sessionError = error as? SessionActionError {
            return sessionError.message
        }
        let nsError = error as NSError
        let base = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
        if let body = nsError.userInfo["body"] as? String, !body.isEmpty {
            return "\(base) (\(body.prefix(300)))"
        }
        return base
    }
}

enum SessionAction: String {
    case lesson = "Lesson"
    case quiz = "Quiz"
    case milestone = "Milestone"
}

struct SessionActionError: Identifiable, Error {
    let id = UUID()
    let action: SessionAction
    let message: String
}

extension SessionActionError: LocalizedError {
    var errorDescription: String? { message }
}
