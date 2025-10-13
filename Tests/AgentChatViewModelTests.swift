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

    func testUpdatePreferencesPersistsToHistory() throws {
        let suiteName = "AgentChatTests-" + UUID().uuidString
        guard let defaults = UserDefaults(suiteName: suiteName) else {
            XCTFail("Failed to create isolated UserDefaults")
            return
        }
        defaults.removePersistentDomain(forName: suiteName)
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let store = ChatHistoryStore(userDefaults: defaults)
        let viewModel = AgentChatViewModel(historyStore: store)
        viewModel.prepareWelcomeMessage(isBackendReady: true)
        viewModel.updatePreferences(webEnabled: true, reasoningLevel: "high")

        guard let summary = viewModel.recents.first else {
            XCTFail("Expected a transcript summary to be recorded")
            return
        }
        XCTAssertTrue(summary.webEnabled)
        XCTAssertEqual(summary.reasoningLevel, "high")

        let persisted = store.load()
        XCTAssertEqual(persisted.first?.reasoningLevel, "high")
    }

    func testAddAttachmentPersistsToHistory() throws {
        let suiteName = "AgentChatAttachment-" + UUID().uuidString
        guard let defaults = UserDefaults(suiteName: suiteName) else {
            XCTFail("Failed to create isolated UserDefaults")
            return
        }
        defaults.removePersistentDomain(forName: suiteName)
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let store = ChatHistoryStore(userDefaults: defaults)
        let viewModel = AgentChatViewModel(historyStore: store)
        viewModel.prepareWelcomeMessage(isBackendReady: true)

        let attachment = ChatAttachment(
            id: "file-1",
            name: "notes.md",
            mimeType: "text/markdown",
            size: 2048,
            preview: "A quick summary of the learner portfolio.",
            openAIFileId: nil
        )
        viewModel.addAttachment(attachment)
        XCTAssertEqual(viewModel.composerAttachments.count, 1)

        let message = ChatMessage(role: .user, text: "See attached.", attachments: viewModel.composerAttachments)
        viewModel.recordMessage(message)
        viewModel.composerAttachments.removeAll()

        let persisted = store.load()
        XCTAssertEqual(persisted.first?.attachments.first?.name, "notes.md")
    }

    func testApplyModelDisablesUnsupportedFeatures() throws {
        let viewModel = AgentChatViewModel(initialWebEnabled: true, initialReasoningLevel: "medium")
        viewModel.composerAttachments = [ChatAttachment(id: "file-1", name: "doc.txt", mimeType: "text/plain", size: 12, preview: nil, openAIFileId: nil)]
        viewModel.updatePreferences(webEnabled: true, reasoningLevel: "medium")

        let capability = ChatModelCapability(supportsWeb: true, attachmentPolicy: .imagesOnly)
        viewModel.applyModel("gpt-5-codex", capability: capability, backendURL: "")

        XCTAssertTrue(viewModel.modelSupportsWeb)
        XCTAssertTrue(viewModel.webSearchEnabled)
        XCTAssertTrue(viewModel.allowsImagesOnly)
        XCTAssertTrue(viewModel.composerAttachments.isEmpty)
    }

    func testCodexAllowsOnlyImageAttachments() throws {
        let viewModel = AgentChatViewModel(initialWebEnabled: true, initialReasoningLevel: "medium")
        let capability = ChatModelCapability(supportsWeb: true, attachmentPolicy: .imagesOnly)
        viewModel.applyModel("gpt-5-codex", capability: capability, backendURL: "")

        let imageAttachment = ChatAttachment(id: "img", name: "diagram.png", mimeType: "image/png", size: 1024, preview: nil, openAIFileId: nil)
        viewModel.addAttachment(imageAttachment)
        XCTAssertEqual(viewModel.composerAttachments.count, 1)

        let textAttachment = ChatAttachment(id: "txt", name: "notes.txt", mimeType: "text/plain", size: 64, preview: nil, openAIFileId: nil)
        viewModel.addAttachment(textAttachment)
        XCTAssertEqual(viewModel.composerAttachments.count, 1, "Non-image attachment should be rejected for Codex")
    }

    func testResumeTranscriptRestoresSessionState() throws {
        let suiteName = "AgentChatResume-" + UUID().uuidString
        guard let defaults = UserDefaults(suiteName: suiteName) else {
            XCTFail("Failed to create isolated UserDefaults")
            return
        }
        defaults.removePersistentDomain(forName: suiteName)
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let historyStore = ChatHistoryStore(userDefaults: defaults)
        let message = ChatTranscript.Message(role: "assistant", text: "Hello again!", sentAt: Date(), attachments: [])
        let transcript = ChatTranscript(
            id: "chat-existing",
            title: "Session Snapshot",
            startedAt: Date(),
            updatedAt: Date(),
            webEnabled: true,
            reasoningLevel: "high",
            model: "gpt-5-codex",
            messages: [message],
            attachments: []
        )
        historyStore.save([transcript])

        let viewModel = AgentChatViewModel(historyStore: historyStore)
        viewModel.resumeTranscript(
            transcript,
            modelId: "gpt-5-codex",
            capability: ChatModelCapability(supportsWeb: true, attachmentPolicy: .imagesOnly)
        )

        XCTAssertEqual(viewModel.selectedModel, "gpt-5-codex")
        XCTAssertEqual(viewModel.messages.count, 1)
        XCTAssertTrue(viewModel.webSearchEnabled)
        XCTAssertEqual(viewModel.attachmentPolicy, .imagesOnly)
        XCTAssertEqual(viewModel.activeTranscriptId, "chat-existing")
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
