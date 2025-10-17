import SwiftUI

struct DashboardMilestonesSection: View {
    let queue: [MilestoneQueueEntry]
    let scheduleItems: [SequencedWorkItem]
    let categoryLabels: [String:String]
    let isRefreshing: Bool
    let launchingItemId: String?
    let completingItemId: String?
    let refreshAction: () -> Void
    let launchAction: (SequencedWorkItem, Bool) -> Void
    let completeAction: (SequencedWorkItem) -> Void

    private var itemsById: [String:SequencedWorkItem] {
        Dictionary(uniqueKeysWithValues: scheduleItems.map { ($0.itemId, $0) })
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            header
            if queue.isEmpty {
                emptyState
            } else {
                ForEach(queue) { entry in
                    milestoneCard(for: entry)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .selectableContent()
    }

    @ViewBuilder
    private var header: some View {
        HStack {
            Label("Milestone Queue", systemImage: "flag.checkered")
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
            .accessibilityLabel("Refresh milestone queue")
        }
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 12) {
            Label("Milestones not available yet", systemImage: "calendar.badge.clock")
                .font(.title3.bold())
                .foregroundStyle(.primary)
            Text("Milestones will appear once Arcadia Coach finishes sequencing your first roadmap slice and prerequisites.")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 420)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 60)
    }

    @ViewBuilder
    private func milestoneCard(for entry: MilestoneQueueEntry) -> some View {
        let readiness = entry.readinessState.lowercased()
        let item = itemsById[entry.itemId]
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(entry.title)
                        .font(.title3.weight(.semibold))
                    Text(categoryLabels[entry.categoryKey] ?? entry.categoryKey)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let summary = entry.summary, !summary.isEmpty {
                        Text(summary)
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer()
                readinessBadge(for: readiness)
            }
            if !entry.badges.isEmpty {
                HStack(spacing: 8) {
                    ForEach(entry.badges, id: \.self) { badge in
                        Text(badge)
                            .font(.caption.bold())
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.accentColor.opacity(0.12), in: Capsule())
                    }
                }
            }
            if !entry.requirements.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Requirements")
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                    ForEach(entry.requirements) { requirement in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(requirement.categoryLabel)
                                    .font(.caption.weight(.semibold))
                                Spacer()
                                Text("\(requirement.currentRating) / \(requirement.minimumRating)")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            ProgressView(value: min(requirement.progressPercent, 1.0))
                                .tint(requirement.currentRating >= requirement.minimumRating ? Color.green : Color.orange)
                        }
                    }
                }
            }
            if let lockReason = entry.launchLockedReason, !lockReason.isEmpty {
                Label(lockReason, systemImage: "lock.fill")
                    .font(.caption)
                    .foregroundStyle(Color.orange)
            }
            if !entry.warnings.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(entry.warnings, id: \.self) { warning in
                        Label(warning, systemImage: "exclamationmark.triangle.fill")
                            .font(.caption)
                            .foregroundStyle(Color.red)
                    }
                }
            }
            if !entry.nextActions.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Next actions")
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                    ForEach(entry.nextActions, id: \.self) { action in
                        Text("• \(action)")
                            .font(.caption)
                    }
                }
            }
            actionRow(for: entry, item: item)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(cardBackground(for: readiness), in: RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(borderColor(for: readiness), lineWidth: 1)
        )
    }

    @ViewBuilder
    private func readinessBadge(for readiness: String) -> some View {
        let (label, color, symbol): (String, Color, String) = {
            switch readiness {
            case "ready":
                return ("Ready", .green, "checkmark.circle.fill")
            case "in_progress":
                return ("In progress", .blue, "hourglass")
            case "completed":
                return ("Completed", .primary, "checkmark.seal.fill")
            default:
                return ("Locked", .orange, "lock.fill")
            }
        }()
        Label(label, systemImage: symbol)
            .font(.caption.bold())
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(color.opacity(0.15), in: Capsule())
            .foregroundStyle(color)
    }

    @ViewBuilder
    private func actionRow(for entry: MilestoneQueueEntry, item: SequencedWorkItem?) -> some View {
        HStack(spacing: 12) {
            if let item {
                launchButtons(for: entry, item: item)
                if item.launchStatus == .inProgress {
                    if completingItemId == item.itemId {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Button {
                            completeAction(item)
                        } label: {
                            Label("Mark complete", systemImage: "checkmark.circle")
                        }
                        .buttonStyle(.bordered)
                        .accessibilityLabel("Mark \(entry.title) complete")
                    }
                }
            } else {
                Text("Milestone not found in current schedule.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let updated = entry.lastUpdatedAt {
                Text(updated, style: .relative)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func launchButtons(for entry: MilestoneQueueEntry, item: SequencedWorkItem) -> some View {
        let readiness = entry.readinessState.lowercased()
        let actionLabel = readiness == "in_progress" ? "Resume" : "Launch"
        if launchingItemId == item.itemId {
            ProgressView()
                .controlSize(.small)
        } else {
            Button {
                launchAction(item, false)
            } label: {
                Label(
                    actionLabel,
                    systemImage: readiness == "in_progress" ? "play.circle" : "flag"
                )
            }
            .buttonStyle(.borderedProminent)
            .disabled(readiness == "locked")
            .accessibilityLabel("\(actionLabel) \(entry.title)")
            if let lockReason = entry.launchLockedReason,
               readiness == "locked",
               entry.requirements.allSatisfy({ $0.currentRating >= $0.minimumRating }) {
                Button {
                    launchAction(item, true)
                } label: {
                    Label("Override lock", systemImage: "exclamationmark.shield")
                }
                .buttonStyle(.bordered)
                .foregroundStyle(Color.orange)
                .accessibilityLabel("Override lock for \(entry.title)")
                .help(lockReason)
            }
        }
    }

    private func cardBackground(for readiness: String) -> Color {
        switch readiness {
        case "ready":
            return Color.green.opacity(0.08)
        case "in_progress":
            return Color.blue.opacity(0.08)
        case "completed":
            return Color.secondary.opacity(0.08)
        default:
            return Color.orange.opacity(0.08)
        }
    }

    private func borderColor(for readiness: String) -> Color {
        switch readiness {
        case "ready":
            return Color.green.opacity(0.25)
        case "in_progress":
            return Color.blue.opacity(0.25)
        case "completed":
            return Color.secondary.opacity(0.2)
        default:
            return Color.orange.opacity(0.25)
        }
    }
}
