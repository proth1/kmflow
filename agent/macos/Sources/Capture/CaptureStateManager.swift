/// Central state machine for the capture lifecycle.
///
/// States: idle → capturing ↔ paused → idle
///                                    → error
/// The consent flow must complete before transitioning to capturing.

import Foundation

public enum CaptureState: String, Sendable {
    case idle
    case consentRequired
    case capturing
    case paused
    case error
    case engagementExpired
}

@MainActor
public final class CaptureStateManager: ObservableObject {
    @Published public private(set) var state: CaptureState = .idle
    @Published public private(set) var eventCount: UInt64 = 0
    @Published public private(set) var lastEventAt: Date?
    @Published public private(set) var errorMessage: String?

    private var sequenceCounter: UInt64 = 0

    public init() {}

    /// Transition to capturing state. Requires consent to have been given.
    public func startCapture() {
        guard state == .idle || state == .paused else { return }
        state = .capturing
        errorMessage = nil
    }

    /// Pause capture (user-initiated).
    public func pauseCapture() {
        guard state == .capturing else { return }
        state = .paused
    }

    /// Resume capture from paused state.
    public func resumeCapture() {
        guard state == .paused else { return }
        state = .capturing
        errorMessage = nil
    }

    /// Stop capture and return to idle.
    public func stopCapture() {
        state = .idle
    }

    /// Mark consent as required (first launch or revoked).
    public func requireConsent() {
        state = .consentRequired
    }

    /// Mark engagement as expired (auto-disable).
    public func expireEngagement() {
        state = .engagementExpired
    }

    /// Set error state with message.
    public func setError(_ message: String) {
        state = .error
        errorMessage = message
    }

    /// Record that an event was emitted.
    public func recordEvent() {
        eventCount += 1
        lastEventAt = Date()
    }

    /// Get the next sequence number for event ordering.
    public func nextSequenceNumber() -> UInt64 {
        sequenceCounter += 1
        return sequenceCounter
    }
}
