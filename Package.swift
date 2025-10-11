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
                "App_debugging_instructions.pdf",
                "ArcadiaCoachApp.swift",
                "backend",
                "docs",
                "Info.plist",
                "Models/AppSettings.swift",
                "Models/AgentModels.swift",
                "Models/WidgetModels.swift",
                "Models/GameState.swift",
                "mcp_server",
                "node_modules",
                "openai-agents-python",
                "openai-chatkit-advanced-samples",
                "package.json",
                "package-lock.json",
                "render.yaml",
                "Resources",
                "Services",
                "Tests",
                "ViewModels",
                "Views",
            ],
            sources: [
                "Models/EloEngine.swift",
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
