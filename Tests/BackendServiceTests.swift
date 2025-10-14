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
            "time_horizon_days": 126,
            "timezone": "America/Los_Angeles",
            "anchor_date": "2025-10-14T00:00:00Z",
            "cadence_notes": "Scheduled 18 items across 18 sessions (~780 minutes total) spanning ~126 days.",
            "items": [],
            "is_stale": false,
            "warnings": [],
            "pacing_overview": "Pacing 3 sessions/week (~130 minutes/week) over 126 days (~18 weeks, ~780 minutes total). Focus mix: Backend Systems 60%; Frontend Flow 40%.",
            "category_allocations": [
                {
                    "category_key": "backend",
                    "planned_minutes": 480,
                    "target_share": 0.6,
                    "deferral_pressure": "high",
                    "deferral_count": 3,
                    "max_deferral_days": 21,
                    "rationale": "Weight 0.60; ELO 1040; Assessment 55%; Δ-25; High deferrals (3); Max defer 21d"
                },
                {
                    "category_key": "frontend",
                    "planned_minutes": 300,
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
                    "headline": "Roadmap extended to 126 days with 3 sessions/week cadence.",
                    "summary": "Prioritising Backend Systems while pacing at 3 sessions per week. Goal: Ship a resilient backend for the Arcadia agent.",
                    "related_categories": ["backend", "frontend"],
                    "adjustment_notes": ["Adjusted pacing for Backend Systems after 3 deferrals. Max defer 21 days.", "Maintained learner-selected offsets from recent deferrals."]
                }
            ],
            "sessions_per_week": 3,
            "projected_weekly_minutes": 130,
            "long_range_item_count": 6,
            "extended_weeks": 18,
            "long_range_category_keys": ["backend", "frontend"]
        }
        """
        let data = Data(json.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        let schedule = try decoder.decode(CurriculumSchedule.self, from: data)

        XCTAssertEqual(schedule.timezone, "America/Los_Angeles")
        XCTAssertEqual(schedule.pacingOverview, "Pacing 3 sessions/week (~130 minutes/week) over 126 days (~18 weeks, ~780 minutes total). Focus mix: Backend Systems 60%; Frontend Flow 40%.")
        XCTAssertEqual(schedule.categoryAllocations.count, 2)
        XCTAssertEqual(schedule.categoryAllocations.first?.deferralPressure, .high)
        XCTAssertEqual(schedule.categoryAllocations.first?.deferralCount, 3)
        XCTAssertEqual(schedule.rationaleHistory.first?.headline, "Roadmap extended to 126 days with 3 sessions/week cadence.")
        XCTAssertEqual(schedule.sessionsPerWeek, 3)
        XCTAssertEqual(schedule.projectedWeeklyMinutes, 130)
        XCTAssertEqual(schedule.longRangeItemCount, 6)
        XCTAssertEqual(schedule.extendedWeeks, 18)
        XCTAssertEqual(schedule.longRangeCategoryKeys, ["backend", "frontend"])
    }

    func testLearnerProfileSnapshotDecodesGoalInference() throws {
        let json = """
        {
            "username": "coder",
            "skill_ratings": [{"category": "backend", "rating": 1120}],
            "assessment_submissions": [],
            "knowledge_tags": [],
            "recent_sessions": [],
            "memory_records": [],
            "memory_index_id": "vs_demo",
            "goal_inference": {
                "generated_at": "2025-10-14T12:00:00Z",
                "summary": "Prioritise backend foundations and observability.",
                "target_outcomes": ["Launch a resilient service", "Automate runtime observability"],
                "tracks": [
                    {
                        "track_id": "backend",
                        "label": "Backend Foundations",
                        "priority": "now",
                        "confidence": "high",
                        "weight": 1.5,
                        "technologies": ["FastAPI", "AsyncIO"],
                        "focus_areas": ["architecture", "observability"],
                        "prerequisites": ["Python Foundations"],
                        "recommended_modules": [
                            {
                                "module_id": "backend-foundations",
                                "category_key": "backend",
                                "priority": "core",
                                "suggested_weeks": 4,
                                "notes": "Refactor async flows and add tracing."
                            }
                        ],
                        "suggested_weeks": 4,
                        "notes": "Focus on service design patterns and production readiness."
                    }
                ],
                "missing_templates": []
            },
            "foundation_tracks": [
                {
                    "track_id": "backend",
                    "label": "Backend Foundations",
                    "priority": "now",
                    "confidence": "high",
                    "weight": 1.5,
                    "technologies": ["FastAPI"],
                    "focus_areas": ["architecture"],
                    "prerequisites": [],
                    "recommended_modules": [
                        {
                            "module_id": "backend-foundations",
                            "category_key": "backend",
                            "priority": "core"
                        }
                    ],
                    "suggested_weeks": 4,
                    "notes": "Prioritise reinforcement every two weeks."
                }
            ]
        }
        """
        let data = Data(json.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        let snapshot = try decoder.decode(LearnerProfileSnapshot.self, from: data)

        XCTAssertEqual(snapshot.username, "coder")
        XCTAssertEqual(snapshot.goalInference?.tracks.first?.label, "Backend Foundations")
        XCTAssertEqual(snapshot.goalInference?.targetOutcomes.count, 2)
        XCTAssertEqual(snapshot.foundationTracks.first?.priority, "now")
    }
}
