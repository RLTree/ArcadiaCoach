import SwiftUI

struct WidgetStatRowView: View {
    let props: WidgetStatRowProps
    @EnvironmentObject private var settings: AppSettings

    var body: some View {
        HStack(spacing: 12) {
            ForEach(props.items, id: \.label) { item in
                VStack(spacing: 4) {
                    Text(item.value).font(.system(size: 22, weight: .bold))
                    Text(item.label).font(.caption)
                }
                .frame(maxWidth: .infinity)
                .padding(12)
                .background(settings.highContrast ? Color("HighContrast") : Color.secondary.opacity(0.15), in: RoundedRectangle(cornerRadius: 10))
            }
        }
        .accessibilityElement(children: .contain)
    }
}
