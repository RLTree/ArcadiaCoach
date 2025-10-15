# Phase 23 – Dashboard Navigation & Tabbed Layout

**Completed:** October 15, 2025  
**Owner:** Arcadia Coach macOS client  

## Highlights
- Replaced the single-column Home dashboard with a segmented control that routes between **ELO**, **Schedule**, **Assessments**, and **Resources** sections. Selection persists via `AppSettings.dashboardSection` so learners resume where they left off.
- Extracted dashboard subviews into dedicated SwiftUI files under `Views/Dashboard/`, keeping the layout maintainable and allowing each tab to own its scrollable content.
- Added telemetry: `dashboard_tab_selected` fires on every selection (with an `initial=true` flag on first load) and `session_action_triggered` records the resources tab buttons, including the originating section metadata.
- Hardened session controls by disabling lesson/quiz/milestone launches until onboarding and assessments finish, while surfacing the existing explanatory copy.
- Updated `ArcadiaCoach.xcodeproj` to include the new sources so the Xcode target remains the source of truth for the macOS build.

## Verification
- `swift test`
- `xcodebuild -scheme ArcadiaCoach -configuration Debug build`

## Follow-ups
1. Extend dashboard tab selection analytics with learner identifiers once privacy review completes, enabling per-user retention analysis.
2. Consider lightweight onboarding/prompts to guide first-time learners toward the Assessments tab after calibration completes (UX follow-up).
