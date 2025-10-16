import SwiftUI

struct CurriculumScheduleView: View {
    let schedule: CurriculumSchedule
    let categoryLabels: [String:String]
    let milestoneCompletions: [MilestoneCompletion]
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
                        if let notes = completion.notes, !notes.isEmpty {
                            Text(notes)
                                .font(.caption)
                                .foregroundStyle(.primary)
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
                    ForEach(item.objectives, id: \.self) { objective in
                        Text("• \(objective)")
                            .font(.caption)
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

            if let brief = item.milestoneBrief {
                if !brief.prerequisites.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Prerequisites")
                            .font(.caption.bold())
                        ForEach(brief.prerequisites) { prerequisite in
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
                if !brief.externalWork.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("External Work")
                            .font(.caption.bold())
                        ForEach(brief.externalWork, id: \.self) { item in
                            Text("• \(item)")
                                .font(.caption)
                        }
                    }
                }
                if !brief.capturePrompts.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Capture Prompts")
                            .font(.caption.bold())
                        ForEach(brief.capturePrompts, id: \.self) { prompt in
                            Text("• \(prompt)")
                                .font(.caption)
                        }
                    }
                }
                if !brief.successCriteria.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Success Criteria")
                            .font(.caption.bold())
                        ForEach(brief.successCriteria, id: \.self) { criterion in
                            Text("• \(criterion)")
                                .font(.caption)
                        }
                    }
                }
                if !brief.eloFocus.isEmpty {
                    HStack(spacing: 6) {
                        ForEach(brief.eloFocus, id: \.self) { focus in
                            Text(focus)
                                .font(.caption2.bold())
                                .padding(.horizontal, 6)
                                .padding(.vertical, 3)
                                .background(Color.accentColor.opacity(0.12), in: Capsule())
                        }
                    }
                }
                if !brief.resources.isEmpty {
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
