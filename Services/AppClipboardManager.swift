import AppKit

@MainActor
protocol ClipboardManaging {
    func copy(_ string: String)
}

@MainActor
final class AppClipboardManager: ClipboardManaging {
    static let shared = AppClipboardManager()

    private let pasteboard: NSPasteboard

    init(pasteboard: NSPasteboard = .general) {
        self.pasteboard = pasteboard
    }

    func copy(_ string: String) {
        pasteboard.clearContents()
        pasteboard.setString(string, forType: .string)
    }
}
