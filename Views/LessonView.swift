import SwiftUI

struct LessonView: View {
    @EnvironmentObject private var settings: AppSettings
    let envelope: WidgetEnvelope

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            FocusTimerView()
                .environmentObject(settings)
                .padding(.bottom, 8)
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if let display = envelope.display {
                        Text(display)
                            .font(.title3)
                            .padding(.bottom, 8)
                    }
                    ForEach(envelope.widgets, id: \.self) { widget in
                        widgetView(for: widget)
                    }
                    if let citations = envelope.citations, !citations.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Citations")
                                .font(.headline)
                            ForEach(citations, id: \.self) { reference in
                                Text(reference).font(.footnote)
                            }
                        }
                        .padding(12)
                        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                    }
                }
                .padding(.horizontal, 8)
            }
        }
        .padding(10)
    }

    @ViewBuilder
    private func widgetView(for widget: Widget) -> some View {
                switch widget.type {
                case .Card:
                    if let props = widget.propsCard {
                        WidgetCardView(props: props)
                            .environmentObject(settings)
                    }
                case .List:
                    if let props = widget.propsList {
                        WidgetListView(props: props)
                            .environmentObject(settings)
                    }
                case .StatRow:
                    if let props = widget.propsStat {
                        WidgetStatRowView(props: props)
                            .environmentObject(settings)
                    }
                case .ArcadiaChatbot, .MiniChatbot:
                    if let props = widget.propsArcadiaChatbot {
                        WidgetArcadiaChatbotView(props: props)
                            .environmentObject(settings)
                    }
                }
            }
}
