import SwiftUI

struct FoundationTracksCard: View {
    var tracks: [FoundationTrackModel]
    var goalSummary: String?
    var targetOutcomes: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                Label("Foundation Tracks", systemImage: "target")
                    .font(.headline)
                Spacer()
            }
            if let trimmedSummary = goalSummary?.trimmingCharacters(in: .whitespacesAndNewlines),
               !trimmedSummary.isEmpty {
                Text(trimmedSummary)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            if !targetOutcomes.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Target outcomes")
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                    ForEach(targetOutcomes, id: \.self) { outcome in
                        HStack(alignment: .top, spacing: 6) {
                            Text("•")
                            Text(outcome)
                        }
                        .font(.caption)
                    }
                }
            }
            ForEach(tracks) { track in
                let technologies = track.technologies.joined(separator: ", ")
                let focusAreas = track.focusAreas.joined(separator: ", ")
                VStack(alignment: .leading, spacing: 6) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(track.label)
                            .font(.subheadline.weight(.semibold))
                        Spacer()
                        Text(track.priority.replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.caption.bold())
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(priorityColor(for: track.priority).opacity(0.18))
                            .foregroundStyle(priorityColor(for: track.priority))
                            .clipShape(Capsule())
                    }
                    if !technologies.isEmpty {
                        Text("Technologies: \(technologies)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if !focusAreas.isEmpty {
                        Text("Focus areas: \(focusAreas)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if let weeks = track.suggestedWeeks {
                        Text("Suggested duration: \(weeks) week\(weeks == 1 ? "" : "s")")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                    if let notes = track.notes?.trimmingCharacters(in: .whitespacesAndNewlines),
                       !notes.isEmpty {
                        Text(notes)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.primary.opacity(0.04))
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
        )
    }

    private func priorityColor(for priority: String) -> Color {
        switch priority.lowercased() {
        case "now":
            return .red
        case "up_next", "up-next":
            return .orange
        case "later":
            return .blue
        default:
            return .accentColor
        }
    }
}
