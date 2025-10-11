import SwiftUI

struct OnboardingView: View {
    var onContinue: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Welcome to Arcadia Coach")
                .font(.system(size: 30, weight: .bold))
                .accessibilityAddTraits(.isHeader)
            Text("A calm, game-inspired workspace tuned for AuDHD learning.")
                .font(.title3)
            VStack(alignment: .leading, spacing: 10) {
                Label("Paste your OpenAI API Key in Settings", systemImage: "key.fill")
                Label("Add your Agent ID to link your Arcadia agent", systemImage: "person.3.sequence")
                Label("Set your ChatKit backend URL to reach the custom server", systemImage: "globe")
            }
            .font(.body)
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.secondary.opacity(0.1), in: RoundedRectangle(cornerRadius: 12))
            Text("You control the pacing. Motion stays minimal and sounds stay muted unless you choose otherwise.")
                .font(.footnote)
                .foregroundStyle(.secondary)
            HStack {
                Spacer()
                GlassButton(title: "Enter App", systemName: "arrow.right.circle.fill", action: onContinue)
                Spacer()
            }
        }
        .padding(24)
    }
}
