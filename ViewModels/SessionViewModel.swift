import SwiftUI

@MainActor
final class SessionViewModel: ObservableObject {
    @Published var lesson: EndLearn?
    @Published var quiz: EndQuiz?
    @Published var milestone: EndMilestone?
    @Published var sessionId: String? = UUID().uuidString

    func loadLesson(agentId: String, topic: String) async {
        guard !agentId.isEmpty else { return }
        do {
            let output: EndLearn = try await AgentService.send(agentId: agentId, model: "gpt-5", message: "learn \(topic)", sessionId: sessionId, expecting: EndLearn.self)
            lesson = output
        } catch {
            print("Lesson error", error)
        }
    }

    func loadQuiz(agentId: String, topic: String) async {
        guard !agentId.isEmpty else { return }
        do {
            let output: EndQuiz = try await AgentService.send(agentId: agentId, model: "gpt-5-codex", message: "quiz \(topic)", sessionId: sessionId, expecting: EndQuiz.self)
            quiz = output
        } catch {
            print("Quiz error", error)
        }
    }

    func loadMilestone(agentId: String, topic: String) async {
        guard !agentId.isEmpty else { return }
        do {
            let output: EndMilestone = try await AgentService.send(agentId: agentId, model: "gpt-5", message: "milestone \(topic)", sessionId: sessionId, expecting: EndMilestone.self)
            milestone = output
        } catch {
            print("Milestone error", error)
        }
    }
}
