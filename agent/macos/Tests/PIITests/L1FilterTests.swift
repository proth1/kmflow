import Capture
import PII
import XCTest

final class L1FilterTests: XCTestCase {
    func testBlockedAppDetection() {
        XCTAssertTrue(L1Filter.isBlockedApp(
            bundleId: "com.1password.1password",
            blocklist: L1Filter.hardcodedBlocklist
        ))
        XCTAssertTrue(L1Filter.isBlockedApp(
            bundleId: "com.bitwarden.desktop",
            blocklist: L1Filter.hardcodedBlocklist
        ))
    }

    func testAllowedApp() {
        XCTAssertFalse(L1Filter.isBlockedApp(
            bundleId: "com.microsoft.Excel",
            blocklist: L1Filter.hardcodedBlocklist
        ))
    }

    func testNilBundleIdNotBlocked() {
        XCTAssertFalse(L1Filter.isBlockedApp(
            bundleId: nil,
            blocklist: L1Filter.hardcodedBlocklist
        ))
    }

    func testCustomBlocklist() {
        var custom = L1Filter.hardcodedBlocklist
        custom.insert("com.custom.app")
        XCTAssertTrue(L1Filter.isBlockedApp(bundleId: "com.custom.app", blocklist: custom))
    }

    // MARK: - Private Browsing Detection

    func testSafariPrivateBrowsing() {
        XCTAssertTrue(PrivateBrowsingDetector.isPrivateBrowsing(
            bundleId: "com.apple.Safari",
            windowTitle: "Wikipedia — Private Browsing"
        ))
    }

    func testSafariNormalBrowsing() {
        XCTAssertFalse(PrivateBrowsingDetector.isPrivateBrowsing(
            bundleId: "com.apple.Safari",
            windowTitle: "Wikipedia — Safari"
        ))
    }

    func testChromeIncognito() {
        XCTAssertTrue(PrivateBrowsingDetector.isPrivateBrowsing(
            bundleId: "com.google.Chrome",
            windowTitle: "New Tab - Incognito"
        ))
    }

    func testChromeNormal() {
        XCTAssertFalse(PrivateBrowsingDetector.isPrivateBrowsing(
            bundleId: "com.google.Chrome",
            windowTitle: "New Tab - Google Chrome"
        ))
    }

    func testFirefoxPrivate() {
        XCTAssertTrue(PrivateBrowsingDetector.isPrivateBrowsing(
            bundleId: "org.mozilla.firefox",
            windowTitle: "Mozilla Firefox Private Browsing"
        ))
    }

    func testEdgeInPrivate() {
        XCTAssertTrue(PrivateBrowsingDetector.isPrivateBrowsing(
            bundleId: "com.microsoft.edgemac",
            windowTitle: "New Tab - InPrivate"
        ))
    }

    func testNilWindowTitle() {
        XCTAssertFalse(PrivateBrowsingDetector.isPrivateBrowsing(
            bundleId: "com.apple.Safari",
            windowTitle: nil
        ))
    }

    func testNonBrowserApp() {
        XCTAssertFalse(PrivateBrowsingDetector.isPrivateBrowsing(
            bundleId: "com.microsoft.Excel",
            windowTitle: "Budget 2026.xlsx"
        ))
    }

    // MARK: - L2 PII Filter

    func testL2ScrubsSSN() {
        let result = L2PIIFilter.scrub("SSN: 123-45-6789")
        XCTAssertFalse(result.contains("123-45-6789"))
        XCTAssertTrue(result.contains("[PII_REDACTED]"))
    }

    func testL2ScrubsEmail() {
        let result = L2PIIFilter.scrub("Contact: user@example.com")
        XCTAssertFalse(result.contains("user@example.com"))
        XCTAssertTrue(result.contains("[PII_REDACTED]"))
    }

    func testL2ScrubsPhone() {
        let result = L2PIIFilter.scrub("Call (555) 123-4567")
        XCTAssertFalse(result.contains("(555) 123-4567"))
    }

    func testL2CleanTextUnchanged() {
        let text = "Budget Report Q4 2026"
        XCTAssertEqual(L2PIIFilter.scrub(text), text)
    }

    func testL2ContainsPII() {
        XCTAssertTrue(L2PIIFilter.containsPII("Email: test@example.com"))
        XCTAssertFalse(L2PIIFilter.containsPII("Normal title"))
    }

    // MARK: - Window Title Capture

    func testSanitizeNormalTitle() {
        let result = WindowTitleCapture.sanitize(title: "Budget.xlsx - Excel", bundleId: "com.microsoft.Excel")
        XCTAssertEqual(result, "Budget.xlsx - Excel")
    }

    func testSanitizePrivateBrowsing() {
        let result = WindowTitleCapture.sanitize(
            title: "Google - Private Browsing",
            bundleId: "com.apple.Safari"
        )
        XCTAssertEqual(result, "[PRIVATE_BROWSING]")
    }

    func testSanitizeNilTitle() {
        let result = WindowTitleCapture.sanitize(title: nil, bundleId: "com.apple.Safari")
        XCTAssertNil(result)
    }

    func testSanitizeTruncatesLongTitle() {
        let longTitle = String(repeating: "a", count: 600)
        let result = WindowTitleCapture.sanitize(title: longTitle, bundleId: nil)
        XCTAssertEqual(result?.count, 512)
    }

    func testSanitizeScrubsPII() {
        let result = WindowTitleCapture.sanitize(
            title: "Customer SSN: 123-45-6789 - CRM",
            bundleId: "com.salesforce.desktop"
        )
        XCTAssertNotNil(result)
        XCTAssertFalse(result!.contains("123-45-6789"))
    }
}
