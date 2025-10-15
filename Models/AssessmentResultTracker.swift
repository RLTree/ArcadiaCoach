import Foundation

struct AssessmentResultTracker {
    private(set) var hasUnseenResults: Bool = false
    private(set) var lastSeenSubmissionId: String?

    mutating func apply(history: [AssessmentSubmissionRecord]) -> AssessmentSubmissionRecord? {
        guard let latest = history.first(where: { $0.grading != nil }) else {
            hasUnseenResults = false
            return nil
        }
        if latest.submissionId == lastSeenSubmissionId {
            hasUnseenResults = false
            return nil
        }
        hasUnseenResults = true
        return latest
    }

    mutating func updateLastSeen(_ id: String?, history: [AssessmentSubmissionRecord]) -> AssessmentSubmissionRecord? {
        if let id, !id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            lastSeenSubmissionId = id
        } else {
            lastSeenSubmissionId = nil
        }
        return apply(history: history)
    }

    mutating func markResultsSeen(history: [AssessmentSubmissionRecord]) -> String? {
        guard let latest = history.first(where: { $0.grading != nil }) else {
            lastSeenSubmissionId = nil
            hasUnseenResults = false
            return nil
        }
        lastSeenSubmissionId = latest.submissionId
        hasUnseenResults = false
        return latest.submissionId
    }

    mutating func reset() {
        hasUnseenResults = false
        lastSeenSubmissionId = nil
    }
}
