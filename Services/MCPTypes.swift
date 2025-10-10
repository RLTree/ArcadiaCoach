import Foundation

struct MCPQuizSummary: Decodable {
    let display: String?
    let widgets: [Widget]
    let citations: [String]?
}
