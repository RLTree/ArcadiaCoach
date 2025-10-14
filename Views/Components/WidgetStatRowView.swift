import SwiftUI

struct WidgetStatRowView: View {
    let props: WidgetStatRowProps
    @EnvironmentObject private var settings: AppSettings

    var body: some View {
        LazyVStack(alignment: .leading, spacing: 12) {
            ForEach(Array(chunkedItems.enumerated()), id: \.offset) { _, row in
                HStack(spacing: 12) {
                    ForEach(row, id: \.offset) { element in
                        statCard(for: element.element)
                    }
                }
            }
        }
        .accessibilityElement(children: .contain)
    }

    private typealias EnumeratedItem = EnumeratedSequence<[WidgetStatItem]>.Element

    private var chunkedItems: [[EnumeratedItem]] {
        let enumerated = Array(props.items.enumerated())
        let perRow = max(1, props.itemsPerRow ?? defaultColumns)
        guard perRow > 0 else { return [enumerated] }
        return stride(from: 0, to: enumerated.count, by: perRow).map { index in
            Array(enumerated[index ..< min(index + perRow, enumerated.count)])
        }
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
