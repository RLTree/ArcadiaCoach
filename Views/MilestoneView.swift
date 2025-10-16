import SwiftUI

struct MilestoneView: View {
    @EnvironmentObject private var settings: AppSettings
    let content: EndMilestone

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let header = sanitizedDisplay(from: content.display), !header.isEmpty {
                    Text(header)
                        .font(.title3)
                }
                ForEach(content.widgets, id: \.self) { widget in
                    widgetView(for: widget)
                }
            }
            .padding(12)
        }
    }

    private func sanitizedDisplay(from text: String) -> String? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let lines = trimmed.components(separatedBy: .newlines)
        let filtered = lines.filter { line in
            let lower = line.trimmingCharacters(in: .whitespaces).lowercased()
            guard !lower.isEmpty else { return false }
            return !(
                lower.hasPrefix("recommended duration") ||
                lower.hasPrefix("focus:") ||
                lower.hasPrefix("milestone brief") ||
                lower.hasPrefix("external work") ||
                lower.hasPrefix("capture prompts") ||
                lower.hasPrefix("success criteria")
            )
        }
        let result = filtered.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        return result.isEmpty ? nil : result
    }

    @ViewBuilder
    private func widgetView(for widget: Widget) -> some View {
        switch widget.type {
        case .Card:
            if let props = widget.propsCard {
                WidgetCardView(props: props).environmentObject(settings)
            }
        case .List:
            if let props = widget.propsList {
                WidgetListView(props: props).environmentObject(settings)
            }
        case .StatRow:
            if let props = widget.propsStat {
                WidgetStatRowView(props: props).environmentObject(settings)
            }
        case .ArcadiaChatbot, .MiniChatbot:
            if let props = widget.propsArcadiaChatbot {
                WidgetArcadiaChatbotView(props: props).environmentObject(settings)
            }
        }
    }
}
