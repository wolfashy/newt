import SwiftUI
import Combine

/// Tiny wrapper around UserDefaults so SwiftUI can observe individual prefs.
@MainActor
final class NewtSettings: ObservableObject {
    @Published var voiceMuted: Bool {
        didSet { UserDefaults.standard.set(voiceMuted, forKey: "newt.voiceMuted") }
    }
    @Published var hapticsEnabled: Bool {
        didSet { UserDefaults.standard.set(hapticsEnabled, forKey: "newt.haptics") }
    }
    @Published var streamingEnabled: Bool {
        didSet { UserDefaults.standard.set(streamingEnabled, forKey: "newt.streaming") }
    }
    @Published var defaultDevice: String {  // "ios" or "mac"
        didSet { UserDefaults.standard.set(defaultDevice, forKey: "newt.defaultDevice") }
    }
    @Published var serverHost: String {
        didSet {
            let trimmed = serverHost.trimmingCharacters(in: .whitespaces)
            UserDefaults.standard.set(trimmed, forKey: "newt.serverHost")
        }
    }

    init() {
        let d = UserDefaults.standard
        self.voiceMuted        = d.bool(forKey: "newt.voiceMuted")
        self.hapticsEnabled    = d.object(forKey: "newt.haptics") as? Bool ?? true
        self.streamingEnabled  = d.object(forKey: "newt.streaming") as? Bool ?? true
        self.defaultDevice     = d.string(forKey: "newt.defaultDevice") ?? "ios"
        self.serverHost        = d.string(forKey: "newt.serverHost") ?? ""
    }
}

// MARK: - Settings sheet

struct SettingsView: View {
    @ObservedObject var settings: NewtSettings
    @ObservedObject var network: NetworkManager
    @Environment(\.dismiss) private var dismiss

    @State private var pingResult: String? = nil
    @State private var pinging = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Voice") {
                    Toggle("Mute Newt's voice", isOn: $settings.voiceMuted)
                    Toggle("Haptics", isOn: $settings.hapticsEnabled)
                }

                Section("Chat") {
                    Toggle("Stream replies", isOn: $settings.streamingEnabled)
                    Text("Newt's text replies appear word-by-word as they generate. Faster perceived response.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Section("Default device for \"open X\"") {
                    Picker("Open on", selection: $settings.defaultDevice) {
                        Text("iPhone").tag("ios")
                        Text("iMac").tag("mac")
                    }
                    .pickerStyle(.segmented)
                    Text("Override anytime by saying \"on my mac\" or \"on my phone\".")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Section("Bridge") {
                    HStack {
                        Image(systemName: connectionIcon)
                            .foregroundColor(connectionColor)
                        Text(connectionLabel)
                            .foregroundColor(connectionColor)
                        Spacer()
                        Button {
                            checkConnection()
                        } label: {
                            if pinging {
                                ProgressView()
                            } else {
                                Text("Check")
                            }
                        }
                        .buttonStyle(.bordered)
                        .disabled(pinging)
                    }

                    HStack {
                        Text("Host")
                        TextField("http://newt:8001", text: $settings.serverHost)
                            .keyboardType(.URL)
                            .autocorrectionDisabled()
                            .textInputAutocapitalization(.never)
                            .multilineTextAlignment(.trailing)
                    }
                    Text("Default: http://newt:8001 (Tailscale MagicDNS).")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Section("About") {
                    LabeledContent("Newt", value: "1.0")
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .onAppear { checkConnection() }
        }
    }

    private var connectionIcon: String {
        switch network.connection {
        case .online:  return "checkmark.circle.fill"
        case .offline: return "exclamationmark.triangle.fill"
        case .unknown: return "circle.dashed"
        }
    }
    private var connectionColor: Color {
        switch network.connection {
        case .online:  return .green
        case .offline: return .red
        case .unknown: return .secondary
        }
    }
    private var connectionLabel: String {
        switch network.connection {
        case .online:  return "Online"
        case .offline: return "Offline"
        case .unknown: return "Checking…"
        }
    }
    private func checkConnection() {
        pinging = true
        network.ping { _ in pinging = false }
    }
}
