import SwiftUI

struct AssessmentSubmissionDetailView: View {
    @EnvironmentObject private var appVM: AppViewModel
    @EnvironmentObject private var settings: AppSettings
    @Environment(\.dismiss) private var dismiss

    let submission: AssessmentSubmissionRecord
    let plan: EloCategoryPlan?
    let curriculum: OnboardingCurriculumPlan?

    private var grading: AssessmentGradingResult? { submission.grading }

    private var categoryOutcomes: [AssessmentCategoryOutcome] {
        grading?.categoryOutcomes ?? []
    }

    private var blockedOutcomes: [AssessmentCategoryOutcome] {
        categoryOutcomes.filter { $0.ratingDelta <= 0 }
    }

    private var totalDelta: Int {
        categoryOutcomes.reduce(0) { $0 + $1.ratingDelta }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    headerSection
                    attachmentsSection
                    responsesSection
                    gradingOverviewSection
                    categoryImpactSection
                    taskDrilldownsSection
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(24)
            }
            .background(Color(nsColor: .windowBackgroundColor).ignoresSafeArea())
            .navigationTitle(titleLabel)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .frame(minWidth: 720, minHeight: 640)
    }

    private var titleLabel: String {
        let dateLabel = submission.submittedAt.formatted(date: .abbreviated, time: .shortened)
        return "Submission · \(dateLabel)"
    }

    @ViewBuilder
    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Text(submission.statusLabel)
                    .font(.title3.bold())
                Spacer()
                if let gradedAt = submission.gradedAt {
                    Text("Graded \(gradedAt.formatted(date: .abbreviated, time: .shortened))")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                } else {
                    Text("Grading in progress")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            }

            HStack(alignment: .center, spacing: 16) {
                Label("Submitted \(submission.submittedAt.formatted(date: .abbreviated, time: .shortened))", systemImage: "tray.and.arrow.down")
                    .font(.callout)
                Label("\(submission.answeredCount) prompts", systemImage: "list.bullet.rectangle")
                    .font(.callout)
                if let average = submission.averageScoreLabel {
                    Label("Average \(average)", systemImage: "percent")
                        .font(.callout)
                }
                if totalDelta != 0 {
                    let deltaLabel = totalDelta > 0 ? "+\(totalDelta)" : "\(totalDelta)"
                    Label("ΔELO \(deltaLabel)", systemImage: totalDelta > 0 ? "arrow.up" : "arrow.down")
                        .font(.callout)
                        .foregroundStyle(totalDelta > 0 ? .green : .orange)
                }
            }
            .foregroundStyle(.secondary)

            if !blockedOutcomes.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Label("Blocked categories", systemImage: "exclamationmark.octagon")
                        .font(.headline)
                        .foregroundStyle(.orange)
                    ForEach(blockedOutcomes) { outcome in
                        Text("• \(appVM.label(for: outcome.categoryKey)) needs more work (Δ\(outcome.ratingDelta))")
                            .font(.callout)
                    }
                }
            }
        }
        .padding(20)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
    }

    @ViewBuilder
    private var attachmentsSection: some View {
        if submission.attachments.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 12) {
                Label("Attachments", systemImage: "paperclip")
                    .font(.headline)
                ForEach(submission.attachments) { attachment in
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: icon(for: attachment.kind))
                            .foregroundStyle(.secondary)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(attachment.name)
                                .font(.callout.weight(.semibold))
                            if let description = attachment.description, !description.isEmpty {
                                Text(description)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            if let url = attachment.url, let destination = URL(string: url) {
                                Link("Open", destination: destination)
                                    .font(.caption)
                            }
                            if let source = attachment.source, !source.isEmpty {
                                Text("Source: \(source)")
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                            }
                        }
                    }
                    .padding(.vertical, 6)
                }
            }
            .padding(20)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
        }
    }

    @ViewBuilder
    private var responsesSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Learner Responses", systemImage: "square.and.pencil")
                .font(.headline)
            ForEach(submission.responses) { response in
                DisclosureGroup {
                    ScrollView {
                        Text(response.response)
                            .font(.body.monospaced())
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .textSelection(.enabled)
                            .padding(.vertical, 4)
                    }
                    .frame(maxHeight: 200)
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(response.taskId)
                            .font(.subheadline.weight(.semibold))
                        Text(responsePreview(for: response))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding(20)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
    }

    @ViewBuilder
    private var gradingOverviewSection: some View {
        if let grading {
            VStack(alignment: .leading, spacing: 12) {
                Label("Feedback Summary", systemImage: "text.bubble")
                    .font(.headline)
                Text(grading.overallFeedback)
                    .font(.body)
                if !grading.strengths.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Strengths")
                            .font(.subheadline.bold())
                        ForEach(grading.strengths, id: \.self) { item in
                            Text("• \(item)")
                                .font(.callout)
                        }
                    }
                }
                if !grading.focusAreas.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Focus next")
                            .font(.subheadline.bold())
                        ForEach(grading.focusAreas, id: \.self) { item in
                            Text("• \(item)")
                                .font(.callout)
                        }
                    }
                }
            }
            .padding(20)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
        }
    }

    @ViewBuilder
    private var categoryImpactSection: some View {
        if !categoryOutcomes.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                Label("Category Impact", systemImage: "chart.bar")
                    .font(.headline)
                let moduleLookup: [String:[OnboardingCurriculumModule]]
                if appVM.modulesByCategory.isEmpty, let curriculum {
                    moduleLookup = Dictionary(grouping: curriculum.modules, by: { $0.categoryKey })
                } else {
                    moduleLookup = appVM.modulesByCategory
                }
                ForEach(categoryOutcomes) { outcome in
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(appVM.label(for: outcome.categoryKey))
                                .font(.subheadline.weight(.semibold))
                            Spacer()
                            Text("Rating \(outcome.initialRating)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            let delta = outcome.ratingDelta
                            if delta != 0 {
                                Text(delta > 0 ? "+\(delta)" : "\(delta)")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(delta > 0 ? .green : .orange)
                            }
                        }
                        if let rationale = outcome.rationale, !rationale.isEmpty {
                            Text(rationale)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        if let category = plan?.categories.first(where: { $0.key == outcome.categoryKey }), !category.focusAreas.isEmpty {
                            Text("Focus areas: \(category.focusAreas.joined(separator: ", "))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        if let moduleList = moduleLookup[outcome.categoryKey], !moduleList.isEmpty {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Suggested modules")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.secondary)
                                ForEach(moduleList.prefix(3)) { module in
                                    Text("• \(module.title)")
                                        .font(.caption)
                                }
                            }
                        }
                    }
                    .padding(12)
                    .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
                }
            }
            .padding(20)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
        }
    }

    @ViewBuilder
    private var taskDrilldownsSection: some View {
        if let grading, !grading.taskResults.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                Label("Task Drilldowns", systemImage: "doc.text.magnifyingglass")
                    .font(.headline)
                ForEach(grading.taskResults) { task in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(alignment: .firstTextBaseline) {
                            Text(task.taskId)
                                .font(.subheadline.weight(.semibold))
                            Spacer()
                            Text("Score \(Int((task.score * 100).rounded()))%")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(task.confidence.rawValue.capitalized)
                                .font(.caption)
                                .foregroundStyle(.tertiary)
                        }
                        Text(task.feedback)
                            .font(.callout)
                        if !task.strengths.isEmpty {
                            Text("Strengths: \(task.strengths.joined(separator: ", "))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        if !task.improvements.isEmpty {
                            Text("Improve: \(task.improvements.joined(separator: ", "))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        if !task.rubric.isEmpty {
                            DisclosureGroup("Rubric feedback") {
                                VStack(alignment: .leading, spacing: 4) {
                                    ForEach(task.rubric, id: \.criterion) { rubric in
                                        HStack(alignment: .top, spacing: 6) {
                                            Image(systemName: rubric.met ? "checkmark.circle.fill" : "xmark.circle")
                                                .foregroundStyle(rubric.met ? .green : .orange)
                                                .imageScale(.small)
                                            VStack(alignment: .leading, spacing: 2) {
                                                Text(rubric.criterion)
                                                    .font(.caption.weight(.semibold))
                                                if let notes = rubric.notes, !notes.isEmpty {
                                                    Text(notes)
                                                        .font(.caption)
                                                        .foregroundStyle(.secondary)
                                                }
                                            }
                                        }
                                    }
                                }
                                .padding(.top, 4)
                            }
                            .font(.caption)
                        }
                    }
                    .padding(12)
                    .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
                }
            }
            .padding(20)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
        }
    }

    private func responsePreview(for response: AssessmentTaskSubmission) -> String {
        let preview = response.preview
        if preview.isEmpty {
            return "(No response)"
        }
        return preview
    }

    private func icon(for kind: AssessmentSubmissionRecord.Attachment.Kind) -> String {
        switch kind {
        case .file:
            return "doc"
        case .link:
            return "link"
        case .note:
            return "note.text"
        }
    }
}
