import SwiftUI

struct DashboardEloSection: View {
    @EnvironmentObject private var settings: AppSettings
    @EnvironmentObject private var appVM: AppViewModel

    let eloItems: [WidgetStatItem]
    let latestAssessmentGradeTimestamp: Date?
    let latestSubmissionTimestamp: Date?

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if !settings.minimalMode && !eloItems.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Label("Current ELO Ratings", systemImage: "chart.bar")
                        .font(.subheadline.bold())
                        .foregroundStyle(.primary)
                    if let stamp = latestAssessmentGradeTimestamp {
                        Text("Calibrated \(stamp.formatted(date: .abbreviated, time: .shortened))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else if let pending = latestSubmissionTimestamp {
                        Text("Awaiting grading for submission on \(pending.formatted(date: .abbreviated, time: .shortened))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    WidgetStatRowView(props: .init(items: eloItems, itemsPerRow: 4))
                        .environmentObject(settings)
                }
            }

            if let plan = appVM.eloPlan, !plan.categories.isEmpty {
                EloPlanSummaryView(plan: plan)
                    .transition(.opacity)
            }

            if !appVM.foundationTracks.isEmpty {
                FoundationTracksCard(
                    tracks: appVM.foundationTracks,
                    goalSummary: appVM.goalInference?.summary,
                    targetOutcomes: appVM.goalInference?.targetOutcomes ?? []
                )
                .transition(.opacity)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
