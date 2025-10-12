import SwiftUI

struct ChatPanel: View {
    @EnvironmentObject private var settings: AppSettings
    @StateObject private var viewModel = AgentChatViewModel()

    var body: some View {
        let backend = trimmedBackendURL
        VStack(alignment: .leading, spacing: 12) {
            Text("Agent Chat")
                .font(.title2)
                .bold()

            if backend.isEmpty {
                Text("Set your Arcadia backend URL in Settings to chat with your deployed agent.")
                    .font(.body)
                    .foregroundStyle(.secondary)
            }

            ArcadiaChatbotView(
                title: "Arcadia Coach",
                levelLabel: "Medium effort",
                messages: viewModel.messages,
                placeholder: "Ask Arcadia Coach anything…",
                status: viewModel.statusLabel(),
                canSend: viewModel.canSend(),
                isSending: viewModel.isSending,
                webEnabled: false,
                showTonePicker: false,
                levels: [],
                selectedLevel: "medium",
                onSubmit: { text in
                    await viewModel.send(message: text)
                }
            )
            .frame(minHeight: 420)

            if !backend.isEmpty {
                Text("Connected to \(backend).")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            if let error = viewModel.lastError {
                Text(error)
                    .font(.footnote)
                    .foregroundStyle(.red)
            }
        }
        .padding(12)
        .onAppear {
            viewModel.handleBackendChange(backend)
        }
        .onChange(of: settings.chatkitBackendURL) { newValue in
            viewModel.handleBackendChange(newValue)
        }
    }

    private var trimmedBackendURL: String {
        settings.chatkitBackendURL.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
