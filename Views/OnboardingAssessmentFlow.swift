import SwiftUI

struct OnboardingAssessmentFlow: View {
    @EnvironmentObject private var appVM: AppViewModel
    @EnvironmentObject private var settings: AppSettings
    @State private var activeIndex: Int = 0
    @State private var finishingAssessment = false

    private let cornerRadius: CGFloat = 24
    private let maxContentWidth: CGFloat = 960
    private let minContentWidth: CGFloat = 580
    private let desiredModalHeight: CGFloat = 680
    private let minModalHeight: CGFloat = 420
    private let chromeAllowance: CGFloat = 150
    private let safeInsets: CGFloat = 120

    var body: some View {
        GeometryReader { proxy in
            let modalWidth = min(maxContentWidth, max(minContentWidth, proxy.size.width - 96))
            let availableHeight = max(minModalHeight, proxy.size.height - safeInsets)
            let modalMaxHeight = min(desiredModalHeight, availableHeight)
            let scrollMaxHeight = max(160, modalMaxHeight - chromeAllowance)

            VStack(spacing: 0) {
                header
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 26)
                    .padding(.top, 24)
                    .padding(.bottom, 14)

                Divider()

                ScrollView(.vertical, showsIndicators: true) {
                    VStack(alignment: .leading, spacing: 24) {
                        if let curriculum = appVM.curriculumPlan {
                            curriculumSummary(plan: curriculum)
                        }
                        if let assessment = appVM.onboardingAssessment {
                            taskPicker(for: assessment)
                            Divider()
                            taskDetail(for: assessment)
                        } else {
                            ProgressView("Preparing personalised assessment…")
                                .controlSize(.large)
                                .padding(.vertical, 48)
                                .frame(maxWidth: .infinity, alignment: .center)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 26)
                    .padding(.vertical, 20)
                }
                .frame(maxHeight: scrollMaxHeight, alignment: .top)

                Divider()

                footer
                    .padding(.horizontal, 26)
                    .padding(.vertical, 18)
            }
            .frame(width: modalWidth, alignment: .top)
            .background(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(.ultraThinMaterial)
                    .shadow(color: .black.opacity(0.22), radius: 22, y: 10)
            )
            .frame(maxHeight: modalMaxHeight, alignment: .top)
            .padding(.horizontal, 24)
            .padding(.vertical, 20)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .task {
            await startAssessmentIfNeeded()
        }
        .onChange(of: appVM.onboardingAssessment?.tasks.count ?? 0) { _ in
            activeIndex = 0
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Onboarding Assessment")
                    .font(.title2.weight(.semibold))
                if let status = appVM.onboardingAssessment?.status {
                    Label(statusLabel(for: status), systemImage: statusIcon(for: status))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            Button {
                appVM.closeAssessmentFlow()
            } label: {
                Label("Close", systemImage: "xmark.circle.fill")
                    .labelStyle(.titleAndIcon)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.regular)
        }
    }

    private func statusLabel(for status: OnboardingAssessment.Status) -> String {
        switch status {
        case .pending: "Pending calibration"
        case .inProgress: "In progress"
        case .completed: "Completed"
        }
    }

    private func statusIcon(for status: OnboardingAssessment.Status) -> String {
        switch status {
        case .pending: "clock"
        case .inProgress: "arrow.triangle.2.circlepath"
        case .completed: "checkmark.circle"
        }
    }

    // MARK: - Content Builders

    @ViewBuilder
    private func curriculumSummary(plan: OnboardingCurriculumPlan) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Curriculum Overview")
                .font(.title3.weight(.semibold))
            Text(plan.overview)
                .font(.body)
            if !plan.successCriteria.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Success Criteria")
                        .font(.headline)
                    ForEach(plan.successCriteria, id: \.self) { item in
                        Text("• \(item)")
                            .font(.subheadline)
                    }
                }
            }
            if !plan.modules.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Modules")
                        .font(.headline)
                    ForEach(plan.modules) { module in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text(module.title)
                                    .font(.subheadline.bold())
                                Spacer()
                                Text(module.formattedDuration)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Text(module.summary)
                                .font(.footnote)
                            if !module.objectives.isEmpty {
                                Text("Objectives: \(module.objectives.joined(separator: ", "))")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(12)
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func taskPicker(for assessment: OnboardingAssessment) -> some View {
        let tasks = assessment.tasks
        if tasks.isEmpty {
            Text("No assessment tasks available.")
                .foregroundStyle(.secondary)
        } else {
            VStack(alignment: .leading, spacing: 8) {
                Text("Tasks")
                    .font(.headline)
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(Array(tasks.enumerated()), id: \.1.taskId) { index, task in
                            Button {
                                activeIndex = index
                            } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Task \(index + 1)")
                                        .font(.footnote.bold())
                                    Text(task.taskType.label)
                                        .font(.caption)
                                    Text(categoryLabel(for: task.categoryKey))
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                                .padding(.vertical, 9)
                                .padding(.horizontal, 11)
                                .frame(minWidth: 110)
                                .background(activeIndex == index ? Color.accentColor.opacity(0.18) : Color.primary.opacity(0.05))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(activeIndex == index ? Color.accentColor : Color.secondary.opacity(0.28), lineWidth: 1)
                                )
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func taskDetail(for assessment: OnboardingAssessment) -> some View {
        let tasks = assessment.tasks
        if tasks.isEmpty {
            Text("No tasks to display.")
                .foregroundStyle(.secondary)
        } else {
            let index = min(activeIndex, tasks.count - 1)
            let task = tasks[index]
            let response = Binding(
                get: { appVM.response(for: task.taskId) },
                set: { appVM.setResponse($0, for: task.taskId) }
            )

            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    Text(task.title)
                        .font(.title2.weight(.semibold))
                    Spacer()
                    Text("Expected \(task.expectedMinutes) min")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Text(categoryLabel(for: task.categoryKey))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Text(task.prompt)
                    .font(.body)
                if !task.guidance.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text(task.guidance)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                if !task.rubric.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Rubric checkpoints")
                            .font(.headline)
                        ForEach(task.rubric, id: \.self) { item in
                            Text("• \(item)")
                                .font(.footnote)
                        }
                    }
                }

                if task.taskType == .code, let starter = task.starterCode, !starter.isEmpty {
                    Button("Insert starter code") {
                        appVM.insertStarter(for: task)
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 4)
                }

                TextEditor(text: response)
                    .font(task.taskType == .code ? .system(.body, design: .monospaced) : .body)
                    .frame(minHeight: task.taskType == .code ? 220 : 160)
                    .padding(10)
                    .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 12))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(Color.secondary.opacity(0.22))
                    )

                if task.taskType == .code, let answer = task.answerKey, !answer.isEmpty {
                    DisclosureGroup("Agent reference solution") {
                        Text(answer)
                            .font(.system(.footnote, design: .monospaced))
                            .padding(12)
                            .background(Color.primary.opacity(0.03), in: RoundedRectangle(cornerRadius: 8))
                    }
                }
            }
        }
    }

    // MARK: - Footer / Controls

    @ViewBuilder
    private var footer: some View {
        if let assessment = appVM.onboardingAssessment {
            footerControls(for: assessment)
        } else {
            HStack {
                Spacer()
                ProgressView()
                    .controlSize(.small)
                Spacer()
            }
        }
    }

    @ViewBuilder
    private func footerControls(for assessment: OnboardingAssessment) -> some View {
        let tasks = assessment.tasks
        let total = tasks.count
        let index = min(activeIndex, max(total - 1, 0))
        let answeredCount = tasks.filter { appVM.isAssessmentTaskAnswered($0) }.count
        let allAnswered = answeredCount == total && total > 0

        VStack(alignment: .leading, spacing: 12) {
            ProgressView(value: Double(answeredCount), total: Double(max(total, 1)))
            Text("Answered \(answeredCount) of \(total) prompts")
                .font(.footnote)
                .foregroundStyle(.secondary)
            if appVM.requiresAssessment, let message = appVM.error, !message.isEmpty {
                Text(message)
                    .font(.footnote)
                    .foregroundStyle(.red)
            }

            HStack {
                Button("Previous") {
                    activeIndex = max(index - 1, 0)
                }
                .disabled(index == 0)

                Button("Next") {
                    activeIndex = min(index + 1, total - 1)
                }
                .disabled(index >= total - 1)

                Spacer()

                if assessment.status != .completed {
                    Button {
                        finishingAssessment = true
                        Task {
                            let success = await appVM.submitAndCompleteAssessment(
                                baseURL: settings.chatkitBackendURL,
                                username: settings.arcadiaUsername
                            )
                            await MainActor.run {
                                finishingAssessment = false
                                if success {
                                    appVM.closeAssessmentFlow()
                                }
                            }
                        }
                    } label: {
                        if finishingAssessment {
                            ProgressView().controlSize(.small)
                        } else {
                            Text("Mark Completed")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(
                        !allAnswered ||
                        finishingAssessment ||
                        settings.chatkitBackendURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                        settings.arcadiaUsername.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    )
                } else {
                    Button("Done") {
                        appVM.closeAssessmentFlow()
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
    }

    private func categoryLabel(for key: String) -> String {
        guard let plan = appVM.eloPlan else { return key.capitalized }
        return plan.categories.first(where: { $0.key == key })?.label ?? key.capitalized
    }

    private func startAssessmentIfNeeded() async {
        guard let assessment = appVM.onboardingAssessment else { return }
        guard assessment.status == .pending else { return }
        await appVM.updateAssessmentStatus(
            to: .inProgress,
            baseURL: settings.chatkitBackendURL,
            username: settings.arcadiaUsername
        )
    }
}
