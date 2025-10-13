import Foundation
import OSLog
#if canImport(UniformTypeIdentifiers)
import UniformTypeIdentifiers
#endif

private let pathAllowed = CharacterSet.urlPathAllowed

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
        var webEnabled: Bool?
        var reasoningLevel: String?
        var model: String?
        var attachments: [ChatAttachmentPayload]?
    }

    private struct ResetPayload: Encodable {
        var sessionId: String?
    }

    private struct OnboardingPlanPayload: Encodable {
        var username: String
        var goal: String
        var useCase: String?
        var strengths: String?
        var force: Bool?
    }

    private struct AssessmentStatusPayload: Encodable {
        var status: String
    }

    struct AssessmentSubmissionUploadItem: Encodable {
        var taskId: String
        var response: String
    }

    private struct AssessmentSubmissionUpload: Encodable {
        var responses: [AssessmentSubmissionUploadItem]
        var metadata: [String: String]?
    }

    private struct DeveloperResetPayload: Encodable {
        var username: String
    }

    private struct ChatAttachmentPayload: Encodable {
        var fileId: String
        var name: String
        var mimeType: String
        var size: Int
        var preview: String?
        var openaiFileId: String?
    }

    private struct ChatAttachmentUploadResponse: Decodable {
        var fileId: String
        var name: String
        var mimeType: String
        var size: Int
        var preview: String?
        var openaiFileId: String?
    }

    struct OnboardingStatusSnapshot: Decodable {
        var username: String
        var planReady: Bool
        var assessmentReady: Bool
        var generatedAt: Date?
    }

    private static let logger = Logger(subsystem: "com.arcadiacoach.app", category: "BackendService")
    private static let requestTimeout: TimeInterval = 1800
    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let value = try container.decode(String.self)
            if let date = iso8601WithFractional.date(from: value) {
                return date
            }
            if let date = iso8601Basic.date(from: value) {
                return date
            }
            if let seconds = TimeInterval(value) {
                return Date(timeIntervalSince1970: seconds)
            }
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Unrecognised date format: \(value)"
            )
        }
        return decoder
    }()

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()

    private static let iso8601WithFractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let iso8601Basic: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    static func resetSession(baseURL: String, sessionId: String?) async {
        guard let base = trimmed(url: baseURL), let url = endpoint(baseURL: base, path: "api/session/reset") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = requestTimeout
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? encoder.encode(ResetPayload(sessionId: sessionId))
        do {
            _ = try await URLSession.shared.data(for: request)
        } catch {
            logger.notice("Failed to reset backend session (id=\(sessionId ?? "nil", privacy: .public)): \(error.localizedDescription, privacy: .public)")
        }
    }

    static func fetchProfile(baseURL: String, username: String) async throws -> LearnerProfileSnapshot {
        guard let trimmedBase = trimmed(url: baseURL) else {
            throw BackendServiceError.missingBackend
        }
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty else {
            throw BackendServiceError.invalidURL
        }
        let encodedUsername = trimmedUsername.addingPercentEncoding(withAllowedCharacters: pathAllowed) ?? trimmedUsername
        guard let url = endpoint(baseURL: trimmedBase, path: "api/profile/\(encodedUsername)") else {
            throw BackendServiceError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = requestTimeout

        logger.debug("GET \(url.absoluteString, privacy: .public)")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw BackendServiceError.transportFailure(status: -1, body: "Invalid response")
        }
        guard (200 ..< 300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? "<no body>"
            throw BackendServiceError.transportFailure(status: http.statusCode, body: body)
        }

        do {
            return try decoder.decode(LearnerProfileSnapshot.self, from: data)
        } catch {
            throw BackendServiceError.decodingFailure(error.localizedDescription)
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

    static func ensureOnboardingPlan(
        baseURL: String,
        username: String,
        goal: String,
        useCase: String,
        strengths: String,
        force: Bool = false
    ) async throws -> LearnerProfileSnapshot {
        guard let trimmedBase = trimmed(url: baseURL) else {
            throw BackendServiceError.missingBackend
        }
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedGoal = goal.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty, !trimmedGoal.isEmpty else {
            throw BackendServiceError.invalidURL
        }
        let trimmedUseCase = useCase.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedStrengths = strengths.trimmingCharacters(in: .whitespacesAndNewlines)
        let payload = OnboardingPlanPayload(
            username: trimmedUsername,
            goal: trimmedGoal,
            useCase: trimmedUseCase.isEmpty ? nil : trimmedUseCase,
            strengths: trimmedStrengths.isEmpty ? nil : trimmedStrengths,
            force: force ? true : nil
        )
        return try await post(
            baseURL: trimmedBase,
            path: "api/onboarding/plan",
            body: payload,
            expecting: LearnerProfileSnapshot.self
        )
    }

    static func fetchOnboardingStatus(baseURL: String, username: String) async throws -> OnboardingStatusSnapshot {
        guard let trimmedBase = trimmed(url: baseURL) else {
            throw BackendServiceError.missingBackend
        }
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty else {
            throw BackendServiceError.invalidURL
        }
        let encodedUsername = trimmedUsername.addingPercentEncoding(withAllowedCharacters: pathAllowed) ?? trimmedUsername
        guard let url = endpoint(baseURL: trimmedBase, path: "api/onboarding/\(encodedUsername)/status") else {
            throw BackendServiceError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = requestTimeout

        logger.debug("GET \(url.absoluteString, privacy: .public)")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw BackendServiceError.transportFailure(status: -1, body: "Invalid response")
        }
        guard (200 ..< 300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? "<no body>"
            throw BackendServiceError.transportFailure(status: http.statusCode, body: body)
        }

        do {
            return try decoder.decode(OnboardingStatusSnapshot.self, from: data)
        } catch {
            throw BackendServiceError.decodingFailure(error.localizedDescription)
        }
    }

    static func updateOnboardingAssessmentStatus(
        baseURL: String,
        username: String,
        status: OnboardingAssessment.Status
    ) async throws -> OnboardingAssessment {
        guard let trimmedBase = trimmed(url: baseURL) else {
            throw BackendServiceError.missingBackend
        }
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty else {
            throw BackendServiceError.invalidURL
        }
        let encodedUsername = trimmedUsername.addingPercentEncoding(withAllowedCharacters: pathAllowed) ?? trimmedUsername
        return try await post(
            baseURL: trimmedBase,
            path: "api/onboarding/\(encodedUsername)/assessment/status",
            body: AssessmentStatusPayload(status: status.rawValue),
            expecting: OnboardingAssessment.self
        )
    }

    static func submitAssessmentResponses(
        baseURL: String,
        username: String,
        responses: [AssessmentSubmissionUploadItem],
        metadata: [String: String] = [:]
    ) async throws -> AssessmentSubmissionRecord {
        guard let trimmedBase = trimmed(url: baseURL) else {
            throw BackendServiceError.missingBackend
        }
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty, !responses.isEmpty else {
            throw BackendServiceError.invalidURL
        }
        let encodedUsername = trimmedUsername.addingPercentEncoding(withAllowedCharacters: pathAllowed) ?? trimmedUsername
        let cleanedMetadata = metadata
            .mapValues { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.value.isEmpty }
        let payload = AssessmentSubmissionUpload(
            responses: responses,
            metadata: cleanedMetadata.isEmpty ? nil : cleanedMetadata
        )
        return try await post(
            baseURL: trimmedBase,
            path: "api/onboarding/\(encodedUsername)/assessment/submissions",
            body: payload,
            expecting: AssessmentSubmissionRecord.self
        )
    }

    static func fetchAssessmentSubmissions(
        baseURL: String,
        username: String? = nil
    ) async throws -> [AssessmentSubmissionRecord] {
        guard let trimmedBase = trimmed(url: baseURL) else {
            throw BackendServiceError.missingBackend
        }
        guard var url = endpoint(baseURL: trimmedBase, path: "api/developer/submissions") else {
            throw BackendServiceError.invalidURL
        }
        if let username, !username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
            let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
            components?.queryItems = [URLQueryItem(name: "username", value: trimmedUsername)]
            if let resolved = components?.url {
                url = resolved
            }
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = requestTimeout

        logger.debug("GET \(url.absoluteString, privacy: .public)")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw BackendServiceError.transportFailure(status: -1, body: "Invalid response")
        }
        guard (200 ..< 300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? "<no body>"
            throw BackendServiceError.transportFailure(status: http.statusCode, body: body)
        }

        do {
            return try decoder.decode([AssessmentSubmissionRecord].self, from: data)
        } catch {
            throw BackendServiceError.decodingFailure(error.localizedDescription)
        }
    }

    static func developerReset(baseURL: String, username: String) async throws {
        guard let trimmedBase = trimmed(url: baseURL) else {
            throw BackendServiceError.missingBackend
        }
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty else {
            throw BackendServiceError.invalidURL
        }
        guard let url = endpoint(baseURL: trimmedBase, path: "api/developer/reset") else {
            throw BackendServiceError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = requestTimeout
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(DeveloperResetPayload(username: trimmedUsername))

        logger.debug("POST \(url.absoluteString, privacy: .public) [developer reset]")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw BackendServiceError.transportFailure(status: -1, body: "Invalid response")
        }
        guard (200 ..< 300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? "<no body>"
            throw BackendServiceError.transportFailure(status: http.statusCode, body: body)
        }
    }

    static func uploadChatAttachment(
        baseURL: String,
        fileURL: URL
    ) async throws -> ChatAttachment {
        guard let trimmedBase = trimmed(url: baseURL) else {
            throw BackendServiceError.missingBackend
        }
        guard let url = endpoint(baseURL: trimmedBase, path: "api/chatkit/upload") else {
            throw BackendServiceError.invalidURL
        }
        let data = try Data(contentsOf: fileURL)

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = requestTimeout
        let boundary = "Boundary-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()
        let filename = fileURL.lastPathComponent
        let mimeType = mimeType(for: fileURL)
        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n")
        body.append("Content-Type: \(mimeType)\r\n\r\n")
        body.append(data)
        body.append("\r\n")
        body.append("--\(boundary)--\r\n")
        request.httpBody = body

        logger.debug("POST \(url.absoluteString, privacy: .public) [upload]")

        let (responseData, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw BackendServiceError.transportFailure(status: -1, body: "Invalid response")
        }
        guard (200 ..< 300).contains(http.statusCode) else {
            let body = String(data: responseData, encoding: .utf8) ?? "<no body>"
            throw BackendServiceError.transportFailure(status: http.statusCode, body: body)
        }

        do {
            let decoded = try decoder.decode(ChatAttachmentUploadResponse.self, from: responseData)
            return ChatAttachment(
                id: decoded.fileId,
                name: decoded.name,
                mimeType: decoded.mimeType,
                size: decoded.size,
                preview: decoded.preview,
                openAIFileId: decoded.openaiFileId,
                addedAt: Date()
            )
        } catch {
            throw BackendServiceError.decodingFailure(error.localizedDescription)
        }
    }

    static func sendChat(
        baseURL: String,
        sessionId: String?,
        history: [BackendChatTurn],
        message: String,
        metadata: [String: String] = [:],
        webEnabled: Bool = false,
        reasoningLevel: String = "medium",
        model: String? = nil,
        attachments: [ChatAttachment] = []
    ) async throws -> WidgetEnvelope {
        let attachmentPayloads = attachments.map { attachment in
            ChatAttachmentPayload(
                fileId: attachment.id,
                name: attachment.name,
                mimeType: attachment.mimeType,
                size: attachment.size,
                preview: attachment.preview,
                openaiFileId: attachment.openAIFileId
            )
        }
        return try await post(
            baseURL: baseURL,
            path: "api/session/chat",
            body: ChatPayload(
                message: message,
                sessionId: sessionId,
                history: history,
                metadata: metadata.isEmpty ? nil : metadata,
                webEnabled: webEnabled,
                reasoningLevel: reasoningLevel,
                model: model,
                attachments: attachmentPayloads.isEmpty ? nil : attachmentPayloads
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
        request.timeoutInterval = requestTimeout
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

    private static func mimeType(for fileURL: URL) -> String {
        #if canImport(UniformTypeIdentifiers)
        if #available(macOS 11.0, *) {
            if let type = UTType(filenameExtension: fileURL.pathExtension.lowercased()),
               let preferred = type.preferredMIMEType {
                return preferred
            }
        }
        #endif
        return "application/octet-stream"
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

private extension Data {
    mutating func append(_ string: String) {
        if let data = string.data(using: .utf8) {
            append(data)
        }
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
