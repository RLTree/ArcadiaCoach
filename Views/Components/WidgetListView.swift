import SwiftUI

struct WidgetListView: View {
    let props: WidgetListProps
    @EnvironmentObject private var settings: AppSettings

    private struct ParsedRow: Identifiable {
        let id = UUID()
        let label: String
        let meta: String?
        let href: String?
    }

    private var parsedContent: (title: String?, rows: [ParsedRow], footnotes: [CitationFormatter.Group]) {
        var nextMarker = 1
        var footnotes: [CitationFormatter.Group] = []

        func parse(_ text: String?) -> String? {
            guard let text else { return nil }
            let result = CitationFormatter.parse(text, startingAt: nextMarker)
            nextMarker = result.nextMarker
            footnotes.append(contentsOf: result.groups)
            return result.displayText
        }

        let title = parse(props.title)
        let rows = props.rows.map { row -> ParsedRow in
            ParsedRow(
                label: parse(row.label) ?? row.label,
                meta: parse(row.meta),
                href: row.href
            )
        }
        return (title, rows, footnotes)
    }

    var body: some View {
        let content = parsedContent
        VStack(alignment: .leading, spacing: 8) {
            if let title = content.title {
                Text(title).font(.headline)
            }
            ForEach(content.rows) { row in
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
            if !content.footnotes.isEmpty {
                CitationFootnotesView(groups: content.footnotes)
            }
        }
        .padding(8)
    }
}
