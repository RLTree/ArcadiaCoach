import Foundation

struct EloRubricBand: Codable, Hashable {
    var level: String
    var descriptor: String
}

struct EloCategoryDefinition: Codable, Hashable, Identifiable {
    var key: String
    var label: String
    var description: String
    var focusAreas: [String]
    var weight: Double
    var rubric: [EloRubricBand]
    var startingRating: Int

    var id: String { key }
}

struct EloCategoryPlan: Codable, Hashable {
    var generatedAt: Date
    var sourceGoal: String?
    var strategyNotes: String?
    var categories: [EloCategoryDefinition]
}

struct SkillRating: Codable, Hashable {
    var category: String
    var rating: Int
}

struct LearnerProfileSnapshot: Codable {
    var username: String
    var skillRatings: [SkillRating]
    var eloCategoryPlan: EloCategoryPlan?
    var curriculumPlan: OnboardingCurriculumPlan?
    var onboardingAssessment: OnboardingAssessment?
    var onboardingAssessmentResult: AssessmentGradingResult?
}
