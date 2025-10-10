import SwiftUI

struct AssignmentView: View {
    @EnvironmentObject private var settings: AppSettings
    let envelope: WidgetEnvelope

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let display = envelope.display {
                    Text(display)
                        .font(.headline)
                }
                ForEach(envelope.widgets, id: \.self) { widget in
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
        }
    }
}
