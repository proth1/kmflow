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

    /// Duration of the current idle period, rounded to 15-minute bins to
    /// reduce granularity and protect employee privacy.
    ///
    /// Returns 0 if the user is not idle. Coarsening prevents detailed
    /// inference of exact break timing from idle durations.
    public var coarsenedIdleDuration: TimeInterval {
        guard isIdle else { return 0 }
        let raw = Date().timeIntervalSince(lastActivityTime)
        let binSize: TimeInterval = 900 // 15 minutes
        return (raw / binSize).rounded(.down) * binSize
    }
}

public enum IdleTransition: Sendable {
    case idleStart
    case idleEnd
}
