import SwiftUI

final class AppSettings: ObservableObject {
    @AppStorage("reduceMotion") var reduceMotion: Bool = true
    @AppStorage("highContrast") var highContrast: Bool = false
    @AppStorage("focusChunks") var focusChunks: Int = 3   // tasks per session
    @AppStorage("sessionMinutes") var sessionMinutes: Int = 25
    @AppStorage("fontScale") var fontScale: Double = 1.0
    @AppStorage("muteSounds") var muteSounds: Bool = true
    @AppStorage("minimalMode") var minimalMode: Bool = false
    @AppStorage("chatkitBackendURL") var chatkitBackendURL: String = ""
    @AppStorage("chatkitDomainKey") var chatkitDomainKey: String = ""
    @AppStorage("chatModel") var chatModel: String = "gpt-5"
    @AppStorage("chatWebSearchEnabled") var chatWebSearchEnabled: Bool = false
    @AppStorage("chatReasoningLevel") var chatReasoningLevel: String = "medium"
    @AppStorage("openaiApiKey") var openaiApiKey: String = ""
    @AppStorage("arcadiaUsername") var arcadiaUsername: String = ""
    @AppStorage("learnerGoal") var learnerGoal: String = ""
    @AppStorage("learnerUseCase") var learnerUseCase: String = ""
    @AppStorage("learnerStrengths") var learnerStrengths: String = ""
    @AppStorage("learnerTimezone") var learnerTimezone: String = TimeZone.current.identifier
}
