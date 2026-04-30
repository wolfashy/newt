import Foundation
import AVFoundation
import UIKit
import Combine

/// Talks to the Newt Flask bridge running on your Mac at `newt:8001`
/// (Tailscale MagicDNS). Override with the `NEWT_HOST` env var on the
/// scheme if you ever need a different host (e.g. a LAN IP for testing).
final class NetworkManager: ObservableObject {
    static let shared = NetworkManager()

    /// Live connection status, observable from SwiftUI.
    enum ConnectionState { case unknown, online, offline }
    @Published private(set) var connection: ConnectionState = .unknown

    /// Whether Newt's cloned voice is allowed to play.
    var voiceMuted: Bool {
        get { UserDefaults.standard.bool(forKey: "newt.voiceMuted") }
        set { UserDefaults.standard.set(newValue, forKey: "newt.voiceMuted") }
    }

    /// Default uses Tailscale MagicDNS so the app works from anywhere on
    /// your tailnet (home, hotspot, coffee shop, etc.).
    var baseURL: String {
        if let saved = UserDefaults.standard.string(forKey: "newt.serverHost"),
           !saved.isEmpty {
            return saved
        }
        if let override = ProcessInfo.processInfo.environment["NEWT_HOST"], !override.isEmpty {
            return override
        }
        return "http://newt:8001"
    }

    private var audioPlayer: AVPlayer?

    // MARK: - Health check

    /// Pings /health. Updates `connection` and calls `completion(true|false)`.
    func ping(completion: ((Bool) -> Void)? = nil) {
        guard let url = URL(string: "\(baseURL)/health") else {
            DispatchQueue.main.async {
                self.connection = .offline
                completion?(false)
            }
            return
        }
        var request = URLRequest(url: url)
        request.timeoutInterval = 4
        URLSession.shared.dataTask(with: request) { [weak self] _, response, _ in
            let ok = (response as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.async {
                self?.connection = ok ? .online : .offline
                completion?(ok)
            }
        }.resume()
    }

    // MARK: - Chat

    /// Send a prompt; receive (replyText, action?). Auto-plays the cloned voice.
    func sendMessage(_ message: String,
                     completion: @escaping (_ reply: String, _ action: [String: Any]?) -> Void) {
        guard let url = URL(string: "\(baseURL)/chat") else {
            completion("Invalid server URL", nil)
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 20  // was 60 — fail fast, retry rather than wait
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["prompt": message])

        URLSession.shared.dataTask(with: request) { [weak self] data, _, error in
            if let error = error {
                DispatchQueue.main.async {
                    self?.connection = .offline
                    completion(Self.friendlyError(error), nil)
                }
                return
            }
            guard let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                DispatchQueue.main.async { completion("Invalid server response", nil) }
                return
            }

            DispatchQueue.main.async { self?.connection = .online }

            let reply = (json["reply"] as? String)
                ?? (json["response"] as? String)
                ?? "No reply"

            if let audioPath = json["audio_url"] as? String {
                self?.playAudio(at: audioPath)
            }

            let action = json["action"] as? [String: Any]
            self?.executeOpenURLIfPresent(action)

            DispatchQueue.main.async { completion(reply, action) }
        }.resume()
    }

    // MARK: - Voice in (push-to-talk)

    func sendAudio(_ fileURL: URL,
                   completion: @escaping (_ transcript: String, _ reply: String, _ action: [String: Any]?) -> Void) {
        guard let url = URL(string: "\(baseURL)/listen"),
              let audioData = try? Data(contentsOf: fileURL) else {
            DispatchQueue.main.async { completion("", "Failed to read recording", nil) }
            return
        }

        let boundary = "newt-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 25  // a bit longer for audio upload + Whisper
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()
        let crlf = "\r\n"
        body.append("--\(boundary)\(crlf)".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(fileURL.lastPathComponent)\"\(crlf)".data(using: .utf8)!)
        body.append("Content-Type: audio/m4a\(crlf)\(crlf)".data(using: .utf8)!)
        body.append(audioData)
        body.append("\(crlf)--\(boundary)--\(crlf)".data(using: .utf8)!)
        request.httpBody = body

        URLSession.shared.dataTask(with: request) { [weak self] data, _, error in
            try? FileManager.default.removeItem(at: fileURL)

            if let error = error {
                DispatchQueue.main.async {
                    self?.connection = .offline
                    completion("", Self.friendlyError(error), nil)
                }
                return
            }
            guard let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                DispatchQueue.main.async { completion("", "Invalid server response", nil) }
                return
            }

            DispatchQueue.main.async { self?.connection = .online }

            let transcript = (json["transcript"] as? String) ?? ""
            let reply = (json["reply"] as? String)
                ?? (json["response"] as? String)
                ?? (json["error"] as? String)
                ?? "No reply"

            if let audioPath = json["audio_url"] as? String {
                self?.playAudio(at: audioPath)
            }

            let action = json["action"] as? [String: Any]
            self?.executeOpenURLIfPresent(action)

            DispatchQueue.main.async { completion(transcript, reply, action) }
        }.resume()
    }

    // MARK: - Vision (image + prompt -> LLM description)

    /// POST a UIImage + text prompt to the bridge's /vision endpoint.
    /// The bridge forwards to OpenAI Vision and returns the description.
    func sendImage(_ image: UIImage, prompt: String,
                   completion: @escaping (_ reply: String, _ action: [String: Any]?) -> Void) {
        guard let url = URL(string: "\(baseURL)/vision"),
              let imageData = image.jpegData(compressionQuality: 0.7) else {
            completion("Couldn't prepare the image.", nil)
            return
        }

        let boundary = "newt-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 45
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()
        let crlf = "\r\n"

        // prompt field
        body.append("--\(boundary)\(crlf)".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"prompt\"\(crlf)\(crlf)".data(using: .utf8)!)
        body.append(prompt.data(using: .utf8)!)
        body.append(crlf.data(using: .utf8)!)

        // file field
        body.append("--\(boundary)\(crlf)".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"newt-photo.jpg\"\(crlf)".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\(crlf)\(crlf)".data(using: .utf8)!)
        body.append(imageData)
        body.append("\(crlf)--\(boundary)--\(crlf)".data(using: .utf8)!)
        request.httpBody = body

        URLSession.shared.dataTask(with: request) { [weak self] data, _, error in
            if let error = error {
                DispatchQueue.main.async {
                    self?.connection = .offline
                    completion(Self.friendlyError(error), nil)
                }
                return
            }
            guard let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                DispatchQueue.main.async { completion("Invalid server response", nil) }
                return
            }

            DispatchQueue.main.async { self?.connection = .online }

            let reply = (json["reply"] as? String)
                ?? (json["error"] as? String)
                ?? "No description."
            let action = json["action"] as? [String: Any]
            DispatchQueue.main.async { completion(reply, action) }
        }.resume()
    }

    // MARK: - File upload (phone -> Mac)

    /// POST a file from the phone to the bridge's /upload endpoint.
    /// The bridge saves it to ~/newt/inbox/.
    func uploadFile(_ fileURL: URL,
                    completion: @escaping (_ message: String) -> Void) {
        guard let url = URL(string: "\(baseURL)/upload"),
              let data = try? Data(contentsOf: fileURL) else {
            completion("Couldn't read the file.")
            return
        }
        let filename = fileURL.lastPathComponent.isEmpty ? "upload" : fileURL.lastPathComponent

        let boundary = "newt-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 120  // big files take time
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()
        let crlf = "\r\n"
        body.append("--\(boundary)\(crlf)".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\(crlf)".data(using: .utf8)!)
        body.append("Content-Type: application/octet-stream\(crlf)\(crlf)".data(using: .utf8)!)
        body.append(data)
        body.append("\(crlf)--\(boundary)--\(crlf)".data(using: .utf8)!)
        request.httpBody = body

        URLSession.shared.dataTask(with: request) { [weak self] data, _, error in
            if let error = error {
                DispatchQueue.main.async {
                    self?.connection = .offline
                    completion(Self.friendlyError(error))
                }
                return
            }
            guard let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                DispatchQueue.main.async { completion("Invalid server response.") }
                return
            }

            DispatchQueue.main.async { self?.connection = .online }

            if json["ok"] as? Bool == true {
                let savedTo = (json["saved_to"] as? String) ?? "your Mac"
                let size = json["size"] as? Int ?? 0
                let sizeStr: String
                if size > 1024 * 1024 { sizeStr = String(format: "%.1f MB", Double(size) / (1024 * 1024)) }
                else if size > 1024  { sizeStr = String(format: "%.0f KB", Double(size) / 1024) }
                else                 { sizeStr = "\(size) bytes" }
                // Path is on the Mac — strip /Users/<name> for readability
                let pretty = savedTo.replacingOccurrences(
                    of: #"^/Users/[^/]+/"#, with: "~/", options: .regularExpression
                )
                DispatchQueue.main.async {
                    completion("✓ Sent \(sizeStr) → \(pretty) on your Mac.")
                }
            } else {
                let err = json["error"] as? String ?? "Upload failed."
                DispatchQueue.main.async { completion(err) }
            }
        }.resume()
    }

    // MARK: - Cross-app actions

    private func executeOpenURLIfPresent(_ rawAction: [String: Any]?) {
        guard let action = rawAction,
              let urlString = action["open_url"] as? String,
              let url = URL(string: urlString) else { return }

        DispatchQueue.main.async {
            UIApplication.shared.open(url, options: [:]) { success in
                if !success {
                    print("Newt: open(\(url)) returned success=false")
                }
            }
        }
    }

    // MARK: - Voice playback

    func speak(_ text: String) {
        guard let escaped = text.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) else { return }
        playAudio(at: "/speak?text=\(escaped)")
    }

    /// Stop any currently-playing cloned-voice clip immediately.
    func stopVoice() {
        DispatchQueue.main.async { [weak self] in
            self?.audioPlayer?.pause()
            self?.audioPlayer?.replaceCurrentItem(with: nil)
            self?.audioPlayer = nil
            try? AVAudioSession.sharedInstance().setActive(
                false, options: .notifyOthersOnDeactivation
            )
        }
    }

    /// True while the cloned voice is currently audible. Used by the UI to
    /// show a "stop" button while Newt is talking.
    var isSpeaking: Bool {
        guard let player = audioPlayer else { return false }
        return player.timeControlStatus == .playing
    }

    private func playAudio(at path: String) {
        if voiceMuted { return }
        let urlString = path.hasPrefix("http") ? path : "\(baseURL)\(path)"
        guard let url = URL(string: urlString) else { return }

        DispatchQueue.main.async { [weak self] in
            try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio)
            try? AVAudioSession.sharedInstance().setActive(true)

            let item = AVPlayerItem(url: url)
            let player = AVPlayer(playerItem: item)
            self?.audioPlayer = player
            player.play()
        }
    }

    // MARK: - Helpers

    private static func friendlyError(_ error: Error) -> String {
        let ns = error as NSError
        switch ns.code {
        case NSURLErrorTimedOut:           return "Newt didn't respond in time. Check the bridge."
        case NSURLErrorCannotFindHost:     return "Can't find Newt — is Tailscale on?"
        case NSURLErrorCannotConnectToHost,
             NSURLErrorNetworkConnectionLost,
             NSURLErrorNotConnectedToInternet:
            return "Newt is offline. Bridge running?"
        default:
            return "Network error: \(error.localizedDescription)"
        }
    }
}
