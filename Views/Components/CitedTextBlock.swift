import SwiftUI

struct CitedTextBlock: View {
    let text: String
    var textStyle: Font?

    var body: some View {
        let parsed = CitationFormatter.parse(text)
        VStack(alignment: .leading, spacing: 6) {
            if let textStyle {
                Text(parsed.displayText).font(textStyle)
            } else {
                Text(parsed.displayText)
            }
            if !parsed.groups.isEmpty {
                CitationFootnotesView(groups: parsed.groups)
            }
        }
        .selectableContent()
    }
}
