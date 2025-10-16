import XCTest
@testable import ArcadiaCoach

final class BackendServiceTests: XCTestCase {
    private let sampleScheduleJSON = """
    {
        "generated_at": "2025-10-14T12:00:00Z",
        "time_horizon_days": 126,
        "timezone": "America/Los_Angeles",
        "anchor_date": "2025-10-14T00:00:00Z",
        "cadence_notes": "Scheduled 18 items across 18 sessions (~780 minutes total) spanning ~126 days.",
        "items": [],
        "milestone_completions": [
            {
                "completion_id": "complete-backend",
                "item_id": "milestone-backend",
                "category_key": "backend",
                "title": "Milestone: Apply Backend Systems",
                "headline": "Milestone: Apply Backend Systems",
                "summary": "Wrapped a resilient service increment.",
                "notes": "Captured observability rollout and next stretch goals.",
                "external_links": ["https://example.com/demo"],
                "attachment_ids": ["attach-1"],
                "elo_focus": ["Backend Systems"],
                "recommended_day_offset": 14,
                "session_id": "session-789",
                "recorded_at": "2025-10-13T18:00:00Z",
                "project_status": "completed",
                "evaluation_outcome": "passed",
                "evaluation_notes": "Provided observability walkthrough.",
                "elo_delta": 24
            }
        ],
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
        "long_range_category_keys": ["backend", "frontend"],
        "slice": {
            "start_day": 0,
            "end_day": 6,
            "day_span": 7,
            "total_items": 18,
            "total_days": 126,
            "has_more": true,
            "next_start_day": 7
        }
    }
    """
    private let sampleLaunchJSON = """
    {
        "schedule": {
            "generated_at": "2025-10-15T12:00:00Z",
            "time_horizon_days": 7,
            "timezone": "UTC",
            "items": [
                {
                    "item_id": "lesson-intro",
                    "kind": "lesson",
                    "category_key": "backend",
                    "title": "Intro Lesson",
                    "summary": "Kick-off workshop.",
                    "objectives": [],
                    "prerequisites": [],
                    "recommended_minutes": 45,
                    "recommended_day_offset": 0,
                    "effort_level": "moderate",
                    "focus_reason": null,
                    "expected_outcome": null,
                    "user_adjusted": false,
                    "scheduled_for": "2025-10-15T00:00:00Z",
                    "launch_status": "in_progress",
                    "last_launched_at": "2025-10-15T12:05:00Z",
                    "last_completed_at": null,
                    "active_session_id": "session-123",
                    "launch_locked_reason": null
                }
            ],
            "milestone_completions": [],
            "category_allocations": [],
            "rationale_history": [],
            "is_stale": false,
            "warnings": [],
            "sessions_per_week": 3,
            "projected_weekly_minutes": 120,
            "long_range_item_count": 2,
            "extended_weeks": 4,
            "long_range_category_keys": []
        },
        "item": {
            "item_id": "lesson-intro",
            "kind": "lesson",
            "category_key": "backend",
            "title": "Intro Lesson",
            "summary": "Kick-off workshop.",
            "objectives": [],
            "prerequisites": [],
            "recommended_minutes": 45,
            "recommended_day_offset": 0,
            "effort_level": "moderate",
            "focus_reason": null,
            "expected_outcome": null,
            "user_adjusted": false,
            "scheduled_for": "2025-10-15T00:00:00Z",
            "launch_status": "in_progress",
            "last_launched_at": "2025-10-15T12:05:00Z",
            "last_completed_at": null,
            "active_session_id": "session-123",
            "launch_locked_reason": null
        },
        "content": {
            "kind": "lesson",
            "session_id": "session-123",
            "lesson": {
                "intent": "learn",
                "display": "Intro Lesson",
                "widgets": [],
                "citations": []
            },
            "quiz": null,
            "milestone": null
        }
    }
    """
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
        let data = Data(sampleScheduleJSON.utf8)
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
        XCTAssertEqual(schedule.milestoneCompletions.count, 1)
        XCTAssertEqual(schedule.milestoneCompletions.first?.title, "Milestone: Apply Backend Systems")
        XCTAssertEqual(schedule.milestoneCompletions.first?.projectStatus, "completed")
        XCTAssertEqual(schedule.milestoneCompletions.first?.evaluationOutcome, "passed")
        XCTAssertEqual(schedule.milestoneCompletions.first?.eloDelta, 24)
        XCTAssertEqual(schedule.slice?.startDay, 0)
        XCTAssertEqual(schedule.slice?.daySpan, 7)
        XCTAssertEqual(schedule.slice?.hasMore, true)
        XCTAssertEqual(schedule.slice?.nextStartDay, 7)
    }

    func testScheduleLaunchResponseDecodes() throws {
        let data = Data(sampleLaunchJSON.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        let response = try decoder.decode(BackendService.ScheduleLaunchResponse.self, from: data)

        XCTAssertEqual(response.item.launchStatus, .inProgress)
        XCTAssertEqual(response.content.kind, "lesson")
        XCTAssertEqual(response.content.sessionId, "session-123")
        XCTAssertNotNil(response.content.lesson)
        XCTAssertEqual(response.schedule.items.first?.activeSessionId, "session-123")
    }

    func testSequencedWorkItemDecodesMilestoneBriefAndProgress() throws {
        let json = """
        {
            "item_id": "milestone-backend",
            "kind": "milestone",
            "category_key": "backend",
            "title": "Milestone: Apply Backend Systems",
            "summary": "Translate the lesson into a project increment.",
            "objectives": ["Integrate lesson outcomes", "Document decisions"],
            "prerequisites": ["lesson-backend", "quiz-backend"],
            "recommended_minutes": 120,
            "recommended_day_offset": 6,
            "effort_level": "focus",
            "user_adjusted": false,
            "scheduled_for": "2025-10-21T00:00:00Z",
            "launch_status": "pending",
            "milestone_brief": {
                "headline": "Ship Backend Foundations",
                "summary": "Apply backend concepts to a tangible artefact.",
                "objectives": ["Demonstrate backend fluency"],
                "deliverables": ["Repository branch", "Reflection notes"],
                "success_criteria": ["Share working prototype"],
                "external_work": ["Build feature outside Arcadia"],
                "capture_prompts": ["What did you build?"],
                "prerequisites": [
                    {"item_id": "lesson-backend", "title": "Lesson • Backend Foundations", "kind": "lesson", "status": "completed", "required": true},
                    {"item_id": "quiz-backend", "title": "Skill Check • Backend Foundations", "kind": "quiz", "status": "in_progress", "required": true}
                ],
                "elo_focus": ["Backend Systems"],
                "resources": ["Backend playbook"],
                "kickoff_steps": ["Block 90 minutes of focus time."],
                "coaching_prompts": ["Share blockers with Arcadia Coach early."],
                "rationale": "Agent emphasised backend scaling backlog.",
                "authored_at": "2025-10-20T12:00:00Z",
                "authored_by_model": "gpt-5",
                "reasoning_effort": "medium",
                "source": "agent",
                "warnings": ["Remember to capture metrics."],
                "project": {
                    "project_id": "backend-service-slice",
                    "title": "Ship a Production-Ready Service Slice",
                    "goal_alignment": "Show how this service slice advances your target outcome.",
                    "summary": "Develop a service endpoint or workflow that demonstrates reliability.",
                    "deliverables": ["Service repository", "API contract"],
                    "evidence_checklist": ["CI run", "Observability snapshot"],
                    "recommended_tools": ["FastAPI", "pytest"],
                    "evaluation_focus": ["Code quality", "Operational readiness"],
                    "evaluation_steps": ["Run load tests", "Document release plan"]
                }
            },
            "milestone_progress": {
                "recorded_at": "2025-10-21T18:05:00Z",
                "notes": "Shipped API refactor.",
                "external_links": ["https://example.com/demo"],
                "attachment_ids": ["attach-1"],
                "project_status": "building",
                "next_steps": ["Capture CI results"]
            },
            "milestone_project": {
                "project_id": "backend-service-slice",
                "title": "Ship a Production-Ready Service Slice",
                "goal_alignment": "Show how this service slice advances your target outcome.",
                "summary": "Develop a service endpoint or workflow that demonstrates reliability.",
                "deliverables": ["Service repository", "API contract"],
                "evidence_checklist": ["CI run", "Observability snapshot"],
                "recommended_tools": ["FastAPI", "pytest"],
                "evaluation_focus": ["Code quality", "Operational readiness"],
                "evaluation_steps": ["Run load tests", "Document release plan"]
            },
            "milestone_guidance": {
                "state": "in_progress",
                "summary": "Milestone in progress. Capture blockers and progress snapshots.",
                "badges": ["In progress"],
                "next_actions": ["Log quick notes or links to capture progress."],
                "warnings": [],
                "last_update_at": "2025-10-21T18:05:00Z"
            }
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        let item = try decoder.decode(SequencedWorkItem.self, from: Data(json.utf8))

        XCTAssertEqual(item.kind, .milestone)
        XCTAssertEqual(item.milestoneBrief?.headline, "Ship Backend Foundations")
        XCTAssertEqual(item.milestoneBrief?.prerequisites.count, 2)
        XCTAssertEqual(item.milestoneBrief?.eloFocus, ["Backend Systems"])
        XCTAssertEqual(item.milestoneBrief?.kickoffSteps.first, "Block 90 minutes of focus time.")
        XCTAssertEqual(item.milestoneBrief?.project?.projectId, "backend-service-slice")
        XCTAssertEqual(item.milestoneBrief?.source, "agent")
        XCTAssertEqual(item.milestoneBrief?.authoredByModel, "gpt-5")
        XCTAssertEqual(item.milestoneBrief?.reasoningEffort, "medium")
        XCTAssertEqual(item.milestoneBrief?.warnings, ["Remember to capture metrics."])
        XCTAssertEqual(item.milestoneProgress?.externalLinks, ["https://example.com/demo"])
        XCTAssertEqual(item.milestoneProgress?.attachmentIds, ["attach-1"])
        XCTAssertEqual(item.milestoneProgress?.projectStatus, "building")
        XCTAssertEqual(item.milestoneProgress?.nextSteps, ["Capture CI results"])
        XCTAssertEqual(item.milestoneProject?.title, "Ship a Production-Ready Service Slice")
        XCTAssertEqual(item.milestoneGuidance?.state, "in_progress")
        XCTAssertEqual(item.milestoneGuidance?.nextActions.first, "Log quick notes or links to capture progress.")
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
            "milestone_completions": [
                {
                    "completion_id": "complete-backend",
                    "item_id": "milestone-backend",
                    "category_key": "backend",
                    "title": "Backend Systems Milestone",
                    "headline": "Backend Systems Milestone",
                    "summary": "Delivered backend reliability improvements.",
                    "notes": "Documented tracing rollout.",
                    "external_links": ["https://example.com/demo"],
                    "attachment_ids": ["attach-2"],
                    "elo_focus": ["Backend Systems"],
                    "recommended_day_offset": 7,
                    "session_id": "session-123",
                    "recorded_at": "2025-10-14T12:00:00Z",
                    "project_status": "ready_for_review",
                    "evaluation_outcome": "needs_revision",
                    "evaluation_notes": "Add load test summary.",
                    "elo_delta": 10
                }
            ],
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
        XCTAssertEqual(snapshot.milestoneCompletions.first?.notes, "Documented tracing rollout.")
        XCTAssertEqual(snapshot.milestoneCompletions.first?.projectStatus, "ready_for_review")
        XCTAssertEqual(snapshot.milestoneCompletions.first?.evaluationOutcome, "needs_revision")
        XCTAssertEqual(snapshot.milestoneCompletions.first?.evaluationNotes, "Add load test summary.")
        XCTAssertEqual(snapshot.milestoneCompletions.first?.eloDelta, 10)
    }

    func testTelemetryResponseDecodes() throws {
        let json = """
        {
            "events": [
                {
                    "event_id": "evt-1",
                    "event_type": "schedule_launch_completed",
                    "created_at": "2025-10-16T12:00:00Z",
                    "actor": "telemetry",
                    "payload": {
                        "item_id": "milestone-backend",
                        "kind": "milestone",
                        "progress_recorded": "false"
                    }
                }
            ]
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        let response = try decoder.decode(LearnerTelemetryResponse.self, from: Data(json.utf8))

        XCTAssertEqual(response.events.count, 1)
        XCTAssertEqual(response.events.first?.eventType, "schedule_launch_completed")
        XCTAssertEqual(response.events.first?.payload["progress_recorded"], "false")
    }

    @MainActor
    func testScheduleSliceCacheStoresByStartDay() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        var schedule = try decoder.decode(CurriculumSchedule.self, from: Data(sampleScheduleJSON.utf8))
        schedule.timeHorizonDays = 21
        schedule.items = [
            SequencedWorkItem(
                itemId: "lesson-1",
                kind: .lesson,
                categoryKey: "backend",
                title: "Backend Foundations",
                summary: nil,
                objectives: [],
                prerequisites: [],
                recommendedMinutes: 60,
                recommendedDayOffset: 7,
                effortLevel: .moderate,
                focusReason: nil,
                expectedOutcome: nil,
                userAdjusted: false,
                scheduledFor: Date()
            )
        ]
        schedule.slice = CurriculumSchedule.Slice(
            startDay: 7,
            endDay: 13,
            daySpan: 7,
            totalItems: 5,
            totalDays: 21,
            hasMore: true,
            nextStartDay: 14
        )

        let username = "cache-user"
        ScheduleSliceCache.shared.clear(username: username)

        ScheduleSliceCache.shared.store(schedule: schedule, username: username)
        let cachedSlice = ScheduleSliceCache.shared.load(username: username, startDay: schedule.slice?.startDay)
        XCTAssertNotNil(cachedSlice)
        XCTAssertEqual(cachedSlice?.slice?.startDay, 7)

        schedule.slice = nil
        ScheduleSliceCache.shared.store(schedule: schedule, username: username, startDay: 0)
        let aggregated = ScheduleSliceCache.shared.load(username: username)
        XCTAssertNotNil(aggregated)
        XCTAssertNil(aggregated?.slice)

        ScheduleSliceCache.shared.clear(username: username)
    }
}
