// swift-tools-version: 5.9
// KMFlow Desktop Agent — macOS

import PackageDescription

let package = Package(
    name: "KMFlowAgent",
    platforms: [
        .macOS(.v13),
    ],
    products: [
        .executable(name: "KMFlowAgent", targets: ["KMFlowAgent"]),
        .library(name: "Capture", targets: ["Capture"]),
        .library(name: "IPC", targets: ["IPC"]),
    ],
    dependencies: [],
    targets: [
        // Main app executable
        .executableTarget(
            name: "KMFlowAgent",
            dependencies: ["Capture", "Consent", "UI", "IPC", "PII", "Config", "Utilities"],
            path: "Sources/KMFlowAgent"
        ),

        // Capture layer: app switch, input monitoring, window titles, idle detection
        .target(
            name: "Capture",
            dependencies: ["IPC", "PII", "Config"],
            path: "Sources/Capture"
        ),

        // Consent and permissions management
        .target(
            name: "Consent",
            dependencies: [],
            path: "Sources/Consent"
        ),

        // SwiftUI views: menu bar, preferences, transparency log
        .target(
            name: "UI",
            dependencies: ["Capture", "Consent"],
            path: "Sources/UI",
            linkerSettings: [
                // TransparencyLogController reads the SQLite capture buffer.
                .linkedLibrary("sqlite3"),
            ]
        ),

        // IPC: Unix domain socket protocol, event serialization
        .target(
            name: "IPC",
            dependencies: [],
            path: "Sources/IPC"
        ),

        // PII: L1 capture prevention, private browsing detection
        .target(
            name: "PII",
            dependencies: [],
            path: "Sources/PII"
        ),

        // Config: agent configuration, blocklist management
        .target(
            name: "Config",
            dependencies: ["PII"],
            path: "Sources/Config"
        ),

        // Utilities: Keychain, logging
        .target(
            name: "Utilities",
            dependencies: [],
            path: "Sources/Utilities"
        ),

        // Test targets
        .testTarget(
            name: "CaptureTests",
            dependencies: ["Capture"],
            path: "Tests/CaptureTests"
        ),
        .testTarget(
            name: "ConsentTests",
            dependencies: ["Consent"],
            path: "Tests/ConsentTests"
        ),
        .testTarget(
            name: "IPCTests",
            dependencies: ["IPC"],
            path: "Tests/IPCTests"
        ),
        .testTarget(
            name: "PIITests",
            dependencies: ["PII", "Capture"],
            path: "Tests/PIITests"
        ),
        .testTarget(
            name: "ConfigTests",
            dependencies: ["Config", "PII"],
            path: "Tests/ConfigTests"
        ),
        .testTarget(
            name: "IntegrityTests",
            dependencies: ["KMFlowAgent"],
            path: "Tests/IntegrityTests"
        ),
    ]
)
