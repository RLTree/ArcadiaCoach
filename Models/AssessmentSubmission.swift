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

    private enum CodingKeys: String, CodingKey {
        case taskId
        case response
        case categoryKey
        case taskType
        case wordCount
    }

    init(
        taskId: String,
        response: String,
        categoryKey: String,
        taskType: OnboardingAssessmentTask.TaskType,
        wordCount: Int
    ) {
        self.taskId = taskId
        self.response = response
        self.categoryKey = categoryKey
        self.taskType = taskType
        self.wordCount = wordCount
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        taskId = try container.decode(String.self, forKey: .taskId)
        response = try container.decodeIfPresent(String.self, forKey: .response) ?? ""
        categoryKey = try container.decodeIfPresent(String.self, forKey: .categoryKey) ?? ""
        if let decodedType = try container.decodeIfPresent(OnboardingAssessmentTask.TaskType.self, forKey: .taskType) {
            taskType = decodedType
        } else {
            taskType = .conceptCheck
        }
        wordCount = try container.decodeIfPresent(Int.self, forKey: .wordCount) ?? response.split(whereSeparator: \.isWhitespace).count
    }
}

struct AssessmentSubmissionRecord: Codable, Identifiable, Hashable {
    var submissionId: String
    var username: String
    var submittedAt: Date
    var responses: [AssessmentTaskSubmission]
    var metadata: [String:String]
    var grading: AssessmentGradingResult?

    var id: String { submissionId }

    var answeredCount: Int { responses.count }

    var gradedAt: Date? {
        grading?.evaluatedAt
    }

    var averageScore: Double? {
        guard let grading else { return nil }
        let scores = grading.taskResults.map { $0.score }
        guard !scores.isEmpty else { return nil }
        let total = scores.reduce(0, +)
        return total / Double(scores.count)
    }

    var averageScoreLabel: String? {
        guard let value = averageScore else { return nil }
        return "\(Int((value * 100).rounded()))%"
    }

    var statusLabel: String {
        grading == nil ? "Pending" : "Graded"
    }

    private enum CodingKeys: String, CodingKey {
        case submissionId
        case username
        case submittedAt
        case responses
        case metadata
        case grading
    }

    init(
        submissionId: String,
        username: String,
        submittedAt: Date,
        responses: [AssessmentTaskSubmission],
        metadata: [String:String],
        grading: AssessmentGradingResult?
    ) {
        self.submissionId = submissionId
        self.username = username
        self.submittedAt = submittedAt
        self.responses = responses
        self.metadata = metadata
        self.grading = grading
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        submissionId = try container.decode(String.self, forKey: .submissionId)
        username = try container.decodeIfPresent(String.self, forKey: .username) ?? ""
        submittedAt = try container.decode(Date.self, forKey: .submittedAt)
        responses = try container.decodeIfPresent([AssessmentTaskSubmission].self, forKey: .responses) ?? []
        metadata = try container.decodeIfPresent([String:String].self, forKey: .metadata) ?? [:]
        grading = try container.decodeIfPresent(AssessmentGradingResult.self, forKey: .grading)
    }
}
