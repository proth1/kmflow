/// Step 3 — macOS Accessibility permission setup.
///
/// Explains why Accessibility access is required for activity capture, provides
/// a button to open the correct System Settings pane, and polls
/// `AXIsProcessTrusted()` every 2 seconds to update the status indicator.

import SwiftUI
import ApplicationServices

/// The permissions step of the onboarding wizard.
///
/// Accessibility access is mandatory for window-focus tracking. This view
/// auto-polls the system every 2 seconds and updates `OnboardingState.accessibilityGranted`
/// when the user grants permission without leaving the wizard.
public struct PermissionsView: View {

    // MARK: - Dependencies

    @ObservedObject private var state: OnboardingState

    // MARK: - Private State

    /// Timer used to poll `AXIsProcessTrusted()` while this view is on screen.
    @State private var pollTimer: Timer? = nil

    // MARK: - Constants

    private static let accessibilityPrefsURL =
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"

    // MARK: - Initialiser

    /// - Parameter state: The shared wizard state.
    public init(state: OnboardingState) {
        self.state = state
    }

    // MARK: - Body

    public var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            headerSection
            accessibilitySection
            Divider()
            optionalPermissionsNote
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear(perform: startPolling)
        .onDisappear(perform: stopPolling)
    }

    // MARK: - Sub-views

    /// Icon and explanatory header.
    private var headerSection: some View {
        HStack(alignment: .top, spacing: 16) {
            Image(systemName: "hand.raised.circle.fill")
                .resizable()
                .scaledToFit()
                .frame(width: 44, height: 44)
                .foregroundStyle(.tint)
                .symbolRenderingMode(.hierarchical)

            VStack(alignment: .leading, spacing: 6) {
                Text("macOS Permissions")
                    .font(.headline)

                Text(
                    "KMFlow requires Accessibility access to detect application switches and monitor window focus changes. This permission enables the agent to observe which apps you are using — it does not read screen content."
                )
                .font(.body)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// Accessibility permission row with status indicator and open-settings button.
    private var accessibilitySection: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Required Permission")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundColor(.secondary)
                .textCase(.uppercase)

            HStack(spacing: 14) {
                // Status indicator
                accessibilityStatusBadge

                VStack(alignment: .leading, spacing: 3) {
                    Text("Accessibility Access")
                        .font(.body)
                        .fontWeight(.medium)

                    Text("Allows window-focus and application-switch tracking")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Spacer()

                Button("Open System Settings") {
                    openAccessibilityPreferences()
                }
                .buttonStyle(.bordered)
            }
            .padding(14)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color(NSColor.controlBackgroundColor))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(
                        state.accessibilityGranted
                            ? Color.green.opacity(0.5)
                            : Color.orange.opacity(0.4),
                        lineWidth: 1
                    )
            )
        }
    }

    /// Green checkmark when granted, yellow warning triangle when not.
    private var accessibilityStatusBadge: some View {
        Group {
            if state.accessibilityGranted {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.green)
                    .font(.title2)
                    .transition(.scale.combined(with: .opacity))
            } else {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundColor(.orange)
                    .font(.title2)
                    .transition(.scale.combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.2), value: state.accessibilityGranted)
    }

    /// Note about Screen Recording being optional / future-phase only.
    private var optionalPermissionsNote: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "info.circle")
                .foregroundColor(.secondary)
                .frame(width: 16)
            Text(
                "Screen Recording permission is optional and only needed for screenshot analysis (Phase 2). It is not required to complete setup."
            )
            .font(.footnote)
            .foregroundColor(.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - Polling

    /// Starts a 2-second repeating timer that calls `AXIsProcessTrusted()`.
    private func startPolling() {
        // Perform an immediate check before the first tick.
        checkAccessibility()

        // Capture `state` (a reference type) rather than `self` (a struct)
        // to avoid retaining a stale copy of the view struct in the timer closure.
        let observedState = state
        let timer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { _ in
            Task { @MainActor in
                let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: false] as CFDictionary
                observedState.accessibilityGranted = AXIsProcessTrustedWithOptions(options)
            }
        }
        pollTimer = timer
    }

    /// Invalidates and releases the polling timer.
    private func stopPolling() {
        pollTimer?.invalidate()
        pollTimer = nil
    }

    /// Queries `AXIsProcessTrusted()` and updates `state.accessibilityGranted`.
    private func checkAccessibility() {
        // Pass an empty options dict to avoid prompting the user with a dialog —
        // the "Open System Settings" button is the intended prompt path.
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: false] as CFDictionary
        let trusted = AXIsProcessTrustedWithOptions(options)
        state.accessibilityGranted = trusted
    }

    // MARK: - Actions

    /// Opens the Accessibility section of System Settings (Privacy & Security).
    private func openAccessibilityPreferences() {
        guard let url = URL(string: Self.accessibilityPrefsURL) else { return }
        NSWorkspace.shared.open(url)
    }
}

// MARK: - Preview

#if DEBUG
struct PermissionsView_Previews: PreviewProvider {
    static var previews: some View {
        PermissionsView(state: OnboardingState())
            .padding(24)
            .frame(width: 552)
    }
}
#endif
