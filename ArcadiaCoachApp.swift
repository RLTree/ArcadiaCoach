import SwiftUI

@main
struct ArcadiaCoachApp: App {
    @StateObject var settings = AppSettings()
    @StateObject var appVM = AppViewModel()
    var body: some Scene {
        WindowGroup {
            HomeView()
                .environmentObject(settings)
                .environmentObject(appVM)
                .environment(\.sizeCategory, settings.fontScale >= 1.25 ? .accessibilityLarge : .large)
                .preferredColorScheme(settings.highContrast ? .dark : nil)
                .animation(settings.reduceMotion ? .none : .default, value: settings.reduceMotion)
        }
        .commands {
            CommandMenu("Session") {
                Button("Reset Focus Timer") {
                    NotificationCenter.default.post(name: .resetFocusTimer, object: nil)
                }
                .keyboardShortcut("r", modifiers: [.command, .option])
            }
        }
    }
}

extension Notification.Name {
    static let resetFocusTimer = Notification.Name("resetFocusTimer")
    static let developerResetCompleted = Notification.Name("developerResetCompleted")
}
