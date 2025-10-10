import SwiftUI

struct WidgetListView: View {
    let props: WidgetListProps
    @EnvironmentObject private var settings: AppSettings

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let title = props.title {
                Text(title).font(.headline)
            }
            ForEach(props.rows, id: \.label) { row in
                HStack {
                    VStack(alignment: .leading) {
                        Text(row.label)
                        if let meta = row.meta {
                            Text(meta).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    if let href = row.href, let url = URL(string: href) {
                        Link("Open", destination: url)
                            .accessibilityLabel("Open \(row.label)")
                    }
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(settings.highContrast ? Color("HighContrast") : Color.secondary.opacity(0.1), in: RoundedRectangle(cornerRadius: 8))
            }
        }
        .padding(8)
    }
}
