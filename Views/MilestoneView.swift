import SwiftUI

struct MilestoneView: View {
    @EnvironmentObject private var settings: AppSettings
    let content: EndMilestone

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text(content.display)
                    .font(.title3)
                ForEach(content.widgets, id: \.self) { widget in
                    widgetView(for: widget)
                }
            }
            .padding(12)
        }
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
        case .MiniChatbot:
            EmptyView()
        }
    }
}
