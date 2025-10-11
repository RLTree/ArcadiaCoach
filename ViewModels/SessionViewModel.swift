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

    func reset(for agentId: String) async {
        let cacheKey = sessionId ?? "default"
        await AgentService.resetSession(agentId: agentId, key: cacheKey)
        sessionId = UUID().uuidString
        lesson = nil
        quiz = nil
        milestone = nil
        lastError = nil
        lastEventDescription = "Session reset at \(Date().formatted(date: .omitted, time: .standard))"
        Self.logger.info("Reset session cache for agent \(agentId, privacy: .public)")
    }

    func loadLesson(agentId: String, topic: String) async {
        await perform(action: .lesson, agentId: agentId, topic: topic) {
            let output: EndLearn = try await AgentService.send(
                agentId: agentId,
                model: "gpt-5",
                message: "learn \(topic)",
                sessionId: sessionId,
                expecting: EndLearn.self
            )
            lesson = output
            lastEventDescription = "Loaded lesson envelope (\(output.widgets.count) widgets)."
        }
    }

    func loadQuiz(agentId: String, topic: String) async {
        await perform(action: .quiz, agentId: agentId, topic: topic) {
            let output: EndQuiz = try await AgentService.send(
                agentId: agentId,
                model: "gpt-5-codex",
                message: "quiz \(topic)",
                sessionId: sessionId,
                expecting: EndQuiz.self
            )
            quiz = output
            lastEventDescription = "Loaded quiz results (ELO keys: \(output.elo.keys.joined(separator: ", ")))."
        }
    }

    func loadMilestone(agentId: String, topic: String) async {
        await perform(action: .milestone, agentId: agentId, topic: topic) {
            let output: EndMilestone = try await AgentService.send(
                agentId: agentId,
                model: "gpt-5",
                message: "milestone \(topic)",
                sessionId: sessionId,
                expecting: EndMilestone.self
            )
            milestone = output
            lastEventDescription = "Loaded milestone update (\(output.widgets.count) widgets)."
        }
    }

    private func perform(
        action: SessionAction,
        agentId: String,
        topic: String,
        block: () async throws -> Void
    ) async {
        do {
            guard !agentId.isEmpty else {
                throw SessionActionError(
                    action: action,
                    message: "Add an Agent ID on the Settings tab before launching a \(action.rawValue.lowercased()) flow."
                )
            }
            activeAction = action
            lastError = nil
            Self.logger.debug("Starting \(action.rawValue) action (agent=\(agentId, privacy: .public), topic=\(topic, privacy: .public))")
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
