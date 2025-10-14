import Foundation

struct FoundationModuleReferenceModel: Codable, Hashable {
    var moduleId: String
    var categoryKey: String
    var priority: String
    var suggestedWeeks: Int?
    var notes: String?
}

struct FoundationTrackModel: Codable, Identifiable, Hashable {
    var trackId: String
    var label: String
    var priority: String
    var confidence: String
    var weight: Double
    var technologies: [String]
    var focusAreas: [String]
    var prerequisites: [String]
    var recommendedModules: [FoundationModuleReferenceModel]
    var suggestedWeeks: Int?
    var notes: String?

    var id: String { trackId }
}

struct GoalInferenceModel: Codable, Hashable {
    var generatedAt: Date
    var summary: String?
    var targetOutcomes: [String]
    var tracks: [FoundationTrackModel]
    var missingTemplates: [String]
}
