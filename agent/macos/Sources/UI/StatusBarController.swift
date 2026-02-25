/// Manages the NSStatusItem (menu bar icon) and its menu.

import AppKit
import Capture
import Foundation

@MainActor
public final class StatusBarController {
    private var statusItem: NSStatusItem?
    private let stateManager: CaptureStateManager
    private var menuDelegate: MenuActionDelegate?

    public init(stateManager: CaptureStateManager) {
        self.stateManager = stateManager
    }

    public func setup() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        updateIcon()
    }

    public func updateIcon() {
        guard let button = statusItem?.button else { return }

        let symbolName: String
        switch stateManager.state {
        case .capturing:
            symbolName = "waveform.circle.fill"
        case .paused:
            symbolName = "waveform.circle"
        case .error, .engagementExpired:
            symbolName = "exclamationmark.circle"
        case .consentRequired:
            symbolName = "questionmark.circle"
        case .idle:
            symbolName = "waveform.circle"
        }

        if let image = NSImage(systemSymbolName: symbolName, accessibilityDescription: "KMFlow Agent") {
            image.isTemplate = true
            button.image = image
        }

        // Tooltip
        switch stateManager.state {
        case .capturing:
            button.toolTip = "KMFlow — Capturing activity"
        case .paused:
            button.toolTip = "KMFlow — Capture paused"
        case .error:
            button.toolTip = "KMFlow — Error: \(stateManager.errorMessage ?? "unknown")"
        case .engagementExpired:
            button.toolTip = "KMFlow — Engagement expired"
        case .consentRequired:
            button.toolTip = "KMFlow — Consent required"
        case .idle:
            button.toolTip = "KMFlow — Idle"
        }
    }

    public func buildMenu(
        onPauseResume: @escaping () -> Void,
        onPreferences: @escaping () -> Void,
        onQuit: @escaping () -> Void
    ) -> NSMenu {
        let menu = NSMenu()

        // Keep delegate alive
        let delegate = MenuActionDelegate(
            onPauseResume: onPauseResume,
            onPreferences: onPreferences,
            onQuit: onQuit
        )
        self.menuDelegate = delegate

        // Status line
        let statusItem = NSMenuItem(title: "Status: \(stateManager.state.rawValue)", action: nil, keyEquivalent: "")
        statusItem.isEnabled = false
        menu.addItem(statusItem)

        // Event count
        let countItem = NSMenuItem(
            title: "Events captured: \(stateManager.eventCount)",
            action: nil,
            keyEquivalent: ""
        )
        countItem.isEnabled = false
        menu.addItem(countItem)

        menu.addItem(NSMenuItem.separator())

        // Pause/Resume
        if stateManager.state == .capturing {
            let pauseItem = NSMenuItem(title: "Pause Capture", action: #selector(delegate.pauseResume), keyEquivalent: "p")
            pauseItem.target = delegate
            menu.addItem(pauseItem)
        } else if stateManager.state == .paused {
            let resumeItem = NSMenuItem(title: "Resume Capture", action: #selector(delegate.pauseResume), keyEquivalent: "p")
            resumeItem.target = delegate
            menu.addItem(resumeItem)
        }

        menu.addItem(NSMenuItem.separator())

        // Preferences
        let prefsItem = NSMenuItem(title: "Preferences...", action: #selector(delegate.preferences), keyEquivalent: ",")
        prefsItem.target = delegate
        menu.addItem(prefsItem)

        menu.addItem(NSMenuItem.separator())

        // Quit
        let quitItem = NSMenuItem(title: "Quit KMFlow Agent", action: #selector(delegate.quit), keyEquivalent: "q")
        quitItem.target = delegate
        menu.addItem(quitItem)

        return menu
    }
}

/// Target for NSMenuItem actions — bridges closures to @objc selectors.
final class MenuActionDelegate: NSObject {
    private let onPauseResume: () -> Void
    private let onPreferences: () -> Void
    private let onQuit: () -> Void

    init(onPauseResume: @escaping () -> Void, onPreferences: @escaping () -> Void, onQuit: @escaping () -> Void) {
        self.onPauseResume = onPauseResume
        self.onPreferences = onPreferences
        self.onQuit = onQuit
    }

    @objc func pauseResume() { onPauseResume() }
    @objc func preferences() { onPreferences() }
    @objc func quit() { onQuit() }
}
