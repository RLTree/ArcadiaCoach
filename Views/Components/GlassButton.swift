import SwiftUI

struct GlassButton: View {
    var title: String
    var systemName: String
    var isBusy: Bool = false
    var isDisabled: Bool = false
    var action: () -> Void

    var body: some View {
        let disabled = isBusy || isDisabled
        Button(action: action) {
            Label(title, systemImage: systemName)
                .padding(.vertical, 10).padding(.horizontal, 14)
                .contentShape(RoundedRectangle(cornerRadius: 12))
                .overlay(alignment: .trailing) {
                    if isBusy {
                        ProgressView()
                            .controlSize(.small)
                            .padding(.trailing, 6)
                    }
                }
        }
        .buttonStyle(.plain)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityLabel(Text(title))
        .accessibilityHint(Text(disabled ? "\(title) is busy" : "Activates \(title)"))
        .frame(minWidth: 140)
        .disabled(disabled)
        .opacity(disabled ? 0.6 : 1.0)
    }
}
