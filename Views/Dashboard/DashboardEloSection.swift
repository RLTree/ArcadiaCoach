import SwiftUI

struct DashboardEloSection: View {
    @EnvironmentObject private var settings: AppSettings
    @EnvironmentObject private var appVM: AppViewModel

    let eloItems: [WidgetStatItem]
    let latestAssessmentGradeTimestamp: Date?
    let latestSubmissionTimestamp: Date?
    private let clipboard: ClipboardManaging = AppClipboardManager.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if !settings.minimalMode && !eloItems.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Label("Current ELO Ratings", systemImage: "chart.bar")
                        .font(.subheadline.bold())
                        .foregroundStyle(.primary)
                        .selectableContent()
                        .contextMenu {
                            Button("Copy Heading") { clipboard.copy("Current ELO Ratings") }
                        }
                    if let stamp = latestAssessmentGradeTimestamp {
                        Text("Calibrated \(stamp.formatted(date: .abbreviated, time: .shortened))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .selectableContent()
                    } else if let pending = latestSubmissionTimestamp {
                        Text("Awaiting grading for submission on \(pending.formatted(date: .abbreviated, time: .shortened))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .selectableContent()
                    }
                    WidgetStatRowView(props: .init(items: eloItems, itemsPerRow: 4))
                        .environmentObject(settings)
                }
                .selectableContent()
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
        .selectableContent()
        .contextMenu {
            Button("Copy ELO summary") {
                clipboard.copy(eloSummary())
            }
        }
    }

    private func eloSummary() -> String {
        var lines: [String] = []
        if !eloItems.isEmpty {
            lines.append("Current ELO Ratings:")
            for item in eloItems {
                lines.append("• \(item.label): \(item.value)")
            }
        }
        if let stamp = latestAssessmentGradeTimestamp {
            lines.append("Calibrated: \(stamp.formatted(date: .abbreviated, time: .shortened))")
        } else if let pending = latestSubmissionTimestamp {
            lines.append("Awaiting grading for submission on \(pending.formatted(date: .abbreviated, time: .shortened))")
        }

        if let plan = appVM.eloPlan {
            lines.append("Active categories: \(plan.categories.map { $0.label }.joined(separator: ", "))")
        }

        if !appVM.foundationTracks.isEmpty {
            lines.append("Foundation tracks: \(appVM.foundationTracks.map { $0.label }.joined(separator: ", "))")
        }

        return lines.joined(separator: "\n")
    }
}
