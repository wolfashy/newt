import Foundation
import Combine

/// Persists Newt's chat history to a JSON file in Documents/.
/// Survives app relaunch. Capped at MAX_MESSAGES so it never blows up.
@MainActor
final class MessageStore: ObservableObject {
    @Published var messages: [Message] = []

    private let fileURL: URL
    private static let MAX_MESSAGES = 500

    init() {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        self.fileURL = docs.appendingPathComponent("newt-history.json")
        load()
    }

    // MARK: - Public API

    func append(_ message: Message) {
        messages.append(message)
        if messages.count > Self.MAX_MESSAGES {
            messages.removeFirst(messages.count - Self.MAX_MESSAGES)
        }
        save()
    }

    func clear() {
        messages.removeAll()
        save()
    }

    // MARK: - Persistence

    private func load() {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return }
        do {
            let data = try Data(contentsOf: fileURL)
            let decoded = try JSONDecoder().decode([Message].self, from: data)
            self.messages = decoded
        } catch {
            print("MessageStore: failed to load history: \(error)")
        }
    }

    private func save() {
        do {
            let data = try JSONEncoder().encode(messages)
            try data.write(to: fileURL, options: [.atomic])
        } catch {
            print("MessageStore: failed to save history: \(error)")
        }
    }
}
