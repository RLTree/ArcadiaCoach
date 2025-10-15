import SwiftUI

struct DashboardAssessmentsSection: View {
    @EnvironmentObject private var appVM: AppViewModel
    @EnvironmentObject private var settings: AppSettings

    let awaitingAssessmentResults: Bool
    let requiresAssessment: Bool
    let categoryLabels: [String:String]
    let onRunOnboarding: () -> Void
    let onOpenAssessmentFlow: () -> Void

    var body: some View {
        if awaitingAssessmentResults {
            VStack(spacing: 12) {
                ProgressView()
                    .controlSize(.large)
                Text("Waiting for assessment results…")
                    .font(.headline)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: 240)
        } else {
            VStack(alignment: .leading, spacing: 18) {
                assessmentSummaryCard
                if requiresAssessment, let bundle = appVM.onboardingAssessment {
                    assessmentBanner(status: bundle.status)
                }
                if let result = appVM.assessmentResult ?? appVM.latestGradedAssessment?.grading {
                    assessmentResultsCard(result: result)
                }
                assessmentHistorySection
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var assessmentSummaryCard: some View {
        let pendingSubmission = appVM.assessmentHistory.first { $0.grading == nil }
        let readiness = appVM.assessmentReadinessStatus
        let statusText = readiness.displayText
        let statusIcon = readiness.systemImageName
        let statusColor = readiness.tintColor

        let submissionLabel = appVM.latestAssessmentSubmittedAt?
            .formatted(date: .abbreviated, time: .shortened) ?? "No submissions yet"

        let gradingLabel: String = {
            if let pendingSubmission {
                return "Pending since \(pendingSubmission.submittedAt.formatted(date: .abbreviated, time: .shortened))"
            }
            if let gradedAt = appVM.latestAssessmentGradeTimestamp {
                if let average = appVM.latestGradedAssessment?.averageScoreLabel {
                    return "\(average) average • \(gradedAt.formatted(date: .abbreviated, time: .shortened))"
                }
                return gradedAt.formatted(date: .abbreviated, time: .shortened)
            }
            return "No grading yet"
        }()

        let latestFeedback = appVM.latestGradedAssessment?.grading?.overallFeedback
            .trimmingCharacters(in: .whitespacesAndNewlines)

        return VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center) {
                Label("Assessment Status", systemImage: "checkmark.seal")
                    .labelStyle(.titleAndIcon)
                    .font(.title3.weight(.semibold))
                Spacer()
                Label(statusText, systemImage: statusIcon)
                    .font(.footnote.weight(.semibold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(statusColor.opacity(0.18), in: Capsule())
            }

            VStack(alignment: .leading, spacing: 6) {
                Label("Last submission", systemImage: "calendar.badge.clock")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(submissionLabel)
                    .font(.callout)
                Label("Grading status", systemImage: "checkmark.bubble")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(gradingLabel)
                    .font(.callout)
            }

            if let latestFeedback, !latestFeedback.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Latest feedback")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Text(latestFeedback)
                        .font(.body)
                }
            }

            HStack {
                Button {
                    onOpenAssessmentFlow()
                } label: {
                    Label("Open assessment", systemImage: "checkmark.circle")
                }
                .buttonStyle(.borderedProminent)

                Button {
                    onRunOnboarding()
                } label: {
                    Label("Run onboarding", systemImage: "arrow.triangle.2.circlepath")
                }
                .buttonStyle(.bordered)
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
    }

    @ViewBuilder
    private func assessmentBanner(status: OnboardingAssessment.Status) -> some View {
        HStack(alignment: .center, spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Onboarding assessment pending")
                    .font(.headline)
                Text(status == .inProgress ? "Pick up where you left off to finish calibration." : "Complete the initial assessment so Arcadia can calibrate your curriculum.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button("Resume") {
                appVM.openAssessmentFlow()
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(16)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16))
    }

    @ViewBuilder
    private var assessmentHistorySection: some View {
        let history = Array(appVM.assessmentHistory.prefix(6))
        if history.isEmpty {
            VStack(spacing: 12) {
                Label("No assessment submissions yet", systemImage: "tray")
                    .font(.headline)
                Text("Submit your onboarding assessment to see graded history and ELO deltas.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity)
            .padding(20)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
        } else {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Label("Assessment History", systemImage: "clock.arrow.circlepath")
                        .labelStyle(.titleAndIcon)
                        .font(.headline)
                    Spacer()
                    Text("Newest first")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(history.enumerated()), id: \.element.id) { index, submission in
                        assessmentHistoryRow(for: submission, index: index + 1)
                        if index < history.count - 1 {
                            Divider().padding(.vertical, 10)
                        }
                    }
                }

                if appVM.assessmentHistory.count > history.count {
                    Text("Showing latest \(history.count) of \(appVM.assessmentHistory.count) submissions.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
        }
    }

    private func assessmentHistoryRow(for submission: AssessmentSubmissionRecord, index: Int) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text("#\(index) · \(submission.submittedAt.formatted(date: .abbreviated, time: .shortened))")
                    .font(.subheadline.weight(.semibold))
                Spacer()
                let isPending = submission.grading == nil
                let badgeForeground: Color = isPending ? .orange : .green
                Text(submission.statusLabel)
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(badgeForeground.opacity(0.18), in: Capsule())
                    .foregroundStyle(badgeForeground)
            }

            HStack(spacing: 12) {
                Label("\(submission.answeredCount) prompts", systemImage: "list.bullet.rectangle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let average = submission.averageScoreLabel, submission.grading != nil {
                    Label("\(average) average", systemImage: "percent")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let gradedAt = submission.gradedAt {
                    Label("Graded \(gradedAt.formatted(date: .abbreviated, time: .shortened))", systemImage: "clock")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if submission.hasAttachments {
                    Label("\(submission.attachments.count) attachment\(submission.attachments.count == 1 ? "" : "s")", systemImage: "paperclip")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let outcomes = submission.grading?.categoryOutcomes {
                    let totalDelta = outcomes.reduce(0) { $0 + $1.ratingDelta }
                    if totalDelta != 0 {
                        let label = totalDelta > 0 ? "+\(totalDelta)" : "\(totalDelta)"
                        Label("ΔELO \(label)", systemImage: totalDelta > 0 ? "arrow.up" : "arrow.down")
                            .font(.caption)
                            .foregroundStyle(totalDelta > 0 ? .green : .orange)
                    }
                }
            }

            if let grading = submission.grading {
                if !grading.overallFeedback.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text(grading.overallFeedback)
                        .font(.footnote)
                        .foregroundStyle(.primary)
                        .lineLimit(3)
                }
                let strengths = grading.strengths.prefix(2).joined(separator: ", ")
                if !strengths.isEmpty {
                    Text("Strengths: \(strengths)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                let focus = grading.focusAreas.prefix(2).joined(separator: ", ")
                if !focus.isEmpty {
                    Text("Focus next: \(focus)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text("Arcadia Coach is grading this submission.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack {
                Spacer()
                Button {
                    appVM.focus(on: submission)
                } label: {
                    Label("View details", systemImage: "arrow.right.circle")
                        .font(.caption.weight(.semibold))
                }
                .buttonStyle(.bordered)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func assessmentResultsCard(result: AssessmentGradingResult) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top) {
                Label("Assessment Results", systemImage: "chart.bar.doc.horizontal")
                    .labelStyle(.titleAndIcon)
                    .font(.title3.weight(.semibold))
                Spacer()
                Text(result.evaluatedAt.formatted(date: .abbreviated, time: .shortened))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Text(result.overallFeedback)
                .font(.body)

            if !result.strengths.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Strengths")
                        .font(.subheadline.bold())
                    ForEach(result.strengths, id: \.self) { item in
                        Text("• \(item)")
                            .font(.footnote)
                    }
                }
            }

            if !result.focusAreas.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Focus Next")
                        .font(.subheadline.bold())
                    ForEach(result.focusAreas, id: \.self) { item in
                        Text("• \(item)")
                            .font(.footnote)
                    }
                }
            }

            if !result.categoryOutcomes.isEmpty {
                let columns = [GridItem(.adaptive(minimum: 160), spacing: 12, alignment: .top)]
                LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
                    ForEach(result.categoryOutcomes) { outcome in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(categoryLabels[outcome.categoryKey] ?? outcome.categoryKey)
                                .font(.headline)
                            Text("Rating \(outcome.initialRating)")
                                .font(.subheadline)
                            Text("Avg score \(Int((outcome.averageScore * 100).rounded()))%")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            if outcome.ratingDelta != 0 {
                                let label = outcome.ratingDelta > 0 ? "+\(outcome.ratingDelta)" : "\(outcome.ratingDelta)"
                                Text("ΔELO \(label)")
                                    .font(.caption.bold())
                                    .foregroundStyle(outcome.ratingDelta > 0 ? .green : .orange)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                        .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 12))
                    }
                }
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
    }
}
