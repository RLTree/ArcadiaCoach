import SwiftUI

struct WidgetCardView: View {
    let props: WidgetCardProps
    @EnvironmentObject private var settings: AppSettings

    private struct ParsedSection: Identifiable {
        let id = UUID()
        let heading: String?
        let items: [ParsedItem]
    }

    private struct ParsedItem: Identifiable {
        let id = UUID()
        let text: String
    }

    private var backgroundStyle: some ShapeStyle {
        settings.highContrast ? AnyShapeStyle(Color("HighContrast")) : AnyShapeStyle(.ultraThinMaterial)
    }

    private var parsedContent: (title: String, sections: [ParsedSection], footnotes: [CitationFormatter.Group]) {
        var nextMarker = 1
        var footnotes: [CitationFormatter.Group] = []

        func parse(_ text: String) -> String {
            let result = CitationFormatter.parse(text, startingAt: nextMarker)
            nextMarker = result.nextMarker
            footnotes.append(contentsOf: result.groups)
            return result.displayText
        }

        let parsedTitle = parse(props.title)
        let parsedSections = (props.sections ?? []).map { section -> ParsedSection in
            let heading = section.heading.map(parse)
            let items = section.items.map { item -> ParsedItem in
                ParsedItem(text: parse(item))
            }
            return ParsedSection(heading: heading, items: items)
        }

        return (parsedTitle, parsedSections, footnotes)
    }

    var body: some View {
        let content = parsedContent
        VStack(alignment: .leading, spacing: 12) {
            Text(content.title).font(.title3).bold()
            ForEach(content.sections) { section in
                if let heading = section.heading {
                    Text(heading).font(.headline)
                }
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(section.items) { item in
                        Text("• \(item.text)").accessibilityLabel(item.text)
                    }
                }
            }
            if !content.footnotes.isEmpty {
                CitationFootnotesView(groups: content.footnotes)
            }
        }
        .padding(14)
        .background(backgroundStyle, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .combine)
        .selectableContent()
    }
}
