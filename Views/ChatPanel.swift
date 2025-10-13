import SwiftUI
import AppKit

struct ChatPanel: View {
    @EnvironmentObject private var settings: AppSettings
    @StateObject private var viewModel = AgentChatViewModel()
    @State private var selectedTranscriptId: String?

    var body: some View {
        let backend = trimmedBackendURL
        HStack(alignment: .top, spacing: 20) {
            sidebar
                .frame(width: 260, alignment: .topLeading)

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
                    levelLabel: viewModel.levelLabel,
                    messages: viewModel.messages,
                    placeholder: "Ask Arcadia Coach anything…",
                    status: viewModel.statusLabel(),
                    canSend: viewModel.canSend(),
                    isSending: viewModel.isSending,
                    webEnabled: viewModel.webSearchEnabled,
                    showTonePicker: true,
                    levels: viewModel.levelOptions,
                    selectedLevel: viewModel.reasoningLevel,
                    onSelectLevel: { level in
                        settings.chatReasoningLevel = level
                        viewModel.selectReasoning(level: level)
                    },
                    onToggleWeb: { enabled in
                        settings.chatWebSearchEnabled = enabled
                        viewModel.toggleWebSearch(enabled)
                    },
                    attachments: viewModel.attachments,
                    isAttachmentUploading: viewModel.isUploadingAttachment,
                    onAddAttachment: backend.isEmpty ? nil : presentAttachmentPicker,
                    onRemoveAttachment: { id in
                        viewModel.removeAttachment(id: id)
                    },
                    onSubmit: { text in
                        await viewModel.send(message: text)
                    }
                )
                .frame(minHeight: 440)

                if !backend.isEmpty {
                    Text("Connected to \(backend).")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                if let error = viewModel.lastError, !error.isEmpty {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(16)
        .onAppear {
            configureViewModel(with: backend)
        }
        .onChange(of: settings.chatkitBackendURL) { newValue in
            viewModel.handleBackendChange(newValue)
        }
        .onChange(of: settings.arcadiaUsername) { newValue in
            viewModel.updateUser(newValue)
        }
        .onChange(of: settings.learnerGoal) { newValue in
            viewModel.updateProfile(
                goal: newValue,
                useCase: settings.learnerUseCase,
                strengths: settings.learnerStrengths
            )
        }
        .onChange(of: settings.learnerUseCase) { newValue in
            viewModel.updateProfile(
                goal: settings.learnerGoal,
                useCase: newValue,
                strengths: settings.learnerStrengths
            )
        }
        .onChange(of: settings.learnerStrengths) { newValue in
            viewModel.updateProfile(
                goal: settings.learnerGoal,
                useCase: settings.learnerUseCase,
                strengths: newValue
            )
        }
        .onChange(of: settings.chatWebSearchEnabled) { newValue in
            viewModel.updatePreferences(
                webEnabled: newValue,
                reasoningLevel: viewModel.reasoningLevel
            )
        }
        .onChange(of: settings.chatReasoningLevel) { newValue in
            viewModel.updatePreferences(
                webEnabled: viewModel.webSearchEnabled,
                reasoningLevel: newValue
            )
        }
        .onChange(of: viewModel.recents) { recents in
            guard let selected = selectedTranscriptId else { return }
            if !recents.contains(where: { $0.id == selected }) {
                selectedTranscriptId = nil
                viewModel.clearPreview()
            }
        }
        .onChange(of: viewModel.previewTranscript) { preview in
            selectedTranscriptId = preview?.id
        }
    }

    // Phase 6 sidebar: surfaces prior transcripts for fast recall.
    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Previous Sessions")
                .font(.headline)

            if viewModel.recents.isEmpty {
                Text("Once you chat with Arcadia Coach, your transcripts will appear here for quick reference.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(viewModel.recents) { summary in
                            Button {
                                selectedTranscriptId = summary.id
                                viewModel.showTranscript(withId: summary.id)
                            } label: {
                                summaryCard(for: summary)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 280)
            }

            if let preview = viewModel.previewTranscript {
                transcriptPreview(preview)
            }

            Spacer()
        }
    }

    private func summaryCard(for summary: ChatTranscriptSummary) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(summary.title)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Spacer()
                if summary.id == selectedTranscriptId {
                    Image(systemName: "arrow.right.circle.fill")
                        .foregroundStyle(Color.accentColor)
                }
            }
            Text(summary.snippet)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
            HStack(spacing: 6) {
                Label(summary.webEnabled ? "Web on" : "Web off", systemImage: "globe")
                    .font(.caption2)
                    .foregroundStyle(summary.webEnabled ? Color.accentColor : Color.secondary)
                Label(summary.reasoningLevel.capitalized, systemImage: "brain.head.profile")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Spacer()
                Text(summary.lastUpdated.formatted(date: .abbreviated, time: .shortened))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(summary.id == selectedTranscriptId ? Color.accentColor.opacity(0.15) : Color.secondary.opacity(0.08))
        )
    }

    private func transcriptPreview(_ transcript: ChatTranscript) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(transcript.title)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Spacer()
                Button {
                    selectedTranscriptId = nil
                    viewModel.clearPreview()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(Color.secondary)
                }
                .buttonStyle(.plain)
            }
            Text("Last updated \(transcript.updatedAt.formatted(date: .numeric, time: .shortened))")
                .font(.caption)
                .foregroundStyle(.secondary)

            ScrollView {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(Array(transcript.messages.enumerated()), id: \.offset) { _, message in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(message.role == "user" ? "You" : "Coach")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)
                            Text(message.text)
                                .font(.footnote)
                                .foregroundStyle(.primary)
                            Text(message.sentAt.formatted(date: .omitted, time: .shortened))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: message.role == "user" ? .trailing : .leading)
                        .padding(8)
                        .background(
                            message.role == "user"
                                ? Color.accentColor.opacity(0.12)
                                : Color.secondary.opacity(0.08),
                            in: RoundedRectangle(cornerRadius: 10, style: .continuous)
                        )
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: 220)
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color(nsColor: .underPageBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.primary.opacity(0.08), lineWidth: 1)
        )
    }

    private func configureViewModel(with backend: String) {
        viewModel.updateProfile(
            goal: settings.learnerGoal,
            useCase: settings.learnerUseCase,
            strengths: settings.learnerStrengths
        )
        viewModel.updateUser(settings.arcadiaUsername)
        viewModel.updatePreferences(
            webEnabled: settings.chatWebSearchEnabled,
            reasoningLevel: settings.chatReasoningLevel
        )
        viewModel.handleBackendChange(backend)
    }

    private func presentAttachmentPicker() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Attach"
        panel.begin { response in
            guard response == .OK, let url = panel.url else { return }
            Task {
                await viewModel.uploadAttachment(from: url)
            }
        }
    }

    private var trimmedBackendURL: String {
        settings.chatkitBackendURL.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
