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

/// Closure invoked when capture state changes, allowing monitors to start/stop.
public typealias CaptureStateChangeHandler = @MainActor (CaptureState, CaptureState) -> Void

@MainActor
public final class CaptureStateManager: ObservableObject {
    @Published public private(set) var state: CaptureState = .idle
    @Published public private(set) var eventCount: UInt64 = 0
    @Published public private(set) var lastEventAt: Date?
    @Published public private(set) var errorMessage: String?

    private var sequenceCounter: UInt64 = 0

    /// Registered handlers notified on every state transition.
    /// Monitors register here to actually stop/start their event taps.
    private var stateChangeHandlers: [CaptureStateChangeHandler] = []

    /// UserDefaults key for persisting the last known capture state across launches.
    private static let persistedStateKey = "com.kmflow.agent.captureState"

    public init() {
        // Restore persisted state if available (crash recovery).
        if let raw = UserDefaults.standard.string(forKey: Self.persistedStateKey),
           let restored = CaptureState(rawValue: raw) {
            state = restored
        }
    }

    /// Register a handler that is called on every state transition.
    /// Use this to wire monitor start/stop to the state machine.
    public func onStateChange(_ handler: @escaping CaptureStateChangeHandler) {
        stateChangeHandlers.append(handler)
    }

    private func transition(to newState: CaptureState) {
        let oldState = state
        state = newState
        UserDefaults.standard.set(newState.rawValue, forKey: Self.persistedStateKey)
        for handler in stateChangeHandlers {
            handler(oldState, newState)
        }
    }

    /// Transition to capturing state. Requires consent to have been given.
    public func startCapture() {
        guard state == .idle || state == .paused else { return }
        transition(to: .capturing)
        errorMessage = nil
    }

    /// Pause capture (user-initiated). Monitors are notified to stop event taps.
    public func pauseCapture() {
        guard state == .capturing else { return }
        transition(to: .paused)
    }

    /// Resume capture from paused state. Monitors are notified to restart.
    public func resumeCapture() {
        guard state == .paused else { return }
        transition(to: .capturing)
        errorMessage = nil
    }

    /// Stop capture and return to idle.
    public func stopCapture() {
        transition(to: .idle)
    }

    /// Mark consent as required (first launch or revoked).
    public func requireConsent() {
        transition(to: .consentRequired)
    }

    /// Mark engagement as expired (auto-disable).
    public func expireEngagement() {
        transition(to: .engagementExpired)
    }

    /// Set error state with message.
    public func setError(_ message: String) {
        transition(to: .error)
        errorMessage = message
    }

    /// Returns `true` if the current state permits event capture.
    ///
    /// Monitors should call this before emitting each event to enforce
    /// per-event consent checking (defense-in-depth — even if the monitor
    /// was started correctly, consent could be revoked between events).
    public var isCapturePermitted: Bool {
        state == .capturing
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
