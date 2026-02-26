/// Detects user idle periods based on event cadence.
///
/// Emits IDLE_START when no events for `idleTimeoutSeconds` and
/// IDLE_END when activity resumes.

import Foundation

public actor IdleDetector {
    private var lastActivityTime: Date
    private var isIdle: Bool = false
    private let timeoutSeconds: TimeInterval

    public init(timeoutSeconds: TimeInterval = 300) {
        self.timeoutSeconds = timeoutSeconds
        self.lastActivityTime = Date()
    }

    /// Record user activity. Returns .idleEnd if transitioning out of idle.
    public func recordActivity() -> IdleTransition? {
        lastActivityTime = Date()
        if isIdle {
            isIdle = false
            return .idleEnd
        }
        return nil
    }

    /// Check if the user has gone idle. Call periodically (e.g., every 10s).
    /// Returns .idleStart if transitioning into idle.
    public func checkIdle() -> IdleTransition? {
        if !isIdle && Date().timeIntervalSince(lastActivityTime) >= timeoutSeconds {
            isIdle = true
            return .idleStart
        }
        return nil
    }

    public var currentlyIdle: Bool {
        isIdle
    }
}

public enum IdleTransition: Sendable {
    case idleStart
    case idleEnd
}
