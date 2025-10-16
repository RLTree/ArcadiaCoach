import Foundation

struct AssessmentRubricEvaluation: Codable, Hashable, Identifiable {
    var criterion: String
    var met: Bool
    var notes: String?
    var score: Double?

    var id: String { "\(criterion)|\(notes ?? "")|\(score?.description ?? "nil")" }
}

struct AssessmentTaskGrade: Codable, Hashable, Identifiable {
    enum ConfidenceLevel: String, Codable, Hashable {
        case low
        case medium
        case high
    }

    var taskId: String
    var categoryKey: String
    var taskType: OnboardingAssessmentTask.TaskType
    var score: Double
    var confidence: ConfidenceLevel
    var feedback: String
    var strengths: [String]
    var improvements: [String]
    var rubric: [AssessmentRubricEvaluation]

    var id: String { taskId }
}

struct AssessmentCategoryOutcome: Codable, Hashable, Identifiable {
    var categoryKey: String
    var averageScore: Double
    var initialRating: Int
    var startingRating: Int
    var ratingDelta: Int
    var rationale: String?

    var id: String { categoryKey }

    private enum CodingKeys: String, CodingKey {
        case categoryKey
        case averageScore
        case initialRating
        case startingRating
        case ratingDelta
        case rationale
    }

    init(
        categoryKey: String,
        averageScore: Double,
        initialRating: Int,
        startingRating: Int,
        ratingDelta: Int,
        rationale: String?
    ) {
        self.categoryKey = categoryKey
        self.averageScore = averageScore
        self.initialRating = initialRating
        self.startingRating = startingRating
        self.ratingDelta = ratingDelta
        self.rationale = rationale
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        categoryKey = try container.decode(String.self, forKey: .categoryKey)
        averageScore = try container.decodeIfPresent(Double.self, forKey: .averageScore) ?? 0.5
        initialRating = try container.decodeIfPresent(Int.self, forKey: .initialRating) ?? 1100
        startingRating = try container.decodeIfPresent(Int.self, forKey: .startingRating) ?? initialRating
        ratingDelta = try container.decodeIfPresent(Int.self, forKey: .ratingDelta) ?? (initialRating - startingRating)
        rationale = try container.decodeIfPresent(String.self, forKey: .rationale)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(categoryKey, forKey: .categoryKey)
        try container.encode(averageScore, forKey: .averageScore)
        try container.encode(initialRating, forKey: .initialRating)
        try container.encode(startingRating, forKey: .startingRating)
        try container.encode(ratingDelta, forKey: .ratingDelta)
        try container.encodeIfPresent(rationale, forKey: .rationale)
    }
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
    var curriculumSchedule: CurriculumSchedule?
    var milestoneCompletions: [MilestoneCompletion] = []
    var onboardingAssessment: OnboardingAssessment?
    var onboardingAssessmentResult: AssessmentGradingResult?
    var assessmentSubmissions: [AssessmentSubmissionRecord] = []
    var timezone: String?
    var goalInference: GoalInferenceModel?
    var foundationTracks: [FoundationTrackModel] = []
}

struct LearnerTelemetryResponse: Codable {
    var events: [LearnerTelemetryEvent]
}

struct LearnerTelemetryEvent: Codable, Hashable, Identifiable {
    var eventId: String
    var eventType: String
    var createdAt: Date
    var actor: String?
    var payload: [String: String]

    var id: String { eventId }

    private enum CodingKeys: String, CodingKey {
        case eventId
        case eventType
        case createdAt
        case actor
        case payload
    }

    init(eventId: String, eventType: String, createdAt: Date, actor: String?, payload: [String: String]) {
        self.eventId = eventId
        self.eventType = eventType
        self.createdAt = createdAt
        self.actor = actor
        self.payload = payload
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        eventId = try container.decode(String.self, forKey: .eventId)
        eventType = try container.decode(String.self, forKey: .eventType)
        createdAt = try container.decode(Date.self, forKey: .createdAt)
        actor = try container.decodeIfPresent(String.self, forKey: .actor)
        if let raw = try? container.decode([String: String].self, forKey: .payload) {
            payload = raw
        } else {
            let dynamic = try? container.nestedContainer(keyedBy: DynamicCodingKey.self, forKey: .payload)
            var converted: [String: String] = [:]
            if let dynamic {
                for key in dynamic.allKeys {
                    if let stringValue = try? dynamic.decode(String.self, forKey: key) {
                        converted[key.stringValue] = stringValue
                    } else if let intValue = try? dynamic.decode(Int.self, forKey: key) {
                        converted[key.stringValue] = String(intValue)
                    } else if let doubleValue = try? dynamic.decode(Double.self, forKey: key) {
                        converted[key.stringValue] = String(doubleValue)
                    } else if let boolValue = try? dynamic.decode(Bool.self, forKey: key) {
                        converted[key.stringValue] = boolValue ? "true" : "false"
                    }
                }
            }
            payload = converted
        }
        payload = normalizedPayload(payload)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(eventId, forKey: .eventId)
        try container.encode(eventType, forKey: .eventType)
        try container.encode(createdAt, forKey: .createdAt)
        try container.encodeIfPresent(actor, forKey: .actor)
        try container.encode(payload, forKey: .payload)
    }

    private func normalizedPayload(_ raw: [String: String]) -> [String: String] {
        var output: [String: String] = [:]
        for (key, value) in raw {
            output[key] = value
            let snake = key.snakeCased()
            if output[snake] == nil {
                output[snake] = value
            }
        }
        return output
    }
}

private struct DynamicCodingKey: CodingKey {
    var stringValue: String
    var intValue: Int?

    init?(stringValue: String) {
        self.stringValue = stringValue
        self.intValue = nil
    }

    init?(intValue: Int) {
        self.stringValue = "\(intValue)"
        self.intValue = intValue
    }
}

private extension String {
    func snakeCased() -> String {
        guard !isEmpty else { return self }
        var scalars = [Character]()
        for character in self {
            if character.isUppercase {
                if !scalars.isEmpty {
                    scalars.append(Character("_"))
                }
                if let lower = character.lowercased().first {
                    scalars.append(lower)
                }
            } else {
                scalars.append(character)
            }
        }
        return String(scalars)
    }
}

struct ScheduleWarning: Codable, Hashable, Identifiable {
    var code: String
    var message: String
    var detail: String?
    var generatedAt: Date

    var id: String { "\(code)-\(generatedAt.timeIntervalSince1970)" }
}

struct CategoryPacingAllocation: Codable, Hashable, Identifiable {
    enum Pressure: String, Codable, Hashable {
        case low
        case medium
        case high

        var description: String {
            rawValue.capitalized
        }
    }

    var categoryKey: String
    var plannedMinutes: Int
    var targetShare: Double
    var deferralPressure: Pressure
    var deferralCount: Int
    var maxDeferralDays: Int
    var rationale: String?

    var id: String { categoryKey }

    var targetSharePercent: String {
        "\(Int(round(targetShare * 100)))%"
    }

    var formattedPlannedDuration: String {
        if plannedMinutes >= 60 {
            let hours = Double(plannedMinutes) / 60.0
            return String(format: "%.1f h", hours)
        }
        return "~\(plannedMinutes) min"
    }
}

struct ScheduleRationaleEntry: Codable, Hashable, Identifiable {
    var generatedAt: Date
    var headline: String
    var summary: String
    var relatedCategories: [String]
    var adjustmentNotes: [String]

    var id: String { "\(generatedAt.timeIntervalSince1970)-\(headline)" }
}

struct CurriculumSchedule: Codable, Hashable {
    struct Slice: Codable, Hashable {
        var startDay: Int
        var endDay: Int
        var daySpan: Int
        var totalItems: Int
        var totalDays: Int
        var hasMore: Bool
        var nextStartDay: Int?
    }

    var generatedAt: Date
    var timeHorizonDays: Int
    var timezone: String?
    var anchorDate: Date?
    var cadenceNotes: String?
    var items: [SequencedWorkItem]
    var milestoneCompletions: [MilestoneCompletion] = []
    var isStale: Bool = false
    var warnings: [ScheduleWarning] = []
    var pacingOverview: String?
    var categoryAllocations: [CategoryPacingAllocation] = []
    var rationaleHistory: [ScheduleRationaleEntry] = []
    var sessionsPerWeek: Int = 0
    var projectedWeeklyMinutes: Int = 0
    var longRangeItemCount: Int = 0
    var extendedWeeks: Int = 0
    var longRangeCategoryKeys: [String] = []
    var slice: Slice?

    struct Group: Hashable, Identifiable {
        var offset: Int
        var date: Date?
        var items: [SequencedWorkItem]

        var id: Int { offset }
    }

    var groupedItems: [Group] {
        Dictionary(grouping: items) { $0.recommendedDayOffset }
            .map { entry -> Group in
                let sorted = entry.value.sorted { $0.recommendedMinutes > $1.recommendedMinutes }
                return Group(offset: entry.key, date: sorted.first?.scheduledFor, items: sorted)
            }
            .sorted { $0.offset < $1.offset }
    }

    var latestRationale: ScheduleRationaleEntry? {
        rationaleHistory.sorted { $0.generatedAt < $1.generatedAt }.last
    }

    var longRangeSummary: String? {
        guard sessionsPerWeek > 0 || projectedWeeklyMinutes > 0 || longRangeItemCount > 0 else {
            return nil
        }
        let weeks = extendedWeeks > 0 ? extendedWeeks : max(1, Int((Double(timeHorizonDays) / 7.0).rounded(.up)))
        var segments: [String] = []
        if sessionsPerWeek > 0 {
            let weeklyMinutes = projectedWeeklyMinutes > 0 ? " (~\(projectedWeeklyMinutes) min/week)" : ""
            segments.append("\(weeks) week horizon at \(sessionsPerWeek) sessions/week\(weeklyMinutes)")
        } else {
            segments.append("\(weeks) week horizon")
            if projectedWeeklyMinutes > 0 {
                segments.append("~\(projectedWeeklyMinutes) min/week")
            }
        }
        if longRangeItemCount > 0 {
            segments.append("\(longRangeItemCount) spaced refreshers")
        }
        if !longRangeCategoryKeys.isEmpty {
            segments.append("focus on \(longRangeCategoryKeys.joined(separator: ", "))")
        }
        return segments.joined(separator: " · ")
    }
}

struct MilestonePrerequisite: Codable, Hashable, Identifiable {
    var itemId: String
    var title: String
    var kind: String
    var status: String
    var required: Bool
    var recommendedDayOffset: Int?

    var id: String { itemId }
}

struct MilestoneProject: Codable, Hashable {
    var projectId: String
    var title: String
    var goalAlignment: String
    var summary: String?
    var deliverables: [String]
    var evidenceChecklist: [String]
    var recommendedTools: [String]
    var evaluationFocus: [String]
    var evaluationSteps: [String]
}

struct MilestoneBrief: Codable, Hashable {
    var headline: String
    var summary: String?
    var objectives: [String]
    var deliverables: [String]
    var successCriteria: [String]
    var externalWork: [String]
    var capturePrompts: [String]
    var prerequisites: [MilestonePrerequisite]
    var eloFocus: [String]
    var resources: [String]
    var kickoffSteps: [String] = []
    var coachingPrompts: [String] = []
    var project: MilestoneProject?
}

struct MilestoneProgress: Codable, Hashable {
    var recordedAt: Date
    var notes: String?
    var externalLinks: [String]
    var attachmentIds: [String]
    var projectStatus: String = "not_started"
    var nextSteps: [String] = []
}

struct MilestoneGuidance: Codable, Hashable {
    var state: String
    var summary: String
    var badges: [String]
    var nextActions: [String]
    var warnings: [String]
    var lastUpdateAt: Date?
}

struct MilestoneCompletion: Codable, Hashable, Identifiable {
    var completionId: String
    var itemId: String
    var categoryKey: String
    var title: String
    var headline: String?
    var summary: String?
    var notes: String?
    var externalLinks: [String]
    var attachmentIds: [String]
    var eloFocus: [String]
    var recommendedDayOffset: Int?
    var sessionId: String?
    var recordedAt: Date
    var projectStatus: String = "completed"
    var evaluationOutcome: String?
    var evaluationNotes: String?
    var eloDelta: Int = 12

    var id: String { completionId }
}

struct SequencedWorkItem: Codable, Hashable, Identifiable {
    enum Kind: String, Codable, Hashable {
        case lesson
        case quiz
        case milestone

        var label: String {
            switch self {
            case .lesson:
                return "Lesson"
            case .quiz:
                return "Quiz"
            case .milestone:
                return "Milestone"
            }
        }

        var systemImage: String {
            switch self {
            case .lesson:
                return "book.closed"
            case .quiz:
                return "checklist"
            case .milestone:
                return "flag.checkered"
            }
        }
    }

    enum EffortLevel: String, Codable, Hashable {
        case light
        case moderate
        case focus

        var label: String {
            switch self {
            case .light:
                return "Light"
            case .moderate:
                return "Moderate"
            case .focus:
                return "Focus"
            }
        }
    }

    enum LaunchStatus: String, Codable, Hashable {
        case pending
        case inProgress = "in_progress"
        case completed

        var label: String {
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

    var itemId: String
    var kind: Kind
    var categoryKey: String
    var title: String
    var summary: String?
    var objectives: [String]
    var prerequisites: [String]
    var recommendedMinutes: Int
    var recommendedDayOffset: Int
    var effortLevel: EffortLevel
    var focusReason: String?
    var expectedOutcome: String?
    var userAdjusted: Bool = false
    var scheduledFor: Date?
    var launchStatus: LaunchStatus = .pending
    var lastLaunchedAt: Date?
    var lastCompletedAt: Date?
    var activeSessionId: String?
    var launchLockedReason: String?
    var milestoneBrief: MilestoneBrief?
    var milestoneProgress: MilestoneProgress?
    var milestoneProject: MilestoneProject?
    var milestoneGuidance: MilestoneGuidance?

    var id: String { itemId }

    var formattedDuration: String {
        guard recommendedMinutes > 0 else { return "Flexible" }
        return "~\(recommendedMinutes) min"
    }
}
