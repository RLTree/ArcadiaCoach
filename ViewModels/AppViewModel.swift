import SwiftUI
import OSLog

struct TelemetryEntry: Identifiable, Codable, Equatable {
    var name: String
    var timestamp: Date
    var metadata: [String: String]

    var id: String { "\(name)::\(timestamp.timeIntervalSince1970)" }
}

@MainActor
final class TelemetryReporter {
    static let shared = TelemetryReporter()

    private let logger = Logger(subsystem: "com.arcadiacoach.app", category: "Telemetry")
    private let maxEntries = 50
    private(set) var recentEntries: [TelemetryEntry] = []

    func record(event name: String, metadata: [String: String] = [:]) {
        let entry = TelemetryEntry(name: name, timestamp: Date(), metadata: metadata)
        recentEntries.append(entry)
        if recentEntries.count > maxEntries {
            recentEntries.removeFirst(recentEntries.count - maxEntries)
        }

        if metadata.isEmpty {
            logger.debug("Telemetry \(name, privacy: .public)")
        } else {
            logger.debug("Telemetry \(name, privacy: .public) -> \(metadata.description, privacy: .public)")
        }
    }
}

@MainActor
final class AppViewModel: ObservableObject {
    @Published var game = GameState()
    @Published var lastEnvelope: WidgetEnvelope?
    @Published var busy: Bool = false
    @Published var error: String?
    @Published var eloPlan: EloCategoryPlan?
    @Published var curriculumPlan: OnboardingCurriculumPlan?
    @Published var curriculumSchedule: CurriculumSchedule?
    @Published var onboardingAssessment: OnboardingAssessment?
    @Published var assessmentResult: AssessmentGradingResult?
    // Phase 8 – Track submission/grading history for dashboard + chat surfaces.
    @Published var assessmentHistory: [AssessmentSubmissionRecord] = [] {
        didSet {
            evaluateAssessmentSeenState()
        }
    }
    @Published var assessmentResponses: [String:String] = [:]
    @Published var pendingAssessmentAttachments: [AssessmentSubmissionRecord.Attachment] = []
    @Published var showingAssessmentFlow: Bool = false
    @Published var focusedSubmission: AssessmentSubmissionRecord?
    @Published var latestLesson: EndLearn?
    @Published var latestQuiz: EndQuiz?
    @Published var latestMilestone: EndMilestone?
    @Published var scheduleRefreshing: Bool = false
    @Published var loadingScheduleSlice: Bool = false
    @Published var adjustingScheduleItemId: String?
    @Published var launchingScheduleItemId: String?
    @Published var completingScheduleItemId: String?
    @Published var learnerTimezone: String?
    @Published var goalInference: GoalInferenceModel?
    @Published var foundationTracks: [FoundationTrackModel] = []
    @Published var hasUnseenAssessmentResults: Bool = false

    private var lastScheduleEventSignature: String?
    private var lastScheduleEventTimestamp: Date?
    private let defaultScheduleSliceSpan = 7
    private var lastBackendBaseURL: String?
    private var lastLearnerUsername: String?
    private var assessmentResultTracker = AssessmentResultTracker()
    private lazy var iso8601Formatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    func applyElo(updated: [String:Int], delta: [String:Int]) {
        game.elo = updated
        alignEloSnapshotWithPlan()
        let gained = GameState.xpGain(from: delta)
        game.xp += gained
        game.level = GameState.levelFromXP(game.xp)
    }

    private func eloDelta(from old: [String:Int], to new: [String:Int]) -> [String:Int] {
        var diff: [String:Int] = [:]
        for (key, value) in new {
            diff[key] = value - (old[key] ?? 1100)
        }
        return diff
    }

    func loadProfile(baseURL: String, username: String) async {
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty else { return }
        guard let trimmedBase = BackendService.trimmed(url: baseURL) else { return }
        lastBackendBaseURL = trimmedBase
        lastLearnerUsername = trimmedUsername
        do {
            let snapshot = try await BackendService.fetchProfile(baseURL: trimmedBase, username: trimmedUsername)
            syncProfile(with: snapshot)
            error = nil
        } catch let serviceError as BackendServiceError {
            if case let .transportFailure(status, _) = serviceError, status == 404 {
                eloPlan = nil
                curriculumPlan = nil
                curriculumSchedule = nil
                onboardingAssessment = nil
                assessmentResult = nil
                assessmentHistory = []
                error = nil
                learnerTimezone = nil
            } else {
                error = serviceError.localizedDescription
            }
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
        }
    }

    func refreshCurriculumSchedule(baseURL: String, username: String) async {
        await requestSchedule(
            baseURL: baseURL,
            username: username,
            refresh: true,
            startDay: 0,
            daySpan: defaultScheduleSliceSpan,
            pageToken: nil
        )
    }

    func loadNextScheduleSlice(baseURL: String, username: String, daySpan: Int? = nil) async {
        guard let nextStart = curriculumSchedule?.slice?.nextStartDay else { return }
        await requestSchedule(
            baseURL: baseURL,
            username: username,
            refresh: false,
            startDay: nil,
            daySpan: daySpan ?? curriculumSchedule?.slice?.daySpan ?? defaultScheduleSliceSpan,
            pageToken: nextStart
        )
    }

    func launchScheduleItem(
        baseURL: String,
        username: String,
        item: SequencedWorkItem,
        sessionId: String?,
        force: Bool = false
    ) async throws -> BackendService.ScheduleLaunchResponse {
        launchingScheduleItemId = item.itemId
        defer { launchingScheduleItemId = nil }
        let response = try await BackendService.launchScheduleItem(
            baseURL: baseURL,
            username: username,
            itemId: item.itemId,
            sessionId: sessionId,
            force: force
        )
        curriculumSchedule = response.schedule
        if let timezone = response.schedule.timezone, !timezone.isEmpty {
            learnerTimezone = timezone
        }
        error = nil

        if let lesson = response.content.lesson {
            recordLesson(lesson)
        }
        if let quiz = response.content.quiz {
            let previous = game.elo
            applyElo(updated: quiz.elo, delta: eloDelta(from: previous, to: quiz.elo))
            recordQuiz(quiz)
        }
        if let milestone = response.content.milestone {
            recordMilestone(milestone)
        }

        return response
    }

    func completeScheduleItem(
        baseURL: String,
        username: String,
        item: SequencedWorkItem,
        sessionId: String?
    ) async throws {
        completingScheduleItemId = item.itemId
        defer { completingScheduleItemId = nil }
        let schedule = try await BackendService.completeScheduleItem(
            baseURL: baseURL,
            username: username,
            itemId: item.itemId,
            sessionId: sessionId
        )
        curriculumSchedule = schedule
        if let timezone = schedule.timezone, !timezone.isEmpty {
            learnerTimezone = timezone
        }
        error = nil
    }

    private func requestSchedule(
        baseURL: String,
        username: String,
        refresh: Bool,
        startDay: Int?,
        daySpan: Int?,
        pageToken: Int?
    ) async {
        guard let trimmedBase = BackendService.trimmed(url: baseURL) else { return }
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty else { return }

        let mergeSlices = !refresh && ((startDay ?? 0) > 0 || pageToken != nil)
        let startedAt = Date()
        let startEvent = refresh ? "schedule_refresh_started" : "schedule_slice_started"
        var startMetadata: [String: String] = [
            "username": trimmedUsername,
            "refresh": refresh ? "true" : "false",
        ]
        if let startDay { startMetadata["startDay"] = "\(startDay)" }
        if let daySpan { startMetadata["daySpan"] = "\(daySpan)" }
        if let pageToken { startMetadata["pageToken"] = "\(pageToken)" }

        if mergeSlices {
            loadingScheduleSlice = true
        } else {
            scheduleRefreshing = true
        }
        TelemetryReporter.shared.record(event: startEvent, metadata: startMetadata)

        defer {
            if mergeSlices {
                loadingScheduleSlice = false
            } else {
                scheduleRefreshing = false
            }
        }

        do {
            let schedule = try await BackendService.fetchCurriculumSchedule(
                baseURL: trimmedBase,
                username: trimmedUsername,
                refresh: refresh,
                startDay: startDay,
                daySpan: daySpan,
                pageToken: pageToken
            )
            let merged = mergeSchedules(
                current: curriculumSchedule,
                incoming: schedule,
                merge: mergeSlices && curriculumSchedule != nil
            )
            curriculumSchedule = merged
            if let timezone = merged.timezone, !timezone.isEmpty {
                learnerTimezone = timezone
            }
            error = nil
            let durationMs = Int(Date().timeIntervalSince(startedAt) * 1000)
            let metadata = scheduleTelemetryMetadata(
                schedule: merged,
                username: trimmedUsername,
                durationMs: durationMs,
                refresh: refresh,
                startDay: startDay,
                daySpan: daySpan,
                pageToken: pageToken,
                usedCache: false
            )
            var aggregateCopy = merged
            aggregateCopy.slice = nil
            ScheduleSliceCache.shared.store(schedule: aggregateCopy, username: trimmedUsername, startDay: 0)
            recordScheduleTelemetry(
                event: refresh ? "schedule_refresh_completed" : "schedule_slice_completed",
                metadata: metadata
            )
        } catch let serviceError as BackendServiceError {
            let durationMs = Int(Date().timeIntervalSince(startedAt) * 1000)
            error = serviceError.localizedDescription
            var metadata: [String: String] = [
                "username": trimmedUsername,
                "durationMs": "\(durationMs)",
                "error": serviceError.localizedDescription,
            ]
            if let startDay { metadata["startDay"] = "\(startDay)" }
            if let daySpan { metadata["daySpan"] = "\(daySpan)" }
            if let pageToken { metadata["pageToken"] = "\(pageToken)" }
            TelemetryReporter.shared.record(
                event: refresh ? "schedule_refresh_failed" : "schedule_slice_failed",
                metadata: metadata
            )
            var cachedSchedule: CurriculumSchedule?
            var cacheStartDay: Int? = nil
            if !refresh {
                let requestedStart = pageToken ?? startDay
                if let specificCache = ScheduleSliceCache.shared.load(username: trimmedUsername, startDay: requestedStart) {
                    cachedSchedule = specificCache
                    cacheStartDay = requestedStart
                } else if let fallbackCache = ScheduleSliceCache.shared.load(username: trimmedUsername, startDay: 0) {
                    cachedSchedule = fallbackCache
                    cacheStartDay = 0
                }
            }
            if let cached = cachedSchedule {
                let mergedCache = mergeSchedules(
                    current: curriculumSchedule,
                    incoming: cached,
                    merge: mergeSlices && curriculumSchedule != nil
                )
                curriculumSchedule = mergedCache
                if let timezone = mergedCache.timezone, !timezone.isEmpty {
                    learnerTimezone = timezone
                }
                let cacheMetadata = scheduleTelemetryMetadata(
                    schedule: mergedCache,
                    username: trimmedUsername,
                    durationMs: durationMs,
                    refresh: refresh,
                    startDay: startDay,
                    daySpan: daySpan,
                    pageToken: pageToken,
                    usedCache: true,
                    cacheStartDay: cacheStartDay
                )
                recordScheduleTelemetry(
                    event: "schedule_slice_cache_loaded",
                    metadata: cacheMetadata
                )
            }
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
            let durationMs = Int(Date().timeIntervalSince(startedAt) * 1000)
            var metadata: [String: String] = [
                "username": trimmedUsername,
                "durationMs": "\(durationMs)",
                "error": self.error ?? "unknown",
            ]
            if let startDay { metadata["startDay"] = "\(startDay)" }
            if let daySpan { metadata["daySpan"] = "\(daySpan)" }
            if let pageToken { metadata["pageToken"] = "\(pageToken)" }
            TelemetryReporter.shared.record(
                event: refresh ? "schedule_refresh_failed" : "schedule_slice_failed",
                metadata: metadata
            )
            var cachedSchedule: CurriculumSchedule?
            var cacheStartDay: Int? = nil
            if !refresh {
                let requestedStart = pageToken ?? startDay
                if let specificCache = ScheduleSliceCache.shared.load(username: trimmedUsername, startDay: requestedStart) {
                    cachedSchedule = specificCache
                    cacheStartDay = requestedStart
                } else if let fallbackCache = ScheduleSliceCache.shared.load(username: trimmedUsername, startDay: 0) {
                    cachedSchedule = fallbackCache
                    cacheStartDay = 0
                }
            }
            if let cached = cachedSchedule {
                let mergedCache = mergeSchedules(
                    current: curriculumSchedule,
                    incoming: cached,
                    merge: mergeSlices && curriculumSchedule != nil
                )
                curriculumSchedule = mergedCache
                if let timezone = mergedCache.timezone, !timezone.isEmpty {
                    learnerTimezone = timezone
                }
                let cacheMetadata = scheduleTelemetryMetadata(
                    schedule: mergedCache,
                    username: trimmedUsername,
                    durationMs: durationMs,
                    refresh: refresh,
                    startDay: startDay,
                    daySpan: daySpan,
                    pageToken: pageToken,
                    usedCache: true,
                    cacheStartDay: cacheStartDay
                )
                recordScheduleTelemetry(
                    event: "schedule_slice_cache_loaded",
                    metadata: cacheMetadata
                )
            }
        }
    }

    private func mergeSchedules(
        current: CurriculumSchedule?,
        incoming: CurriculumSchedule,
        merge: Bool
    ) -> CurriculumSchedule {
        guard merge, let current else { return incoming }
        var merged = incoming
        let incomingIds = Set(incoming.items.map { $0.itemId })
        let retained = current.items.filter { !incomingIds.contains($0.itemId) }
        merged.items.append(contentsOf: retained)
        merged.items.sort { lhs, rhs in
            if lhs.recommendedDayOffset == rhs.recommendedDayOffset {
                return lhs.recommendedMinutes > rhs.recommendedMinutes
            }
            return lhs.recommendedDayOffset < rhs.recommendedDayOffset
        }
        merged.isStale = incoming.isStale || current.isStale
        return merged
    }

    private func scheduleTelemetryMetadata(
        schedule: CurriculumSchedule,
        username: String,
        durationMs: Int,
        refresh: Bool,
        startDay: Int?,
        daySpan: Int?,
        pageToken: Int?,
        usedCache: Bool,
        cacheStartDay: Int? = nil
    ) -> [String: String] {
        var metadata: [String: String] = [
            "username": username,
            "durationMs": "\(durationMs)",
            "itemCount": "\(schedule.items.count)",
            "isStale": schedule.isStale ? "true" : "false",
            "warningCount": "\(schedule.warnings.count)",
            "usedCache": usedCache ? "true" : "false",
            "refresh": refresh ? "true" : "false",
        ]
        if let timezone = schedule.timezone, !timezone.isEmpty {
            metadata["timezone"] = timezone
        }
        if let anchor = schedule.anchorDate {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withFullDate]
            metadata["anchorDate"] = formatter.string(from: anchor)
        }
        if let slice = schedule.slice {
            metadata["sliceStartDay"] = "\(slice.startDay)"
            metadata["sliceEndDay"] = "\(slice.endDay)"
            metadata["sliceDaySpan"] = "\(slice.daySpan)"
            metadata["sliceHasMore"] = slice.hasMore ? "true" : "false"
            metadata["sliceTotalItems"] = "\(slice.totalItems)"
            metadata["sliceTotalDays"] = "\(slice.totalDays)"
            if let next = slice.nextStartDay {
                metadata["sliceNextStartDay"] = "\(next)"
            }
        }
        if let startDay { metadata["startDay"] = "\(startDay)" }
        if let daySpan { metadata["daySpan"] = "\(daySpan)" }
        if let pageToken { metadata["pageToken"] = "\(pageToken)" }
        if let cacheStartDay { metadata["cacheStartDay"] = "\(cacheStartDay)" }
        return metadata
    }

    private func recordScheduleTelemetry(event: String, metadata: [String: String]) {
        let signatureComponents = [
            event,
            metadata["username"] ?? "",
            metadata["startDay"] ?? "",
            metadata["pageToken"] ?? "",
            metadata["usedCache"] ?? "",
            metadata["itemCount"] ?? ""
        ]
        let signature = signatureComponents.joined(separator: "|")
        if signature == lastScheduleEventSignature,
           let last = lastScheduleEventTimestamp,
           Date().timeIntervalSince(last) < 2 {
            return
        }
        lastScheduleEventSignature = signature
        lastScheduleEventTimestamp = Date()
        TelemetryReporter.shared.record(event: event, metadata: metadata)
    }

    private func dedupeCategoriesByLabel(_ categories: [EloCategoryDefinition]) -> [EloCategoryDefinition] {
        var seen: Set<String> = []
        var result: [EloCategoryDefinition] = []
        for category in categories {
            let key = category.label.lowercased()
            if seen.insert(key).inserted {
                result.append(category)
            }
        }
        return result
    }

    private func dedupeTracksByLabel(_ tracks: [FoundationTrackModel]) -> [FoundationTrackModel] {
        var seen: Set<String> = []
        var result: [FoundationTrackModel] = []
        for track in tracks {
            let key = track.label.lowercased()
            if seen.insert(key).inserted {
                result.append(track)
            }
        }
        return result
    }

    func deferScheduleItem(
        baseURL: String,
        username: String,
        item: SequencedWorkItem,
        days: Int,
        targetDayOffset: Int? = nil,
        reason: String? = nil
    ) async {
        guard let trimmedBase = BackendService.trimmed(url: baseURL) else { return }
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty else { return }
        let safeDays = max(1, days)
        adjustingScheduleItemId = item.itemId
        let startedAt = Date()
        var metadata: [String: String] = [
            "username": trimmedUsername,
            "itemId": item.itemId,
            "days": "\(safeDays)",
        ]
        if let target = targetDayOffset {
            metadata["target"] = "\(target)"
        }
        if let reason, !reason.isEmpty {
            metadata["reason"] = reason
        }
        TelemetryReporter.shared.record(event: "schedule_adjustment_started", metadata: metadata)
        defer { adjustingScheduleItemId = nil }
        do {
            let schedule = try await BackendService.adjustCurriculumSchedule(
                baseURL: trimmedBase,
                username: trimmedUsername,
                itemId: item.itemId,
                days: safeDays,
                targetDayOffset: targetDayOffset,
                reason: reason
            )
            curriculumSchedule = schedule
            if let timezone = schedule.timezone, !timezone.isEmpty {
                learnerTimezone = timezone
            }
            error = nil
            let durationMs = Int(Date().timeIntervalSince(startedAt) * 1000)
            let newOffset = schedule.items.first(where: { $0.itemId == item.itemId })?.recommendedDayOffset ?? -1
            var metadata: [String: String] = [
                "username": trimmedUsername,
                "itemId": item.itemId,
                "durationMs": "\(durationMs)",
                "newOffset": "\(newOffset)",
            ]
            if let timezone = schedule.timezone, !timezone.isEmpty {
                metadata["timezone"] = timezone
            }
            if let anchor = schedule.anchorDate {
                let formatter = ISO8601DateFormatter()
                formatter.formatOptions = [.withFullDate]
                metadata["anchorDate"] = formatter.string(from: anchor)
            }
            TelemetryReporter.shared.record(
                event: "schedule_adjustment_completed",
                metadata: metadata
            )
        } catch let serviceError as BackendServiceError {
            error = serviceError.localizedDescription
            let durationMs = Int(Date().timeIntervalSince(startedAt) * 1000)
            TelemetryReporter.shared.record(
                event: "schedule_adjustment_failed",
                metadata: [
                    "username": trimmedUsername,
                    "itemId": item.itemId,
                    "durationMs": "\(durationMs)",
                    "error": serviceError.localizedDescription,
                ]
            )
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
            let durationMs = Int(Date().timeIntervalSince(startedAt) * 1000)
            TelemetryReporter.shared.record(
                event: "schedule_adjustment_failed",
                metadata: [
                    "username": trimmedUsername,
                    "itemId": item.itemId,
                    "durationMs": "\(durationMs)",
                    "error": self.error ?? "unknown",
                ]
            )
        }
    }

    func ensureOnboardingPlan(
        baseURL: String,
        username: String,
        goal: String,
        useCase: String,
        strengths: String,
        timezone: String,
        force: Bool = false
    ) async throws {
        learnerTimezone = timezone
        busy = true
        defer { busy = false }
        let snapshot = try await BackendService.ensureOnboardingPlan(
            baseURL: baseURL,
            username: username,
            goal: goal,
            useCase: useCase,
            strengths: strengths,
            timezone: timezone,
            force: force
        )
        syncProfile(with: snapshot)
        error = nil
        if requiresAssessment {
            showingAssessmentFlow = true
        }
    }

    func response(for taskId: String) -> String {
        assessmentResponses[taskId] ?? ""
    }

    func setResponse(_ value: String, for taskId: String) {
        assessmentResponses[taskId] = value
    }

    func insertStarter(for task: OnboardingAssessmentTask) {
        if let starter = task.starterCode, !starter.isEmpty {
            assessmentResponses[task.taskId] = starter
        }
    }

    func recordLesson(_ lesson: EndLearn) {
        latestLesson = lesson
        lastEnvelope = WidgetEnvelope(display: lesson.display, widgets: lesson.widgets, citations: lesson.citations)
    }

    func recordQuiz(_ quiz: EndQuiz) {
        latestQuiz = quiz
    }

    func recordMilestone(_ milestone: EndMilestone) {
        latestMilestone = milestone
        lastEnvelope = WidgetEnvelope(display: milestone.display, widgets: milestone.widgets, citations: nil)
    }

    func clearSessionContent() {
        latestLesson = nil
        latestQuiz = nil
        latestMilestone = nil
        lastEnvelope = nil
    }

    func focus(on submission: AssessmentSubmissionRecord) {
        focusedSubmission = submission
    }

    func focusSubmission(by id: String) {
        focusedSubmission = assessmentHistory.first { $0.submissionId == id }
    }

    func dismissSubmissionFocus() {
        focusedSubmission = nil
    }

    func isAssessmentTaskAnswered(_ task: OnboardingAssessmentTask) -> Bool {
        let trimmed = response(for: task.taskId).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return false }
        if task.taskType == .code, let starter = task.starterCode, !starter.isEmpty {
            let starterTrimmed = starter.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed == starterTrimmed {
                return false
            }
        }
        return true
    }

    func updateAssessmentStatus(
        to status: OnboardingAssessment.Status,
        baseURL: String,
        username: String
    ) async {
        do {
            let updated = try await BackendService.updateOnboardingAssessmentStatus(
                baseURL: baseURL,
                username: username,
                status: status
            )
            onboardingAssessment = updated
            error = nil
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
        }
    }

    func submitAndCompleteAssessment(
        baseURL: String,
        username: String
    ) async -> Bool {
        guard let assessment = onboardingAssessment else { return false }
        guard let responses = makeSubmissionItems(for: assessment) else {
            error = "Complete every prompt before submitting the assessment."
            return false
        }
        error = nil
        do {
            let submission = try await BackendService.submitAssessmentResponses(
                baseURL: baseURL,
                username: username,
                responses: responses,
                metadata: submissionMetadata()
            )
            assessmentResult = submission.grading
            let updated = try await BackendService.updateOnboardingAssessmentStatus(
                baseURL: baseURL,
                username: username,
                status: .completed
            )
            onboardingAssessment = updated
            assessmentResponses.removeAll()
            showingAssessmentFlow = false
            pendingAssessmentAttachments.removeAll()
            await loadProfile(baseURL: baseURL, username: username)
            error = nil
            return true
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
            return false
        }
    }

    func refreshPendingAssessmentAttachments(
        baseURL: String,
        username: String
    ) async {
        guard let trimmedBase = BackendService.trimmed(url: baseURL) else {
            pendingAssessmentAttachments = []
            return
        }
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedUsername.isEmpty else {
            pendingAssessmentAttachments = []
            return
        }
        do {
            let attachments = try await BackendService.listAssessmentAttachments(
                baseURL: trimmedBase,
                username: trimmedUsername
            )
            pendingAssessmentAttachments = attachments
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
        }
    }

    @discardableResult
    func uploadAssessmentAttachmentFile(
        baseURL: String,
        username: String,
        fileURL: URL,
        description: String? = nil
    ) async -> Bool {
        do {
            _ = try await BackendService.uploadAssessmentAttachment(
                baseURL: baseURL,
                username: username,
                fileURL: fileURL,
                description: description
            )
            await refreshPendingAssessmentAttachments(baseURL: baseURL, username: username)
            return true
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
            return false
        }
    }

    @discardableResult
    func addAssessmentAttachmentLink(
        baseURL: String,
        username: String,
        name: String?,
        url: String,
        description: String?
    ) async -> Bool {
        do {
            _ = try await BackendService.createAssessmentAttachmentLink(
                baseURL: baseURL,
                username: username,
                name: name,
                url: url,
                description: description
            )
            await refreshPendingAssessmentAttachments(baseURL: baseURL, username: username)
            return true
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
            return false
        }
    }

    @discardableResult
    func removeAssessmentAttachment(
        baseURL: String,
        username: String,
        attachmentId: String
    ) async -> Bool {
        do {
            try await BackendService.deleteAssessmentAttachment(
                baseURL: baseURL,
                username: username,
                attachmentId: attachmentId
            )
            await refreshPendingAssessmentAttachments(baseURL: baseURL, username: username)
            return true
        } catch {
            let nsError = error as NSError
            self.error = nsError.localizedDescription.isEmpty ? String(describing: error) : nsError.localizedDescription
            return false
        }
    }

    func updateLastSeenAssessmentSubmissionId(_ id: String?) {
        let wasUnseen = hasUnseenAssessmentResults
        let latest = assessmentResultTracker.updateLastSeen(id, history: assessmentHistory)
        hasUnseenAssessmentResults = assessmentResultTracker.hasUnseenResults
        if let latest, hasUnseenAssessmentResults, !wasUnseen {
            recordAssessmentUnseenTelemetry(for: latest)
        }
    }

    @discardableResult
    func markAssessmentResultsAsSeen() -> String? {
        let previouslyUnseen = hasUnseenAssessmentResults
        let seenId = assessmentResultTracker.markResultsSeen(history: assessmentHistory)
        hasUnseenAssessmentResults = assessmentResultTracker.hasUnseenResults
        if previouslyUnseen, let latest = latestGradedAssessment {
            recordAssessmentSeenTelemetry(for: latest)
        }
        return seenId
    }

    func openAssessmentFlow() {
        showingAssessmentFlow = true
    }

    func closeAssessmentFlow() {
        showingAssessmentFlow = false
    }

    func resetAfterDeveloperClear() {
        game = GameState()
        busy = false
        error = nil
        eloPlan = nil
        curriculumPlan = nil
        curriculumSchedule = nil
        onboardingAssessment = nil
        assessmentResult = nil
        assessmentHistory = []
        assessmentResponses.removeAll()
        showingAssessmentFlow = false
        focusedSubmission = nil
        clearSessionContent()
        pendingAssessmentAttachments.removeAll()
        lastBackendBaseURL = nil
        lastLearnerUsername = nil
        assessmentResultTracker.reset()
        hasUnseenAssessmentResults = false
    }

    var requiresAssessment: Bool {
        guard let bundle = onboardingAssessment else { return false }
        return bundle.status != .completed
    }

    var awaitingAssessmentResults: Bool {
        if let pending = assessmentHistory.first, pending.grading == nil {
            return true
        }
        guard let bundle = onboardingAssessment else { return false }
        if bundle.status == .completed {
            return assessmentResult == nil
        }
        return false
    }

    enum AssessmentReadinessStatus {
        case notGenerated
        case pendingStart
        case inProgress
        case awaitingGrading
        case ready
    }

    var assessmentReadinessStatus: AssessmentReadinessStatus {
        if assessmentHistory.first(where: { $0.grading == nil }) != nil {
            return .awaitingGrading
        }
        if let onboarding = onboardingAssessment {
            switch onboarding.status {
            case .pending:
                return .pendingStart
            case .inProgress:
                return .inProgress
            case .completed:
                return .ready
            }
        }
        if !assessmentHistory.isEmpty {
            return .ready
        }
        return .notGenerated
    }

    var latestAssessmentSubmission: AssessmentSubmissionRecord? {
        assessmentHistory.first
    }

    var latestGradedAssessment: AssessmentSubmissionRecord? {
        assessmentHistory.first(where: { $0.grading != nil })
    }

    var latestAssessmentGradeTimestamp: Date? {
        latestGradedAssessment?.grading?.evaluatedAt
    }

    var latestAssessmentSubmittedAt: Date? {
        latestAssessmentSubmission?.submittedAt
    }

    var categoryLabelMap: [String:String] {
        guard let plan = eloPlan else { return [:] }
        return Dictionary(uniqueKeysWithValues: plan.categories.map { ($0.key, $0.label) })
    }

    func label(for categoryKey: String) -> String {
        categoryLabelMap[categoryKey] ?? categoryKey
    }

    var modulesByCategory: [String:[OnboardingCurriculumModule]] {
        guard let modules = curriculumPlan?.modules else { return [:] }
        return Dictionary(grouping: modules, by: { $0.categoryKey })
    }

    private func alignEloSnapshotWithPlan() {
        guard let plan = eloPlan else { return }
        var aligned: [String:Int] = [:]
        for category in plan.categories {
            let current = game.elo[category.key] ?? category.startingRating
            aligned[category.key] = current
        }
        game.elo = aligned
    }

    private func syncProfile(with snapshot: LearnerProfileSnapshot) {
        learnerTimezone = snapshot.timezone ?? snapshot.curriculumSchedule?.timezone
        game.elo = Dictionary(uniqueKeysWithValues: snapshot.skillRatings.map { ($0.category, $0.rating) })
        if var plan = snapshot.eloCategoryPlan {
            plan.categories = dedupeCategoriesByLabel(plan.categories)
            eloPlan = plan
        } else {
            eloPlan = nil
        }
        curriculumPlan = snapshot.curriculumPlan
        curriculumSchedule = snapshot.curriculumSchedule
        if let schedule = snapshot.curriculumSchedule {
            ScheduleSliceCache.shared.store(schedule: schedule, username: snapshot.username)
        }
        adjustingScheduleItemId = nil
        onboardingAssessment = snapshot.onboardingAssessment
        assessmentResult = snapshot.onboardingAssessmentResult
        assessmentHistory = snapshot.assessmentSubmissions.sorted { $0.submittedAt > $1.submittedAt }
        goalInference = snapshot.goalInference
        foundationTracks = dedupeTracksByLabel(snapshot.foundationTracks ?? [])
        if let currentFocusId = focusedSubmission?.submissionId {
            focusedSubmission = assessmentHistory.first { $0.submissionId == currentFocusId }
        }
        alignEloSnapshotWithPlan()
        pruneAssessmentResponses()
        if let backend = lastBackendBaseURL,
           let username = lastLearnerUsername,
           let schedule = snapshot.curriculumSchedule,
           schedule.slice == nil,
           !schedule.items.isEmpty {
            Task {
                await refreshCurriculumSchedule(baseURL: backend, username: username)
            }
        }
    }

    private func pruneAssessmentResponses() {
        guard let assessment = onboardingAssessment else {
            assessmentResponses.removeAll()
            return
        }
        let validIds = Set(assessment.tasks.map { $0.taskId })
        assessmentResponses = assessmentResponses.filter { validIds.contains($0.key) }
    }

    private func evaluateAssessmentSeenState() {
        let wasUnseen = hasUnseenAssessmentResults
        let latest = assessmentResultTracker.apply(history: assessmentHistory)
        hasUnseenAssessmentResults = assessmentResultTracker.hasUnseenResults
        if hasUnseenAssessmentResults, !wasUnseen, let latest {
            recordAssessmentUnseenTelemetry(for: latest)
        }
    }

    private func recordAssessmentUnseenTelemetry(for submission: AssessmentSubmissionRecord) {
        guard let grading = submission.grading else { return }
        var metadata: [String:String] = ["submissionId": submission.submissionId]
        metadata["evaluatedAt"] = iso8601Formatter.string(from: grading.evaluatedAt)
        TelemetryReporter.shared.record(event: "assessment_results_unseen", metadata: metadata)
    }

    private func recordAssessmentSeenTelemetry(for submission: AssessmentSubmissionRecord) {
        guard let grading = submission.grading else { return }
        var metadata: [String:String] = ["submissionId": submission.submissionId]
        metadata["evaluatedAt"] = iso8601Formatter.string(from: grading.evaluatedAt)
        TelemetryReporter.shared.record(event: "assessment_results_seen", metadata: metadata)
    }

    private func makeSubmissionItems(for assessment: OnboardingAssessment) -> [BackendService.AssessmentSubmissionUploadItem]? {
        var items: [BackendService.AssessmentSubmissionUploadItem] = []
        for task in assessment.tasks {
            let trimmed = response(for: task.taskId).trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { return nil }
            if task.taskType == .code, let starter = task.starterCode, !starter.isEmpty {
                let starterTrimmed = starter.trimmingCharacters(in: .whitespacesAndNewlines)
                if trimmed == starterTrimmed {
                    return nil
                }
            }
            items.append(.init(taskId: task.taskId, response: trimmed))
        }
        return items
    }

    private func submissionMetadata() -> [String: String] {
        var metadata: [String: String] = ["platform": "macOS"]
        if let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String, !version.isEmpty {
            metadata["client_version"] = version
        }
        if let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String, !build.isEmpty {
            metadata["build"] = build
        }
        return metadata
    }
}

extension AppViewModel.AssessmentReadinessStatus {
    var displayText: String {
        switch self {
        case .awaitingGrading:
            return "Awaiting grading"
        case .pendingStart:
            return "Not started"
        case .inProgress:
            return "In progress"
        case .ready:
            return "Ready"
        case .notGenerated:
            return "Not generated"
        }
    }

    var systemImageName: String {
        switch self {
        case .awaitingGrading:
            return "hourglass"
        case .pendingStart:
            return "square.and.pencil"
        case .inProgress:
            return "play.circle"
        case .ready:
            return "checkmark.circle"
        case .notGenerated:
            return "questionmark.circle"
        }
    }

    var tintColor: Color {
        switch self {
        case .awaitingGrading:
            return .orange
        case .pendingStart:
            return .orange
        case .inProgress:
            return .blue
        case .ready:
            return .green
        case .notGenerated:
            return .secondary
        }
    }
}
