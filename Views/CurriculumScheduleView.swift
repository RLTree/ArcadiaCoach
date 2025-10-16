import SwiftUI

struct CurriculumScheduleView: View {
    let schedule: CurriculumSchedule
    let categoryLabels: [String:String]
    let skillRatings: [String:Int]
    let milestoneCompletions: [MilestoneCompletion]
    let telemetryEvents: [LearnerTelemetryEvent]
    let isRefreshing: Bool
    let isLoadingNextSlice: Bool
    let adjustingItemId: String?
    let launchingItemId: String?
    let completingItemId: String?
    let refreshAction: () -> Void
    let adjustAction: (SequencedWorkItem, Int) -> Void
    let loadMoreAction: () -> Void
    let launchAction: (SequencedWorkItem, Bool) -> Void
    let completeAction: (SequencedWorkItem) -> Void
    @State private var expandedMilestoneItems: Set<String> = []

    private var scheduleTimeZone: TimeZone? {
        guard let identifier = schedule.timezone else { return nil }
        return TimeZone(identifier: identifier)
    }

    private var timezoneLabel: String? {
        guard let zone = scheduleTimeZone else { return nil }
        if let localized = zone.localizedName(for: .generic, locale: .current) {
            return "\(localized) (\(zone.identifier))"
        }
        return zone.identifier
    }

    private var scheduledDateFormatter: DateFormatter {
        let formatter = DateFormatter()
        formatter.locale = .current
        if let tz = scheduleTimeZone {
            formatter.timeZone = tz
        }
        formatter.dateFormat = "EEEE, MMM d, yyyy (zzz)"
        return formatter
    }

    private var maxPlannedMinutes: Int {
        schedule.categoryAllocations.map(\.plannedMinutes).max() ?? 0
    }

    private var rationaleEntries: [ScheduleRationaleEntry] {
        schedule.rationaleHistory.sorted { $0.generatedAt > $1.generatedAt }
    }

    private var recentMilestoneCompletions: [MilestoneCompletion] {
        Array(milestoneCompletions.prefix(3))
    }

    private var milestoneAlerts: [LearnerTelemetryEvent] {
        telemetryEvents.filter { event in
            switch event.eventType {
            case "schedule_launch_completed":
                guard payloadValue(event.payload, keys: ["kind"])?.lowercased() == "milestone" else { return false }
                return payloadValue(event.payload, keys: ["progress_recorded", "progressRecorded"])?.lowercased() == "false"
            case "milestone_completion_recorded":
                let attachments = Int(payloadValue(event.payload, keys: ["attachment_count", "attachmentCount"]) ?? "0") ?? 0
                let links = Int(payloadValue(event.payload, keys: ["link_count", "linkCount"]) ?? "0") ?? 0
                let hasNotes = payloadValue(event.payload, keys: ["has_notes", "hasNotes"])?.lowercased() == "true"
                return attachments == 0 || links == 0 || !hasNotes
            default:
                return false
            }
        }
        .sorted { $0.createdAt > $1.createdAt }
    }

    private func rating(for categoryKey: String) -> Int {
        skillRatings[categoryKey] ?? 0
    }

    private func requirementStatus(for requirement: MilestoneRequirement) -> (met: Bool, current: Int) {
        let current = rating(for: requirement.categoryKey)
        return (current >= requirement.minimumRating, current)
    }

    private var longRangeDescription: String? {
        guard schedule.sessionsPerWeek > 0 || schedule.projectedWeeklyMinutes > 0 || schedule.longRangeItemCount > 0 else {
            return nil
        }
        let weeks = schedule.extendedWeeks > 0 ? schedule.extendedWeeks : max(1, Int((Double(schedule.timeHorizonDays) / 7.0).rounded(.up)))
        var segments: [String] = []
        if schedule.sessionsPerWeek > 0 {
            var segment = "\(weeks) week horizon at \(schedule.sessionsPerWeek) session\(schedule.sessionsPerWeek == 1 ? "" : "s")/week"
            if schedule.projectedWeeklyMinutes > 0 {
                segment += " (~\(schedule.projectedWeeklyMinutes) min/week)"
            }
            segments.append(segment)
        } else {
            segments.append("\(weeks) week horizon")
            if schedule.projectedWeeklyMinutes > 0 {
                segments.append("~\(schedule.projectedWeeklyMinutes) min/week")
            }
        }
        if schedule.longRangeItemCount > 0 {
            segments.append("\(schedule.longRangeItemCount) spaced refresher\(schedule.longRangeItemCount == 1 ? "" : "s")")
        }
        let friendlyCategories = schedule.longRangeCategoryKeys.compactMap { key -> String? in
            if let label = categoryLabels[key], !label.isEmpty {
                return label
            }
            return key.isEmpty ? nil : key
        }
        if !friendlyCategories.isEmpty {
            segments.append("Focus: \(friendlyCategories.joined(separator: ", "))")
        }
        return segments.joined(separator: " · ")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            if schedule.isStale || !schedule.warnings.isEmpty {
                warningsSection
            }
            if !milestoneAlerts.isEmpty {
                milestoneAlertsSection
            }
            if let pacing = schedule.pacingOverview, !pacing.isEmpty {
                Text(pacing)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let cadence = schedule.cadenceNotes, !cadence.isEmpty {
                Text(cadence)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !recentMilestoneCompletions.isEmpty {
                milestoneHistorySection
            }
            if !schedule.categoryAllocations.isEmpty {
                pacingSection
            }
            if !rationaleEntries.isEmpty {
                rationaleSection
            }
            ForEach(schedule.groupedItems) { group in
                VStack(alignment: .leading, spacing: 10) {
                    Text(dayLabel(for: group))
                        .font(.subheadline.bold())
                    ForEach(group.items) { item in
                        itemRow(for: item)
                    }
                }
            }
            if showLoadMoreButton {
                loadMoreSection
            }
        }
        .padding(20)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
        .selectableContent()
    }

    private var showLoadMoreButton: Bool {
        guard let slice = schedule.slice else { return false }
        return slice.hasMore || isLoadingNextSlice
    }

@ViewBuilder
private var loadMoreSection: some View {
    VStack(spacing: 12) {
        if isLoadingNextSlice {
            ProgressView("Loading more sessions…")
                    .progressViewStyle(.circular)
            } else {
                Button {
                    loadMoreAction()
                } label: {
                    Label("Load more sessions", systemImage: "arrow.down.circle")
                        .font(.callout.bold())
                }
                .buttonStyle(.bordered)
                .disabled(isRefreshing)
            }
            if let nextStart = schedule.slice?.nextStartDay {
                Text("Next block begins around day \(nextStart)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
    }
    .frame(maxWidth: .infinity)
    .padding(12)
}

    @ViewBuilder
    private var milestoneAlertsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Milestone alerts", systemImage: "exclamationmark.triangle")
                .font(.subheadline.bold())
                .foregroundStyle(Color.red)
            ForEach(milestoneAlerts.prefix(3)) { event in
                VStack(alignment: .leading, spacing: 4) {
                    Text(alertMessage(for: event))
                        .font(.caption)
                    Text(event.createdAt.formatted(date: .abbreviated, time: .shortened))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .padding(10)
                .background(Color.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.red.opacity(0.06), in: RoundedRectangle(cornerRadius: 14))
    }

    @ViewBuilder
    private var milestoneHistorySection: some View {
        if recentMilestoneCompletions.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 8) {
                Label("Latest milestone wins", systemImage: "flag.checkered")
                    .font(.subheadline.bold())
                ForEach(recentMilestoneCompletions) { completion in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(completion.title)
                            .font(.callout.bold())
                        Text(completion.recordedAt, style: .date)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        HStack(spacing: 10) {
                            Label(projectStatusLabel(completion.projectStatus), systemImage: "flag")
                                .font(.caption2.bold())
                                .padding(.horizontal, 6)
                                .padding(.vertical, 3)
                                .background(progressStatusColor(completion.projectStatus).opacity(0.12), in: Capsule())
                                .foregroundStyle(progressStatusColor(completion.projectStatus))
                            if let outcomeLabel = evaluationOutcomeLabel(completion.evaluationOutcome) {
                                Label(outcomeLabel, systemImage: "checkmark.seal")
                                    .font(.caption2.bold())
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 3)
                                    .background(evaluationOutcomeColor(completion.evaluationOutcome).opacity(0.12), in: Capsule())
                                    .foregroundStyle(evaluationOutcomeColor(completion.evaluationOutcome))
                            }
                            if completion.eloDelta != 0 {
                                let deltaSymbol = completion.eloDelta > 0 ? "+" : ""
                                Label("ΔELO \(deltaSymbol)\(completion.eloDelta)", systemImage: "chart.line.uptrend.xyaxis")
                                    .font(.caption2.bold())
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 3)
                                    .background((completion.eloDelta > 0 ? Color.green : Color.orange).opacity(0.12), in: Capsule())
                                    .foregroundStyle(completion.eloDelta > 0 ? Color.green : Color.orange)
                            }
                        }
                        if let notes = completion.notes, !notes.isEmpty {
                            Text(notes)
                                .font(.caption)
                                .foregroundStyle(.primary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        if let evaluationNotes = completion.evaluationNotes, !evaluationNotes.isEmpty {
                            Text("Feedback: \(evaluationNotes)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        HStack(spacing: 12) {
                            if !completion.externalLinks.isEmpty {
                                Label("Links: \(completion.externalLinks.count)", systemImage: "link")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            if !completion.attachmentIds.isEmpty {
                                Label("Attachments: \(completion.attachmentIds.count)", systemImage: "paperclip")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            if !completion.eloFocus.isEmpty {
                                Label("Focus: \(completion.eloFocus.joined(separator: ", "))", systemImage: "target")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                }
            }
        }
    }

    @ViewBuilder
    private var warningsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(
                schedule.isStale ? "Using previous schedule" : "Schedule warnings",
                systemImage: "exclamationmark.triangle.fill"
            )
            .font(.subheadline.bold())
            .foregroundStyle(schedule.isStale ? Color.orange : Color.yellow)

            if schedule.warnings.isEmpty {
                Text("We'll retry generation soon.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(schedule.warnings) { warning in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(warning.message)
                            .font(.footnote)
                        if let detail = warning.detail, !detail.isEmpty {
                            Text(detail)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Text(warning.generatedAt.formatted(date: .numeric, time: .shortened))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            schedule.isStale ? Color.orange.opacity(0.12) : Color.yellow.opacity(0.1),
            in: RoundedRectangle(cornerRadius: 12)
        )
    }

    @ViewBuilder
    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .center, spacing: 12) {
                Label("Upcoming Schedule", systemImage: "calendar.badge.clock")
                    .font(.headline)
                Spacer()
                Button {
                    refreshAction()
                } label: {
                    if isRefreshing {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Label("Refresh", systemImage: "arrow.clockwise")
                            .labelStyle(.titleAndIcon)
                    }
                }
                .buttonStyle(.bordered)
                .disabled(isRefreshing)
                .accessibilityLabel("Refresh curriculum schedule")
            }
            if let tzLabel = timezoneLabel {
                Text("Times shown in \(tzLabel)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let outlook = longRangeDescription {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "calendar.badge.plus")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(outlook)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    @ViewBuilder
    private var pacingSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Pacing Plan", systemImage: "speedometer")
                .font(.subheadline.bold())
            ForEach(schedule.categoryAllocations) { allocation in
                VStack(alignment: .leading, spacing: 6) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(categoryName(for: allocation.categoryKey))
                            .font(.headline)
                        Spacer()
                        Text(allocation.targetSharePercent)
                            .font(.caption)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.primary.opacity(0.08), in: Capsule())
                        Label(allocation.deferralPressure.description, systemImage: "arrow.triangle.2.circlepath")
                            .font(.caption.bold())
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(pressureColor(for: allocation.deferralPressure).opacity(0.15), in: Capsule())
                            .foregroundStyle(pressureColor(for: allocation.deferralPressure))
                    }
                    ProgressView(
                        value: Double(allocation.plannedMinutes),
                        total: Double(max(maxPlannedMinutes, 1))
                    )
                    .progressViewStyle(.linear)
                    .tint(pressureColor(for: allocation.deferralPressure))
                    HStack(alignment: .center) {
                        Text("Planned: \(allocation.formattedPlannedDuration)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        if allocation.deferralCount > 0 {
                            Text("\(allocation.deferralCount) deferrals • max \(allocation.maxDeferralDays)d")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                    if let rationale = allocation.rationale, !rationale.isEmpty {
                        Text(rationale)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.primary.opacity(0.03), in: RoundedRectangle(cornerRadius: 14))
    }

    @ViewBuilder
    private var rationaleSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Schedule Updates", systemImage: "list.bullet.rectangle")
                .font(.subheadline.bold())
            ForEach(Array(rationaleEntries.enumerated()), id: \.element.id) { index, entry in
                VStack(alignment: .leading, spacing: 6) {
                    Text(entry.headline)
                        .font(.headline)
                    Text(entry.summary)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if !entry.adjustmentNotes.isEmpty {
                        VStack(alignment: .leading, spacing: 2) {
                            ForEach(entry.adjustmentNotes, id: \.self) { note in
                                Text("• \(note)")
                                    .font(.caption)
                            }
                        }
                    }
                    Text(entry.generatedAt.formatted(date: .abbreviated, time: .shortened))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if index < rationaleEntries.count - 1 {
                    Divider()
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.primary.opacity(0.03), in: RoundedRectangle(cornerRadius: 14))
    }

    @ViewBuilder
    private func itemRow(for item: SequencedWorkItem) -> some View {
        let isAdjusting = adjustingItemId == item.itemId
        let isMilestone = item.kind == .milestone
        let expansionBinding = Binding(
            get: { expandedMilestoneItems.contains(item.itemId) },
            set: { newValue in
                if newValue {
                    expandedMilestoneItems.insert(item.itemId)
                } else {
                    expandedMilestoneItems.remove(item.itemId)
                }
            }
        )
        let isExpanded = isMilestone ? expansionBinding.wrappedValue : true
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Label(item.kind.label, systemImage: item.kind.systemImage)
                    .font(.subheadline.bold())
                if item.userAdjusted {
                    Label("Rescheduled", systemImage: "arrow.uturn.down")
                        .font(.caption.bold())
                        .foregroundStyle(Color.accentColor)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.12), in: Capsule())
                        .accessibilityLabel("Rescheduled item")
                }
                Spacer()
                Text(item.formattedDuration)
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(effortColor(for: item.effortLevel).opacity(0.15), in: Capsule())
                    .foregroundStyle(effortColor(for: item.effortLevel))
                Menu {
                    Button("Defer 1 day") {
                        adjustAction(item, 1)
                    }
                    Button("Defer 3 days") {
                        adjustAction(item, 3)
                    }
                    Button("Defer 1 week") {
                        adjustAction(item, 7)
                    }
                } label: {
                    if isAdjusting {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Label("Reschedule", systemImage: "calendar.badge.plus")
                            .labelStyle(.iconOnly)
                            .padding(6)
                    }
                }
                .menuStyle(.borderlessButton)
                .disabled(isRefreshing || isAdjusting)
                .accessibilityLabel("Reschedule \(item.title)")
            }
            Text(item.title)
                .font(.headline)
            if let summary = item.summary, !summary.isEmpty {
                Text(summary)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let scheduled = item.scheduledFor {
                Text(scheduledDateFormatter.string(from: scheduled))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack(alignment: .center, spacing: 12) {
                Label(categoryLabels[item.categoryKey] ?? item.categoryKey, systemImage: "folder")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(item.effortLevel.label)
                    .font(.caption)
                    .foregroundStyle(effortColor(for: item.effortLevel))
            }

            if !item.objectives.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Objectives")
                        .font(.caption.bold())
                    let (preview, remaining) = truncatedItems(
                        item.objectives,
                        limitWhenCollapsed: isMilestone ? 2 : item.objectives.count,
                        isExpanded: isExpanded
                    )
                    ForEach(preview, id: \.self) { objective in
                        Text("• \(objective)")
                            .font(.caption)
                    }
                    if isMilestone, !isExpanded, remaining > 0 {
                        Text("• +\(remaining) more")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            if let outcome = item.expectedOutcome, !outcome.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Expected Outcome")
                        .font(.caption.bold())
                    Text(outcome)
                        .font(.caption)
                }
            }

            if let focus = item.focusReason, !focus.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Focus")
                        .font(.caption.bold())
                    Text(focus)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if isMilestone {
                milestonePreview(for: item, isExpanded: isExpanded, binding: expansionBinding)
            } else if let project = item.milestoneProject ?? item.milestoneBrief?.project {
                projectSection(for: project, isExpanded: true)
            } else if !item.prerequisites.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Prerequisites")
                        .font(.caption.bold())
                    Text(item.prerequisites.joined(separator: ", "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            if let progress = item.milestoneProgress {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Latest Progress")
                        .font(.caption.bold())
                    Text("Status: \(projectStatusLabel(progress.projectStatus))")
                        .font(.caption)
                        .foregroundStyle(progressStatusColor(progress.projectStatus))
                    if let notes = progress.notes, !notes.isEmpty {
                        Text(notes)
                            .font(.caption)
                    }
                    if !progress.externalLinks.isEmpty {
                        ForEach(progress.externalLinks, id: \.self) { link in
                            Text(link)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                    if !progress.attachmentIds.isEmpty {
                        Text("Attachments: \(progress.attachmentIds.joined(separator: ", "))")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    if !progress.nextSteps.isEmpty {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Next steps")
                                .font(.caption.bold())
                            ForEach(progress.nextSteps, id: \.self) { step in
                                Text("• \(step)")
                                    .font(.caption)
                            }
                        }
                    }
                }
            }
            if let guidance = item.milestoneGuidance {
                if !guidance.badges.isEmpty {
                    HStack(spacing: 6) {
                        ForEach(guidance.badges, id: \.self) { badge in
                            Text(badge)
                                .font(.caption2.bold())
                                .padding(.horizontal, 6)
                                .padding(.vertical, 3)
                                .background(Color.orange.opacity(0.15), in: Capsule())
                        }
                    }
                }
                Text(guidance.summary)
                    .font(.caption)
                if !guidance.nextActions.isEmpty {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(guidance.nextActions, id: \.self) { action in
                            Text("• \(action)")
                                .font(.caption)
                        }
                    }
                }
                if !guidance.warnings.isEmpty {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(guidance.warnings, id: \.self) { warning in
                            Text(warning)
                                .font(.caption)
                                .foregroundStyle(Color.red)
                        }
                    }
                }
            }
            HStack(alignment: .center, spacing: 12) {
                statusBadge(for: item)
                Spacer()
                launchButton(for: item)
                if item.launchStatus == .inProgress {
                    completeButton(for: item)
                }
            }
            if let locked = item.launchLockedReason, item.launchStatus != .completed {
                Label(locked, systemImage: "lock.fill")
                    .font(.caption)
                    .foregroundStyle(Color.orange)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(rowBackground(for: item), in: RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(item.userAdjusted ? Color.accentColor.opacity(0.4) : Color.clear, lineWidth: 1)
        )
        .animation(.easeInOut(duration: 0.2), value: item.userAdjusted)
    }

    @ViewBuilder
    private func projectSection(for project: MilestoneProject, isExpanded: Bool) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Milestone Project")
                .font(.caption.bold())
            Text(project.title)
                .font(.callout.bold())
            Text(project.goalAlignment)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if let summary = project.summary, !summary.isEmpty {
                Text(summary)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !project.deliverables.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Deliverables")
                        .font(.caption.bold())
                    let (preview, remaining) = truncatedItems(project.deliverables, limitWhenCollapsed: 3, isExpanded: isExpanded)
                    ForEach(preview, id: \.self) { deliverable in
                        Text("• \(deliverable)")
                            .font(.caption)
                    }
                    if !isExpanded, remaining > 0 {
                        Text("• +\(remaining) more")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            if !project.evidenceChecklist.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Evidence checklist")
                        .font(.caption.bold())
                    let (preview, remaining) = truncatedItems(project.evidenceChecklist, limitWhenCollapsed: 3, isExpanded: isExpanded)
                    ForEach(preview, id: \.self) { item in
                        Text("• \(item)")
                            .font(.caption)
                    }
                    if !isExpanded, remaining > 0 {
                        Text("• +\(remaining) more")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            if !project.recommendedTools.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Recommended tools")
                        .font(.caption.bold())
                    HStack(spacing: 6) {
                        let tools = isExpanded ? project.recommendedTools : Array(project.recommendedTools.prefix(4))
                        ForEach(tools, id: \.self) { tool in
                            Text(tool)
                                .font(.caption2.bold())
                                .padding(.horizontal, 6)
                                .padding(.vertical, 3)
                                .background(Color.blue.opacity(0.12), in: Capsule())
                        }
                        if !isExpanded, project.recommendedTools.count > 4 {
                            Text("+\(project.recommendedTools.count - 4) more")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            if !project.evaluationFocus.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Evaluation focus")
                        .font(.caption.bold())
                    let (preview, remaining) = truncatedItems(project.evaluationFocus, limitWhenCollapsed: 3, isExpanded: isExpanded)
                    ForEach(preview, id: \.self) { focus in
                        Text("• \(focus)")
                            .font(.caption)
                    }
                    if !isExpanded, remaining > 0 {
                        Text("• +\(remaining) more")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            if !project.evaluationSteps.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Evaluation steps")
                        .font(.caption.bold())
                    let (preview, remaining) = truncatedItems(project.evaluationSteps, limitWhenCollapsed: 3, isExpanded: isExpanded)
                    ForEach(preview, id: \.self) { step in
                        Text("• \(step)")
                            .font(.caption)
                    }
                    if !isExpanded, remaining > 0 {
                        Text("• +\(remaining) more")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func milestonePreview(for item: SequencedWorkItem, isExpanded: Bool, binding: Binding<Bool>) -> some View {
        let brief = item.milestoneBrief
        let project = item.milestoneProject ?? brief?.project
        let summaryText = project?.summary ?? brief?.summary ?? item.summary

        if let summary = summaryText, !summary.isEmpty {
            Text(summary)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .lineLimit(isExpanded ? nil : 3)
        }

        if let project, !project.deliverables.isEmpty {
            let (preview, remaining) = truncatedItems(project.deliverables, limitWhenCollapsed: 2, isExpanded: isExpanded)
            VStack(alignment: .leading, spacing: 2) {
                Text("Deliverables")
                    .font(.caption.bold())
                ForEach(preview, id: \.self) { deliverable in
                    Text("• \(deliverable)")
                        .font(.caption)
                }
                if !isExpanded, remaining > 0 {
                    Text("• +\(remaining) more")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }

        if let success = brief?.successCriteria, !success.isEmpty {
            let (preview, remaining) = truncatedItems(success, limitWhenCollapsed: 2, isExpanded: isExpanded)
            VStack(alignment: .leading, spacing: 2) {
                Text("Success criteria")
                    .font(.caption.bold())
                ForEach(preview, id: \.self) { item in
                    Text("• \(item)")
                        .font(.caption)
                }
                if !isExpanded, remaining > 0 {
                    Text("• +\(remaining) more")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }

        if let brief, !brief.eloFocus.isEmpty {
            HStack(spacing: 6) {
                let focuses = isExpanded ? brief.eloFocus : Array(brief.eloFocus.prefix(3))
                ForEach(focuses, id: \.self) { focus in
                    Text(focus)
                        .font(.caption2.bold())
                        .padding(.horizontal, 6)
                        .padding(.vertical, 3)
                        .background(Color.accentColor.opacity(0.12), in: Capsule())
                }
                if !isExpanded, brief.eloFocus.count > 3 {
                    Text("+\(brief.eloFocus.count - 3)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }

        if let project, !project.recommendedTools.isEmpty {
            HStack(spacing: 6) {
                let tools = isExpanded ? project.recommendedTools : Array(project.recommendedTools.prefix(3))
                        ForEach(tools, id: \.self) { tool in
                            Text(tool)
                                .font(.caption2.bold())
                                .padding(.horizontal, 6)
                                .padding(.vertical, 3)
                                .background(Color.accentColor.opacity(0.12), in: Capsule())
                }
                if !isExpanded, project.recommendedTools.count > 3 {
                    Text("+\(project.recommendedTools.count - 3)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }

        if let brief, let rationale = brief.rationale, !rationale.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text("Why this milestone")
                    .font(.caption.bold())
                Text(rationale)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .lineLimit(isExpanded ? nil : 2)
            }
        }

        if let brief, brief.source == "agent" || brief.authoredByModel != nil || brief.authoredAt != nil {
            HStack(spacing: 8) {
                if brief.source == "agent" {
                    Label("Agent-authored", systemImage: "sparkles")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if let model = brief.authoredByModel, !model.isEmpty {
                    Text(model)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if let effort = brief.reasoningEffort, !effort.isEmpty {
                    Text(effort.capitalized)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if let authoredAt = brief.authoredAt {
                    Text(authoredAt.formatted(date: .abbreviated, time: .shortened))
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
        }

        if let brief, !brief.warnings.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text("Notes")
                    .font(.caption.bold())
                ForEach(brief.warnings, id: \.self) { note in
                    Text("• \(note)")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
            }
        }

        let effectiveRequirements: [MilestoneRequirement] = {
            if !item.milestoneRequirements.isEmpty {
                return item.milestoneRequirements
            }
            return brief?.requirements ?? []
        }()

        let additionalProjectItems: Bool = {
            guard let project else { return false }
            if isExpanded { return false }
            return project.deliverables.count > 2
                || project.evidenceChecklist.count > 3
                || project.recommendedTools.count > 3
                || project.evaluationFocus.count > 3
                || project.evaluationSteps.count > 3
        }()

        let successHasMore = {
            guard let success = brief?.successCriteria else { return false }
            return !isExpanded && success.count > 2
        }()

        let detailSectionsAvailable = {
            guard let brief else { return false }
            return !brief.externalWork.isEmpty
                || !brief.capturePrompts.isEmpty
                || !brief.resources.isEmpty
                || !brief.prerequisites.isEmpty
                || !effectiveRequirements.isEmpty
        }()

        if !effectiveRequirements.isEmpty && !isExpanded {
            let unmet = effectiveRequirements.filter { !requirementStatus(for: $0).met }
            if let first = unmet.first {
                let status = requirementStatus(for: first)
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(.orange)
                    Text("Need \(first.minimumRating) in \(first.categoryLabel) • current \(status.current)")
                        .font(.caption2)
                        .foregroundStyle(.orange)
                        .lineLimit(1)
                }
            } else {
                Label("Requirements met", systemImage: "checkmark.circle")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }

        if isExpanded {
            if let project {
                projectSection(for: project, isExpanded: true)
            }
            milestoneDetailSections(
                brief: brief,
                prerequisites: brief?.prerequisites ?? [],
                requirements: effectiveRequirements
            )
            Button {
                withAnimation { binding.wrappedValue = false }
            } label: {
                Label("Hide milestone brief", systemImage: "chevron.up.circle.fill")
                    .font(.caption.bold())
            }
            .buttonStyle(.plain)
        } else if additionalProjectItems || successHasMore || detailSectionsAvailable {
            Button {
                withAnimation { binding.wrappedValue = true }
            } label: {
                Label("Show full milestone brief", systemImage: "chevron.down.circle")
                    .font(.caption.bold())
            }
            .buttonStyle(.plain)
        }
    }

    @ViewBuilder
    private func milestoneDetailSections(
        brief: MilestoneBrief?,
        prerequisites: [MilestonePrerequisite],
        requirements: [MilestoneRequirement]
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if !prerequisites.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Prerequisites")
                        .font(.caption.bold())
                    ForEach(prerequisites) { prerequisite in
                        let status = SequencedWorkItem.LaunchStatus(rawValue: prerequisite.status) ?? .pending
                        HStack(spacing: 8) {
                            Image(systemName: statusIcon(for: status))
                                .font(.caption)
                            Text(prerequisite.title)
                                .font(.caption)
                            Spacer()
                            Text(status.label)
                                .font(.caption2)
                                .foregroundStyle(statusColor(for: status))
                        }
                    }
                }
            }
            if !requirements.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Requirements")
                        .font(.caption.bold())
                    ForEach(requirements) { requirement in
                        let status = requirementStatus(for: requirement)
                        HStack(spacing: 8) {
                            Image(systemName: status.met ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                                .font(.caption)
                                .foregroundStyle(status.met ? Color.green : Color.orange)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(requirement.categoryLabel)
                                    .font(.caption)
                                Text("Need \(requirement.minimumRating) • Current \(status.current)")
                                    .font(.caption2)
                                    .foregroundStyle(status.met ? Color.secondary : Color.orange)
                                if let rationale = requirement.rationale, !rationale.isEmpty {
                                    Text(rationale)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
            if let brief, !brief.externalWork.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("External work")
                        .font(.caption.bold())
                    ForEach(brief.externalWork, id: \.self) { item in
                        Text("• \(item)")
                            .font(.caption)
                    }
                }
            }
            if let brief, !brief.capturePrompts.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Capture prompts")
                        .font(.caption.bold())
                    ForEach(brief.capturePrompts, id: \.self) { prompt in
                        Text("• \(prompt)")
                            .font(.caption)
                    }
                }
            }
            if let brief, !brief.resources.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Resources")
                        .font(.caption.bold())
                    ForEach(brief.resources, id: \.self) { resource in
                        Text("• \(resource)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding(.top, 4)
    }

    private func truncatedItems(_ items: [String], limitWhenCollapsed: Int, isExpanded: Bool) -> ([String], Int) {
        guard !items.isEmpty else { return ([], 0) }
        if isExpanded || items.count <= limitWhenCollapsed {
            return (items, 0)
        }
        let display = Array(items.prefix(limitWhenCollapsed))
        return (display, items.count - display.count)
    }

    private func formattedDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = .current
        if let tz = scheduleTimeZone {
            formatter.timeZone = tz
        }
        formatter.setLocalizedDateFormatFromTemplate("EEEE MMMM d")
        return formatter.string(from: date)
    }

    private func dayLabel(for group: CurriculumSchedule.Group) -> String {
        guard let date = group.date else {
            return fallbackLabel(for: group.offset)
        }
        let dateText = formattedDate(date)
        let tzAbbr = scheduleTimeZone?.abbreviation(for: date) ?? scheduleTimeZone?.abbreviation(for: Date())
        let fullDateText = tzAbbr.map { "\(dateText) (\($0))" } ?? dateText
        let tz = scheduleTimeZone ?? TimeZone.current
        var calendar = Calendar.current
        calendar.timeZone = tz
        let todayStart = calendar.startOfDay(for: Date())
        let targetStart = calendar.startOfDay(for: date)
        let diff = calendar.dateComponents([.day], from: todayStart, to: targetStart).day ?? group.offset
        let prefix: String
        switch diff {
        case 0:
            prefix = "Today • "
        case 1:
            prefix = "Tomorrow • "
        default:
            prefix = ""
        }
        return prefix.isEmpty ? fullDateText : prefix + fullDateText
    }

    private func fallbackLabel(for offset: Int) -> String {
        switch offset {
        case ..<0:
            return "Backlog"
        case 0:
            return "Today"
        case 1:
            return "Tomorrow"
        default:
            return "Day \(offset + 1)"
        }
    }

    private func rowBackground(for item: SequencedWorkItem) -> Color {
        switch item.launchStatus {
        case .completed:
            return Color.green.opacity(0.12)
        case .inProgress:
            return Color.blue.opacity(0.10)
        case .pending:
            return item.userAdjusted ? Color.accentColor.opacity(0.08) : Color.primary.opacity(0.04)
        }
    }

    private func projectStatusLabel(_ rawValue: String) -> String {
        switch rawValue {
        case "":
            return "Not set"
        case "not_started":
            return "Not started"
        case "building":
            return "Building"
        case "ready_for_review":
            return "Ready for review"
        case "blocked":
            return "Blocked"
        case "completed":
            return "Completed"
        default:
            return rawValue.capitalized
        }
    }

    private func progressStatusColor(_ rawValue: String) -> Color {
        switch rawValue {
        case "completed":
            return .green
        case "ready_for_review":
            return .blue
        case "building":
            return .accentColor
        case "blocked":
            return .red
        default:
            return .secondary
        }
    }

    private func evaluationOutcomeLabel(_ rawValue: String?) -> String? {
        guard let value = rawValue, !value.isEmpty else {
            return nil
        }
        switch value {
        case "passed":
            return "Passed"
        case "needs_revision":
            return "Needs revision"
        case "failed":
            return "Failed"
        default:
            return value.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private func evaluationOutcomeColor(_ rawValue: String?) -> Color {
        guard let value = rawValue else {
            return .secondary
        }
        switch value {
        case "passed":
            return .green
        case "needs_revision":
            return .orange
        case "failed":
            return .red
        default:
            return .secondary
        }
    }


    @ViewBuilder
    private func statusBadge(for item: SequencedWorkItem) -> some View {
        let color = statusColor(for: item.launchStatus)
        Label(item.launchStatus.label, systemImage: statusIcon(for: item.launchStatus))
            .font(.caption.bold())
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(color.opacity(0.15), in: Capsule())
            .foregroundStyle(color)
    }

    @ViewBuilder
    private func launchButton(for item: SequencedWorkItem) -> some View {
        Button {
            launchAction(item, false)
        } label: {
            if launchingItemId == item.itemId {
                ProgressView()
                    .controlSize(.small)
            } else {
                Label(launchButtonTitle(for: item), systemImage: launchButtonIcon(for: item))
                    .font(.callout.bold())
            }
        }
        .buttonStyle(.borderedProminent)
        .disabled(isRefreshing || launchingItemId == item.itemId)
        .accessibilityLabel("\(launchButtonTitle(for: item)) \(item.title)")
    }

    @ViewBuilder
    private func completeButton(for item: SequencedWorkItem) -> some View {
        Button {
            completeAction(item)
        } label: {
            if completingItemId == item.itemId {
                ProgressView()
                    .controlSize(.small)
            } else {
                Label("Mark complete", systemImage: "checkmark.circle")
                    .font(.callout)
            }
        }
        .buttonStyle(.bordered)
        .disabled(isRefreshing || completingItemId == item.itemId)
        .accessibilityLabel("Mark \(item.title) as complete")
    }

    private func launchButtonTitle(for item: SequencedWorkItem) -> String {
        switch item.launchStatus {
        case .pending:
            return item.kind == .milestone ? "Start milestone" : "Start"
        case .inProgress:
            return "Resume"
        case .completed:
            return "Revisit"
        }
    }

    private func launchButtonIcon(for item: SequencedWorkItem) -> String {
        switch item.launchStatus {
        case .pending:
            return "play.fill"
        case .inProgress:
            return "arrow.triangle.2.circlepath"
        case .completed:
            return "arrow.clockwise"
        }
    }

    private func statusColor(for status: SequencedWorkItem.LaunchStatus) -> Color {
        switch status {
        case .pending:
            return .secondary
        case .inProgress:
            return .blue
        case .completed:
            return .green
        }
    }

    private func statusIcon(for status: SequencedWorkItem.LaunchStatus) -> String {
        switch status {
        case .pending:
            return "circle.dotted"
        case .inProgress:
            return "bolt.circle"
        case .completed:
            return "checkmark.circle.fill"
        }
    }

    private func alertMessage(for event: LearnerTelemetryEvent) -> String {
        let title = payloadValue(event.payload, keys: ["title", "item_id", "itemId"]) ?? "Milestone"
        switch event.eventType {
        case "schedule_launch_completed":
            return "\(title): completion recorded without notes or artefacts."
        case "milestone_completion_recorded":
            let attachments = Int(payloadValue(event.payload, keys: ["attachment_count", "attachmentCount"]) ?? "0") ?? 0
            let links = Int(payloadValue(event.payload, keys: ["link_count", "linkCount"]) ?? "0") ?? 0
            let hasNotes = payloadValue(event.payload, keys: ["has_notes", "hasNotes"])?.lowercased() == "true"
            var components: [String] = []
            if !hasNotes { components.append("add notes") }
            if attachments == 0 { components.append("upload attachments") }
            if links == 0 { components.append("link artefacts") }
            if components.isEmpty {
                return "\(title): milestone ready for review."
            }
            return "\(title): " + components.joined(separator: ", ")
        default:
            return title
        }
    }

    private func effortColor(for level: SequencedWorkItem.EffortLevel) -> Color {
        switch level {
        case .light:
            return .green
        case .moderate:
            return .blue
        case .focus:
            return .orange
        }
    }

    private func payloadValue(_ payload: [String: String], keys: [String]) -> String? {
        for key in keys {
            if let value = payload[key] {
                return value
            }
        }
        return nil
    }

    private func categoryName(for key: String) -> String {
        if let label = categoryLabels[key], !label.isEmpty {
            return label
        }
        return key.replacingOccurrences(of: "-", with: " ").capitalized
    }

    private func pressureColor(for pressure: CategoryPacingAllocation.Pressure) -> Color {
        switch pressure {
        case .low:
            return .green
        case .medium:
            return .orange
        case .high:
            return .red
        }
    }
}
