import SwiftUI

struct CurriculumScheduleView: View {
    let schedule: CurriculumSchedule
    let categoryLabels: [String:String]
    let isRefreshing: Bool
    let adjustingItemId: String?
    let refreshAction: () -> Void
    let adjustAction: (SequencedWorkItem, Int) -> Void

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

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            if schedule.isStale || !schedule.warnings.isEmpty {
                warningsSection
            }
            if let cadence = schedule.cadenceNotes, !cadence.isEmpty {
                Text(cadence)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
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
        }
        .padding(20)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
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
        }
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

            if !item.prerequisites.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Prerequisites")
                        .font(.caption.bold())
                    Text(item.prerequisites.joined(separator: ", "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
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
        return prefix.isEmpty ? dateText : prefix + dateText
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
        item.userAdjusted ? Color.accentColor.opacity(0.08) : Color.primary.opacity(0.04)
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
}
