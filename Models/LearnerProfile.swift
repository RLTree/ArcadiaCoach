import Foundation

struct LearnerMemoryRecord: Codable, Identifiable, Equatable {
    var noteId: String
    var note: String
    var tags: [String]
    var createdAt: Date

    var id: String { noteId }
}

struct LearnerProfileModel: Codable, Identifiable, Equatable {
    var username: String
    var goal: String
    var useCase: String
    var strengths: String
    var timezone: String?
    var knowledgeTags: [String]
    var recentSessions: [String]
    var memoryRecords: [LearnerMemoryRecord]
    var memoryIndexId: String
    var eloSnapshot: [String:Int]
    var curriculumPlan: OnboardingCurriculumPlan?
    var curriculumSchedule: CurriculumSchedule?
    var onboardingAssessment: OnboardingAssessment?
    var assessmentSubmissions: [AssessmentSubmissionRecord] = []
    var lastUpdated: Date

    var id: String { username }

    static let empty = LearnerProfileModel(
        username: "",
        goal: "",
        useCase: "",
        strengths: "",
        timezone: nil,
        knowledgeTags: [],
        recentSessions: [],
        memoryRecords: [],
        memoryIndexId: "",
        eloSnapshot: [:],
        curriculumPlan: nil,
        curriculumSchedule: nil,
        onboardingAssessment: nil,
        assessmentSubmissions: [],
        lastUpdated: .distantPast
    )
}
