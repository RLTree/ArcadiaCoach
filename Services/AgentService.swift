import Foundation

final class AgentService {
    struct ResponseEnvelope<T:Decodable>: Decodable { let output: T }
    private static let base = URL(string: "https://api.openai.com/v1/responses")!

    static func send<T:Decodable>(agentId: String, message: String, sessionId: String? = nil, expecting: T.Type) async throws -> T {
        let apiKey = KeychainHelper.get("OPENAI_API_KEY") ?? ""
        var req = URLRequest(url: base)
        req.httpMethod = "POST"
        req.addValue("application/json", forHTTPHeaderField: "Content-Type")
        req.addValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        var input: [String:Any] = [
            "agent_id": agentId,
            "input": message
        ]
        if let sessionId {
            input["session_id"] = sessionId
        }
        req.httpBody = try JSONSerialization.data(withJSONObject: input)
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? "<no body>"
            throw NSError(domain: "AgentService", code: 1, userInfo: [NSLocalizedDescriptionKey:"Bad status", "body": body])
        }
        // Expect the Agent’s End node JSON in data; decode to T
        return try JSONDecoder().decode(T.self, from: data)
    }
}
