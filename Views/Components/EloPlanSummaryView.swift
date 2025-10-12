import SwiftUI

struct EloPlanSummaryView: View {
    let plan: EloCategoryPlan

    private var normalizedCategories: [(EloCategoryDefinition, Double)] {
        let total = plan.categories.map(\.weight).reduce(0.0, +)
        guard total > 0 else {
            let count = Double(plan.categories.count)
            guard count > 0 else { return [] }
            return plan.categories.map { ($0, 1.0 / count) }
        }
        return plan.categories.map { ($0, $0.weight / total) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Skill Focus Plan")
                    .font(.headline)
                Spacer()
                Text(plan.generatedAt.formatted(date: .abbreviated, time: .shortened))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let goal = plan.sourceGoal, !goal.isEmpty {
                Text("Aligned to: \(goal)")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            if let notes = plan.strategyNotes, !notes.isEmpty {
                Text(notes)
                    .font(.footnote)
            }
            ForEach(normalizedCategories, id: \.0.id) { category, weight in
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text(category.label)
                            .font(.subheadline)
                            .fontWeight(.semibold)
                        Spacer()
                        Text(weightPercentage(weight: weight))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Text(category.description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if !category.focusAreas.isEmpty {
                        Text("Focus: \(category.focusAreas.joined(separator: " • "))")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    if !category.rubric.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            ForEach(category.rubric, id: \.self) { band in
                                HStack(alignment: .firstTextBaseline, spacing: 6) {
                                    Text(band.level)
                                        .font(.caption2)
                                        .fontWeight(.bold)
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 2)
                                        .background(Color("Brand").opacity(0.15), in: Capsule())
                                    Text(band.descriptor)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
                .padding(12)
                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
            }
        }
        .padding(16)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16))
        .accessibilityElement(children: .combine)
    }

    private func weightPercentage(weight: Double) -> String {
        let percentage = (weight * 100).rounded()
        if percentage.isNaN || !percentage.isFinite {
            return "—"
        }
        return "\(Int(percentage))%"
    }
}
