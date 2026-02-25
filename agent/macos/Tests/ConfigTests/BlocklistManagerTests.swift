import Config
import PII
import XCTest

final class BlocklistManagerTests: XCTestCase {
    func testHardcodedBlocklist() {
        let manager = BlocklistManager()
        XCTAssertFalse(manager.shouldCapture(bundleId: "com.1password.1password"))
        XCTAssertFalse(manager.shouldCapture(bundleId: "com.bitwarden.desktop"))
        XCTAssertTrue(manager.shouldCapture(bundleId: "com.microsoft.Excel"))
    }

    func testCustomBlocklist() {
        let config = AgentConfig(appBlocklist: ["com.custom.blocked"])
        let manager = BlocklistManager(config: config)
        XCTAssertFalse(manager.shouldCapture(bundleId: "com.custom.blocked"))
        XCTAssertTrue(manager.shouldCapture(bundleId: "com.other.app"))
    }

    func testAllowlistOverridesBlocklist() {
        let config = AgentConfig(
            appAllowlist: ["com.allowed.app"],
            appBlocklist: ["com.blocked.app"]
        )
        let manager = BlocklistManager(config: config)
        XCTAssertTrue(manager.shouldCapture(bundleId: "com.allowed.app"))
        XCTAssertFalse(manager.shouldCapture(bundleId: "com.other.app"))
    }

    func testNilBundleIdAllowed() {
        let manager = BlocklistManager()
        XCTAssertTrue(manager.shouldCapture(bundleId: nil))
    }

    func testUpdateConfig() {
        let manager = BlocklistManager()
        XCTAssertTrue(manager.shouldCapture(bundleId: "com.new.blocked"))

        let newConfig = AgentConfig(appBlocklist: ["com.new.blocked"])
        manager.update(config: newConfig)
        XCTAssertFalse(manager.shouldCapture(bundleId: "com.new.blocked"))
    }
}
