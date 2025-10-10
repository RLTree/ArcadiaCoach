import SwiftUI

struct ChatMessage: Identifiable, Equatable {
    enum Role { case user, assistant }
    let id = UUID()
    let role: Role
    let text: String
}

@MainActor
final class AgentChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var isSending: Bool = false
    @Published var lastError: String?

    private var welcomed = false
    private var sessionKey = UUID().uuidString

    func prepareWelcomeMessage(agentId: String) {
        guard !welcomed else { return }
        welcomed = true
        if agentId.isEmpty {
            messages = [ChatMessage(role: .assistant, text: "Add an Agent ID in Settings to start chatting.")]
        } else {
            messages = [ChatMessage(role: .assistant, text: "Hi! I’m your Arcadia Coach. What would you like to explore today?")]
        }
    }

    func handleAgentChange(agentId: String) {
        welcomed = false
        messages.removeAll()
        let previousKey = sessionKey
        Task {
            await AgentService.resetSession(agentId: agentId, key: previousKey)
        }
        sessionKey = UUID().uuidString
        prepareWelcomeMessage(agentId: agentId)
    }

    func statusLabel(for agentId: String) -> String {
        if agentId.isEmpty { return "Offline" }
        return isSending ? "Thinking…" : "Online"
    }

    func canSend(agentId: String) -> Bool {
        !agentId.isEmpty && !isSending
    }

    func send(agentId: String, message: String) async {
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !agentId.isEmpty else { return }

        messages.append(ChatMessage(role: .user, text: trimmed))
        isSending = true
        do {
            let envelope: WidgetEnvelope = try await AgentService.send(agentId: agentId, model: "gpt-5", message: trimmed, sessionId: sessionKey, expecting: WidgetEnvelope.self)
            let reply = Self.extractReply(from: envelope)
            messages.append(ChatMessage(role: .assistant, text: reply))
            lastError = nil
        } catch {
            let message = error.localizedDescription
            messages.append(ChatMessage(role: .assistant, text: "Sorry, I ran into a problem: \(message)"))
            lastError = message
        }
        isSending = false
    }

    static func extractReply(from envelope: WidgetEnvelope) -> String {
        if let display = envelope.display, !display.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return display
        }
        if let first = envelope.widgets.first {
            switch first.type {
            case .Card:
                if let card = first.propsCard {
                    var parts: [String] = [card.title]
                    if let sections = card.sections {
                        for section in sections {
                            if let heading = section.heading {
                                parts.append("\n**\(heading)**")
                            }
                            for item in section.items {
                                parts.append("• \(item)")
                            }
                        }
                    }
                    return parts.joined(separator: "\n")
                }
            case .List:
                if let list = first.propsList {
                    var parts: [String] = []
                    if let title = list.title { parts.append(title) }
                    for row in list.rows {
                        parts.append("• \(row.label)")
                    }
                    return parts.joined(separator: "\n")
                }
            case .StatRow:
                if let stat = first.propsStat {
                    let items = stat.items.map { "\($0.label): \($0.value)" }
                    return items.joined(separator: ", ")
                }
            case .MiniChatbot:
                if let chat = first.propsMiniChatbot {
                    return chat.messages.last?.text ?? ""
                }
            }
        }
        return "Thanks for the update!"
    }
}
