import SwiftUI

struct QuizSummaryView: View {
    @EnvironmentObject private var settings: AppSettings
    let elo: [String:Int]
    let widgets: [Widget]
    let last: EndQuiz.LastQuiz?

    private var sortedElo: [WidgetStatItem] {
        elo.sorted { $0.value > $1.value }.prefix(3).map { .init(label: $0.key, value: String($0.value)) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            FocusTimerView()
                .environmentObject(settings)
                .padding(.bottom, 8)
            WidgetStatRowView(props: .init(items: sortedElo))
                .environmentObject(settings)
            if let last {
                Text("Last quiz: \(last.topic ?? "–") • Score: \(Int((last.score ?? 0) * 100))%")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(widgets, id: \.self) { widget in
                        widgetView(for: widget)
                    }
                }
            }
        }
        .padding(10)
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
