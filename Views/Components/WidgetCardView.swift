import SwiftUI

struct WidgetCardView: View {
    let props: WidgetCardProps
    @EnvironmentObject private var settings: AppSettings

    private var backgroundStyle: some ShapeStyle {
        settings.highContrast ? AnyShapeStyle(Color("HighContrast")) : AnyShapeStyle(.ultraThinMaterial)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(props.title).font(.title3).bold()
            if let sections = props.sections {
                ForEach(sections, id: \.self) { section in
                    if let heading = section.heading {
                        Text(heading).font(.headline)
                    }
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(section.items, id: \.self) { item in
                            Text("• \(item)").accessibilityLabel(item)
                        }
                    }
                }
            }
        }
        .padding(14)
        .background(backgroundStyle, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .combine)
    }
}
