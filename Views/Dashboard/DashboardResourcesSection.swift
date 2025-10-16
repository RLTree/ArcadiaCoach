import SwiftUI

struct DashboardResourcesSection: View {
    @EnvironmentObject private var appVM: AppViewModel

    let needsOnboarding: Bool
    let onRunOnboarding: () -> Void
    private let clipboard: ClipboardManaging = AppClipboardManager.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if let curriculum = appVM.curriculumPlan {
                CurriculumOutlineView(plan: curriculum)
                    .transition(.opacity)
            } else {
                Text("Curriculum outline unavailable. Run onboarding to generate your personalised roadmap.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .selectableContent()
                if needsOnboarding {
                    Button {
                        onRunOnboarding()
                    } label: {
                        Label("Run onboarding", systemImage: "person.fill.badge.plus")
                    }
                    .buttonStyle(.borderedProminent)
                }
            }

        if let plan = appVM.goalInference {
            FoundationTracksCard(
                tracks: plan.tracks,
                goalSummary: plan.summary,
                targetOutcomes: plan.targetOutcomes
            )
                .transition(.opacity)
        }

            if let summary = appVM.curriculumPlan?.overview, !summary.isEmpty {
                Text(summary)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .selectableContent()
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .selectableContent()
        .contextMenu {
            Button("Copy resources overview") {
                clipboard.copy(resourcesSummary())
            }
        }
    }

    private func resourcesSummary() -> String {
        var lines: [String] = []
        if let curriculum = appVM.curriculumPlan {
            lines.append("Curriculum outline available: \(curriculum.modules.count) modules")
        } else {
            lines.append("Curriculum outline unavailable")
        }
        if let inference = appVM.goalInference {
            lines.append("Goal parser tracks: \(inference.tracks.count)")
            if let summary = inference.summary, !summary.isEmpty {
                lines.append("Goal summary: \(summary)")
            }
            if !inference.targetOutcomes.isEmpty {
                lines.append("Target outcomes: \(inference.targetOutcomes.joined(separator: \", \"))")
            }
        }
        if let overview = appVM.curriculumPlan?.overview, !overview.isEmpty {
            lines.append("Overview: \(overview)")
        }
        return lines.joined(separator: "\n")
    }
}
