import Foundation

enum WidgetResource {
    static func miniChatbotWidgetBase64() -> String {
        guard let url = Bundle.main.url(forResource: "Mini_Chatbot", withExtension: "widget", subdirectory: "Resources/Widgets") ?? Bundle.main.url(forResource: "Mini_Chatbot", withExtension: "widget") else {
            return ""
        }
        guard let data = try? Data(contentsOf: url) else {
            return ""
        }
        return data.base64EncodedString()
    }
}
