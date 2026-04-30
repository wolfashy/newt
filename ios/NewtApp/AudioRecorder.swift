import Foundation
import AVFoundation
import Combine

/// Tiny wrapper around AVAudioRecorder for push-to-talk.
/// Records to AAC m4a in the temp dir; returns the file URL on stop().
/// Publishes a normalized 0…1 input level for waveform UI.
final class AudioRecorder: NSObject, ObservableObject {
    @Published private(set) var isRecording = false
    /// Smoothed mic level in 0…1, suitable for driving a waveform.
    @Published private(set) var level: CGFloat = 0

    private var recorder: AVAudioRecorder?
    private var fileURL: URL?
    private var meterTimer: Timer?
    private var startedAt: Date?

    /// Recordings shorter than this are treated as accidental taps.
    static let minDuration: TimeInterval = 0.30

    /// Ask for mic permission once. Calls completion(true) on grant, false otherwise.
    func requestPermission(_ completion: @escaping (Bool) -> Void) {
        if #available(iOS 17.0, *) {
            AVAudioApplication.requestRecordPermission { granted in
                DispatchQueue.main.async { completion(granted) }
            }
        } else {
            AVAudioSession.sharedInstance().requestRecordPermission { granted in
                DispatchQueue.main.async { completion(granted) }
            }
        }
    }

    /// Begin recording. No-op if already recording.
    func start() {
        guard !isRecording else { return }

        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(.playAndRecord,
                                    mode: .spokenAudio,
                                    options: [.defaultToSpeaker, .allowBluetooth])
            try session.setActive(true)
        } catch {
            print("AudioRecorder: failed to set up session: \(error)")
            return
        }

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("newt-\(UUID().uuidString).m4a")

        let settings: [String: Any] = [
            AVFormatIDKey:            Int(kAudioFormatMPEG4AAC),
            AVSampleRateKey:          16_000,                   // Whisper sweet spot
            AVNumberOfChannelsKey:    1,
            AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue,
        ]

        do {
            let r = try AVAudioRecorder(url: url, settings: settings)
            r.isMeteringEnabled = true
            r.record()
            recorder = r
            fileURL  = url
            startedAt = Date()
            isRecording = true
            startMetering()
        } catch {
            print("AudioRecorder: failed to start: \(error)")
        }
    }

    /// Stop recording and return the file URL.
    /// Returns `nil` if the recording was too short (treated as an accidental tap)
    /// — in that case the temp file is also deleted so the caller doesn't have to.
    func stop() -> URL? {
        guard isRecording, let r = recorder else { return nil }
        r.stop()
        stopMetering()
        isRecording = false
        recorder = nil

        let url = fileURL
        let duration = startedAt.map { Date().timeIntervalSince($0) } ?? 0
        fileURL = nil
        startedAt = nil

        // Release the audio session so other apps (Music, podcasts) can resume.
        try? AVAudioSession.sharedInstance().setActive(
            false, options: .notifyOthersOnDeactivation
        )

        // Bail on accidental taps — also clean up the empty file.
        if duration < Self.minDuration {
            if let url = url {
                try? FileManager.default.removeItem(at: url)
            }
            return nil
        }
        return url
    }

    // MARK: - Level metering

    private func startMetering() {
        meterTimer?.invalidate()
        // 20 Hz — smooth enough for animation, cheap on battery.
        meterTimer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
            self?.tickMeter()
        }
    }

    private func stopMetering() {
        meterTimer?.invalidate()
        meterTimer = nil
        DispatchQueue.main.async { [weak self] in
            self?.level = 0
        }
    }

    private func tickMeter() {
        guard let r = recorder else { return }
        r.updateMeters()
        // averagePower(forChannel:) returns dB, typically -160 (silence) … 0 (max).
        let db = r.averagePower(forChannel: 0)
        // Map -50 dB … 0 dB to 0 … 1 with a soft curve.
        let minDb: Float = -50
        let normalized = max(0, min(1, (db - minDb) / -minDb))
        let shaped = pow(CGFloat(normalized), 1.6)   // ease-out: quiet noise stays small

        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            // Light low-pass smoothing so bars don't jitter.
            self.level = self.level * 0.6 + shaped * 0.4
        }
    }
}
