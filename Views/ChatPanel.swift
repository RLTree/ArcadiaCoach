import SwiftUI
import AppKit
import UniformTypeIdentifiers

private struct ChatModelOption: Identifiable, Hashable {
    let id: String
    let name: String
    let detail: String
    let supportsWeb: Bool
    let attachmentPolicy: ChatModelCapability.AttachmentPolicy

    var capability: ChatModelCapability {
        ChatModelCapability(supportsWeb: supportsWeb, attachmentPolicy: attachmentPolicy)
    }
}

struct ChatPanel: View {
    @EnvironmentObject private var settings: AppSettings
    @EnvironmentObject private var appVM: AppViewModel
    @StateObject private var viewModel = AgentChatViewModel()
    @State private var selectedTranscriptId: String?
    @State private var selectedModelId: String = "gpt-5"
    @State private var suppressModelChange = false

    private let clipboard: ClipboardManaging = AppClipboardManager.shared
    private let modelOptions: [ChatModelOption] = [
        ChatModelOption(
            id: "gpt-5",
            name: "GPT-5",
            detail: "Full tools (web search, file uploads).",
            supportsWeb: true,
            attachmentPolicy: .any
        ),
        ChatModelOption(
            id: "gpt-5-mini",
            name: "GPT-5 Mini",
            detail: "Faster responses with web and files enabled.",
            supportsWeb: true,
            attachmentPolicy: .any
        ),
        ChatModelOption(
            id: "gpt-5-codex",
            name: "GPT-5 Codex",
            detail: "Code-first with web search; image uploads only.",
            supportsWeb: true,
            attachmentPolicy: .imagesOnly
        ),
        ChatModelOption(
            id: "gpt-5-nano",
            name: "GPT-5 Nano",
            detail: "Fastest responses. No file uploads; web search optional.",
            supportsWeb: true,
            attachmentPolicy: .none
        ),
    ]

    var body: some View {
        let backend = trimmedBackendURL
        let option = modelOption(for: selectedModelId) ?? modelOptions[0]
        let composerAttachments = viewModel.allowsAttachments ? viewModel.composerAttachments : []
        let canAddAttachment = !backend.isEmpty && viewModel.allowsAttachments

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

                Picker("Model", selection: $selectedModelId) {
                    ForEach(modelOptions) { option in
                        Text(option.name).tag(option.id)
                    }
                }
                .pickerStyle(.segmented)

                modelInfoSection(option)

                chatbotSurface(
                    backend: backend,
                    composerAttachments: composerAttachments,
                    canAddAttachment: canAddAttachment
                )

                if !backend.isEmpty {
                    Text("Connected to \(backend).")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .selectableContent()
                }

                if let error = viewModel.lastError, !error.isEmpty {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .selectableContent()
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
                strengths: settings.learnerStrengths,
                timezone: settings.learnerTimezone
            )
        }
        .onChange(of: settings.learnerUseCase) { newValue in
            viewModel.updateProfile(
                goal: settings.learnerGoal,
                useCase: newValue,
                strengths: settings.learnerStrengths,
                timezone: settings.learnerTimezone
            )
        }
        .onChange(of: settings.learnerStrengths) { newValue in
            viewModel.updateProfile(
                goal: settings.learnerGoal,
                useCase: settings.learnerUseCase,
                strengths: newValue,
                timezone: settings.learnerTimezone
            )
        }
        .onChange(of: settings.learnerTimezone) { newValue in
            viewModel.updateProfile(
                goal: settings.learnerGoal,
                useCase: settings.learnerUseCase,
                strengths: settings.learnerStrengths,
                timezone: newValue
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
        .onChange(of: selectedModelId) { newModel in
            if suppressModelChange {
                suppressModelChange = false
                return
            }
            guard let option = modelOption(for: newModel) else { return }
            settings.chatModel = newModel
            if !option.supportsWeb {
                settings.chatWebSearchEnabled = false
            }
            viewModel.applyModel(
                option.id,
                capability: option.capability,
                backendURL: backend
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
        .onChange(of: viewModel.activeTranscriptId) { active in
            if selectedTranscriptId == nil {
                selectedTranscriptId = active
            }
        }
        .sheet(
            item: Binding(
                get: { appVM.focusedSubmission },
                set: { newValue in
                    if let submission = newValue {
                        appVM.focus(on: submission)
                    } else {
                        appVM.dismissSubmissionFocus()
                    }
                }
            )
        ) { submission in
            AssessmentSubmissionDetailView(
                submission: submission,
                plan: appVM.eloPlan,
                curriculum: appVM.curriculumPlan
            )
            .environmentObject(settings)
            .environmentObject(appVM)
        }
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 12) {
            assessmentSidebarSummary
            if !eloSidebarEntries.isEmpty {
                eloSidebarSummary
            }
            Divider()
            Text("Previous Sessions")
                .font(.headline)
                .selectableContent()

            if viewModel.recents.isEmpty {
                Text("Once you chat with Arcadia Coach, your transcripts will appear here for quick reference.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .selectableContent()
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(viewModel.recents) { summary in
                            let isActive = summary.id == viewModel.activeTranscriptId
                            Button {
                                selectedTranscriptId = summary.id
                                viewModel.showTranscript(withId: summary.id)
                            } label: {
                                summaryCard(for: summary, isActive: isActive)
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

    private var assessmentSidebarSummary: some View {
        let readiness = appVM.assessmentReadinessStatus
        let statusColor = readiness.tintColor
        let submissionLabel = appVM.latestAssessmentSubmittedAt?
            .formatted(date: .abbreviated, time: .shortened) ?? "No submissions recorded"
        let pendingSubmission = appVM.assessmentHistory.first { $0.grading == nil }
        let gradingLabel: String
        if let pendingSubmission {
            gradingLabel = "Pending since \(pendingSubmission.submittedAt.formatted(date: .abbreviated, time: .shortened))"
        } else if let gradedAt = appVM.latestAssessmentGradeTimestamp {
            gradingLabel = gradedAt.formatted(date: .abbreviated, time: .shortened)
        } else {
            gradingLabel = "No grading yet"
        }
        let averageLabel = appVM.latestGradedAssessment?.averageScoreLabel
        let feedback = appVM.latestGradedAssessment?.grading?.overallFeedback
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let recentHistory = Array(appVM.assessmentHistory.prefix(2))

        return VStack(alignment: .leading, spacing: 8) {
            Text("Assessment")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)

            HStack(spacing: 8) {
                Image(systemName: readiness.systemImageName)
                    .foregroundStyle(statusColor)
                Text(readiness.displayText)
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(statusColor)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Submitted: \(submissionLabel)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                if let averageLabel {
                    Text("Latest avg: \(averageLabel)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Text("Graded: \(gradingLabel)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                if let feedback, !feedback.isEmpty {
                    Text("\"\(feedback)\"")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                } else if readiness == .awaitingGrading {
                    Text("Arcadia Coach will update ratings after grading completes.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }

            if !recentHistory.isEmpty {
                Divider()
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(recentHistory, id: \.submissionId) { submission in
                        Button {
                            appVM.focus(on: submission)
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(submission.submittedAt.formatted(date: .abbreviated, time: .shortened))
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                    Spacer()
                                    let badgeColor: Color = submission.grading == nil ? .orange : .green
                                    Text(submission.statusLabel)
                                        .font(.caption2.weight(.semibold))
                                        .foregroundStyle(badgeColor)
                                }
                                if let average = submission.averageScoreLabel, submission.grading != nil {
                                    Text("Avg \(average)")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                } else if submission.grading == nil {
                                    Text("Grading in progress")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                                if let outcomes = submission.grading?.categoryOutcomes {
                                    let delta = outcomes.reduce(0) { $0 + $1.ratingDelta }
                                    if delta != 0 {
                                        let label = delta > 0 ? "+\(delta)" : "\(delta)"
                                        Text("ΔELO \(label)")
                                            .font(.caption2.weight(.semibold))
                                            .foregroundStyle(delta > 0 ? .green : .orange)
                                    }
                                }
                            }
                            .padding(8)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color.primary.opacity(0.05))
        )
        .selectableContent()
        .contextMenu {
            Button("Copy Assessment Status") {
                clipboard.copy(readiness.displayText)
            }
            Button("Copy Latest Submission Info") {
                let info = """
                Submitted: \(submissionLabel)
                Graded: \(gradingLabel)
                Average: \(averageLabel ?? "N/A")
                """
                clipboard.copy(info)
            }
        }
    }

    @ViewBuilder
    private var eloSidebarSummary: some View {
        let entries = eloSidebarEntries
        if entries.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 8) {
                Text("ELO Snapshot")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)

                ForEach(entries.prefix(4), id: \.label) { entry in
                    HStack {
                        Text(entry.label)
                            .font(.caption)
                            .foregroundStyle(.primary)
                            .lineLimit(1)
                        Spacer()
                        Text("\(entry.value)")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.primary)
                    }
                }

                if entries.count > 4 {
                    Text("+\(entries.count - 4) more categories")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                if let stamp = appVM.latestAssessmentGradeTimestamp {
                    Text("Calibrated \(stamp.formatted(date: .abbreviated, time: .shortened))")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                } else if appVM.assessmentHistory.first(where: { $0.grading == nil }) != nil {
                    Text("Ratings refresh once grading finishes.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Color.primary.opacity(0.03))
            )
            .selectableContent()
            .contextMenu {
                Button("Copy Top Categories") {
                    let rows = entries.prefix(4).map { "\($0.label): \($0.value)" }
                    clipboard.copy(rows.joined(separator: "\n"))
                }
            }
        }
    }

    private var eloSidebarEntries: [(label: String, value: Int)] {
        let labels = categoryLabels
        return appVM.game.elo
            .sorted { $0.value > $1.value }
            .map { (labels[$0.key] ?? $0.key, $0.value) }
    }

    private var categoryLabels: [String:String] {
        guard let plan = appVM.eloPlan else { return [:] }
        return Dictionary(uniqueKeysWithValues: plan.categories.map { ($0.key, $0.label) })
    }

    private func summaryCard(for summary: ChatTranscriptSummary, isActive: Bool) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(summary.title)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Spacer()
                if isActive {
                    Text("Active")
                        .font(.caption2.weight(.semibold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.2), in: Capsule())
                } else if summary.id == selectedTranscriptId {
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
                .fill(
                    isActive
                        ? Color.accentColor.opacity(0.28)
                        : (summary.id == selectedTranscriptId ? Color.accentColor.opacity(0.15) : Color.secondary.opacity(0.08))
                )
        )
        .selectableContent()
        .contextMenu {
            Button("Copy Title") {
                clipboard.copy(summary.title)
            }
            Button("Copy Snippet") {
                clipboard.copy(summary.snippet)
            }
            Button("Copy Last Updated") {
                let timestamp = summary.lastUpdated.formatted(date: .abbreviated, time: .shortened)
                clipboard.copy(timestamp)
            }
        }
    }

    private func transcriptPreview(_ transcript: ChatTranscript) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(transcript.title)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Spacer()
                Button {
                    resumeTranscript(transcript)
                } label: {
                    Label("Resume", systemImage: "arrow.uturn.backward")
                        .font(.caption)
                }
                .buttonStyle(.borderless)
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
            HStack(spacing: 10) {
                let option = modelOption(for: transcript.model) ?? modelOptions[0]
                Label(option.name, systemImage: "cpu")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Label(transcript.webEnabled ? "Web on" : "Web off", systemImage: "globe")
                    .font(.caption2)
                    .foregroundStyle(transcript.webEnabled ? Color.accentColor : Color.secondary)
                Label(transcript.reasoningLevel.capitalized, systemImage: "brain.head.profile")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

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
        .selectableContent()
        .contextMenu {
            Button("Copy Title") {
                clipboard.copy(transcript.title)
            }
            Button("Copy Transcript") {
                let combined = transcript.messages.map { message -> String in
                    let speaker = message.role == "user" ? "You" : "Coach"
                    return "\(speaker): \(message.text)"
                }.joined(separator: "\n\n")
                clipboard.copy(combined)
            }
        }
    }

    private func configureViewModel(with backend: String) {
        if modelOption(for: settings.chatModel) == nil {
            settings.chatModel = "gpt-5"
        }
        selectedModelId = settings.chatModel
        let option = modelOption(for: selectedModelId) ?? modelOptions[0]
        if !option.supportsWeb {
            settings.chatWebSearchEnabled = false
        }
        viewModel.updateProfile(
            goal: settings.learnerGoal,
            useCase: settings.learnerUseCase,
            strengths: settings.learnerStrengths,
            timezone: settings.learnerTimezone
        )
        viewModel.updateUser(settings.arcadiaUsername)
        viewModel.updatePreferences(
            webEnabled: settings.chatWebSearchEnabled,
            reasoningLevel: settings.chatReasoningLevel
        )
        viewModel.applyModel(
            option.id,
            capability: option.capability,
            backendURL: backend
        )
        viewModel.handleBackendChange(backend)
    }

    private func presentAttachmentPicker() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Attach"
        if viewModel.allowsImagesOnly {
            if #available(macOS 11.0, *) {
                panel.allowedContentTypes = [.image]
            }
        }
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

    private func resumeTranscript(_ transcript: ChatTranscript) {
        let option = modelOption(for: transcript.model) ?? modelOptions[0]
        let didChangeModel = selectedModelId != option.id
        suppressModelChange = true
        selectedModelId = option.id
        if !didChangeModel {
            suppressModelChange = false
        }
        viewModel.resumeTranscript(transcript, modelId: option.id, capability: option.capability)

        let shouldEnableWeb = option.supportsWeb && transcript.webEnabled
        settings.chatModel = option.id
        settings.chatWebSearchEnabled = shouldEnableWeb
        settings.chatReasoningLevel = transcript.reasoningLevel
        selectedTranscriptId = transcript.id
    }

    private func modelOption(for id: String) -> ChatModelOption? {
        modelOptions.first(where: { $0.id == id })
    }

    private func modelInfoSection(_ option: ChatModelOption) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(option.detail)
                .font(.caption)
                .foregroundStyle(.secondary)
            switch option.attachmentPolicy {
            case .none:
                Text("File uploads are disabled for \(option.name).")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            case .imagesOnly:
                Text("Only image uploads (PNG, JPG, GIF) are supported for \(option.name).")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            case .any:
                EmptyView()
            }
            if !option.supportsWeb {
                Text("Web search is disabled for \(option.name).")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func chatbotSurface(
        backend: String,
        composerAttachments: [ChatAttachment],
        canAddAttachment: Bool
    ) -> some View {
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
            onToggleWeb: viewModel.modelSupportsWeb ? { enabled in
                settings.chatWebSearchEnabled = enabled
                viewModel.toggleWebSearch(enabled)
            } : nil,
            composerAttachments: composerAttachments,
            isAttachmentUploading: viewModel.isUploadingAttachment,
            onAddAttachment: canAddAttachment ? presentAttachmentPicker : nil,
            onRemoveAttachment: { id in
                viewModel.removeAttachment(id: id)
            },
            allowsImagesOnly: viewModel.allowsImagesOnly,
            onSubmit: { text in
                await viewModel.send(message: text)
            }
        )
        .frame(minHeight: 440)
    }
}
