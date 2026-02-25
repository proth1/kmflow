import Capture
import XCTest

@MainActor
final class CaptureStateManagerTests: XCTestCase {
    func testInitialStateIsIdle() {
        let manager = CaptureStateManager()
        XCTAssertEqual(manager.state, .idle)
        XCTAssertEqual(manager.eventCount, 0)
    }

    func testStartCaptureFromIdle() {
        let manager = CaptureStateManager()
        manager.startCapture()
        XCTAssertEqual(manager.state, .capturing)
    }

    func testPauseCapture() {
        let manager = CaptureStateManager()
        manager.startCapture()
        manager.pauseCapture()
        XCTAssertEqual(manager.state, .paused)
    }

    func testResumeCapture() {
        let manager = CaptureStateManager()
        manager.startCapture()
        manager.pauseCapture()
        manager.resumeCapture()
        XCTAssertEqual(manager.state, .capturing)
    }

    func testStopCapture() {
        let manager = CaptureStateManager()
        manager.startCapture()
        manager.stopCapture()
        XCTAssertEqual(manager.state, .idle)
    }

    func testCannotPauseFromIdle() {
        let manager = CaptureStateManager()
        manager.pauseCapture()
        XCTAssertEqual(manager.state, .idle)
    }

    func testCannotResumeFromCapturing() {
        let manager = CaptureStateManager()
        manager.startCapture()
        manager.resumeCapture()
        XCTAssertEqual(manager.state, .capturing)
    }

    func testRequireConsent() {
        let manager = CaptureStateManager()
        manager.requireConsent()
        XCTAssertEqual(manager.state, .consentRequired)
    }

    func testExpireEngagement() {
        let manager = CaptureStateManager()
        manager.startCapture()
        manager.expireEngagement()
        XCTAssertEqual(manager.state, .engagementExpired)
    }

    func testSetError() {
        let manager = CaptureStateManager()
        manager.setError("Test error")
        XCTAssertEqual(manager.state, .error)
        XCTAssertEqual(manager.errorMessage, "Test error")
    }

    func testRecordEvent() {
        let manager = CaptureStateManager()
        manager.recordEvent()
        XCTAssertEqual(manager.eventCount, 1)
        XCTAssertNotNil(manager.lastEventAt)
    }

    func testSequenceNumbers() {
        let manager = CaptureStateManager()
        XCTAssertEqual(manager.nextSequenceNumber(), 1)
        XCTAssertEqual(manager.nextSequenceNumber(), 2)
        XCTAssertEqual(manager.nextSequenceNumber(), 3)
    }

    func testStartFromPaused() {
        let manager = CaptureStateManager()
        manager.startCapture()
        manager.pauseCapture()
        manager.startCapture()
        XCTAssertEqual(manager.state, .capturing)
    }
}
