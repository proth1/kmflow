/// Layer 1 capture context filter: prevents capture in sensitive contexts.
///
/// CaptureContextFilter runs BEFORE events are generated. It prevents capture of:
/// - Password fields (AXSecureTextField)
/// - Apps on the blocklist
/// - Private browsing windows
///
/// This is a context-blocking filter (not a PII content filter).
/// It determines WHETHER to capture, not WHAT to redact.
/// PII content redaction is handled by L2PIIFilter.

import Foundation

// MARK: - Protocols for testability

/// Abstraction over AXUIElement for testing without Accessibility permissions.
public protocol AccessibilityProvider: Sendable {
    func focusedElementRole() -> String?
    func isSecureTextField() -> Bool
}

/// Abstraction over NSRunningApplication for testing.
public protocol RunningAppProvider: Sendable {
    var bundleIdentifier: String? { get }
    var localizedName: String? { get }
}

// MARK: - Capture Context Filter

public struct CaptureContextFilter: Sendable {
    /// Returns true if the current focused element is a password field.
    public static func isPasswordField(provider: AccessibilityProvider) -> Bool {
        return provider.isSecureTextField()
    }

    /// Returns true if the app should be blocked from capture.
    ///
    /// Apps with a nil bundle identifier are blocked by default (least
    /// privilege) — unidentified processes should never be captured.
    public static func isBlockedApp(bundleId: String?, blocklist: Set<String>) -> Bool {
        guard let bid = bundleId else { return true }
        return blocklist.contains(bid)
    }

    /// Known password manager bundle IDs (always blocked regardless of config).
    public static let hardcodedBlocklist: Set<String> = [
        "com.1password.1password",
        "com.agilebits.onepassword7",
        "org.chromium.chromium",  // Chromium raw (not Chrome)
        "com.lastpass.LastPass",
        "com.bitwarden.desktop",
        "com.dashlane.Dashlane",
        "com.apple.keychainaccess",
    ]
}

// MARK: - Private Browsing Detection

public struct PrivateBrowsingDetector: Sendable {
    /// Checks if the window title suggests private/incognito browsing.
    public static func isPrivateBrowsing(
        bundleId: String?,
        windowTitle: String?
    ) -> Bool {
        guard let title = windowTitle else { return false }

        // Safari private browsing
        if bundleId == "com.apple.Safari" {
            // Safari private windows contain "Private Browsing" in the title
            if title.contains("Private Browsing") { return true }
        }

        // Chrome incognito
        if bundleId == "com.google.Chrome" {
            if title.hasSuffix("- Incognito") { return true }
        }

        // Firefox private
        if bundleId == "org.mozilla.firefox" {
            if title.contains("Private Browsing") { return true }
        }

        // Arc incognito
        if bundleId == "company.thebrowser.Browser" {
            if title.contains("Incognito") { return true }
        }

        // Edge InPrivate
        if bundleId == "com.microsoft.edgemac" {
            if title.contains("InPrivate") { return true }
        }

        // Brave private
        if bundleId == "com.brave.Browser" {
            if title.contains("Private") { return true }
        }

        // Vivaldi private
        if bundleId == "com.vivaldi.Vivaldi" {
            if title.contains("Private Browsing") { return true }
        }

        // Opera private
        if bundleId == "com.operasoftware.Opera" {
            if title.contains("Private") { return true }
        }

        return false
    }
}
