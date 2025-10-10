import Foundation

struct ChatKitSessionResponse: Decodable {
    let session_id: String
    let client_secret: String
    let expires_at: Date?
}

enum ChatKitTokenService {
    static func fetch(baseURL: URL, deviceId: String) async throws -> ChatKitSessionResponse {
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) ?? URLComponents()
        if components.path.isEmpty || components.path == "/" {
            components.path = "/api/chatkit/session"
        }
        guard let targetURL = components.url else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: targetURL)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = [
            "device_id": deviceId
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let bodyText = String(data: data, encoding: .utf8) ?? ""
            throw NSError(domain: "ChatKitTokenService", code: 1, userInfo: [NSLocalizedDescriptionKey: "Backend error", "body": bodyText])
        }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(ChatKitSessionResponse.self, from: data)
    }
}
