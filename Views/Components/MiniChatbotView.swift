import SwiftUI

struct MiniChatbotView: View {
    var title: String
    var status: String
    var placeholder: String
    var messages: [ChatMessage]
    var canSend: Bool
    var isSending: Bool
    var onSubmit: (String) async -> Void

    @State private var draft: String = ""
    @FocusState private var isTextFocused: Bool

    private var statusColor: Color {
        switch status.lowercased() {
        case "online": return .green
        case "thinking…", "thinking...": return .orange
        default: return .gray
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            Divider()
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
            Divider()
            inputArea
        }
        .padding(18)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.primary.opacity(0.08), lineWidth: 1)
        )
    }

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: "sparkles")
                .foregroundStyle(.blue)
            Text(title)
                .font(.headline)
            Spacer()
            Text(status)
                .font(.caption)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(statusColor.opacity(0.15), in: Capsule())
        }
    }

    @ViewBuilder
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
                        .stroke(Color.primary.opacity(0.08), lineWidth: 1)
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
                    Task {
                        await submit()
                    }
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
