import UIKit
import Foundation

/// Tiny façade over UIKit's haptic generators. Prepares them lazily so the
/// first tap doesn't have a perceptible warm-up delay.
enum Haptics {
    /// Honors the user's "haptics enabled" preference.
    private static var enabled: Bool {
        UserDefaults.standard.object(forKey: "newt.haptics") as? Bool ?? true
    }

    private static let lightImpact  = UIImpactFeedbackGenerator(style: .light)
    private static let mediumImpact = UIImpactFeedbackGenerator(style: .medium)
    private static let rigidImpact  = UIImpactFeedbackGenerator(style: .rigid)
    private static let notification = UINotificationFeedbackGenerator()

    /// A subtle tick — for short interactions (button taps, mic engage).
    static func tick() {
        guard enabled else { return }
        lightImpact.prepare()
        lightImpact.impactOccurred(intensity: 0.6)
    }

    /// Stronger thump — for "you committed to something" (send, mic release).
    static func thump() {
        guard enabled else { return }
        mediumImpact.prepare()
        mediumImpact.impactOccurred()
    }

    /// Hard click — for delete / discard.
    static func click() {
        guard enabled else { return }
        rigidImpact.prepare()
        rigidImpact.impactOccurred()
    }

    static func success() {
        guard enabled else { return }
        notification.prepare()
        notification.notificationOccurred(.success)
    }

    static func warning() {
        guard enabled else { return }
        notification.prepare()
        notification.notificationOccurred(.warning)
    }

    static func error() {
        guard enabled else { return }
        notification.prepare()
        notification.notificationOccurred(.error)
    }
}
