import SwiftUI

struct ArcadiaChatbotView: View {
    var title: String
    var levelLabel: String
    var messages: [ChatMessage]
    var placeholder: String
    var status: String
    var canSend: Bool
    var isSending: Bool
    var webEnabled: Bool
    var showTonePicker: Bool
    var levels: [ArcadiaChatbotLevelOption]
    var selectedLevel: String
    var onSubmit: (String) async -> Void

    @State private var draft: String = ""
    @FocusState private var isTextFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            Divider()
            messagesSection
            tonePickerSection
            Divider()
            statusRow
            inputArea
        }
        .padding(18)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color(.controlBackgroundColor).opacity(0.9))
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(Color.primary.opacity(0.08), lineWidth: 1)
                )
        )
        .onChange(of: messages.count) { _ in
            guard !isTextFocused else { return }
            DispatchQueue.main.async {
                isTextFocused = false
            }
        }
    }

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: "sparkles")
                .foregroundStyle(.blue)
            Text(title)
                .font(.headline)
            Spacer()
            Text(levelLabel)
                .font(.caption.weight(.semibold))
                .padding(.horizontal, 12)
                .padding(.vertical, 4)
                .background(Color.accentColor.opacity(0.18), in: Capsule())
        }
    }

    private var messagesSection: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(messages) { message in
                        messageRow(message)
                            .id(message.id)
                    }
                }
                .padding(.vertical, 4)
            }
            .background(Color.clear)
            .onChange(of: messages) { value in
                guard let last = value.last?.id else { return }
                DispatchQueue.main.async {
                    withAnimation(.easeOut(duration: 0.2)) {
                        proxy.scrollTo(last, anchor: .bottom)
                    }
                }
            }
        }
    }

    private func messageRow(_ message: ChatMessage) -> some View {
        HStack(alignment: .bottom, spacing: 8) {
            if message.role == .assistant {
                avatar(systemName: "sparkles")
            }
            Text(message.text)
                .font(.body)
                .foregroundColor(.primary)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(bubbleBackground(for: message.role))
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(Color.primary.opacity(0.06), lineWidth: 1)
                )
                .frame(maxWidth: 420, alignment: message.role == .user ? .trailing : .leading)
            if message.role == .user {
                avatar(systemName: "person.fill")
            }
        }
        .frame(maxWidth: .infinity, alignment: message.role == .user ? .trailing : .leading)
        .transition(.move(edge: message.role == .user ? .trailing : .leading).combined(with: .opacity))
    }

    private func avatar(systemName: String) -> some View {
        Image(systemName: systemName)
            .font(.caption)
            .padding(8)
            .background(Color.primary.opacity(0.08), in: Circle())
    }

    private func bubbleBackground(for role: ChatMessage.Role) -> some ShapeStyle {
        switch role {
        case .assistant:
            return AnyShapeStyle(Color.secondary.opacity(0.12))
        case .user:
            return AnyShapeStyle(Color.accentColor.opacity(0.15))
        }
    }

    @ViewBuilder
    private var tonePickerSection: some View {
        if showTonePicker && !levels.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Reasoning effort")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 120), spacing: 8)], spacing: 8) {
                    ForEach(levels, id: \.value) { level in
                        Text(level.label)
                            .font(.footnote.weight(level.value == selectedLevel ? .semibold : .regular))
                            .padding(.vertical, 6)
                            .padding(.horizontal, 12)
                            .frame(maxWidth: .infinity)
                            .background(
                                (level.value == selectedLevel ? Color.accentColor.opacity(0.18) : Color.secondary.opacity(0.12)),
                                in: Capsule()
                            )
                            .overlay(
                                Capsule()
                                    .stroke(level.value == selectedLevel ? Color.accentColor : Color.clear, lineWidth: 1)
                            )
                            .foregroundStyle(level.value == selectedLevel ? Color.accentColor : Color.primary)
                            .accessibilityLabel("Reasoning effort \(level.label)")
                    }
                }
            }
        }
    }

    private var statusRow: some View {
        HStack(spacing: 12) {
            Label {
                Text(status)
            } icon: {
                Image(systemName: statusImageName)
            }
            .font(.footnote.weight(.semibold))
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(Color.secondary.opacity(0.12), in: Capsule())

            Label {
                Text(webEnabled ? "Web search on" : "Web search off")
            } icon: {
                Image(systemName: "globe")
            }
            .font(.footnote)
            .foregroundStyle(webEnabled ? Color.accentColor : Color.secondary)

            Spacer()
        }
    }

    private var statusImageName: String {
        switch status.lowercased() {
        case "thinking…", "thinking...": return "hourglass"
        case "offline": return "wifi.slash"
        default: return "bolt"
        }
    }

    private var inputArea: some View {
        VStack(alignment: .leading, spacing: 8) {
            ZStack(alignment: .topLeading) {
                TextEditor(text: $draft)
                    .focused($isTextFocused)
                    .frame(minHeight: 60, maxHeight: 120)
                    .padding(8)
                    .scrollContentBackground(.hidden)
                    .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                if draft.isEmpty {
                    Text(placeholder)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 14)
                }
            }
            HStack {
                if isSending {
                    ProgressView()
                        .progressViewStyle(.circular)
                        .tint(.accentColor)
                } else {
                    Spacer()
                }
                Button {
                    Task { await submit() }
                } label: {
                    HStack(spacing: 6) {
                        Text("Send")
                        Image(systemName: "paperplane.fill")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(!canSend || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
    }

    private func submit() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draft = ""
        await onSubmit(text)
    }
}
