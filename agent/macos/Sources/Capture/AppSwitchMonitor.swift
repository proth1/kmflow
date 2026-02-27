/// Monitors application switches using NSWorkspace notifications.
///
/// Emits APP_SWITCH events when the user switches between applications,
/// and WINDOW_FOCUS events when the window changes within the same app.

import AppKit
import Config
import Foundation

/// Protocol abstracting NSWorkspace for testability.
public protocol WorkspaceObserver: AnyObject {
    func startObserving(handler: @escaping (AppSwitchEvent) -> Void)
    func stopObserving()
}

public struct AppSwitchEvent: Sendable {
    public let fromApp: String?
    public let fromBundleId: String?
    public let toApp: String
    public let toBundleId: String?
    public let dwellMs: UInt64
    public let timestamp: Date

    public init(
        fromApp: String?,
        fromBundleId: String?,
        toApp: String,
        toBundleId: String?,
        dwellMs: UInt64,
        timestamp: Date = Date()
    ) {
        self.fromApp = fromApp
        self.fromBundleId = fromBundleId
        self.toApp = toApp
        self.toBundleId = toBundleId
        self.dwellMs = dwellMs
        self.timestamp = timestamp
    }
}

/// Concrete NSWorkspace-based observer.
///
/// All NSWorkspace notification observation and state updates run on the main
/// queue (`queue: .main`). Full `@MainActor` annotation is deferred until
/// BlocklistManager's `shouldCapture` is made nonisolated or async-compatible.
public final class SystemAppSwitchMonitor: WorkspaceObserver {
    private var observer: NSObjectProtocol?
    private var lastAppName: String?
    private var lastBundleId: String?
    private var lastSwitchTime: Date?
    private let blocklistManager: BlocklistManager

    public init(blocklistManager: BlocklistManager) {
        self.blocklistManager = blocklistManager
    }

    public func startObserving(handler: @escaping (AppSwitchEvent) -> Void) {
        lastSwitchTime = Date()

        observer = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self = self,
                  let app = notification.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication
            else { return }

            let bundleId = app.bundleIdentifier
            let appName = app.localizedName ?? "Unknown"

            // L1 blocklist check
            guard self.blocklistManager.shouldCapture(bundleId: bundleId) else {
                // Update tracking but don't emit event.
                // Clear lastSwitchTime to prevent dwell time from accumulating
                // across blocked apps — otherwise the next allowed app would
                // include time spent in a blocked app in its dwell calculation.
                self.lastAppName = nil
                self.lastBundleId = nil
                self.lastSwitchTime = nil
                return
            }

            let now = Date()
            let dwellMs: UInt64
            if let last = self.lastSwitchTime {
                dwellMs = UInt64(now.timeIntervalSince(last) * 1000)
            } else {
                dwellMs = 0
            }

            let event = AppSwitchEvent(
                fromApp: self.lastAppName,
                fromBundleId: self.lastBundleId,
                toApp: appName,
                toBundleId: bundleId,
                dwellMs: dwellMs,
                timestamp: now
            )

            self.lastAppName = appName
            self.lastBundleId = bundleId
            self.lastSwitchTime = now

            handler(event)
        }
    }

    public func stopObserving() {
        if let obs = observer {
            NSWorkspace.shared.notificationCenter.removeObserver(obs)
            observer = nil
        }
    }

    deinit {
        stopObserving()
    }
}
