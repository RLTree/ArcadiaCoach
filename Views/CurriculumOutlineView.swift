import SwiftUI

struct CurriculumOutlineView: View {
    var plan: OnboardingCurriculumPlan

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Onboarding Curriculum")
                .font(.headline)
            Text(plan.overview)
                .font(.body)
            if !plan.modules.isEmpty {
                ForEach(plan.modules) { module in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(module.title)
                                .font(.subheadline)
                                .bold()
                            Spacer()
                            Text(module.formattedDuration)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Text(module.summary)
                            .font(.footnote)
                        if !module.objectives.isEmpty {
                            Text("Objectives: \(module.objectives.joined(separator: ", "))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(12)
                    .background(Color.primary.opacity(0.03), in: RoundedRectangle(cornerRadius: 12))
                }
            }
        }
        .padding(16)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 20))
    }
}
