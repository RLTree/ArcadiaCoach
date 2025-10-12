import Foundation

struct OnboardingCurriculumModule: Codable, Identifiable, Hashable {
    var moduleId: String
    var categoryKey: String
    var title: String
    var summary: String
    var objectives: [String]
    var activities: [String]
    var deliverables: [String]
    var estimatedMinutes: Int?

    var id: String { moduleId }

    var formattedDuration: String {
        guard let minutes = estimatedMinutes, minutes > 0 else { return "Flexible" }
        return "~\(minutes) min"
    }
}

struct OnboardingCurriculumPlan: Codable, Hashable {
    var generatedAt: Date
    var overview: String
    var successCriteria: [String]
    var modules: [OnboardingCurriculumModule]
}

struct OnboardingAssessmentTask: Codable, Identifiable, Hashable {
    enum TaskType: String, Codable {
        case conceptCheck = "concept_check"
        case code

        var label: String {
            switch self {
            case .conceptCheck:
                return "Concept"
            case .code:
                return "Code"
            }
        }
    }

    var taskId: String
    var categoryKey: String
    var title: String
    var taskType: TaskType
    var prompt: String
    var guidance: String
    var rubric: [String]
    var expectedMinutes: Int
    var starterCode: String?
    var answerKey: String?

    var id: String { taskId }
}

struct OnboardingAssessment: Codable, Hashable {
    enum Status: String, Codable {
        case pending
        case inProgress = "in_progress"
        case completed

        var description: String {
            switch self {
            case .pending:
                return "Not started"
            case .inProgress:
                return "In progress"
            case .completed:
                return "Completed"
            }
        }
    }

    var generatedAt: Date
    var status: Status
    var tasks: [OnboardingAssessmentTask]
}
