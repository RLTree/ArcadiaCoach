import SwiftUI

struct GlassButton: View {
    var title: String
    var systemName: String
    var action: () -> Void
    var body: some View {
        Button(action: action) {
            Label(title, systemImage: systemName)
                .padding(.vertical, 10).padding(.horizontal, 14)
                .contentShape(RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityLabel(Text(title))
        .accessibilityHint(Text("Activates \(title)"))
        .frame(minWidth: 140)
    }
}
