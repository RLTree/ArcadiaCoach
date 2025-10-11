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
        .onChange(of: settings.chatkitBackendURL) { newBackend in
            Task {
                await BackendService.resetSession(baseURL: newBackend, sessionId: sessionKey)
                await MainActor.run {
                    sessionKey = UUID().uuidString
                    messages = []
                }
                await syncMessagesIfNeeded(force: true)
            }
        }
    }

    private var canSend: Bool {
        !settings.chatkitBackendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isSending
    }

    private var statusLabel: String {
        if settings.chatkitBackendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "Offline" }
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
        let backend = settings.chatkitBackendURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !backend.isEmpty else {
            await MainActor.run {
                appendAssistantMessage("Set the ChatKit backend URL in Settings to continue.")
            }
            return
        }
        await MainActor.run {
            messages.append(ChatMessage(role: .user, text: text))
            isSending = true
            errorText = nil
        }
        do {
            let history = messages.dropLast().map { message in
                BackendChatTurn(
                    role: message.role == .user ? "user" : "assistant",
                    text: message.text
                )
            }
            let envelope = try await BackendService.sendChat(
                baseURL: backend,
                sessionId: sessionKey,
                history: history,
                message: text
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
