import Foundation
import OSLog

enum WidgetResource {
    private static let logger = Logger(subsystem: "com.arcadiacoach.app", category: "WidgetResource")

    struct ArcadiaWidgetDiagnostics: Equatable {
        let byteCount: Int
        let hasEncodedWidget: Bool
        let version: String?
        let name: String?
    }

    static func arcadiaChatbotWidgetBase64() -> String {
        guard let result = loadArcadiaChatbotWidget() else {
            return ""
        }
        let data = result.data
        let diagnostics = result.diagnostics
        if diagnostics.hasEncodedWidget {
            logger.debug("Loaded ArcadiaChatbot.widget (\(diagnostics.byteCount, privacy: .public) bytes, encodedWidget present)")
        } else {
            logger.notice("ArcadiaChatbot.widget missing encodedWidget payload; ChatKit will expect streamed widgets.")
        }
        return data.base64EncodedString()
    }

    static func arcadiaChatbotWidgetDiagnostics() -> ArcadiaWidgetDiagnostics? {
        guard let result = loadArcadiaChatbotWidget() else {
            return nil
        }
        return result.diagnostics
    }

    private static func loadArcadiaChatbotWidget() -> (data: Data, diagnostics: ArcadiaWidgetDiagnostics)? {
        guard let url = Bundle.main.url(forResource: "ArcadiaChatbot", withExtension: "widget", subdirectory: "Resources/Widgets") ?? Bundle.main.url(forResource: "ArcadiaChatbot", withExtension: "widget") else {
            logger.error("ArcadiaChatbot.widget not found in bundle resources.")
            return nil
        }
        do {
            let data = try Data(contentsOf: url)
            let diagnostics = inspectWidget(data: data) ?? ArcadiaWidgetDiagnostics(
                byteCount: data.count,
                hasEncodedWidget: false,
                version: nil,
                name: nil
            )
            return (data, diagnostics)
        } catch {
            logger.error("Failed to load ArcadiaChatbot.widget: \(error.localizedDescription, privacy: .public)")
            return nil
        }
    }

    private static func inspectWidget(data: Data) -> ArcadiaWidgetDiagnostics? {
        do {
            guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                logger.notice("Unable to parse ArcadiaChatbot.widget as JSON object.")
                return nil
            }
            let encodedWidget = (object["encodedWidget"] as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let version = object["version"] as? String
            let name = object["name"] as? String
            return ArcadiaWidgetDiagnostics(
                byteCount: data.count,
                hasEncodedWidget: !(encodedWidget?.isEmpty ?? true),
                version: version,
                name: name
            )
        } catch {
            logger.notice("Failed to inspect ArcadiaChatbot.widget: \(error.localizedDescription, privacy: .public)")
            return nil
        }
    }
}
