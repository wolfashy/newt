import SwiftUI
import Contacts
import UIKit
import PhotosUI
import UniformTypeIdentifiers

// MARK: - Model

struct Message: Identifiable, Equatable, Codable {
    var id = UUID()
    let text: String
    let isUser: Bool
    var date: Date = Date()
}

// MARK: - Theme

enum Theme {
    static let accent      = Color(red: 0.20, green: 0.78, blue: 0.45)   // Newt green
    static let accentDeep  = Color(red: 0.10, green: 0.62, blue: 0.36)
    static let bg          = Color(.systemGroupedBackground)
    static let bubbleAI    = Color(.secondarySystemBackground)
    static let textAI      = Color(.label)
    static let inputBg     = Color(.systemBackground)
    static let separator   = Color(.separator).opacity(0.5)
}

// MARK: - Root view

struct ContentView: View {
    @State private var message = ""
    @State private var isThinking = false
    @State private var showSettings = false

    // Media-picker state
    @State private var showCamera = false
    @State private var showFileImporter = false
    @State private var photoItem: PhotosPickerItem?

    @StateObject private var recorder = AudioRecorder()
    @StateObject private var store = MessageStore()
    @StateObject private var calendar = CalendarManager()
    @StateObject private var timers = TimerManager.shared
    @StateObject private var settings = NewtSettings()
    @ObservedObject private var network = NetworkManager.shared
    @FocusState private var inputFocused: Bool

    /// Convenience to keep diff against the rest of the file small.
    private var messages: [Message] { store.messages }

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                header

                Divider()
                    .background(Theme.separator)

                chatScroll

                if recorder.isRecording {
                    WaveformView(level: recorder.level)
                        .frame(height: 56)
                        .padding(.horizontal, 24)
                        .padding(.bottom, 4)
                        .transition(.opacity.combined(with: .move(edge: .bottom)))
                }

                inputBar
            }
        }
        .animation(.spring(response: 0.32, dampingFraction: 0.78), value: recorder.isRecording)
        .animation(.spring(response: 0.35, dampingFraction: 0.82), value: messages)
        .animation(.easeInOut(duration: 0.2), value: isThinking)
        .sheet(isPresented: $showSettings) {
            SettingsView(settings: settings, network: network)
        }
        .fullScreenCover(isPresented: $showCamera) {
            CameraPicker { img in
                handleCapturedImage(img)
            }
            .ignoresSafeArea()
        }
        .fileImporter(
            isPresented: $showFileImporter,
            allowedContentTypes: [.item],
            allowsMultipleSelection: false
        ) { result in
            switch result {
            case .success(let urls):
                if let url = urls.first { sendFileToMac(url) }
            case .failure(let error):
                store.append(Message(text: "Couldn't open file: \(error.localizedDescription)", isUser: false))
            }
        }
        .onChange(of: photoItem) { newItem in
            guard let newItem else { return }
            Task {
                if let img = await loadUIImage(from: newItem) {
                    handleCapturedImage(img)
                }
                photoItem = nil
            }
        }
        .onAppear {
            recorder.requestPermission { _ in }
            network.ping()
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 10) {
            // Status dot reflects connection + thinking state
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)
                .shadow(color: statusColor.opacity(0.6), radius: 4)
                .scaleEffect(isThinking ? 1.4 : 1.0)
                .animation(.easeInOut(duration: 0.6).repeatForever(autoreverses: true),
                           value: isThinking)

            Text("Newt")
                .font(.system(size: 20, weight: .semibold, design: .rounded))
                .foregroundColor(.primary)

            Spacer()

            // Stop-talking button while voice is playing
            if !settings.voiceMuted, isVoicePlaying {
                Button {
                    Haptics.tick()
                    network.stopVoice()
                    isVoicePlaying = false
                } label: {
                    Image(systemName: "stop.circle.fill")
                        .font(.system(size: 22))
                        .foregroundColor(Theme.accent)
                }
                .transition(.opacity)
            }

            Menu {
                Button {
                    Haptics.tick()
                    showSettings = true
                } label: {
                    Label("Settings", systemImage: "gearshape")
                }
                Button {
                    Haptics.tick()
                    settings.voiceMuted.toggle()
                } label: {
                    Label(settings.voiceMuted ? "Unmute voice" : "Mute voice",
                          systemImage: settings.voiceMuted ? "speaker.wave.2" : "speaker.slash")
                }
                Divider()
                Button(role: .destructive) {
                    Haptics.click()
                    withAnimation { store.clear() }
                } label: {
                    Label("Clear history", systemImage: "trash")
                }
            } label: {
                Image(systemName: "ellipsis.circle")
                    .font(.system(size: 18, weight: .medium))
                    .foregroundColor(Theme.accent)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
        .background(.ultraThinMaterial)
    }

    @State private var isVoicePlaying = false

    private var statusColor: Color {
        switch network.connection {
        case .online:  return Theme.accent
        case .offline: return .red
        case .unknown: return .secondary
        }
    }

    /// True if the message at `idx` is the first one of its day.
    private func shouldShowDaySeparator(at idx: Int) -> Bool {
        guard idx < messages.count else { return false }
        if idx == 0 { return true }
        let cal = Calendar.current
        return !cal.isDate(messages[idx].date, inSameDayAs: messages[idx - 1].date)
    }

    // MARK: - Chat

    private var chatScroll: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 10) {
                    if messages.isEmpty && !isThinking {
                        emptyState
                            .padding(.top, 80)
                    }

                    ForEach(Array(messages.enumerated()), id: \.element.id) { idx, msg in
                        // Day separator before this message if the date changed
                        if shouldShowDaySeparator(at: idx) {
                            DaySeparator(date: msg.date)
                                .padding(.top, idx == 0 ? 0 : 8)
                                .padding(.bottom, 4)
                        }
                        MessageBubble(message: msg)
                            .id(msg.id)
                            .transition(.asymmetric(
                                insertion: .move(edge: msg.isUser ? .trailing : .leading)
                                    .combined(with: .opacity),
                                removal: .opacity
                            ))
                    }

                    if isThinking {
                        HStack {
                            TypingIndicator()
                                .padding(.horizontal, 14)
                                .padding(.vertical, 12)
                                .background(Theme.bubbleAI)
                                .clipShape(BubbleShape(isUser: false))
                            Spacer()
                        }
                        .padding(.horizontal, 16)
                        .id("thinking")
                        .transition(.opacity)
                    }

                    Color.clear
                        .frame(height: 4)
                        .id("bottom")
                }
                .padding(.top, 12)
                .padding(.bottom, 8)
            }
            .onChange(of: messages.count) { _ in
                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                    proxy.scrollTo("bottom", anchor: .bottom)
                }
            }
            .onChange(of: isThinking) { _ in
                withAnimation(.easeOut(duration: 0.25)) {
                    proxy.scrollTo("bottom", anchor: .bottom)
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 14) {
            FloatingLeaf()
            Text("Say hi to Newt")
                .font(.system(size: 18, weight: .semibold, design: .rounded))
                .foregroundColor(.primary)
            Text("Hold the mic to talk, or type a message.")
                .font(.system(size: 14))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Input bar

    private var inputBar: some View {
        HStack(spacing: 8) {
            // Plus menu — camera / photo library / send file
            Menu {
                Button {
                    Haptics.tick()
                    showCamera = true
                } label: {
                    Label("Take photo", systemImage: "camera")
                }
                // PhotosPicker can't be inside a Menu cleanly, so we use
                // a state-driven sheet approach via the photoItem binding.
                PhotosPicker(selection: $photoItem,
                             matching: .images,
                             photoLibrary: .shared()) {
                    Label("Photo library", systemImage: "photo.on.rectangle")
                }
                Button {
                    Haptics.tick()
                    showFileImporter = true
                } label: {
                    Label("Send file to Mac", systemImage: "paperplane.circle")
                }
                if hasPasteableImage {
                    Button {
                        Haptics.tick()
                        if let img = UIPasteboard.general.image {
                            handleCapturedImage(img)
                        }
                    } label: {
                        Label("Paste image", systemImage: "doc.on.clipboard")
                    }
                }
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(Theme.accent)
                    .frame(width: 38, height: 38)
                    .background(Circle().fill(Theme.bubbleAI))
            }

            // Push-to-talk mic
            ZStack {
                Circle()
                    .fill(recorder.isRecording ? Color.red : Theme.accent)
                    .frame(width: 44, height: 44)
                    .shadow(color: (recorder.isRecording ? Color.red : Theme.accent).opacity(0.35),
                            radius: 6, x: 0, y: 3)

                Image(systemName: recorder.isRecording ? "mic.fill" : "mic")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(.white)
            }
            .scaleEffect(recorder.isRecording ? 1.12 : 1.0)
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in
                        if !recorder.isRecording {
                            Haptics.tick()
                            startRecording()
                        }
                    }
                    .onEnded { _ in
                        Haptics.thump()
                        stopRecordingAndSend()
                    }
            )

            // Text field
            TextField("Message Newt…", text: $message)
                .focused($inputFocused)
                .padding(.horizontal, 16)
                .padding(.vertical, 11)
                .background(
                    Capsule()
                        .fill(Theme.bubbleAI)
                )
                .overlay(
                    Capsule()
                        .stroke(Theme.separator, lineWidth: 0.5)
                )
                .submitLabel(.send)
                .onSubmit { sendMessage() }

            // Send
            Button(action: { Haptics.thump(); sendMessage() }) {
                ZStack {
                    Circle()
                        .fill(canSend ? Theme.accent : Color.gray.opacity(0.25))
                        .frame(width: 38, height: 38)
                    Image(systemName: "arrow.up")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundColor(.white)
                }
            }
            .disabled(!canSend)
            .animation(.easeInOut(duration: 0.15), value: canSend)
        }
        .padding(.horizontal, 14)
        .padding(.top, 8)
        .padding(.bottom, 10)
        .background(
            Theme.inputBg
                .ignoresSafeArea(edges: .bottom)
        )
        .overlay(
            Rectangle()
                .fill(Theme.separator)
                .frame(height: 0.5),
            alignment: .top
        )
    }

    private var canSend: Bool {
        !message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    // MARK: - Text path

    func sendMessage() {
        let userMessage = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !userMessage.isEmpty else { return }

        store.append(Message(text: userMessage, isUser: true))
        message = ""
        isThinking = true
        isVoicePlaying = !settings.voiceMuted  // assume voice will play

        NetworkManager.shared.sendMessage(userMessage) { [self] reply, action in
            isThinking = false
            store.append(Message(text: reply, isUser: false))
            if action == nil && reply.lowercased().contains("error") {
                Haptics.error()
            }
            handleAction(action)
            // Sample isSpeaking shortly after to keep the stop button accurate
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                isVoicePlaying = network.isSpeaking
            }
        }
    }

    // MARK: - Voice path

    private func startRecording() {
        recorder.requestPermission { granted in
            guard granted else {
                Haptics.error()
                store.append(Message(text: "Mic permission denied. Enable it in Settings.", isUser: false))
                return
            }
            recorder.start()
        }
    }

    private func stopRecordingAndSend() {
        guard let url = recorder.stop() else {
            // Recording was too short — pretend nothing happened.
            return
        }
        isThinking = true
        isVoicePlaying = !settings.voiceMuted

        NetworkManager.shared.sendAudio(url) { [self] transcript, reply, action in
            isThinking = false
            if !transcript.isEmpty {
                store.append(Message(text: transcript, isUser: true))
            }
            store.append(Message(text: reply, isUser: false))
            if action == nil && reply.lowercased().contains("error") {
                Haptics.error()
            }
            handleAction(action)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                isVoicePlaying = network.isSpeaking
            }
        }
    }

    // MARK: - Vision + file upload

    /// Whether UIPasteboard currently contains an image (refreshed each time
    /// the menu is opened — quick, but not reactive). Used to show a "Paste
    /// image" item in the + menu.
    private var hasPasteableImage: Bool {
        UIPasteboard.general.hasImages
    }

    /// User picked a photo or took one. Send to /vision with default prompt.
    private func handleCapturedImage(_ image: UIImage) {
        let userTextRaw = message.trimmingCharacters(in: .whitespacesAndNewlines)
        let prompt = userTextRaw.isEmpty ? "What's in this image? Be concise." : userTextRaw
        let userMessage = userTextRaw.isEmpty
            ? "📷 [photo]"
            : "📷 \(userTextRaw)"

        store.append(Message(text: userMessage, isUser: true))
        message = ""
        isThinking = true

        NetworkManager.shared.sendImage(image, prompt: prompt) { [self] reply, action in
            isThinking = false
            store.append(Message(text: reply, isUser: false))
            handleAction(action)
        }
    }

    /// User picked a file. Upload to bridge — saved to ~/newt/inbox/ on Mac.
    private func sendFileToMac(_ fileURL: URL) {
        // iOS file picker returns security-scoped URLs; access begin/end.
        let needsScope = fileURL.startAccessingSecurityScopedResource()
        defer { if needsScope { fileURL.stopAccessingSecurityScopedResource() } }

        let name = fileURL.lastPathComponent
        store.append(Message(text: "📁 Sending \(name) to Mac…", isUser: true))
        isThinking = true

        NetworkManager.shared.uploadFile(fileURL) { [self] result in
            isThinking = false
            store.append(Message(text: result, isUser: false))
            Haptics.success()
        }
    }

    // MARK: - Action dispatch (calendar / reminders / future)

    private func handleAction(_ action: [String: Any]?) {
        guard let action = action else { return }

        // Reminders
        if let reminder = action["create_reminder"] as? [String: Any] {
            calendar.createReminder(from: reminder) { [self] result in
                store.append(Message(text: result, isUser: false))
            }
        }

        // Calendar events
        if let event = action["create_event"] as? [String: Any] {
            calendar.createEvent(from: event) { [self] result in
                store.append(Message(text: result, isUser: false))
            }
        }

        // Read calendar
        if let read = action["read_events"] as? [String: Any] {
            calendar.fetchEvents(from: read) { [self] summary in
                store.append(Message(text: summary, isUser: false))
            }
        }

        // Read reminders
        if let read = action["read_reminders"] as? [String: Any] {
            calendar.fetchReminders(from: read) { [self] summary in
                store.append(Message(text: summary, isUser: false))
            }
        }

        // Compose SMS / iMessage from the phone
        if let sms = action["compose_sms"] as? [String: Any],
           let recipient = sms["recipient"] as? String,
           let body = sms["body"] as? String {
            composeSMS(recipient: recipient, body: body)
        }

        // Local timer
        if let timer = action["start_timer"] as? [String: Any] {
            timers.start(from: timer) { [self] result in
                store.append(Message(text: result, isUser: false))
            }
        }
    }

    // MARK: - Phone-side messaging

    /// Looks up `recipient` in Contacts; opens Messages.app pre-filled.
    /// User taps Send. Falls back to body-only if contact lookup fails.
    private func composeSMS(recipient: String, body: String) {
        findPhone(for: recipient) { phone in
            let bodyEncoded = body.addingPercentEncoding(
                withAllowedCharacters: .urlQueryAllowed
            ) ?? body

            let urlString: String
            if let phone = phone {
                let stripped = phone.replacingOccurrences(
                    of: "[^0-9+]", with: "", options: .regularExpression
                )
                urlString = "sms:\(stripped)&body=\(bodyEncoded)"
            } else {
                // Couldn't find them in Contacts — open Messages with body only.
                urlString = "sms:&body=\(bodyEncoded)"
                store.append(Message(
                    text: "(Couldn't find \(recipient) in Contacts — pick them in Messages.)",
                    isUser: false
                ))
            }

            guard let url = URL(string: urlString) else { return }
            DispatchQueue.main.async {
                UIApplication.shared.open(url)
            }
        }
    }

    /// Look up the first phone number for a name in Contacts.
    private func findPhone(for name: String, completion: @escaping (String?) -> Void) {
        let store = CNContactStore()
        store.requestAccess(for: .contacts) { granted, _ in
            guard granted else {
                DispatchQueue.main.async { completion(nil) }
                return
            }
            do {
                let predicate = CNContact.predicateForContacts(matchingName: name)
                let keys = [
                    CNContactPhoneNumbersKey,
                    CNContactGivenNameKey,
                    CNContactFamilyNameKey,
                ] as [CNKeyDescriptor]
                let contacts = try store.unifiedContacts(
                    matching: predicate, keysToFetch: keys
                )
                let phone = contacts.first?.phoneNumbers.first?.value.stringValue
                DispatchQueue.main.async { completion(phone) }
            } catch {
                DispatchQueue.main.async { completion(nil) }
            }
        }
    }
}

// MARK: - Message bubble

struct MessageBubble: View {
    let message: Message
    @State private var showTimestamp = false

    var body: some View {
        VStack(alignment: message.isUser ? .trailing : .leading, spacing: 2) {
            HStack(spacing: 0) {
                if message.isUser { Spacer(minLength: 48) }

                Text(message.text)
                    .font(.system(size: 16))
                    .foregroundColor(message.isUser ? .white : Theme.textAI)
                    .textSelection(.enabled)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(
                        Group {
                            if message.isUser {
                                LinearGradient(
                                    colors: [Theme.accent, Theme.accentDeep],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            } else {
                                Theme.bubbleAI
                            }
                        }
                    )
                    .clipShape(BubbleShape(isUser: message.isUser))
                    .shadow(color: Color.black.opacity(message.isUser ? 0.08 : 0.04),
                            radius: 4, x: 0, y: 2)
                    .onTapGesture {
                        withAnimation(.easeInOut(duration: 0.18)) {
                            showTimestamp.toggle()
                        }
                    }
                    .contextMenu {
                        Button {
                            UIPasteboard.general.string = message.text
                            Haptics.tick()
                        } label: {
                            Label("Copy", systemImage: "doc.on.doc")
                        }
                        Button {
                            NetworkManager.shared.speak(message.text)
                            Haptics.tick()
                        } label: {
                            Label("Speak", systemImage: "speaker.wave.2")
                        }
                    }

                if !message.isUser { Spacer(minLength: 48) }
            }

            if showTimestamp {
                Text(MessageBubble.timeFormatter.string(from: message.date))
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 18)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(.horizontal, 14)
    }

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .none
        f.timeStyle = .short
        return f
    }()
}

// MARK: - Floating leaf (empty state)

/// Gently bobbing tree logo. Bare image, no card, no halo — sits on the
/// chat background.
struct FloatingLeaf: View {
    @State private var bob: Bool = false

    var body: some View {
        Image("NewtLogo")
            .resizable()
            .scaledToFit()
            .frame(width: 110, height: 110)
            .rotationEffect(.degrees(bob ? 2 : -2))
            .offset(y: bob ? -2 : 2)
            .onAppear {
                withAnimation(.easeInOut(duration: 2.6).repeatForever(autoreverses: true)) {
                    bob = true
                }
            }
    }
}

// MARK: - Day separator

struct DaySeparator: View {
    let date: Date

    var body: some View {
        HStack(spacing: 8) {
            Rectangle().fill(Theme.separator).frame(height: 0.5)
            Text(label)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(.secondary)
                .padding(.horizontal, 6)
            Rectangle().fill(Theme.separator).frame(height: 0.5)
        }
        .padding(.horizontal, 24)
    }

    private var label: String {
        let cal = Calendar.current
        if cal.isDateInToday(date)     { return "Today" }
        if cal.isDateInYesterday(date) { return "Yesterday" }
        let f = DateFormatter()
        if cal.isDate(date, equalTo: Date(), toGranularity: .weekOfYear) {
            f.dateFormat = "EEEE"           // "Monday"
        } else {
            f.dateStyle = .medium           // "Apr 26, 2026"
            f.timeStyle = .none
        }
        return f.string(from: date)
    }
}

/// Asymmetric rounded bubble — pinched corner on the speaker's side.
struct BubbleShape: Shape {
    let isUser: Bool

    func path(in rect: CGRect) -> Path {
        let big: CGFloat = 18
        let small: CGFloat = 5
        let corners = RectangleCornerRadii(
            topLeading: big,
            bottomLeading: isUser ? big : small,
            bottomTrailing: isUser ? small : big,
            topTrailing: big
        )
        return UnevenRoundedRectangle(cornerRadii: corners).path(in: rect)
    }
}

// MARK: - Typing indicator

struct TypingIndicator: View {
    @State private var phase: CGFloat = 0

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { ctx in
            let t = ctx.date.timeIntervalSinceReferenceDate
            HStack(spacing: 5) {
                ForEach(0..<3) { i in
                    Circle()
                        .fill(Color.secondary.opacity(0.6))
                        .frame(width: 7, height: 7)
                        .scaleEffect(dotScale(t: t, i: i))
                }
            }
        }
    }

    private func dotScale(t: TimeInterval, i: Int) -> CGFloat {
        let phase = (t * 2.0).truncatingRemainder(dividingBy: .pi * 2)
        let offset = Double(i) * 0.5
        let s = sin(phase + offset)
        return 0.7 + 0.5 * CGFloat((s + 1) / 2)
    }
}

// MARK: - Waveform

/// 24 capsule bars whose heights are driven by a traveling sine wave
/// modulated by the current mic level. Fades in when recording starts.
struct WaveformView: View {
    let level: CGFloat
    private let barCount = 24

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { ctx in
            let t = ctx.date.timeIntervalSinceReferenceDate
            GeometryReader { geo in
                let barWidth = max(2, (geo.size.width - CGFloat(barCount - 1) * 4) / CGFloat(barCount))
                HStack(spacing: 4) {
                    ForEach(0..<barCount, id: \.self) { i in
                        Capsule()
                            .fill(
                                LinearGradient(
                                    colors: [Theme.accent, Theme.accentDeep],
                                    startPoint: .top,
                                    endPoint: .bottom
                                )
                            )
                            .frame(width: barWidth,
                                   height: barHeight(for: i, t: t, total: geo.size.height))
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
            }
        }
    }

    private func barHeight(for index: Int, t: TimeInterval, total: CGFloat) -> CGFloat {
        // Traveling wave across the bars.
        let phase = t * 6.0
        let position = Double(index) / Double(barCount - 1) * .pi * 3
        let wave = sin(position - phase)
        let normalizedWave = CGFloat((wave + 1) / 2)             // 0…1

        // Mix in mic level — quiet voice = small bars, loud = tall.
        // Floor at 0.12 so the waveform never fully collapses.
        let amplitude = max(0.12, level)
        let envelope = 0.35 + 0.65 * normalizedWave              // peaks taller than valleys
        let h = total * amplitude * envelope
        return max(3, min(total, h))
    }
}

// MARK: - Preview

#Preview {
    ContentView()
}
