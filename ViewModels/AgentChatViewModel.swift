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
    private var backendURL: String = ""
    private var username: String = ""
    private var learnerGoal: String = ""
    private var learnerUseCase: String = ""

    func prepareWelcomeMessage(isBackendReady: Bool) {
        guard !welcomed else { return }
        welcomed = true
        if !isBackendReady {
            messages = [ChatMessage(role: .assistant, text: "Set your Arcadia backend URL in Settings to start chatting.")]
        } else {
            if username.isEmpty {
                messages = [ChatMessage(role: .assistant, text: "Hi! I’m your Arcadia Coach. What would you like to explore today?")]
            } else {
                messages = [ChatMessage(role: .assistant, text: "Welcome back, \(username)! What should we focus on today?")]
            }
        }
    }

    func handleBackendChange(_ url: String) {
        let trimmed = url.trimmingCharacters(in: .whitespacesAndNewlines)
        let alreadyConfigured = trimmed == backendURL
        backendURL = trimmed
        prepareWelcomeMessage(isBackendReady: !trimmed.isEmpty)
        if alreadyConfigured {
            return
        }
        welcomed = false
        messages.removeAll()
        let previousKey = sessionKey
        Task {
            await BackendService.resetSession(baseURL: trimmed, sessionId: previousKey)
        }
        sessionKey = sessionIdentifier()
        prepareWelcomeMessage(isBackendReady: !trimmed.isEmpty)
    }

    func updateUser(_ name: String) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed == username { return }
        let previousKey = sessionKey
        username = trimmed
        sessionKey = sessionIdentifier()
        welcomed = false
        messages.removeAll()
        if let backend = BackendService.trimmed(url: backendURL) {
            Task { await BackendService.resetSession(baseURL: backend, sessionId: previousKey) }
        }
        prepareWelcomeMessage(isBackendReady: !backendURL.isEmpty)
    }

    func statusLabel() -> String {
        if backendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "Offline" }
        return isSending ? "Thinking…" : "Online"
    }

    func canSend() -> Bool {
        !backendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isSending
    }

    func updateProfile(goal: String, useCase: String) {
        learnerGoal = goal.trimmingCharacters(in: .whitespacesAndNewlines)
        learnerUseCase = useCase.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func send(message: String) async {
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !backendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }

        messages.append(ChatMessage(role: .user, text: trimmed))
        isSending = true
        do {
            let history = messages.dropLast().map { message in
                BackendChatTurn(
                    role: message.role == .user ? "user" : "assistant",
                    text: message.text
                )
            }
            let envelope = try await BackendService.sendChat(
                baseURL: backendURL,
                sessionId: sessionKey,
                history: history,
                message: trimmed,
                metadata: metadataPayload()
            )
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

    private func sessionIdentifier() -> String {
        guard !username.isEmpty else { return UUID().uuidString }
        let allowed = username.lowercased().filter { $0.isLetter || $0.isNumber || $0 == "-" || $0 == "_" }
        return allowed.isEmpty ? UUID().uuidString : "chat-\(allowed)"
    }

    private func metadataPayload() -> [String: String] {
        var metadata: [String: String] = [:]
        if !username.isEmpty {
            metadata["username"] = username
        }
        if !learnerGoal.isEmpty {
            metadata["goal"] = learnerGoal
        }
        if !learnerUseCase.isEmpty {
            metadata["use_case"] = learnerUseCase
        }
        return metadata
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
            case .ArcadiaChatbot, .MiniChatbot:
                if let chat = first.propsArcadiaChatbot {
                    return chat.messages.last?.text ?? ""
                }
            }
        }
        return "Thanks for the update!"
    }
}
