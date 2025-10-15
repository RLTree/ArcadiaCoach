import SwiftUI

struct SelectableContentModifier: ViewModifier {
    let isEnabled: Bool

    @ViewBuilder
    func body(content: Content) -> some View {
        if isEnabled {
            if #available(macOS 12.0, *) {
                content.textSelection(.enabled)
            } else {
                content
            }
        } else {
            content
        }
    }
}

extension View {
    func selectableContent(_ isEnabled: Bool = true) -> some View {
        modifier(SelectableContentModifier(isEnabled: isEnabled))
    }
}
