import Foundation

struct AssessmentTaskSubmission: Codable, Identifiable, Hashable {
    var taskId: String
    var response: String
    var categoryKey: String
    var taskType: OnboardingAssessmentTask.TaskType
    var wordCount: Int

    var id: String { taskId }

    var preview: String {
        let trimmed = response.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count > 120 else { return trimmed }
        let index = trimmed.index(trimmed.startIndex, offsetBy: 120)
        return "\(trimmed[..<index])…"
    }
}

struct AssessmentSubmissionRecord: Codable, Identifiable, Hashable {
    var submissionId: String
    var username: String
    var submittedAt: Date
    var responses: [AssessmentTaskSubmission]
    var metadata: [String:String]

    var id: String { submissionId }

    var answeredCount: Int { responses.count }
}
