import Foundation
import OSLog
import SwiftUI
import UniformTypeIdentifiers

// Phase 6 data models (kept local for Xcode target inclusion).
struct ChatAttachment: Identifiable, Codable, Hashable {
    var id: String
    var name: String
    var mimeType: String
    var size: Int
    var preview: String?
    var openAIFileId: String?
    var addedAt: Date

    init(
        id: String,
        name: String,
        mimeType: String,
        size: Int,
        preview: String?,
        openAIFileId: String?,
        addedAt: Date = Date()
    ) {
        self.id = id
        self.name = name
        self.mimeType = mimeType
        self.size = size
        self.preview = preview
        self.openAIFileId = openAIFileId
        self.addedAt = addedAt
    }

    var sizeLabel: String {
        let formatter = ByteCountFormatter()
        formatter.allowedUnits = [.useKB, .useMB]
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(size))
    }

    var previewSnippet: String? {
        guard let preview else { return nil }
        let trimmed = preview.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        return String(trimmed.prefix(220))
    }

    var iconSystemName: String {
        if mimeType.contains("image/") { return "photo" }
        if mimeType.contains("pdf") { return "doc.richtext" }
        if mimeType.contains("zip") { return "archivebox" }
        if mimeType.contains("text") { return "doc.text" }
        if mimeType.contains("audio") { return "waveform" }
        if mimeType.contains("video") { return "film" }
        return "paperclip"
    }
}

struct ChatTranscript: Identifiable, Codable, Equatable {
    struct Message: Codable, Equatable {
        var role: String
        var text: String
        var sentAt: Date
        var attachments: [ChatAttachment]
    }

    var id: String
    var title: String
    var startedAt: Date
    var updatedAt: Date
    var webEnabled: Bool
    var reasoningLevel: String
    var messages: [Message]
    var attachments: [ChatAttachment]

    mutating func refreshTitle() {
        if let headline = messages.first(where: { $0.role == "user" && !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) {
            let trimmed = headline.text.trimmingCharacters(in: .whitespacesAndNewlines)
            title = String(trimmed.prefix(60))
        } else {
            let formatter = DateFormatter()
            formatter.dateStyle = .medium
            formatter.timeStyle = .short
            title = "Session \(formatter.string(from: startedAt))"
        }
    }
}

struct ChatTranscriptSummary: Identifiable, Hashable {
    var id: String
    var title: String
    var lastUpdated: Date
    var snippet: String
    var webEnabled: Bool
    var reasoningLevel: String

    init(transcript: ChatTranscript) {
        id = transcript.id
        title = transcript.title
        lastUpdated = transcript.updatedAt
        reasoningLevel = transcript.reasoningLevel
        webEnabled = transcript.webEnabled
        if let last = transcript.messages.last {
            let trimmed = last.text.trimmingCharacters(in: .whitespacesAndNewlines)
            snippet = trimmed.isEmpty ? "No messages yet." : String(trimmed.prefix(100))
        } else {
            snippet = "No messages yet."
        }
    }
}

struct ChatModelCapability {
    enum AttachmentPolicy {
        case any
        case imagesOnly
        case none
    }

    var supportsWeb: Bool
    var attachmentPolicy: AttachmentPolicy
}

/// Stores per-session chat transcripts for the Phase 6 sidebar experience.
/// Phase 6 – Frontend Chat & Accessibility Enhancements (Oct 2025).
final class ChatHistoryStore {
    static let shared = ChatHistoryStore()

    private let storageKey = "com.arcadiacoach.chatHistory"
    private let userDefaults: UserDefaults
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder
    private let logger = Logger(subsystem: "com.arcadiacoach.app", category: "ChatHistoryStore")

    init(userDefaults: UserDefaults = .standard) {
        self.userDefaults = userDefaults
        self.encoder = JSONEncoder()
        self.encoder.outputFormatting = [.sortedKeys]
        self.encoder.dateEncodingStrategy = .iso8601
        self.decoder = JSONDecoder()
        self.decoder.dateDecodingStrategy = .iso8601
    }

    func load() -> [ChatTranscript] {
        guard let data = userDefaults.data(forKey: storageKey) else {
            return []
        }
        do {
            return try decoder.decode([ChatTranscript].self, from: data)
        } catch {
            logger.error("Failed to decode chat history: \(error.localizedDescription, privacy: .public)")
            return []
        }
    }

    func save(_ transcripts: [ChatTranscript]) {
        do {
            let data = try encoder.encode(transcripts)
            userDefaults.set(data, forKey: storageKey)
        } catch {
            logger.error("Failed to persist chat history: \(error.localizedDescription, privacy: .public)")
        }
    }

    func clear() {
        userDefaults.removeObject(forKey: storageKey)
    }
}

struct ChatMessage: Identifiable, Equatable {
    enum Role { case user, assistant }
    let id = UUID()
    let role: Role
    let text: String
    let attachments: [ChatAttachment]

    init(role: Role, text: String, attachments: [ChatAttachment] = []) {
        self.role = role
        self.text = text
        self.attachments = attachments
    }
}

@MainActor
final class AgentChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var isSending: Bool = false
    @Published var lastError: String?
    @Published var webSearchEnabled: Bool
    @Published var reasoningLevel: String
    @Published var composerAttachments: [ChatAttachment] = []
    @Published var selectedModel: String
    @Published private(set) var modelSupportsWeb: Bool
    @Published private(set) var attachmentPolicy: ChatModelCapability.AttachmentPolicy
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

    var allowsAttachments: Bool {
        attachmentPolicy != .none
    }

    var allowsImagesOnly: Bool {
        attachmentPolicy == .imagesOnly
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
        initialReasoningLevel: String = "medium",
        initialModel: String = "gpt-5",
        initialModelSupportsWeb: Bool = true,
        initialModelSupportsAttachments: Bool = true
    ) {
        self.historyStore = historyStore
        self.webSearchEnabled = initialWebEnabled
        self.reasoningLevel = initialReasoningLevel
        self.selectedModel = initialModel
        self.modelSupportsWeb = initialModelSupportsWeb
        self.attachmentPolicy = initialModelSupportsAttachments ? .any : .none
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
                    ChatTranscript.Message(role: "assistant", text: welcome.text, sentAt: Date(), attachments: [])
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
        composerAttachments.removeAll()
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
        composerAttachments.removeAll()
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
        if !modelSupportsWeb && webSearchEnabled {
            webSearchEnabled = false
        }
        if changed {
            updateCurrentTranscript { _ in }
        }
    }

    func toggleWebSearch(_ enabled: Bool) {
        guard modelSupportsWeb else { return }
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

    func applyModel(
        _ model: String,
        capability: ChatModelCapability,
        backendURL: String
    ) {
        let trimmedBackend = backendURL.trimmingCharacters(in: .whitespacesAndNewlines)
        let capabilitiesChanged = modelSupportsWeb != capability.supportsWeb || attachmentPolicy != capability.attachmentPolicy
        let modelChanged = selectedModel != model
        guard modelChanged || capabilitiesChanged else { return }

        selectedModel = model
        modelSupportsWeb = capability.supportsWeb
        attachmentPolicy = capability.attachmentPolicy
        if !modelSupportsWeb {
            webSearchEnabled = false
        }
        enforceAttachmentPolicy()

        welcomed = false
        messages.removeAll()
        previewTranscript = nil
        isSending = false
        lastError = nil

        let previousKey = sessionKey
        if let backend = BackendService.trimmed(url: trimmedBackend) {
            Task { await BackendService.resetSession(baseURL: backend, sessionId: previousKey) }
        }
        sessionKey = sessionIdentifier()

        ensureTranscript(for: sessionKey)
        prepareWelcomeMessage(isBackendReady: !trimmedBackend.isEmpty)
    }

    func addAttachment(_ attachment: ChatAttachment) {
        guard isAttachmentAllowed(attachment) else {
            lastError = "\(selectedModel) only accepts image uploads."
            return
        }
        composerAttachments.append(attachment)
    }

    func removeAttachment(id: String) {
        guard let index = composerAttachments.firstIndex(where: { $0.id == id }) else { return }
        composerAttachments.remove(at: index)
    }

    func uploadAttachment(from url: URL) async {
        guard canUploadFile(at: url) else {
            lastError = "\(selectedModel) only accepts image uploads (PNG, JPG, GIF)."
            return
        }
        guard let backend = BackendService.trimmed(url: backendURL) else {
            lastError = "Configure the Arcadia backend URL in Settings before uploading files."
            return
        }
        isUploadingAttachment = true
        defer { isUploadingAttachment = false }
        do {
            let uploaded = try await BackendService.uploadChatAttachment(baseURL: backend, fileURL: url)
            guard isAttachmentAllowed(uploaded) else {
                lastError = "Upload succeeded but \(selectedModel) can only use images."
                return
            }
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

        let outgoingAttachments = composerAttachments.filter { isAttachmentAllowed($0) }
        let outgoingAttachmentCount = outgoingAttachments.count
        let userMessage = ChatMessage(role: .user, text: trimmed, attachments: outgoingAttachments)
        messages.append(userMessage)
        recordMessage(userMessage)
        composerAttachments.removeAll()

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
                metadata: metadataPayload(attachmentCount: outgoingAttachmentCount),
                webEnabled: webSearchEnabled,
                reasoningLevel: reasoningLevel,
                model: selectedModel,
                attachments: outgoingAttachments
            )
            let reply = Self.extractReply(from: envelope)
            let assistantMessage = ChatMessage(role: .assistant, text: reply, attachments: [])
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
            composerAttachments = outgoingAttachments
        }
        isSending = false
    }

    private func sessionIdentifier() -> String {
        let modelSlug = sanitizedModelIdentifier()
        if username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return "chat-\(modelSlug)-\(UUID().uuidString.prefix(8))"
        }
        let allowed = username.lowercased().filter { $0.isLetter || $0.isNumber || $0 == "-" || $0 == "_" }
        let base = allowed.isEmpty ? "guest" : allowed
        return "chat-\(base)-\(modelSlug)-\(UUID().uuidString.prefix(6))"
    }

    private func metadataPayload(attachmentCount: Int) -> [String: String] {
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
        metadata["model"] = selectedModel
        if attachmentCount > 0 {
            metadata["attachments_count"] = String(attachmentCount)
        }
        return metadata
    }

    private func enforceAttachmentPolicy() {
        switch attachmentPolicy {
        case .none:
            composerAttachments.removeAll()
        case .imagesOnly:
            composerAttachments.removeAll { !isAttachmentAllowed($0) }
        case .any:
            break
        }
    }

    private func sanitizedModelIdentifier() -> String {
        let slug = selectedModel.lowercased().filter { $0.isLetter || $0.isNumber || $0 == "-" || $0 == "_" }
        return slug.isEmpty ? "gpt" : slug
    }

    func recordMessage(_ message: ChatMessage) {
        updateCurrentTranscript { transcript in
            transcript.messages.append(
                ChatTranscript.Message(
                    role: message.role == .user ? "user" : "assistant",
                    text: message.text,
                    sentAt: Date(),
                    attachments: message.attachments
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
            attachments: []
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
        transcript.attachments = aggregateAttachments(from: transcript.messages)
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

    private func aggregateAttachments(from messages: [ChatTranscript.Message]) -> [ChatAttachment] {
        var seen = Set<String>()
        var unique: [ChatAttachment] = []
        for message in messages {
            for attachment in message.attachments {
                let key = attachment.id
                if seen.insert(key).inserted {
                    unique.append(attachment)
                }
            }
        }
        return unique
    }

    private func isAttachmentAllowed(_ attachment: ChatAttachment) -> Bool {
        switch attachmentPolicy {
        case .none:
            return false
        case .any:
            return true
        case .imagesOnly:
            return attachment.mimeType.lowercased().hasPrefix("image/")
        }
    }

    private func canUploadFile(at url: URL) -> Bool {
        switch attachmentPolicy {
        case .none:
            return false
        case .any:
            return true
        case .imagesOnly:
            if #available(macOS 11.0, *) {
                if let type = UTType(filenameExtension: url.pathExtension.lowercased()) {
                    return type.conforms(to: .image)
                }
            }
            return false
        }
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
