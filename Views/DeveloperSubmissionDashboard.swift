import SwiftUI

struct DeveloperSubmissionDashboard: View {
    enum Scope: String, CaseIterable, Identifiable {
        case current = "Current Learner"
        case all = "All Learners"

        var id: String { rawValue }
    }

    @ObservedObject var viewModel: DeveloperToolsViewModel
    let baseURL: String
    let currentUsername: String

    @State private var scope: Scope = .current

    private var sanitizedUsername: String? {
        let trimmed = currentUsername.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed.lowercased()
    }

    private var groupedSubmissions: [(key: String, value: [AssessmentSubmissionRecord])] {
        let grouped = Dictionary(grouping: viewModel.submissions) { $0.username }
        return grouped
            .map { (key: $0.key, value: $0.value.sorted { $0.submittedAt > $1.submittedAt }) }
            .sorted { $0.key < $1.key }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            header

            if let error = viewModel.lastError {
                Text(error)
                    .font(.footnote)
                    .foregroundStyle(.red)
            }

            if viewModel.isLoadingSubmissions {
                ProgressView("Loading assessment submissions…")
                    .frame(maxWidth: .infinity, alignment: .center)
            } else if viewModel.submissions.isEmpty {
                Text("No assessment submissions stored for the selected scope.")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        ForEach(groupedSubmissions, id: \.key) { entry in
                            VStack(alignment: .leading, spacing: 10) {
                                Text(entry.key)
                                    .font(.headline)
                                ForEach(entry.value) { submission in
                                    submissionRow(submission)
                                }
                            }
                            .padding(14)
                            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 14))
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
        .frame(minWidth: 520, minHeight: 420)
        .padding(24)
        .task(id: scope) {
            await loadSubmissions()
        }
    }

    @ViewBuilder
    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 6) {
                Text("Assessment Submissions")
                    .font(.title2.bold())
                Text("Inspect manual onboarding assessment submissions for debugging.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Picker("Scope", selection: $scope) {
                ForEach(Scope.allCases) { scope in
                    Text(scope.rawValue).tag(scope)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 220)
        }
    }

    @ViewBuilder
    private func submissionRow(_ submission: AssessmentSubmissionRecord) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(submission.submittedAt.formatted(date: .numeric, time: .shortened))
                    .font(.subheadline.weight(.medium))
                Spacer()
                Text("\(submission.answeredCount) responses")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if !submission.metadata.isEmpty {
                Text(submission.metadata.map { "\($0.key): \($0.value)" }.joined(separator: " • "))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            ForEach(submission.responses) { item in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(item.taskId)
                            .font(.footnote.bold())
                        Spacer()
                        Text(item.taskType.label)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Text(item.preview)
                        .font(.footnote)
                    Text("Word count: \(item.wordCount)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .padding(10)
                .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 10))
            }
            if let grading = submission.grading {
                Divider()
                VStack(alignment: .leading, spacing: 6) {
                    Text("Automated grading")
                        .font(.subheadline.bold())
                    Text(grading.overallFeedback)
                        .font(.footnote)
                    if !grading.categoryOutcomes.isEmpty {
                        HStack(spacing: 8) {
                            ForEach(grading.categoryOutcomes) { outcome in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(outcome.categoryKey)
                                        .font(.caption.bold())
                                    Text("Rating \(outcome.initialRating)")
                                        .font(.caption2)
                                    Text("Avg score \(Int(outcome.averageScore * 100))%")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                                .padding(8)
                                .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
                            }
                        }
                    }
                }
            }
        }
    }

    private func loadSubmissions() async {
        let trimmedBase = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedBase.isEmpty else {
            viewModel.submissions = []
            viewModel.lastError = "Add the ChatKit backend URL to fetch submissions."
            return
        }
        switch scope {
        case .current:
            guard let username = sanitizedUsername else {
                viewModel.submissions = []
                viewModel.lastError = "Set a learner username to view scoped submissions."
                return
            }
            await viewModel.refreshSubmissions(baseURL: trimmedBase, username: username)
        case .all:
            await viewModel.refreshSubmissions(baseURL: trimmedBase, username: nil)
        }
    }
}
