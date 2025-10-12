import SwiftUI

struct OnboardingAssessmentFlow: View {
    @EnvironmentObject private var appVM: AppViewModel
    @EnvironmentObject private var settings: AppSettings
    @State private var activeIndex: Int = 0
    @State private var finishingAssessment = false

    var body: some View {
        NavigationStack {
            GeometryReader { proxy in
                if let assessment = appVM.onboardingAssessment,
                   let curriculum = appVM.curriculumPlan {
                    let contentWidth = min(proxy.size.width, 980)
                    ScrollView(.vertical, showsIndicators: true) {
                        VStack(alignment: .leading, spacing: 22) {
                            curriculumSummary(plan: curriculum)
                            taskPicker(for: assessment)
                            Divider()
                            taskDetail(for: assessment)
                        }
                        .frame(maxWidth: contentWidth, alignment: .leading)
                        .frame(minWidth: proxy.size.width, minHeight: proxy.size.height, alignment: .topLeading)
                        .padding(24)
                    }
                    .safeAreaInset(edge: .bottom) {
                        VStack(spacing: 0) {
                            Divider()
                            footerControls(for: assessment)
                                .frame(maxWidth: contentWidth, alignment: .leading)
                                .padding(.horizontal, 24)
                                .padding(.vertical, 16)
                        }
                        .background(.ultraThinMaterial)
                        .shadow(color: .black.opacity(0.15), radius: 8, y: -2)
                    }
                    .frame(width: proxy.size.width, height: proxy.size.height)
                } else {
                    ProgressView("Loading assessment…")
                        .frame(width: proxy.size.width, height: proxy.size.height, alignment: .center)
                }
            }
            .frame(minWidth: 780, minHeight: 580)
            .navigationTitle("Onboarding Assessment")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") {
                        appVM.closeAssessmentFlow()
                    }
                }
            }
        }
        .task {
            await startAssessmentIfNeeded()
        }
        .onChange(of: appVM.onboardingAssessment?.tasks.count ?? 0) { _ in
            activeIndex = 0
        }
    }

    @ViewBuilder
    private func curriculumSummary(plan: OnboardingCurriculumPlan) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Curriculum Overview")
                .font(.title3)
                .bold()
            Text(plan.overview)
                .font(.body)
            if !plan.successCriteria.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Success criteria")
                        .font(.headline)
                    ForEach(plan.successCriteria, id: \.self) { criterion in
                        Text("• \(criterion)")
                            .font(.subheadline)
                    }
                }
            }
            if !plan.modules.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Modules")
                        .font(.headline)
                    ForEach(plan.modules) { module in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(module.title)
                                    .font(.subheadline).bold()
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
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
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
                    HStack(spacing: 12) {
                        ForEach(Array(tasks.enumerated()), id: \.1.taskId) { index, task in
                            Button {
                                activeIndex = index
                            } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Task \(index + 1)")
                                        .font(.footnote)
                                        .bold()
                                    Text(task.taskType.label)
                                        .font(.caption)
                                    Text(categoryLabel(for: task.categoryKey))
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                                .padding(.vertical, 10)
                                .padding(.horizontal, 12)
                                .frame(minWidth: 120)
                                .background(activeIndex == index ? Color.accentColor.opacity(0.18) : Color.primary.opacity(0.05))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(activeIndex == index ? Color.accentColor : Color.secondary.opacity(0.3), lineWidth: 1)
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

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    HStack(alignment: .firstTextBaseline, spacing: 12) {
                        Text(task.title)
                            .font(.title2)
                            .bold()
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
                        .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(Color.secondary.opacity(0.25))
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
                .padding(.vertical, 4)
            }
        }
    }

    @ViewBuilder
    private func footerControls(for assessment: OnboardingAssessment) -> some View {
        let tasks = assessment.tasks
        let total = tasks.count
        let index = min(activeIndex, max(total - 1, 0))
        let answeredCount = tasks.filter { !$0.taskId.isEmpty && !appVM.response(for: $0.taskId).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }.count
        let allAnswered = answeredCount == total && total > 0

        VStack(alignment: .leading, spacing: 12) {
            ProgressView(value: Double(answeredCount), total: Double(max(total, 1)))
            Text("Answered \(answeredCount) of \(total) prompts")
                .font(.footnote)
                .foregroundStyle(.secondary)

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
                            await appVM.updateAssessmentStatus(
                                to: .completed,
                                baseURL: settings.chatkitBackendURL,
                                username: settings.arcadiaUsername
                            )
                            await MainActor.run {
                                finishingAssessment = false
                                appVM.closeAssessmentFlow()
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
                    .disabled(!allAnswered || finishingAssessment)
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
