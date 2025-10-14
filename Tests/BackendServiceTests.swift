import XCTest
@testable import ArcadiaCoach

final class BackendServiceTests: XCTestCase {
    func testEndpointBuildsAPIPath() {
        let url = BackendService.endpoint(baseURL: "https://example.com", path: "api/session/lesson")
        XCTAssertEqual(url?.absoluteString, "https://example.com/api/session/lesson")
    }

    func testEndpointHandlesTrailingSlash() {
        let url = BackendService.endpoint(baseURL: "https://example.com/", path: "api/session/chat")
        XCTAssertEqual(url?.absoluteString, "https://example.com/api/session/chat")
    }

    func testLoadLessonThrowsWhenBackendMissing() async {
        do {
            _ = try await BackendService.loadLesson(baseURL: " ", sessionId: nil, topic: "swift")
            XCTFail("Expected missingBackend error")
        } catch let error as BackendServiceError {
            XCTAssertEqual(error, .missingBackend)
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    func testCurriculumScheduleDecodesPacingMetadata() throws {
        let json = """
        {
            "generated_at": "2025-10-14T12:00:00Z",
            "time_horizon_days": 42,
            "timezone": "America/Los_Angeles",
            "anchor_date": "2025-10-14T00:00:00Z",
            "cadence_notes": "Scheduled 9 items across 9 sessions (~520 minutes total) spanning ~42 days.",
            "items": [],
            "is_stale": false,
            "warnings": [],
            "pacing_overview": "Pacing 3 sessions/week over 42 days (~520 minutes planned). Focus mix: Backend Systems 60%; Frontend Flow 40%.",
            "category_allocations": [
                {
                    "category_key": "backend",
                    "planned_minutes": 320,
                    "target_share": 0.6,
                    "deferral_pressure": "high",
                    "deferral_count": 3,
                    "max_deferral_days": 21,
                    "rationale": "Weight 0.60; ELO 1040; Assessment 55%; Δ-25; High deferrals (3); Max defer 21d"
                },
                {
                    "category_key": "frontend",
                    "planned_minutes": 200,
                    "target_share": 0.4,
                    "deferral_pressure": "low",
                    "deferral_count": 0,
                    "max_deferral_days": 0,
                    "rationale": "Weight 0.40; ELO 1235; Assessment 82%"
                }
            ],
            "rationale_history": [
                {
                    "generated_at": "2025-10-14T12:00:00Z",
                    "headline": "Roadmap extended to 42 days with 3 sessions/week cadence.",
                    "summary": "Prioritising Backend Systems while pacing at 3 sessions per week. Goal: Ship a resilient backend for the Arcadia agent.",
                    "related_categories": ["backend", "frontend"],
                    "adjustment_notes": ["Adjusted pacing for Backend Systems after 3 deferrals. Max defer 21 days.", "Maintained learner-selected offsets from recent deferrals."]
                }
            ]
        }
        """
        let data = Data(json.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        let schedule = try decoder.decode(CurriculumSchedule.self, from: data)

        XCTAssertEqual(schedule.timezone, "America/Los_Angeles")
        XCTAssertEqual(schedule.pacingOverview, "Pacing 3 sessions/week over 42 days (~520 minutes planned). Focus mix: Backend Systems 60%; Frontend Flow 40%.")
        XCTAssertEqual(schedule.categoryAllocations.count, 2)
        XCTAssertEqual(schedule.categoryAllocations.first?.deferralPressure, .high)
        XCTAssertEqual(schedule.categoryAllocations.first?.deferralCount, 3)
        XCTAssertEqual(schedule.rationaleHistory.first?.headline, "Roadmap extended to 42 days with 3 sessions/week cadence.")
    }
}
