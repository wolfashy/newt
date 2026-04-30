import Foundation
import EventKit
import Combine

/// Bridges Newt's chat actions to the iOS Calendar / Reminders databases
/// via EventKit. All write/read operations are async — callbacks deliver a
/// human-readable summary that the chat appends as Newt's reply.
///
/// Action contract from the bridge:
///   {"action": {"create_reminder": {"title": "Call mom", "due": "2026-04-26T17:00:00"}}}
///   {"action": {"create_event":    {"title": "Standup",  "start": "...", "end": "...", "location": "Zoom"}}}
///   {"action": {"read_events":     {"range": "today"}}}
///   {"action": {"read_reminders":  {"list":  "incomplete"}}}
@MainActor
final class CalendarManager: ObservableObject {
    private let store = EKEventStore()

    // MARK: - Authorization helpers

    private func ensureEventAccess(_ completion: @escaping (Bool) -> Void) {
        if #available(iOS 17.0, *) {
            store.requestFullAccessToEvents { granted, _ in
                DispatchQueue.main.async { completion(granted) }
            }
        } else {
            store.requestAccess(to: .event) { granted, _ in
                DispatchQueue.main.async { completion(granted) }
            }
        }
    }

    private func ensureReminderAccess(_ completion: @escaping (Bool) -> Void) {
        if #available(iOS 17.0, *) {
            store.requestFullAccessToReminders { granted, _ in
                DispatchQueue.main.async { completion(granted) }
            }
        } else {
            store.requestAccess(to: .reminder) { granted, _ in
                DispatchQueue.main.async { completion(granted) }
            }
        }
    }

    // MARK: - Reminders (write)

    /// payload: {"title": "...", "due": "ISO8601 string", "notes": "optional"}
    func createReminder(from payload: [String: Any], completion: @escaping (String) -> Void) {
        ensureReminderAccess { [weak self] granted in
            guard let self = self, granted else {
                completion("Reminder access denied. Enable it in Settings → Newt.")
                return
            }
            guard let title = payload["title"] as? String, !title.isEmpty else {
                completion("Couldn't create reminder — no title.")
                return
            }

            let reminder = EKReminder(eventStore: self.store)
            reminder.title = title
            reminder.notes = payload["notes"] as? String
            reminder.calendar = self.store.defaultCalendarForNewReminders()

            if let dueString = payload["due"] as? String,
               let due = Self.parseDate(dueString) {
                reminder.dueDateComponents = Calendar.current.dateComponents(
                    [.year, .month, .day, .hour, .minute], from: due
                )
                let alarm = EKAlarm(absoluteDate: due)
                reminder.addAlarm(alarm)
            }

            do {
                try self.store.save(reminder, commit: true)
                completion("✓ Added \"\(title)\"\(Self.dueLabel(reminder))")
            } catch {
                completion("Failed to save reminder: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Calendar events (write)

    /// payload: {"title": "...", "start": "ISO8601", "end": "ISO8601", "location": "..."}
    func createEvent(from payload: [String: Any], completion: @escaping (String) -> Void) {
        ensureEventAccess { [weak self] granted in
            guard let self = self, granted else {
                completion("Calendar access denied. Enable it in Settings → Newt.")
                return
            }
            guard let title = payload["title"] as? String, !title.isEmpty,
                  let startStr = payload["start"] as? String,
                  let start = Self.parseDate(startStr) else {
                completion("Couldn't create event — title and start time required.")
                return
            }

            let end: Date
            if let endStr = payload["end"] as? String, let parsed = Self.parseDate(endStr) {
                end = parsed
            } else {
                end = start.addingTimeInterval(3600)  // default 1h
            }

            let event = EKEvent(eventStore: self.store)
            event.title = title
            event.startDate = start
            event.endDate = end
            event.location = payload["location"] as? String
            event.notes = payload["notes"] as? String
            event.calendar = self.store.defaultCalendarForNewEvents

            do {
                try self.store.save(event, span: .thisEvent, commit: true)
                let when = DateFormatter.newtFriendly.string(from: start)
                completion("✓ Scheduled \"\(title)\" for \(when)")
            } catch {
                completion("Failed to save event: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Calendar (read)

    /// payload: {"range": "today" | "tomorrow" | "week"}
    func fetchEvents(from payload: [String: Any], completion: @escaping (String) -> Void) {
        ensureEventAccess { [weak self] granted in
            guard let self = self, granted else {
                completion("Calendar access denied. Enable it in Settings → Newt.")
                return
            }

            let range = (payload["range"] as? String ?? "today").lowercased()
            let (start, end, label) = Self.dateRange(for: range)

            let predicate = self.store.predicateForEvents(
                withStart: start, end: end, calendars: nil
            )
            let events = self.store.events(matching: predicate)
                .sorted { $0.startDate < $1.startDate }

            if events.isEmpty {
                completion("Nothing on your calendar \(label).")
                return
            }

            let lines = events.prefix(10).map { ev -> String in
                let t = DateFormatter.newtTime.string(from: ev.startDate)
                let title = ev.title ?? "Untitled"
                if let loc = ev.location, !loc.isEmpty {
                    return "• \(t) — \(title) (\(loc))"
                }
                return "• \(t) — \(title)"
            }
            let header = "Here's \(label):"
            completion(([header] + lines).joined(separator: "\n"))
        }
    }

    /// payload: {"list": "incomplete" | "all" | "today"}
    func fetchReminders(from payload: [String: Any], completion: @escaping (String) -> Void) {
        ensureReminderAccess { [weak self] granted in
            guard let self = self, granted else {
                completion("Reminder access denied. Enable it in Settings → Newt.")
                return
            }

            let listType = (payload["list"] as? String ?? "incomplete").lowercased()
            let predicate: NSPredicate
            switch listType {
            case "today":
                let cal = Calendar.current
                let start = cal.startOfDay(for: Date())
                let end = cal.date(byAdding: .day, value: 1, to: start)!
                predicate = self.store.predicateForIncompleteReminders(
                    withDueDateStarting: start, ending: end, calendars: nil
                )
            case "all":
                predicate = self.store.predicateForReminders(in: nil)
            default:  // incomplete
                predicate = self.store.predicateForIncompleteReminders(
                    withDueDateStarting: nil, ending: nil, calendars: nil
                )
            }

            self.store.fetchReminders(matching: predicate) { reminders in
                DispatchQueue.main.async {
                    let items = reminders ?? []
                    if items.isEmpty {
                        completion("No reminders.")
                        return
                    }
                    let lines = items.prefix(10).map { r -> String in
                        if let due = r.dueDateComponents?.date {
                            let when = DateFormatter.newtFriendly.string(from: due)
                            return "• \(r.title ?? "Untitled") — \(when)"
                        }
                        return "• \(r.title ?? "Untitled")"
                    }
                    completion(("Reminders:" as String).appending("\n").appending(lines.joined(separator: "\n")))
                }
            }
        }
    }

    // MARK: - Helpers

    private static func parseDate(_ s: String) -> Date? {
        let isoFull = ISO8601DateFormatter()
        isoFull.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = isoFull.date(from: s) { return d }

        let isoBasic = ISO8601DateFormatter()
        isoBasic.formatOptions = [.withInternetDateTime]
        if let d = isoBasic.date(from: s) { return d }

        // Try without timezone (assume local)
        let local = DateFormatter()
        local.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        local.timeZone = .current
        if let d = local.date(from: s) { return d }

        return nil
    }

    private static func dueLabel(_ r: EKReminder) -> String {
        guard let date = r.dueDateComponents?.date else { return "" }
        return " for " + DateFormatter.newtFriendly.string(from: date)
    }

    private static func dateRange(for range: String) -> (Date, Date, String) {
        let cal = Calendar.current
        let now = Date()
        switch range {
        case "tomorrow":
            let s = cal.date(byAdding: .day, value: 1, to: cal.startOfDay(for: now))!
            let e = cal.date(byAdding: .day, value: 1, to: s)!
            return (s, e, "tomorrow")
        case "week", "this week":
            let s = cal.startOfDay(for: now)
            let e = cal.date(byAdding: .day, value: 7, to: s)!
            return (s, e, "this week")
        default:  // today
            let s = cal.startOfDay(for: now)
            let e = cal.date(byAdding: .day, value: 1, to: s)!
            return (s, e, "today")
        }
    }
}

// MARK: - Date formatters

private extension DateFormatter {
    static let newtFriendly: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .short
        return f
    }()

    static let newtTime: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "h:mm a"
        return f
    }()
}
