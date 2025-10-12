// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ArcadiaCoach",
    platforms: [
        .macOS(.v13),
    ],
    products: [
        .library(
            name: "ArcadiaCoach",
            targets: ["ArcadiaCoach"]
        ),
    ],
    targets: [
        .target(
            name: "ArcadiaCoach",
            path: ".",
            exclude: [
                "Assets.xcassets",
                "AGENTS.md",
                "ArcadiaCoach.entitlements",
                "ArcadiaCoach.xcodeproj",
                "backend",
                "docs",
                "Info.plist",
                "ArcadiaCoachApp.swift",
                "Models/AppSettings.swift",
                "Models/GameState.swift",
                "mcp_server",
                "node_modules",
                "openai-agents-python",
                "openai-chatkit-advanced-samples",
                "package.json",
                "package-lock.json",
                "render.yaml",
                "Resources",
                "Services/MCPTypes.swift",
                "Services/WidgetResource.swift",
                "Tests",
                "ViewModels/AppViewModel.swift",
                "ViewModels/SessionViewModel.swift",
                "Views",
            ],
            sources: [
                "Models/EloEngine.swift",
                "Models/EloPlan.swift",
                "Models/WidgetModels.swift",
                "Models/AgentModels.swift",
                "Services/BackendService.swift",
                "ViewModels/AgentChatViewModel.swift",
            ],
            swiftSettings: [
                .define("SWIFT_PACKAGE"),
            ]
        ),
        .testTarget(
            name: "ArcadiaCoachTests",
            dependencies: ["ArcadiaCoach"],
            path: "Tests",
            exclude: [
                "TestsInfo.plist",
            ]
        ),
    ]
)
