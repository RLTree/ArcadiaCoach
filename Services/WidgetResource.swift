import Foundation
import OSLog

enum WidgetResource {
    private static let logger = Logger(subsystem: "com.arcadiacoach.app", category: "WidgetResource")

    static func arcadiaChatbotWidgetBase64() -> String {
        guard let url = Bundle.main.url(forResource: "ArcadiaChatbot", withExtension: "widget", subdirectory: "Resources/Widgets") ?? Bundle.main.url(forResource: "ArcadiaChatbot", withExtension: "widget") else {
            logger.error("ArcadiaChatbot.widget not found in bundle resources.")
            return ""
        }
        do {
            let data = try Data(contentsOf: url)
            logger.debug("Loaded ArcadiaChatbot.widget (\(data.count, privacy: .public) bytes)")
            return data.base64EncodedString()
        } catch {
            logger.error("Failed to load ArcadiaChatbot.widget: \(error.localizedDescription, privacy: .public)")
            return ""
        }
    }
}
