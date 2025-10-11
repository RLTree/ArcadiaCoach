import Foundation
import OSLog

final class AgentService {
    private struct SessionResponse: Decodable { let id: String }

    private actor SessionCache {
        private var sessions: [String: String] = [:]

        func sessionId(for agentId: String, key: String, apiKey: String) async throws -> String {
            let composite = "\(agentId)|\(key)"
            if let existing = sessions[composite] {
                return existing
            }
            let session = try await AgentService.createSession(agentId: agentId, apiKey: apiKey)
            sessions[composite] = session
            return session
        }

        func update(agentId: String, key: String, sessionId: String) {
            sessions["\(agentId)|\(key)"] = sessionId
        }

        func reset(agentId: String, key: String?) {
            if let key {
                sessions.removeValue(forKey: "\(agentId)|\(key)")
            } else {
                sessions = sessions.filter { !$0.key.hasPrefix("\(agentId)|") }
            }
        }
    }

    private static let responsesURL = URL(string: "https://api.openai.com/v1/responses")!
    private static let sessionsURL = URL(string: "https://api.openai.com/v1/sessions")!
    private static let sessionCache = SessionCache()
    private static let jsonDecoder = JSONDecoder()
    private static let logger = Logger(subsystem: "com.arcadiacoach.app", category: "AgentService")

    static func resetSession(agentId: String, key: String? = nil) async {
        logger.notice("Resetting cached session (agent=\(agentId, privacy: .public), key=\(key ?? "nil", privacy: .public))")
        await sessionCache.reset(agentId: agentId, key: key)
    }

    private static func createSession(agentId: String, apiKey: String) async throws -> String {
        var request = URLRequest(url: sessionsURL)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["agent_id": agentId])
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200 ..< 300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? "<no body>"
            logger.error("Failed to create session (status=\((response as? HTTPURLResponse)?.statusCode ?? -1, privacy: .public), body=\(body, privacy: .public))")
            throw NSError(domain: "AgentService", code: 2, userInfo: [NSLocalizedDescriptionKey: "Failed to create session", "body": body])
        }
        let sessionId = try jsonDecoder.decode(SessionResponse.self, from: data).id
        logger.debug("Created agent session (agent=\(agentId, privacy: .public), session=\(sessionId, privacy: .public))")
        return sessionId
    }

    static func send<T: Decodable>(agentId: String, model _: String, message: String, sessionId: String? = nil, expecting _: T.Type) async throws -> T {
        let apiKey = KeychainHelper.get("OPENAI_API_KEY") ?? ""
        guard !apiKey.isEmpty else {
            logger.error("Missing OpenAI API key when attempting to send message.")
            throw NSError(domain: "AgentService", code: 3, userInfo: [NSLocalizedDescriptionKey: "Missing OpenAI API key. Add it in Settings."])
        }

        let cacheKey = sessionId ?? "default"
        let session = try await sessionCache.sessionId(for: agentId, key: cacheKey, apiKey: apiKey)

        let payload: [String: Any] = [
            "session_id": session,
            "input": [
                [
                    "role": "user",
                    "content": [
                        ["type": "input_text", "text": message],
                    ],
                ],
            ],
        ]

        var request = URLRequest(url: responsesURL)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)

        logger.debug("Sending agent request (agent=\(agentId, privacy: .public), session=\(session, privacy: .public), messageLength=\(message.count, privacy: .public))")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200 ..< 300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? "<no body>"
            logger.error("Agent request failed (status=\((response as? HTTPURLResponse)?.statusCode ?? -1, privacy: .public), body=\(body, privacy: .public))")
            throw NSError(domain: "AgentService", code: 1, userInfo: [NSLocalizedDescriptionKey: "Bad status", "body": body])
        }

        logger.debug("Agent response received (status=\((response as? HTTPURLResponse)?.statusCode ?? -1, privacy: .public), bytes=\(data.count, privacy: .public))")

        return try await decodeStructuredResponse(
            data: data,
            agentId: agentId,
            cacheKey: cacheKey,
            fallbackSessionId: session
        )
    }

    private static func decodeStructuredResponse<T: Decodable>(
        data: Data,
        agentId: String,
        cacheKey: String,
        fallbackSessionId: String
    ) async throws -> T {
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return try jsonDecoder.decode(T.self, from: data)
        }

        if let error = root["error"] as? [String: Any], let message = error["message"] as? String {
            logger.error("Agent response returned error message: \(message, privacy: .public)")
            throw NSError(domain: "AgentService", code: 5, userInfo: [NSLocalizedDescriptionKey: message])
        }

        let sessionInfo = (root["session"] as? [String: Any]) ?? [:]
        if let newId = (sessionInfo["id"] as? String), !newId.isEmpty, newId != fallbackSessionId {
            await sessionCache.update(agentId: agentId, key: cacheKey, sessionId: newId)
            logger.debug("Session id updated from response: \(newId, privacy: .public)")
        } else if let newId = root["session_id"] as? String, !newId.isEmpty, newId != fallbackSessionId {
            await sessionCache.update(agentId: agentId, key: cacheKey, sessionId: newId)
            logger.debug("Session id updated (legacy field): \(newId, privacy: .public)")
        }

        let responsePayload = (root["response"] as? [String: Any]) ?? root
        if let decoded: T = try decodeOutput(from: responsePayload) {
            return decoded
        }

        if let aggregation = responsePayload["output_text"] as? String {
            if T.self == String.self {
                return aggregation as! T
            }
            if let data = aggregation.data(using: .utf8), let decoded = try? jsonDecoder.decode(T.self, from: data) {
                return decoded
            }
        }

        do {
            return try jsonDecoder.decode(T.self, from: data)
        } catch {
            logger.error("Failed to decode agent payload: \(error.localizedDescription, privacy: .public)")
            throw NSError(
                domain: "AgentService",
                code: 4,
                userInfo: [NSLocalizedDescriptionKey: "Unable to decode response payload.", NSUnderlyingErrorKey: error]
            )
        }
    }

    private static func decodeOutput<T: Decodable>(from payload: [String: Any]) throws -> T? {
        if let directJSON = payload["output_json"] {
            return try decodeJSONValue(directJSON, as: T.self)
        }

        if let outputs = payload["output"] as? [[String: Any]] {
            for item in outputs {
                if let decoded: T = try decodeOutputItem(item, as: T.self) {
                    return decoded
                }
            }
        }

        if let messages = payload["messages"] as? [[String: Any]] {
            for message in messages {
                if let decoded: T = try decodeOutputItem(message, as: T.self) {
                    return decoded
                }
            }
        }

        return nil
    }

    private static func decodeOutputItem<T: Decodable>(_ item: [String: Any], as _: T.Type) throws -> T? {
        if let outputJSON = item["output_json"], let decoded: T = try decodeJSONValue(outputJSON, as: T.self) {
                return decoded
        }

        if let content = item["content"] as? [[String: Any]] {
            for entry in content {
                if let type = entry["type"] as? String {
                    if type == "output_json" {
                        if let jsonValue = entry["json"], let decoded: T = try decodeJSONValue(jsonValue, as: T.self) {
                            return decoded
                        }
                    } else if type == "output_text", let text = entry["text"] as? String {
                        if T.self == String.self {
                            return text as? T
                        }
                        if let data = text.data(using: .utf8), let decoded = try? jsonDecoder.decode(T.self, from: data) {
                            return decoded
                        }
                    }
                }
            }
        }

        if T.self == String.self, let text = item["text"] as? String {
            return text as? T
        }

        return nil
    }

    private static func decodeJSONValue<T: Decodable>(_ value: Any, as _: T.Type) throws -> T? {
        if value is NSNull { return nil }

        if T.self == String.self, let stringValue = value as? String {
            return stringValue as? T
        }

        if let dict = value as? [String: Any], let nested = dict["json"] {
            return try decodeJSONValue(nested, as: T.self)
        }

        if JSONSerialization.isValidJSONObject(value) {
            let data = try JSONSerialization.data(withJSONObject: value)
            return try jsonDecoder.decode(T.self, from: data)
        }

        if let string = value as? String, let data = string.data(using: .utf8) {
            return try jsonDecoder.decode(T.self, from: data)
        }

        return nil
    }
}
