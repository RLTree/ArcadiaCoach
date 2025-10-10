import Foundation

final class AgentService {
    struct ResponseEnvelope<T: Decodable>: Decodable { let output: T }
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

    static func resetSession(agentId: String, key: String? = nil) async {
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
            throw NSError(domain: "AgentService", code: 2, userInfo: [NSLocalizedDescriptionKey: "Failed to create session", "body": body])
        }
        return try JSONDecoder().decode(SessionResponse.self, from: data).id
    }

    static func send<T: Decodable>(agentId: String, model _: String, message: String, sessionId: String? = nil, expecting _: T.Type) async throws -> T {
        let apiKey = KeychainHelper.get("OPENAI_API_KEY") ?? ""
        guard !apiKey.isEmpty else {
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

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200 ..< 300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? "<no body>"
            throw NSError(domain: "AgentService", code: 1, userInfo: [NSLocalizedDescriptionKey: "Bad status", "body": body])
        }

        if let envelope = try? JSONDecoder().decode(ResponseEnvelope<T>.self, from: data) {
            return envelope.output
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
}
