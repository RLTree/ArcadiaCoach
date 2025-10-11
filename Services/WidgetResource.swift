import Foundation
import OSLog

enum WidgetResource {
    private static let logger = Logger(subsystem: "com.arcadiacoach.app", category: "WidgetResource")

    static func arcadiaChatbotWidgetBase64() -> String {
        logger.notice("ArcadiaChatbot.widget not bundled; relying on streamed widgets from the backend.")
        return ""
    }

    static var isArcadiaWidgetBundled: Bool {
        false
    }
}
