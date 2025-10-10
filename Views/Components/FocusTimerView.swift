import SwiftUI
import Combine
import AppKit

struct FocusTimerView: View {
    @EnvironmentObject private var settings: AppSettings
    @State private var remaining: Int
    @State private var isRunning: Bool = false
    @State private var cancellable: AnyCancellable?
    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    init() {
        _remaining = State(initialValue: 0)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Focus Timer")
                    .font(.headline)
                    .accessibilityAddTraits(.isHeader)
                Spacer()
                Text(timeString(from: remaining))
                    .font(.system(size: 28, weight: .semibold, design: .rounded))
                    .monospacedDigit()
            }
            HStack(spacing: 12) {
                GlassButton(title: isRunning ? "Pause" : "Start", systemName: isRunning ? "pause.circle.fill" : "play.circle.fill") {
                    toggle()
                }
                GlassButton(title: "Reset", systemName: "arrow.counterclockwise.circle.fill") {
                    reset()
                }
            }
        }
        .padding(12)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
        .onAppear {
            configure()
            cancellable = NotificationCenter.default.publisher(for: .resetFocusTimer).sink { _ in
                reset()
            }
        }
        .onDisappear {
            cancellable?.cancel()
        }
        .onChange(of: settings.sessionMinutes) { _ in
            configure()
        }
        .onReceive(timer) { _ in
            guard isRunning, remaining > 0 else { return }
            remaining -= 1
            if remaining == 0 {
                isRunning = false
                if !settings.muteSounds {
                    NSSound(named: NSSound.Name("Submarine"))?.play()
                }
            }
        }
        .accessibilityElement(children: .contain)
    }

    private func configure() {
        remaining = settings.sessionMinutes * 60
        isRunning = false
    }

    private func reset() {
        configure()
    }

    private func toggle() {
        if remaining == 0 {
            configure()
        }
        isRunning.toggle()
    }

    private func timeString(from seconds: Int) -> String {
        let minutes = seconds / 60
        let secs = seconds % 60
        return String(format: "%02d:%02d", minutes, secs)
    }
}
