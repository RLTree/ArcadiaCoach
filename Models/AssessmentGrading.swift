import Foundation

struct AssessmentRubricEvaluation: Codable, Hashable, Identifiable {
    var criterion: String
    var met: Bool
    var notes: String?
    var score: Double?

    var id: String { "\(criterion)|\(notes ?? "")|\(score?.description ?? "nil")" }
}

struct AssessmentTaskGrade: Codable, Hashable, Identifiable {
    var taskId: String
    var categoryKey: String
    var taskType: OnboardingAssessmentTask.TaskType
    var score: Double
    var confidence: ConfidenceLevel
    var feedback: String
    var strengths: [String]
    var improvements: [String]
    var rubric: [AssessmentRubricEvaluation]

    enum ConfidenceLevel: String, Codable, Hashable {
        case low
        case medium
        case high
    }

    var id: String { taskId }
}

struct AssessmentCategoryOutcome: Codable, Hashable, Identifiable {
    var categoryKey: String
    var averageScore: Double
    var initialRating: Int
    var rationale: String?

    var id: String { categoryKey }
}

struct AssessmentGradingResult: Codable, Hashable {
    var submissionId: String
    var evaluatedAt: Date
    var overallFeedback: String
    var strengths: [String]
    var focusAreas: [String]
    var taskResults: [AssessmentTaskGrade]
    var categoryOutcomes: [AssessmentCategoryOutcome]

    var isEmpty: Bool {
        taskResults.isEmpty && categoryOutcomes.isEmpty
    }
}
