import Foundation

// Minimal shapes from your Agent’s End nodes
struct EndLearn: Codable {
    let intent: String
    let display: String
    let widgets: [Widget]
    let citations: [String]?
}
struct EndQuiz: Codable {
    let intent: String
    let display: String?
    let widgets: [Widget]
    let elo: [String:Int]
    let last_quiz: LastQuiz?
    struct LastQuiz: Codable { let topic: String?; let score: Double? }
}
struct EndMilestone: Codable {
    let intent: String
    let display: String
    let widgets: [Widget]
}
