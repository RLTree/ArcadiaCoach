import Foundation

struct ChatTranscript: Identifiable, Codable, Equatable {
    struct Message: Codable, Equatable {
        var role: String
        var text: String
        var sentAt: Date
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

