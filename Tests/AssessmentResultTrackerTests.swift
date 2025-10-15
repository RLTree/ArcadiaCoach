import XCTest
@testable import ArcadiaCoach

final class AssessmentResultTrackerTests: XCTestCase {

    private func makeGradedSubmission(
        id: String = "submission-1",
        evaluatedAt: Date = Date()
    ) -> AssessmentSubmissionRecord {
        let grading = AssessmentGradingResult(
            submissionId: id,
            evaluatedAt: evaluatedAt,
            overallFeedback: "Feedback",
            strengths: [],
            focusAreas: [],
            taskResults: [],
            categoryOutcomes: []
        )

        return AssessmentSubmissionRecord(
            submissionId: id,
            username: "tester",
            submittedAt: evaluatedAt,
            responses: [],
            metadata: [:],
            attachments: [],
            grading: grading
        )
    }

    func testApplyMarksUnseenWhenLatestNotSeen() {
        var tracker = AssessmentResultTracker()
        let submission = makeGradedSubmission()

        let latest = tracker.apply(history: [submission])

        XCTAssertTrue(tracker.hasUnseenResults)
        XCTAssertEqual(latest?.submissionId, submission.submissionId)
    }

    func testUpdateLastSeenClearsUnseenWhenSubmissionMatches() {
        var tracker = AssessmentResultTracker()
        let submission = makeGradedSubmission()
        _ = tracker.apply(history: [submission])
        XCTAssertTrue(tracker.hasUnseenResults)

        let latest = tracker.updateLastSeen(submission.submissionId, history: [submission])

        XCTAssertNil(latest)
        XCTAssertFalse(tracker.hasUnseenResults)
    }

    func testMarkResultsSeenReturnsSubmissionId() {
        var tracker = AssessmentResultTracker()
        let submission = makeGradedSubmission()
        _ = tracker.apply(history: [submission])
        XCTAssertTrue(tracker.hasUnseenResults)

        let seenId = tracker.markResultsSeen(history: [submission])

        XCTAssertEqual(seenId, submission.submissionId)
        XCTAssertFalse(tracker.hasUnseenResults)
        XCTAssertEqual(tracker.lastSeenSubmissionId, submission.submissionId)
    }

    func testResetClearsState() {
        var tracker = AssessmentResultTracker()
        _ = tracker.apply(history: [makeGradedSubmission()])
        XCTAssertTrue(tracker.hasUnseenResults)

        tracker.reset()

        XCTAssertFalse(tracker.hasUnseenResults)
        XCTAssertNil(tracker.lastSeenSubmissionId)
    }
}
