import Config
import PII
import XCTest

final class BlocklistManagerTests: XCTestCase {
    func testHardcodedBlocklist() async {
        let manager = BlocklistManager()
        let blocked = await manager.shouldCapture(bundleId: "com.1password.1password")
        XCTAssertFalse(blocked)
        let blocked2 = await manager.shouldCapture(bundleId: "com.bitwarden.desktop")
        XCTAssertFalse(blocked2)
        let allowed = await manager.shouldCapture(bundleId: "com.microsoft.Excel")
        XCTAssertTrue(allowed)
    }

    func testCustomBlocklist() async {
        let config = AgentConfig(appBlocklist: ["com.custom.blocked"])
        let manager = BlocklistManager(config: config)
        let blocked = await manager.shouldCapture(bundleId: "com.custom.blocked")
        XCTAssertFalse(blocked)
        let allowed = await manager.shouldCapture(bundleId: "com.other.app")
        XCTAssertTrue(allowed)
    }

    func testAllowlistOverridesBlocklist() async {
        let config = AgentConfig(
            appAllowlist: ["com.allowed.app"],
            appBlocklist: ["com.blocked.app"]
        )
        let manager = BlocklistManager(config: config)
        let allowed = await manager.shouldCapture(bundleId: "com.allowed.app")
        XCTAssertTrue(allowed)
        let blocked = await manager.shouldCapture(bundleId: "com.other.app")
        XCTAssertFalse(blocked)
    }

    func testNilBundleIdBlocked() async {
        // nil bundle IDs are blocked by default (least privilege) to prevent
        // unidentified processes from being captured.
        let manager = BlocklistManager()
        let result = await manager.shouldCapture(bundleId: nil)
        XCTAssertFalse(result)
    }

    func testUpdateConfig() async {
        let manager = BlocklistManager()
        let before = await manager.shouldCapture(bundleId: "com.new.blocked")
        XCTAssertTrue(before)

        let newConfig = AgentConfig(appBlocklist: ["com.new.blocked"])
        await manager.update(config: newConfig)
        let after = await manager.shouldCapture(bundleId: "com.new.blocked")
        XCTAssertFalse(after)
    }
}
