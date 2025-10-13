import Foundation
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
    @Published var webSearchEnabled: Bool
    @Published var reasoningLevel: String
    @Published var attachments: [ChatAttachment] = []
    @Published private(set) var recents: [ChatTranscriptSummary] = []
    @Published var previewTranscript: ChatTranscript?
    @Published var isUploadingAttachment: Bool = false

    var levelOptions: [ArcadiaChatbotLevelOption] { ArcadiaChatbotProps.defaultLevels }
    var levelLabel: String {
        if let option = levelOptions.first(where: { $0.value == reasoningLevel }) {
            return "\(option.label) effort"
        }
        return "Medium effort"
    }

    private var welcomed = false
    private var sessionKey: String
    private var backendURL: String = ""
    private var username: String = ""
    private var learnerGoal: String = ""
    private var learnerUseCase: String = ""
    private var learnerStrengths: String = ""
    private let historyStore: ChatHistoryStore
    private var transcripts: [ChatTranscript]

    init(
        historyStore: ChatHistoryStore = .shared,
        initialWebEnabled: Bool = false,
        initialReasoningLevel: String = "medium"
    ) {
        self.historyStore = historyStore
        self.webSearchEnabled = initialWebEnabled
        self.reasoningLevel = initialReasoningLevel
        self.transcripts = historyStore.load()
        self.sessionKey = UUID().uuidString
        refreshSummaries()
    }

    func prepareWelcomeMessage(isBackendReady: Bool) {
        guard !welcomed else { return }
        welcomed = true
        let welcomeText: String
        if !isBackendReady {
            welcomeText = "Set your Arcadia backend URL in Settings to start chatting."
        } else if username.isEmpty {
            welcomeText = "Hi! I’m your Arcadia Coach. What would you like to explore today?"
        } else {
            welcomeText = "Welcome back, \(username)! What should we focus on today?"
        }
        let welcome = ChatMessage(role: .assistant, text: welcomeText)
        messages = [welcome]
        ensureTranscript(for: sessionKey)
        updateCurrentTranscript { transcript in
            if transcript.messages.isEmpty {
                transcript.messages.append(
                    ChatTranscript.Message(role: "assistant", text: welcome.text, sentAt: Date())
                )
            }
        }
    }

    func handleBackendChange(_ url: String) {
        let trimmed = url.trimmingCharacters(in: .whitespacesAndNewlines)
        let alreadyConfigured = trimmed == backendURL
        backendURL = trimmed
        if alreadyConfigured {
            prepareWelcomeMessage(isBackendReady: !trimmed.isEmpty)
            return
        }
        welcomed = false
        messages.removeAll()
        attachments.removeAll()
        lastError = nil
        let previousKey = sessionKey
        Task {
            await BackendService.resetSession(baseURL: trimmed, sessionId: previousKey)
        }
        sessionKey = sessionIdentifier()
        ensureTranscript(for: sessionKey)
        refreshSummaries()
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
        attachments.removeAll()
        lastError = nil
        if let backend = BackendService.trimmed(url: backendURL) {
            Task { await BackendService.resetSession(baseURL: backend, sessionId: previousKey) }
        }
        ensureTranscript(for: sessionKey)
        refreshSummaries()
        prepareWelcomeMessage(isBackendReady: !backendURL.isEmpty)
    }

    func statusLabel() -> String {
        let backendReady = !backendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        guard backendReady else { return "Offline" }
        if isSending { return "Thinking…" }
        return webSearchEnabled ? "Online · Web on" : "Online · Web off"
    }

    func canSend() -> Bool {
        !backendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isSending
    }

    func updateProfile(goal: String, useCase: String, strengths: String) {
        learnerGoal = goal.trimmingCharacters(in: .whitespacesAndNewlines)
        learnerUseCase = useCase.trimmingCharacters(in: .whitespacesAndNewlines)
        learnerStrengths = strengths.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func updatePreferences(webEnabled: Bool, reasoningLevel: String) {
        var changed = false
        if webSearchEnabled != webEnabled {
            webSearchEnabled = webEnabled
            changed = true
        }
        if reasoningLevel != self.reasoningLevel,
           levelOptions.contains(where: { $0.value == reasoningLevel }) {
            self.reasoningLevel = reasoningLevel
            changed = true
        }
        if changed {
            updateCurrentTranscript { _ in }
        }
    }

    func toggleWebSearch(_ enabled: Bool) {
        guard webSearchEnabled != enabled else { return }
        webSearchEnabled = enabled
        updateCurrentTranscript { _ in }
    }

    func selectReasoning(level: String) {
        guard levelOptions.contains(where: { $0.value == level }),
              reasoningLevel != level else { return }
        reasoningLevel = level
        updateCurrentTranscript { _ in }
    }

    func addAttachment(_ attachment: ChatAttachment) {
        attachments.append(attachment)
        updateCurrentTranscript { transcript in
            transcript.attachments = attachments
        }
    }

    func removeAttachment(id: String) {
        guard let index = attachments.firstIndex(where: { $0.id == id }) else { return }
        attachments.remove(at: index)
        updateCurrentTranscript { transcript in
            transcript.attachments = attachments
        }
    }

    func uploadAttachment(from url: URL) async {
        guard let backend = BackendService.trimmed(url: backendURL) else {
            lastError = "Configure the Arcadia backend URL in Settings before uploading files."
            return
        }
        isUploadingAttachment = true
        defer { isUploadingAttachment = false }
        do {
            let uploaded = try await BackendService.uploadChatAttachment(baseURL: backend, fileURL: url)
            addAttachment(uploaded)
            lastError = nil
        } catch {
            lastError = error.localizedDescription
        }
    }

    func showTranscript(withId id: String) {
        previewTranscript = transcripts.first(where: { $0.id == id })
    }

    func clearPreview() {
        previewTranscript = nil
    }

    func send(message: String) async {
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty,
              let backend = BackendService.trimmed(url: backendURL) else { return }

        ensureTranscript(for: sessionKey)
        let userMessage = ChatMessage(role: .user, text: trimmed)
        messages.append(userMessage)
        recordMessage(userMessage)

        isSending = true
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
                message: trimmed,
                metadata: metadataPayload(),
                webEnabled: webSearchEnabled,
                reasoningLevel: reasoningLevel,
                attachments: attachments
            )
            let reply = Self.extractReply(from: envelope)
            let assistantMessage = ChatMessage(role: .assistant, text: reply)
            messages.append(assistantMessage)
            recordMessage(assistantMessage)
            lastError = nil
        } catch {
            let failure = error.localizedDescription
            let apologetic = ChatMessage(
                role: .assistant,
                text: "Sorry, I ran into a problem: \(failure)"
            )
            messages.append(apologetic)
            recordMessage(apologetic)
            lastError = failure
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
        if !learnerStrengths.isEmpty {
            metadata["strengths"] = learnerStrengths
        }
        metadata["web_enabled"] = webSearchEnabled ? "true" : "false"
        metadata["reasoning_level"] = reasoningLevel
        if !attachments.isEmpty {
            metadata["attachments_count"] = String(attachments.count)
        }
        return metadata
    }

    private func recordMessage(_ message: ChatMessage) {
        updateCurrentTranscript { transcript in
            transcript.messages.append(
                ChatTranscript.Message(
                    role: message.role == .user ? "user" : "assistant",
                    text: message.text,
                    sentAt: Date()
                )
            )
        }
    }

    private func ensureTranscript(for sessionId: String) {
        if transcripts.contains(where: { $0.id == sessionId }) { return }
        let now = Date()
        var transcript = ChatTranscript(
            id: sessionId,
            title: "Session \(DateFormatter.localizedString(from: now, dateStyle: .medium, timeStyle: .short))",
            startedAt: now,
            updatedAt: now,
            webEnabled: webSearchEnabled,
            reasoningLevel: reasoningLevel,
            messages: [],
            attachments: attachments
        )
        transcript.refreshTitle()
        transcripts.append(transcript)
        historyStore.save(transcripts)
        refreshSummaries()
    }

    private func updateCurrentTranscript(
        _ mutate: (inout ChatTranscript) -> Void
    ) {
        ensureTranscript(for: sessionKey)
        guard let index = transcripts.firstIndex(where: { $0.id == sessionKey }) else { return }
        var transcript = transcripts[index]
        let original = transcript
        mutate(&transcript)
        transcript.webEnabled = webSearchEnabled
        transcript.reasoningLevel = reasoningLevel
        transcript.attachments = attachments
        transcript.refreshTitle()
        if transcript != original {
            transcript.updatedAt = Date()
        }
        transcripts[index] = transcript
        historyStore.save(transcripts)
        refreshSummaries()
    }

    private func refreshSummaries() {
        recents = transcripts
            .sorted { $0.updatedAt > $1.updatedAt }
            .map(ChatTranscriptSummary.init)
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
