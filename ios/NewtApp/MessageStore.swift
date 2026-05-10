import Foundation
import Combine

/// Persists Newt's chat history to a JSON file in Documents/.
/// Survives app relaunch. Capped at MAX_MESSAGES so it never blows up.
@MainActor
final class MessageStore: ObservableObject {
    @Published var messages: [Message] = []

    /// In-progress streamed text from Newt. Renders as a temporary bubble
    /// at the bottom of the chat while the stream is active. When the
    /// stream finishes, call `commitStreaming()` to convert it to a real
    /// Message that gets persisted.
    @Published var streamingText: String?

    /// The most recent agentic-tool badge ("🔍 Searching the web…").
    /// Cleared when the next chunk of real text arrives.
    @Published var toolBadge: String?

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
        streamingText = nil
        save()
    }

    // MARK: - Streaming

    /// Begin a streaming reply (clears any in-progress one).
    func beginStreaming() {
        streamingText = ""
        toolBadge = nil
    }

    /// Append a chunk of streamed text. Clears any tool badge that was showing.
    func appendChunk(_ chunk: String) {
        streamingText = (streamingText ?? "") + chunk
        toolBadge = nil
    }

    /// Show a "Newt is doing X…" badge while the agentic loop runs a tool.
    func setToolBadge(_ badge: String?) {
        toolBadge = badge
    }

    /// Finalize the stream — convert the in-progress text to a real Message.
    func commitStreaming() {
        toolBadge = nil
        guard let text = streamingText, !text.isEmpty else {
            streamingText = nil
            return
        }
        append(Message(text: text, isUser: false))
        streamingText = nil
    }

    /// Cancel without saving (e.g. on error).
    func cancelStreaming() {
        streamingText = nil
        toolBadge = nil
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
