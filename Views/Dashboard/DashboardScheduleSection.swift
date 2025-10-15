import SwiftUI

struct DashboardScheduleSection: View {
    let schedule: CurriculumSchedule?
    let categoryLabels: [String:String]
    let isRefreshing: Bool
    let isLoadingNextSlice: Bool
    let adjustingItemId: String?
    let refreshAction: () -> Void
    let adjustAction: (SequencedWorkItem, Int) -> Void
    let loadMoreAction: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if let schedule, !schedule.items.isEmpty {
                CurriculumScheduleView(
                    schedule: schedule,
                    categoryLabels: categoryLabels,
                    isRefreshing: isRefreshing,
                    isLoadingNextSlice: isLoadingNextSlice,
                    adjustingItemId: adjustingItemId,
                    refreshAction: refreshAction,
                    adjustAction: adjustAction,
                    loadMoreAction: loadMoreAction
                )
                .transition(.opacity)
            } else {
                VStack(spacing: 12) {
                    Label("Schedule not ready", systemImage: "calendar.badge.exclamationmark")
                        .font(.title3.bold())
                        .foregroundStyle(.primary)
                    Text("Arcadia Coach will generate your roadmap after onboarding completes and grading finishes.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 420)
                    Button(action: refreshAction) {
                        Label("Check for schedule", systemImage: "arrow.clockwise")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isRefreshing)
                }
                .frame(maxWidth: .infinity)
                .padding(.top, 80)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
