import Foundation
import OSLog

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
