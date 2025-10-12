import Foundation
import OSLog

struct BackendChatTurn: Codable {
    var role: String
    var text: String
}

enum BackendServiceError: LocalizedError {
    case missingBackend
    case invalidURL
    case transportFailure(status: Int, body: String)
    case decodingFailure(String)

    var errorDescription: String? {
        switch self {
        case .missingBackend:
            return "Configure the Arcadia backend URL in Settings before starting a session."
        case .invalidURL:
            return "The Arcadia backend URL looks invalid. Double-check the value in Settings."
        case let .transportFailure(status, body):
            let snippet = body.trimmingCharacters(in: .whitespacesAndNewlines).prefix(280)
            return "The Arcadia backend returned status \(status). \(snippet)"
        case let .decodingFailure(reason):
            return "Unable to decode the backend response (\(reason))."
        }
    }
}

final class BackendService {
    private struct TopicPayload: Encodable {
        var topic: String
        var sessionId: String?
        var metadata: [String: String]?
    }

    private struct ChatPayload: Encodable {
        var message: String
        var sessionId: String?
        var history: [BackendChatTurn]
        var metadata: [String: String]?
    }

    private struct ResetPayload: Encodable {
        var sessionId: String?
    }

    private static let logger = Logger(subsystem: "com.arcadiacoach.app", category: "BackendService")
    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()

    static func resetSession(baseURL: String, sessionId: String?) async {
        guard let base = trimmed(url: baseURL), let url = endpoint(baseURL: base, path: "api/session/reset") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? encoder.encode(ResetPayload(sessionId: sessionId))
        do {
            _ = try await URLSession.shared.data(for: request)
        } catch {
            logger.notice("Failed to reset backend session (id=\(sessionId ?? "nil", privacy: .public)): \(error.localizedDescription, privacy: .public)")
        }
    }

    static func loadLesson(
        baseURL: String,
        sessionId: String?,
        topic: String,
        metadata: [String: String] = [:]
    ) async throws -> EndLearn {
        try await post(
            baseURL: baseURL,
            path: "api/session/lesson",
            body: TopicPayload(
                topic: topic,
                sessionId: sessionId,
                metadata: metadata.isEmpty ? nil : metadata
            ),
            expecting: EndLearn.self
        )
    }

    static func loadQuiz(
        baseURL: String,
        sessionId: String?,
        topic: String,
        metadata: [String: String] = [:]
    ) async throws -> EndQuiz {
        try await post(
            baseURL: baseURL,
            path: "api/session/quiz",
            body: TopicPayload(
                topic: topic,
                sessionId: sessionId,
                metadata: metadata.isEmpty ? nil : metadata
            ),
            expecting: EndQuiz.self
        )
    }

    static func loadMilestone(
        baseURL: String,
        sessionId: String?,
        topic: String,
        metadata: [String: String] = [:]
    ) async throws -> EndMilestone {
        try await post(
            baseURL: baseURL,
            path: "api/session/milestone",
            body: TopicPayload(
                topic: topic,
                sessionId: sessionId,
                metadata: metadata.isEmpty ? nil : metadata
            ),
            expecting: EndMilestone.self
        )
    }

    static func sendChat(
        baseURL: String,
        sessionId: String?,
        history: [BackendChatTurn],
        message: String,
        metadata: [String: String] = [:]
    ) async throws -> WidgetEnvelope {
        try await post(
            baseURL: baseURL,
            path: "api/session/chat",
            body: ChatPayload(
                message: message,
                sessionId: sessionId,
                history: history,
                metadata: metadata.isEmpty ? nil : metadata
            ),
            expecting: WidgetEnvelope.self
        )
    }

    private static func post<Body: Encodable, Result: Decodable>(
        baseURL: String,
        path: String,
        body: Body,
        expecting _: Result.Type
    ) async throws -> Result {
        guard let trimmedBase = trimmed(url: baseURL) else {
            throw BackendServiceError.missingBackend
        }
        guard let url = endpoint(baseURL: trimmedBase, path: path) else {
            throw BackendServiceError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)

        logger.debug("POST \(url.absoluteString, privacy: .public)")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw BackendServiceError.transportFailure(status: -1, body: "Invalid response")
        }
        guard (200 ..< 300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? "<no body>"
            throw BackendServiceError.transportFailure(status: http.statusCode, body: body)
        }

        do {
            return try decoder.decode(Result.self, from: data)
        } catch {
            throw BackendServiceError.decodingFailure(error.localizedDescription)
        }
    }

    static func endpoint(baseURL: String, path: String) -> URL? {
        guard let base = URL(string: baseURL) else { return nil }
        return base.appendingPathComponent(path, isDirectory: false)
    }

    static func trimmed(url: String) -> String? {
        let trimmed = url.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

extension BackendServiceError: Equatable {
    static func == (lhs: BackendServiceError, rhs: BackendServiceError) -> Bool {
        switch (lhs, rhs) {
        case (.missingBackend, .missingBackend):
            return true
        case (.invalidURL, .invalidURL):
            return true
        case let (.transportFailure(ls, lb), .transportFailure(rs, rb)):
            return ls == rs && lb == rb
        case let (.decodingFailure(le), .decodingFailure(re)):
            return le == re
        default:
            return false
        }
    }
}
