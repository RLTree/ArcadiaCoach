import SwiftUI

struct CurriculumScheduleView: View {
    let schedule: CurriculumSchedule
    let categoryLabels: [String:String]
    let isRefreshing: Bool
    let refreshAction: () -> Void

    private var dateLabelFormatter: DateComponentsFormatter {
        let formatter = DateComponentsFormatter()
        formatter.allowedUnits = [.day]
        formatter.unitsStyle = .spellOut
        return formatter
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
            ForEach(schedule.groupedItems, id: \.offset) { group in
                VStack(alignment: .leading, spacing: 10) {
                    Text(dayLabel(for: group.offset))
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
    }

    @ViewBuilder
    private func itemRow(for item: SequencedWorkItem) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Label(item.kind.label, systemImage: item.kind.systemImage)
                    .font(.subheadline.bold())
                Spacer()
                Text(item.formattedDuration)
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(effortColor(for: item.effortLevel).opacity(0.15), in: Capsule())
                    .foregroundStyle(effortColor(for: item.effortLevel))
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
        .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 14))
    }

    private func dayLabel(for offset: Int) -> String {
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
