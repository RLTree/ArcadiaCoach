import XCTest
import SwiftUI
import AppKit
@testable import ArcadiaCoach

@MainActor
final class ClipboardSupportTests: XCTestCase {
    func testClipboardManagerCopiesString() {
        let name = NSPasteboard.Name("ArcadiaCoachTests-\(UUID().uuidString)")
        let pasteboard = NSPasteboard(name: name)
        let manager = AppClipboardManager(pasteboard: pasteboard)
        manager.copy("Hello world")

        let read = pasteboard.string(forType: .string)
        XCTAssertEqual(read, "Hello world")
    }

    func testSelectableContentModifierIsPresent() {
        let view = Text("Sample").selectableContent()
        let description = String(describing: view)
        XCTAssertTrue(description.contains("SelectableContentModifier"))
    }
}
