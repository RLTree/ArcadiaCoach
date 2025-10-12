import SwiftUI
import OSLog

@MainActor
final class SessionViewModel: ObservableObject {
    @Published var lesson: EndLearn?
    @Published var quiz: EndQuiz?
    @Published var milestone: EndMilestone?
    @Published var sessionId: String?
    @Published private(set) var activeAction: SessionAction?
    @Published var lastError: SessionActionError?
    @Published var lastEventDescription: String?

    private static let logger = Logger(subsystem: "com.arcadiacoach.app", category: "SessionViewModel")
    private var currentUsername: String = ""
    private var profileGoal: String = ""
    private var profileUseCase: String = ""
    private var profileStrengths: String = ""

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
                topic: topic,
                metadata: metadataPayload()
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
                topic: topic,
                metadata: metadataPayload()
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
                topic: topic,
                metadata: metadataPayload()
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
                    message: "Set your Arcadia backend URL in Settings before launching a \(action.rawValue.lowercased()) flow."
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

    func applyUserContext(username: String, backendURL: String) async {
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalized = Self.sessionIdentifier(for: trimmedUsername)
        if normalized == sessionId, trimmedUsername == currentUsername {
            return
        }

        let previousId = sessionId
        if let backend = BackendService.trimmed(url: backendURL), let previousId {
            await BackendService.resetSession(baseURL: backend, sessionId: previousId)
        }

        await MainActor.run {
            sessionId = normalized
            currentUsername = normalized != nil ? trimmedUsername : ""
            lesson = nil
            quiz = nil
            milestone = nil
            lastEventDescription = normalized != nil
                ? "Signed in as \(trimmedUsername)"
                : "Session reset for anonymous user"
        }
    }

    private static func sessionIdentifier(for username: String) -> String? {
        let trimmed = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let allowed = trimmed.lowercased().filter { $0.isLetter || $0.isNumber || $0 == "-" || $0 == "_" }
        guard !allowed.isEmpty else { return nil }
        return "user-\(allowed)"
    }

    private func metadataPayload() -> [String: String] {
        var metadata: [String: String] = [:]
        if !currentUsername.isEmpty {
            metadata["username"] = currentUsername
        }
        if !profileGoal.isEmpty {
            metadata["goal"] = profileGoal
        }
        if !profileUseCase.isEmpty {
            metadata["use_case"] = profileUseCase
        }
        if !profileStrengths.isEmpty {
            metadata["strengths"] = profileStrengths
        }
        return metadata
    }

    func updateProfile(goal: String, useCase: String, strengths: String) {
        profileGoal = goal.trimmingCharacters(in: .whitespacesAndNewlines)
        profileUseCase = useCase.trimmingCharacters(in: .whitespacesAndNewlines)
        profileStrengths = strengths.trimmingCharacters(in: .whitespacesAndNewlines)
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
