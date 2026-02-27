/// KMFlow Desktop Agent — macOS menu bar application.
///
/// This is the main entry point. The agent runs as a menu bar app (LSUIElement)
/// with no Dock icon. It orchestrates the Swift capture layer and communicates
/// with the Python intelligence layer via Unix domain socket.

import AppKit
import Capture
import Consent
import Config
import CryptoKit
import Foundation
import IPC
import PII
import SwiftUI
import UI
import Utilities

@main
struct KMFlowAgentApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        Settings {
            Text("KMFlow Agent Preferences")
                .frame(width: 400, height: 300)
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var stateManager: CaptureStateManager?
    private var statusBarController: StatusBarController?
    private var blocklistManager: BlocklistManager?
    private var pythonManager: PythonProcessManager?
    private var consentManager: ConsentManager?
    private var onboardingWindow: OnboardingWindow?

    private static let log = AgentLogger(category: "AppDelegate")

    func applicationDidFinishLaunching(_ notification: Notification) {
        let state = CaptureStateManager()
        stateManager = state
        blocklistManager = BlocklistManager()
        let statusBar = StatusBarController(stateManager: state)
        statusBarController = statusBar
        statusBar.setup()

        // Verify Python bundle integrity before launching
        if let resourcesURL = Bundle.main.resourceURL?.appendingPathComponent("python") {
            let integrityResult = IntegrityChecker.verify(bundleResourcesPath: resourcesURL)
            switch integrityResult {
            case .passed:
                break
            case .failed(let violations):
                Self.log.error("Python integrity check failed: \(violations)")
                state.setError("Integrity check failed — Python bundle may have been tampered with")
                statusBar.updateIcon()
                return
            case .manifestMissing:
                Self.log.warning("Python integrity manifest not found (development mode)")
            }
        }

        // Check consent state using Keychain-backed store.
        // Run one-time migration to clean up pre-HMAC legacy records.
        let consentStore = KeychainConsentStore()

        // Detect MDM-configured engagement ID, fall back to UserDefaults or "default"
        let engagementId: String
        if let mdmDefaults = UserDefaults(suiteName: "com.kmflow.agent"),
           let mdmEngagement = mdmDefaults.string(forKey: "EngagementID"),
           !mdmEngagement.isEmpty {
            // Validate MDM-supplied engagement ID length
            if mdmEngagement.count > 128 {
                Self.log.error("MDM engagementId exceeds 128 characters — using default")
                engagementId = "default"
            } else {
                engagementId = mdmEngagement
            }
        } else {
            engagementId = UserDefaults.standard.string(forKey: "engagementId") ?? "default"
        }

        // Migrate legacy unsigned consent records before loading
        consentStore.migrateLegacyRecords(engagementId: engagementId)

        let consent = ConsentManager(engagementId: engagementId, store: consentStore)
        consentManager = consent

        // Wire consent revocation handler — stops capture and disconnects IPC
        consent.onRevocation { [weak self] _ in
            guard let self else { return }
            self.stateManager?.stopCapture()
            if let manager = self.pythonManager {
                Task { await manager.stop() }
            }
            self.stateManager?.requireConsent()
            self.statusBarController?.updateIcon()
        }

        // Wire state change handler — update menu bar icon on transitions
        state.onStateChange { [weak self] _, _ in
            self?.statusBarController?.updateIcon()
        }

        if consent.state == .neverConsented {
            // Show first-run onboarding wizard, pre-populating MDM values if available
            let wizardState = OnboardingState()
            if let mdmDefaults = UserDefaults(suiteName: "com.kmflow.agent") {
                if let mdmEng = mdmDefaults.string(forKey: "EngagementID"), !mdmEng.isEmpty {
                    wizardState.engagementId = mdmEng
                    wizardState.isMDMConfigured = true
                }
                if let mdmURL = mdmDefaults.string(forKey: "BackendURL"), !mdmURL.isEmpty {
                    wizardState.backendURL = mdmURL
                }
            }
            onboardingWindow = OnboardingWindow(state: wizardState)
            onboardingWindow?.show()
            state.requireConsent()
        } else if !consent.captureAllowed {
            state.requireConsent()
        } else {
            // Consent granted — start Python subprocess
            startPythonSubprocess()
        }

        statusBar.updateIcon()
    }

    func applicationWillTerminate(_ notification: Notification) {
        stateManager?.stopCapture()
        if let manager = pythonManager {
            Task { await manager.stop() }
        }
    }

    private func startPythonSubprocess() {
        pythonManager = PythonProcessManager()
        Task { await pythonManager.start() }
    }
}
