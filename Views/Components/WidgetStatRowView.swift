import SwiftUI

struct WidgetStatRowView: View {
    let props: WidgetStatRowProps
    @EnvironmentObject private var settings: AppSettings

    var body: some View {
        LazyVGrid(columns: gridColumns, alignment: .leading, spacing: 12) {
            ForEach(props.items, id: \.label) { item in
                statCard(for: item)
            }
        }
        .accessibilityElement(children: .contain)
    }

    private var gridColumns: [GridItem] {
        let requested = props.itemsPerRow ?? defaultColumns
        let columnCount = max(1, min(requested, props.items.count))
        return Array(
            repeating: GridItem(
                .flexible(minimum: 160, maximum: 260),
                spacing: 12,
                alignment: .top
            ),
            count: columnCount
        )
    }

    private var defaultColumns: Int {
        let count = props.items.count
        switch count {
        case 0: return 1
        case 1...3: return count
        default: return 4
        }
    }

    @ViewBuilder
    private func statCard(for item: WidgetStatItem) -> some View {
        VStack(spacing: 4) {
            Text(item.value)
                .font(.system(size: 22, weight: .bold))
            Text(item.label)
                .font(.caption)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, minHeight: 72)
        .padding(12)
        .background(
            settings.highContrast ? Color("HighContrast") : Color.secondary.opacity(0.15),
            in: RoundedRectangle(cornerRadius: 10)
        )
    }
}
