/// KMFlow Desktop Agent — macOS menu bar application.
///
/// This is the main entry point. The agent runs as a menu bar app (LSUIElement)
/// with no Dock icon. It orchestrates the Swift capture layer and communicates
/// with the Python intelligence layer via Unix domain socket.

import AppKit
import Capture
import Consent
import Config
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

    func applicationDidFinishLaunching(_ notification: Notification) {
        stateManager = CaptureStateManager()
        blocklistManager = BlocklistManager()
        statusBarController = StatusBarController(stateManager: stateManager)
        statusBarController.setup()

        // Check consent state
        let consentStore = InMemoryConsentStore()  // TODO: Replace with KeychainConsentStore
        let consentManager = ConsentManager(engagementId: "default", store: consentStore)

        if !consentManager.captureAllowed {
            stateManager.requireConsent()
        }

        statusBarController.updateIcon()
    }

    func applicationWillTerminate(_ notification: Notification) {
        stateManager.stopCapture()
    }
}
