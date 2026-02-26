/// Creates and manages the NSWindow that hosts the onboarding wizard.
///
/// `OnboardingWindow` owns the window lifetime. Call `show()` to present the
/// wizard on first launch and `close()` to dismiss it once setup is complete
/// or the user cancels.

import AppKit
import SwiftUI

/// Manages the floating NSWindow that presents the onboarding SwiftUI wizard.
@MainActor
public final class OnboardingWindow {

    // MARK: - Configuration

    private static let windowWidth: CGFloat  = 600
    private static let windowHeight: CGFloat = 500
    private static let windowTitle           = "KMFlow Agent Setup"

    // MARK: - State

    private var window: NSWindow?
    private var hostingController: NSHostingController<OnboardingContentView>?

    /// The shared state object threaded through all wizard views.
    private let onboardingState: OnboardingState

    // MARK: - Lifecycle

    /// Creates an `OnboardingWindow` with a fresh `OnboardingState`.
    public init() {
        self.onboardingState = OnboardingState()
    }

    /// Creates an `OnboardingWindow` with an externally supplied state object.
    ///
    /// Use this initialiser in tests or when you need to pre-populate wizard fields.
    ///
    /// - Parameter state: The `OnboardingState` to bind into the wizard.
    public init(state: OnboardingState) {
        self.onboardingState = state
    }

    // MARK: - Public Interface

    /// Presents the onboarding wizard in a floating, non-resizable window.
    ///
    /// If a window is already visible this method is a no-op.
    public func show() {
        guard window == nil else { return }

        let contentView = OnboardingContentView(state: onboardingState)
        let hosting = NSHostingController(rootView: contentView)
        self.hostingController = hosting

        let win = NSWindow(
            contentRect: NSRect(
                x: 0, y: 0,
                width: Self.windowWidth,
                height: Self.windowHeight
            ),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )

        win.title = Self.windowTitle
        win.contentViewController = hosting
        win.level = .floating
        win.isReleasedWhenClosed = false

        // Lock size — the wizard layout is designed for exactly 600×500.
        win.minSize = NSSize(width: Self.windowWidth, height: Self.windowHeight)
        win.maxSize = NSSize(width: Self.windowWidth, height: Self.windowHeight)

        // Center on the primary screen.
        win.center()

        win.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        self.window = win
    }

    /// Closes the wizard window and releases all retained resources.
    public func close() {
        window?.close()
        window = nil
        hostingController = nil
    }

    // MARK: - Accessors

    /// The underlying `NSWindow`, or `nil` if the window has not been shown yet.
    public var nsWindow: NSWindow? { window }

    /// The state object driving the wizard. Useful for reading final values after completion.
    public var state: OnboardingState { onboardingState }
}
