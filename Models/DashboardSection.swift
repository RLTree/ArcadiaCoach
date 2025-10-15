import SwiftUI

enum DashboardSection: String, CaseIterable, Identifiable {
    case elo
    case schedule
    case assessments
    case resources

    var id: String { rawValue }

    var label: String {
        switch self {
        case .elo:
            return "ELO"
        case .schedule:
            return "Schedule"
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
        case .assessments:
            return "checklist"
        case .resources:
            return "tray.full"
        }
    }
}
