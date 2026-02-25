/// Keyboard and mouse action counting via CGEventTap.
///
/// In ACTION_LEVEL mode (default), only counts and timing are captured.
/// In CONTENT_LEVEL mode, actual keystrokes are captured (with L2 PII filtering).
/// Password fields (AXSecureTextField) are NEVER captured at any level.

import ApplicationServices
import Foundation

/// Protocol for keyboard/mouse event sources (testable abstraction over CGEventTap).
public protocol InputEventSource: AnyObject {
    func start(handler: @escaping (InputEvent) -> Void) throws
    func stop()
}

public enum InputEvent: Sendable {
    case keyDown(timestamp: Date)
    case keyUp(timestamp: Date)
    case mouseDown(button: MouseButton, x: Double, y: Double, timestamp: Date)
    case mouseUp(button: MouseButton, x: Double, y: Double, timestamp: Date)
    case mouseDrag(x: Double, y: Double, timestamp: Date)
    case scroll(deltaX: Double, deltaY: Double, timestamp: Date)
}

public enum MouseButton: String, Codable, Sendable {
    case left
    case right
    case other
}

/// Aggregates raw input events into semantic keyboard/mouse action counts.
public final class InputAggregator: @unchecked Sendable {
    private let lock = NSLock()
    private var keyCount: Int = 0
    private var backspaceCount: Int = 0
    private var specialKeyCount: Int = 0
    private var typingStarted: Date?
    private var clickCount: Int = 0
    private var scrollCount: Int = 0
    private var dragCount: Int = 0

    public init() {}

    /// Record a key press.
    public func recordKeyDown() {
        lock.lock()
        defer { lock.unlock() }
        if typingStarted == nil { typingStarted = Date() }
        keyCount += 1
    }

    /// Record a backspace press.
    public func recordBackspace() {
        lock.lock()
        defer { lock.unlock() }
        backspaceCount += 1
    }

    /// Record a special key (function keys, arrows, etc.).
    public func recordSpecialKey() {
        lock.lock()
        defer { lock.unlock() }
        specialKeyCount += 1
    }

    /// Record a mouse click.
    public func recordClick() {
        lock.lock()
        defer { lock.unlock() }
        clickCount += 1
    }

    /// Record a scroll action.
    public func recordScroll() {
        lock.lock()
        defer { lock.unlock() }
        scrollCount += 1
    }

    /// Record a mouse drag.
    public func recordDrag() {
        lock.lock()
        defer { lock.unlock() }
        dragCount += 1
    }

    /// Flush and return the current aggregated counts, resetting them.
    public func flush() -> AggregatedInput {
        lock.lock()
        defer { lock.unlock() }
        let durationMs: UInt64
        if let start = typingStarted {
            durationMs = UInt64(Date().timeIntervalSince(start) * 1000)
        } else {
            durationMs = 0
        }
        let result = AggregatedInput(
            charCount: keyCount,
            backspaceCount: backspaceCount,
            specialKeyCount: specialKeyCount,
            typingDurationMs: durationMs,
            clickCount: clickCount,
            scrollCount: scrollCount,
            dragCount: dragCount
        )
        keyCount = 0
        backspaceCount = 0
        specialKeyCount = 0
        typingStarted = nil
        clickCount = 0
        scrollCount = 0
        dragCount = 0
        return result
    }
}

public struct AggregatedInput: Sendable {
    public let charCount: Int
    public let backspaceCount: Int
    public let specialKeyCount: Int
    public let typingDurationMs: UInt64
    public let clickCount: Int
    public let scrollCount: Int
    public let dragCount: Int

    public var isEmpty: Bool {
        charCount == 0 && backspaceCount == 0 && specialKeyCount == 0
            && clickCount == 0 && scrollCount == 0 && dragCount == 0
    }
}
