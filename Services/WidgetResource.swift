import Foundation

enum WidgetResource {
    static func arcadiaChatbotWidgetBase64() -> String {
        guard let url = Bundle.main.url(forResource: "ArcadiaChatbot", withExtension: "widget", subdirectory: "Resources/Widgets") ?? Bundle.main.url(forResource: "ArcadiaChatbot", withExtension: "widget") else {
            return ""
        }
        guard let data = try? Data(contentsOf: url) else {
            return ""
        }
        return data.base64EncodedString()
    }
}
