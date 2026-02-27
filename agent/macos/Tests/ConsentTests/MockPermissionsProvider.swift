/// Mock permissions provider for testing.
///
/// Moved from Sources/Consent/PermissionsManager.swift — test doubles
/// should not ship in production binaries.

import Consent

actor MockPermissionsProvider: PermissionsProvider {
    var accessibilityGranted: Bool
    var screenRecordingGranted: Bool
    var requestCount: Int = 0

    init(accessibilityGranted: Bool = true, screenRecordingGranted: Bool = false) {
        self.accessibilityGranted = accessibilityGranted
        self.screenRecordingGranted = screenRecordingGranted
    }

    nonisolated func isAccessibilityGranted() -> Bool { true }
    func requestAccessibility() { requestCount += 1 }
    nonisolated func isScreenRecordingGranted() -> Bool { false }
}
