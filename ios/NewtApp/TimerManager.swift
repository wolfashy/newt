import Foundation
import Combine
import UserNotifications

/// Schedules a local notification N seconds in the future. Fires even if
/// Newt is closed or backgrounded, with the system alert sound.
@MainActor
final class TimerManager: ObservableObject {
    static let shared = TimerManager()

    /// payload: {"seconds": Int, "label": "10 minutes"}
    func start(from payload: [String: Any], completion: @escaping (String) -> Void) {
        guard let seconds = (payload["seconds"] as? Double) ?? (payload["seconds"] as? Int).map(Double.init),
              seconds > 0 else {
            completion("Couldn't read the timer duration.")
            return
        }
        let label = (payload["label"] as? String) ?? "\(Int(seconds)) seconds"

        UNUserNotificationCenter.current().requestAuthorization(
            options: [.alert, .sound, .badge]
        ) { granted, _ in
            guard granted else {
                DispatchQueue.main.async {
                    completion("Notification permission denied — enable it in Settings → Newt.")
                }
                return
            }

            let content = UNMutableNotificationContent()
            content.title = "Newt timer"
            content.body  = "Your \(label) timer is up."
            content.sound = .default

            let trigger = UNTimeIntervalNotificationTrigger(
                timeInterval: max(1, seconds),  // UN won't accept 0
                repeats: false
            )
            let request = UNNotificationRequest(
                identifier: "newt-timer-\(UUID().uuidString)",
                content: content,
                trigger: trigger
            )

            UNUserNotificationCenter.current().add(request) { error in
                DispatchQueue.main.async {
                    if let error = error {
                        completion("Couldn't schedule timer: \(error.localizedDescription)")
                    } else {
                        completion("⏱ \(label) — I'll buzz you when it's up.")
                    }
                }
            }
        }
    }
}
