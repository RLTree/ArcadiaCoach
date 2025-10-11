import SwiftUI

struct WidgetMiniChatbotView: View {
    let props: MiniChatbotProps

    @EnvironmentObject private var settings: AppSettings
    @State private var messages: [ChatMessage] = []
    @State private var isSending = false
    @State private var errorText: String?
    @State private var sessionKey = UUID().uuidString

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            MiniChatbotView(
                title: props.title,
                status: statusLabel,
                placeholder: props.placeholder,
                messages: messages,
                canSend: canSend,
                isSending: isSending,
                onSubmit: send
            )
            if let errorText {
                Text(errorText)
                    .font(.footnote)
                    .foregroundStyle(Color.red)
            }
        }
        .task { await syncMessagesIfNeeded() }
        .onChange(of: props) { _ in
            Task { await syncMessagesIfNeeded(force: true) }
        }
        .onChange(of: settings.agentId) { newAgent in
            Task {
                await AgentService.resetSession(agentId: newAgent, key: sessionKey)
                await MainActor.run {
                    sessionKey = UUID().uuidString
                    messages = []
                }
                await syncMessagesIfNeeded(force: true)
            }
        }
    }

    private var canSend: Bool {
        !settings.agentId.isEmpty && !isSending
    }

    private var statusLabel: String {
        if settings.agentId.isEmpty { return "Offline" }
        if isSending { return "Thinking…" }
        return props.status.isEmpty ? "Online" : props.status
    }

    @MainActor
    private func syncMessagesIfNeeded(force: Bool = false) async {
        if messages.isEmpty || force {
            messages = props.messages.map { message in
                let role = message.role.lowercased() == "user" ? ChatMessage.Role.user : .assistant
                return ChatMessage(role: role, text: message.text)
            }
        }
    }

    @MainActor
    private func appendAssistantMessage(_ text: String) {
        messages.append(ChatMessage(role: .assistant, text: text))
    }

    private func send(_ text: String) async {
        guard !settings.agentId.isEmpty else {
            await MainActor.run {
                appendAssistantMessage("Add an Agent ID in Settings to continue.")
            }
            return
        }
        await MainActor.run {
            messages.append(ChatMessage(role: .user, text: text))
            isSending = true
            errorText = nil
        }
        do {
            let envelope: WidgetEnvelope = try await AgentService.send(
                agentId: settings.agentId,
                model: "",
                message: text,
                sessionId: sessionKey,
                expecting: WidgetEnvelope.self
            )
            await MainActor.run {
                if let mini = envelope.widgets.first(where: { $0.type == .MiniChatbot })?.propsMiniChatbot {
                    messages = mini.messages.map { message in
                        let role = message.role.lowercased() == "user" ? ChatMessage.Role.user : .assistant
                        return ChatMessage(role: role, text: message.text)
                    }
                } else {
                    let reply = AgentChatViewModel.extractReply(from: envelope)
                    appendAssistantMessage(reply)
                }
                isSending = false
            }
        } catch {
            await MainActor.run {
                let message = error.localizedDescription
                appendAssistantMessage("Sorry, I ran into a problem: \(message)")
                errorText = message
                isSending = false
            }
        }
    }
}
