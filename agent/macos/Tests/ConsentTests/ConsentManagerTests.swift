import Consent
import XCTest

@MainActor
final class ConsentManagerTests: XCTestCase {
    func testInitialStateNeverConsented() {
        let store = InMemoryConsentStore()
        let manager = ConsentManager(engagementId: "eng-1", store: store)
        XCTAssertEqual(manager.state, .neverConsented)
        XCTAssertFalse(manager.captureAllowed)
    }

    func testGrantConsent() {
        let store = InMemoryConsentStore()
        let manager = ConsentManager(engagementId: "eng-1", store: store)
        manager.grantConsent()
        XCTAssertEqual(manager.state, .consented)
        XCTAssertTrue(manager.captureAllowed)
    }

    func testRevokeConsent() {
        let store = InMemoryConsentStore()
        let manager = ConsentManager(engagementId: "eng-1", store: store)
        manager.grantConsent()
        manager.revokeConsent()
        XCTAssertEqual(manager.state, .revoked)
        XCTAssertFalse(manager.captureAllowed)
    }

    func testConsentPersistsAcrossInstances() {
        let store = InMemoryConsentStore()

        let manager1 = ConsentManager(engagementId: "eng-1", store: store)
        manager1.grantConsent()

        let manager2 = ConsentManager(engagementId: "eng-1", store: store)
        XCTAssertEqual(manager2.state, .consented)
    }

    func testDifferentEngagementsAreIsolated() {
        let store = InMemoryConsentStore()

        let manager1 = ConsentManager(engagementId: "eng-1", store: store)
        manager1.grantConsent()

        let manager2 = ConsentManager(engagementId: "eng-2", store: store)
        XCTAssertEqual(manager2.state, .neverConsented)
    }
}
