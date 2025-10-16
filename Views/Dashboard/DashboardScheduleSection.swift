import SwiftUI

struct DashboardScheduleSection: View {
    let schedule: CurriculumSchedule?
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
    private let clipboard: ClipboardManaging = AppClipboardManager.shared
    @State private var pendingLockedItem: SequencedWorkItem?

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if let schedule, !schedule.items.isEmpty {
                CurriculumScheduleView(
                    schedule: schedule,
                    categoryLabels: categoryLabels,
                    skillRatings: skillRatings,
                    milestoneCompletions: milestoneCompletions,
                    telemetryEvents: telemetryEvents,
                    isRefreshing: isRefreshing,
                    isLoadingNextSlice: isLoadingNextSlice,
                    adjustingItemId: adjustingItemId,
                    launchingItemId: launchingItemId,
                    completingItemId: completingItemId,
                    refreshAction: refreshAction,
                    adjustAction: adjustAction,
                    loadMoreAction: loadMoreAction,
                    launchAction: requestLaunch,
                    completeAction: completeAction
                )
                .transition(.opacity)
            } else {
                VStack(spacing: 12) {
                    Label("Schedule not ready", systemImage: "calendar.badge.exclamationmark")
                        .font(.title3.bold())
                        .foregroundStyle(.primary)
                        .selectableContent()
                    Text("Arcadia Coach will generate your roadmap after onboarding completes and grading finishes.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 420)
                        .selectableContent()
                    Button(action: refreshAction) {
                        Label("Check for schedule", systemImage: "arrow.clockwise")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isRefreshing)
                }
                .frame(maxWidth: .infinity)
                .padding(.top, 80)
                .contextMenu {
                    Button("Copy message") {
                        clipboard.copy("Schedule not ready — Arcadia Coach will generate your roadmap after onboarding completes and grading finishes.")
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .selectableContent()
        .contextMenu {
            Button("Copy schedule overview") {
                clipboard.copy(scheduleSummary())
            }
        }
        .confirmationDialog(
            pendingLockedItem?.launchLockedReason ?? "Unlock milestone?",
            isPresented: .init(
                get: { pendingLockedItem != nil },
                set: { value in if !value { pendingLockedItem = nil } }
            ),
            titleVisibility: .visible
        ) {
            if let item = pendingLockedItem {
                Button("Launch milestone anyway") {
                    launchAction(item, true)
                    pendingLockedItem = nil
                }
            }
            Button("Cancel", role: .cancel) {
                pendingLockedItem = nil
            }
        } message: {
            if let message = pendingLockedItem?.launchLockedReason {
                Text(message)
            }
        }
    }

    private func scheduleSummary() -> String {
        guard let schedule else {
            return "Schedule not ready"
        }

        var lines: [String] = []
        lines.append("Schedule generated: \(schedule.generatedAt.formatted(date: .abbreviated, time: .shortened))")
        lines.append("Horizon: \(schedule.timeHorizonDays) days")
        if let tz = schedule.timezone {
            lines.append("Timezone: \(tz)")
        }
        if let cadence = schedule.cadenceNotes, !cadence.isEmpty {
            lines.append("Cadence: \(cadence)")
        }

        let itemLines = schedule.items.prefix(8).map { item -> String in
            let day = item.recommendedDayOffset
            let label = item.kind.label
            let title = item.title
            return "Day \(day): \(label) – \(title)"
        }
        lines.append(contentsOf: itemLines)

        if schedule.items.count > itemLines.count {
            lines.append("…\(schedule.items.count - itemLines.count) more items")
        }

        return lines.joined(separator: "\n")
    }

    private func requestLaunch(_ item: SequencedWorkItem, force: Bool) {
        if !force, item.kind == .milestone, item.launchLockedReason != nil {
            pendingLockedItem = item
        } else {
            launchAction(item, force)
        }
    }
}
