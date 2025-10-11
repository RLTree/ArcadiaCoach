import XCTest
import Foundation
@testable import ArcadiaCoach

@MainActor
final class AgentChatViewModelTests: XCTestCase {
    func testExtractReplyPrefersDisplay() throws {
        let cardWidget = try makeCardWidget(title: "Card", sections: [])
        let widget = WidgetEnvelope(display: "Hello learner!", widgets: [cardWidget], citations: nil)
        XCTAssertEqual(AgentChatViewModel.extractReply(from: widget), "Hello learner!")
    }

    func testExtractReplyFallsBackToCardSections() throws {
        let section = WidgetCardSection(heading: "Focus", items: ["Item 1", "Item 2"])
        let cardWidget = try makeCardWidget(title: "Roadmap", sections: [section])
        let widget = WidgetEnvelope(display: nil, widgets: [cardWidget], citations: nil)
        let reply = AgentChatViewModel.extractReply(from: widget)
        XCTAssertTrue(reply.contains("Roadmap"))
        XCTAssertTrue(reply.contains("Item 1"))
        XCTAssertTrue(reply.contains("Item 2"))
    }

    func testExtractReplyArcadiaChatbot() throws {
        let widget = try makeChatWidget([
            ["id": "1", "role": "user", "text": "Hi"],
            ["id": "2", "role": "assistant", "text": "Hello!"],
        ])
        XCTAssertEqual(AgentChatViewModel.extractReply(from: widget), "Hello!")
    }

    // MARK: - Helpers

    private func makeCardWidget(title: String, sections: [WidgetCardSection]) throws -> Widget {
        let props: [String: Any] = [
            "title": title,
            "sections": sections.map { section in
                let headingValue: Any = section.heading ?? NSNull()
                return [
                    "heading": headingValue,
                    "items": section.items
                ]
            }
        ]
        return try decodeWidget(type: .Card, props: props)
    }

    private func makeChatWidget(_ messages: [[String: Any]]) throws -> WidgetEnvelope {
        let widget = try decodeWidget(
            type: .ArcadiaChatbot,
            props: [
                "title": "Arcadia Coach",
                "webEnabled": false,
                "showTonePicker": false,
                "level": "medium",
                "levelLabel": "Medium",
                "levels": [
                    ["value": "minimal", "label": "Minimal"],
                    ["value": "low", "label": "Low"],
                    ["value": "medium", "label": "Medium"],
                    ["value": "high", "label": "High"],
                ],
                "messages": messages,
                "placeholder": "Say hi"
            ]
        )
        return WidgetEnvelope(display: nil, widgets: [widget], citations: nil)
    }

    private func decodeWidget(type: WidgetType, props: [String: Any]) throws -> Widget {
        let raw: [String: Any] = [
            "type": type.rawValue,
            "props": props
        ]
        let data = try JSONSerialization.data(withJSONObject: raw)
        return try JSONDecoder().decode(Widget.self, from: data)
    }
}
