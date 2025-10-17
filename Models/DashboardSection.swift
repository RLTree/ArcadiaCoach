import SwiftUI

enum DashboardSection: String, CaseIterable, Identifiable {
    case elo
    case schedule
    case milestones
    case sessions
    case assessments
    case resources

    var id: String { rawValue }

    var label: String {
        switch self {
        case .elo:
            return "ELO"
        case .schedule:
            return "Schedule"
        case .milestones:
            return "Milestones"
        case .sessions:
            return "Sessions"
        case .assessments:
            return "Assessments"
        case .resources:
            return "Resources"
        }
    }

    var systemImage: String {
        switch self {
        case .elo:
            return "chart.bar.xaxis"
        case .schedule:
            return "calendar"
        case .milestones:
            return "flag.checkered"
        case .sessions:
            return "sparkles"
        case .assessments:
            return "checklist"
        case .resources:
            return "tray.full"
        }
    }
}
