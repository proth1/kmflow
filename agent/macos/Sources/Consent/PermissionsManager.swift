/// Checks and requests macOS permissions required for capture.
///
/// Required: Accessibility (CGEventTap, AXUIElement)
/// Optional: Screen Recording (Phase 2 screenshots)

import ApplicationServices
import Foundation

/// Protocol for permission checks (testable).
public protocol PermissionsProvider: Sendable {
    func isAccessibilityGranted() -> Bool
    func requestAccessibility()
    func isScreenRecordingGranted() -> Bool
}

/// Concrete implementation using macOS APIs.
public struct SystemPermissionsProvider: PermissionsProvider {
    public init() {}

    public func isAccessibilityGranted() -> Bool {
        return AXIsProcessTrustedWithOptions(
            [kAXTrustedCheckOptionPrompt.takeUnretainedValue(): false] as CFDictionary
        )
    }

    public func requestAccessibility() {
        _ = AXIsProcessTrustedWithOptions(
            [kAXTrustedCheckOptionPrompt.takeUnretainedValue(): true] as CFDictionary
        )
    }

    public func isScreenRecordingGranted() -> Bool {
        // CGWindowListCopyWindowInfo returns empty for non-owned windows
        // if Screen Recording permission is not granted.
        let windowList = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]]
        return (windowList?.count ?? 0) > 1
    }
}

// MockPermissionsProvider moved to Tests/ConsentTests/ — test doubles
// should not ship in production binaries.
