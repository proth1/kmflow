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
    private var stateManager: CaptureStateManager!
    private var statusBarController: StatusBarController!
    private var blocklistManager: BlocklistManager!
    private var pythonManager: PythonProcessManager!
    private var onboardingWindow: OnboardingWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {
        stateManager = CaptureStateManager()
        blocklistManager = BlocklistManager()
        statusBarController = StatusBarController(stateManager: stateManager)
        statusBarController.setup()

        // Verify Python bundle integrity before launching
        if let resourcesURL = Bundle.main.resourceURL?.appendingPathComponent("python") {
            let integrityResult = IntegrityChecker.verify(bundleResourcesPath: resourcesURL)
            switch integrityResult {
            case .passed:
                break
            case .failed(let violations):
                NSLog("KMFlowAgent: Python integrity check failed: \(violations)")
                stateManager.setError("Integrity check failed — Python bundle may have been tampered with")
                statusBarController.updateIcon()
                return
            case .manifestMissing:
                NSLog("KMFlowAgent: Python integrity manifest not found (development mode)")
            }
        }

        // Check consent state using Keychain-backed store
        let consentStore = KeychainConsentStore()

        // Detect MDM-configured engagement ID, fall back to UserDefaults or "default"
        let engagementId: String
        if let mdmDefaults = UserDefaults(suiteName: "com.kmflow.agent"),
           let mdmEngagement = mdmDefaults.string(forKey: "EngagementID"),
           !mdmEngagement.isEmpty {
            engagementId = mdmEngagement
        } else {
            engagementId = UserDefaults.standard.string(forKey: "engagementId") ?? "default"
        }

        let consentManager = ConsentManager(engagementId: engagementId, store: consentStore)

        if consentManager.state == .neverConsented {
            // Show first-run onboarding wizard
            onboardingWindow = OnboardingWindow()
            onboardingWindow?.show()
            stateManager.requireConsent()
        } else if !consentManager.captureAllowed {
            stateManager.requireConsent()
        } else {
            // Consent granted — start Python subprocess
            startPythonSubprocess()
        }

        statusBarController.updateIcon()
    }

    func applicationWillTerminate(_ notification: Notification) {
        stateManager.stopCapture()
        if let manager = pythonManager {
            Task { await manager.stop() }
        }
    }

    private func startPythonSubprocess() {
        pythonManager = PythonProcessManager()
        Task { await pythonManager.start() }
    }
}
