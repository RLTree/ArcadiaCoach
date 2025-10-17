import Foundation
import UserNotifications

final class MilestoneNotificationManager: NSObject, UNUserNotificationCenterDelegate {
    static let shared = MilestoneNotificationManager()

    private let center = UNUserNotificationCenter.current()
    private var didRequestAuthorization = false

    private override init() {
        super.init()
    }

    func requestAuthorizationIfNeeded() {
        guard !didRequestAuthorization else { return }
        didRequestAuthorization = true
        center.requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            if granted {
                self.center.delegate = self
            }
        }
    }

    func sendMilestoneReadyNotification(title: String, body: String, identifier: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default

        let request = UNNotificationRequest(
            identifier: "milestone-ready-\(identifier)",
            content: content,
            trigger: nil
        )

        center.add(request, withCompletionHandler: nil)
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound])
    }
}
