# G2: Privacy & Data Minimization Audit

**Agent**: G2 (Privacy & Data Minimization Auditor)
**Date**: 2026-02-25
**Scope**: KMFlow macOS Task Mining Agent -- PII protection, consent model, data minimization, transparency, regulatory compliance
**Auditor Model**: claude-opus-4-6

---

## Finding Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 3 |
| HIGH | 7 |
| MEDIUM | 8 |
| LOW | 5 |
| **Total** | **23** |

---

## CRITICAL Findings

### [CRITICAL] PII-001: L1 Filter Contains No PII Regex -- Name is Misleading

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/PII/L1Filter.swift:28-49`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
public struct L1Filter: Sendable {
    public static func isPasswordField(provider: AccessibilityProvider) -> Bool {
        return provider.isSecureTextField()
    }
    public static func isBlockedApp(bundleId: String?, blocklist: Set<String>) -> Bool {
        guard let bid = bundleId else { return false }
        return blocklist.contains(bid)
    }
```
**Description**: Despite being named "L1Filter" and residing in the `PII` module, this struct performs zero PII filtering. It only checks for password fields and blocked apps. The actual PII regex filtering (SSN, email, phone, credit card) is performed solely in `L2PIIFilter` within `WindowTitleCapture.swift`. The security whitepaper claims a "four-layer PII protection architecture" where "L1 and L2 operate on-device before data is written to local storage." While L1 does block certain contexts (password fields, private browsing, blocked apps), it is not a PII filter -- it is a context filter. This conflation could mislead CISOs during security reviews into believing two independent PII scrubbing layers exist on-device when only one (L2 regex) actually scrubs PII content from captured text.
**Risk**: Enterprise security reviewers may approve deployment based on the claim of "four-layer PII protection" when in reality there is only one PII content filter on-device (L2 regex), one context filter (L1), and two backend layers (L3 ML + L4 human) that do not yet exist in code. Misrepresentation of security controls can lead to regulatory findings.
**Recommendation**: Rename L1 to "CaptureContextFilter" or "CaptureGatekeeper" and update the whitepaper to clearly distinguish context-level blocking (L1) from content-level PII scrubbing (L2). Do not count L1 as a "PII protection layer" unless it actually inspects and redacts PII patterns.

---

### [CRITICAL] PII-002: No Encryption of Local SQLite Buffer -- Whitepaper Claim of AES-256-GCM is Not Implemented

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogController.swift:109-113`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
        // Load the buffer encryption key from Keychain (for future use when
        // the Python layer encrypts individual columns).  We retrieve it here
        // so the controller wires the full security contract even if decryption
        // is a no-op for plaintext rows today.
        _ = loadBufferKeyFromKeychain()
```
**Description**: The security whitepaper (KMF-SEC-001, Section 5) states: "The local buffer database (buffer.db) stores all captured events in an encrypted SQLite database" using "AES-256-GCM." However, the code comments in the Transparency Log Controller explicitly state that decryption "is a no-op for plaintext rows today." The buffer encryption key is loaded from Keychain but never used. The SQLite database is opened with standard `sqlite3_open_v2` with `SQLITE_OPEN_READONLY` -- no decryption, no SQLCipher, no column-level encryption. The `WelcomeView.swift` also tells users "All data is encrypted and PII is automatically redacted" (line 72), which is false for local data at rest.
**Risk**: This is a material misrepresentation of security controls. If the device is compromised, stolen, or subject to forensic examination, captured activity data is stored in plaintext in `~/Library/Application Support/KMFlowAgent/buffer.db`. This contradicts claims made to CISOs and data protection authorities. Under GDPR Art. 32 and SOC 2 CC6.6, the organization may face regulatory action for failing to implement claimed encryption controls. The whitepaper is the basis for CISO sign-off -- false claims in it constitute a compliance risk.
**Recommendation**: Either implement AES-256-GCM encryption (e.g., via SQLCipher or column-level CryptoKit encryption) before deployment, or immediately update the whitepaper, WelcomeView, and all compliance documentation to accurately state that local buffer encryption is planned for a future phase. Do not deploy with documentation that misrepresents the current security posture.

---

### [CRITICAL] PII-003: L3 and L4 PII Protection Layers Do Not Exist in Code

**File**: `/Users/proth/repos/kmflow/docs/security/task-mining-agent-security-whitepaper.md:214-221`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```markdown
### Layer 3 -- ML-Based NER Scan (Backend, Future Phase)

After upload, an NLP named-entity recognition model scans event records for residual
PII that evaded regex ... This layer is planned for Phase 3 of the platform.

### Layer 4 -- Human Quarantine Review

All uploaded records enter a quarantine queue before becoming visible to analytics.
```
**Description**: The whitepaper repeatedly claims a "four-layer PII protection architecture" as a headline security control. However, L3 is explicitly noted as "planned for Phase 3" and L4 (human quarantine review) has no backend implementation in the audited codebase. The DPA template (KMF-SEC-002) and PIA template (KMF-SEC-003) both reference the "four-layer" architecture as an implemented control. The data flow diagram in Section 3 presents L3 and L4 as active stages in the event processing pipeline without noting they are unimplemented. A CISO reviewing the whitepaper would reasonably conclude all four layers are operational.
**Risk**: If PII leaks through L2 regex (which has known gaps -- see PII-004 through PII-006), there is currently no backend safety net. The "defense in depth" is actually "defense in one layer" for PII content scrubbing. CISOs and DPOs who approved deployment based on the four-layer claim may revoke approval upon learning only one content layer exists. This could constitute a misrepresentation under the DPA.
**Recommendation**: Add a prominent disclaimer to the whitepaper Section 4 header clearly stating: "Layers 3 and 4 are not yet implemented and are planned for future phases. Current on-device PII protection relies on L1 context blocking and L2 regex scrubbing only." Update all references to "four-layer" in the DPA and PIA templates. Do not present unimplemented features as active controls in compliance documentation.

---

## HIGH Findings

### [HIGH] PII-004: L2 PII Filter Missing File Path Username Detection

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/WindowTitleCapture.swift:12-54`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
public struct L2PIIFilter: Sendable {
    private static let ssnDashed = try! NSRegularExpression(
        pattern: #"\b\d{3}-\d{2}-\d{4}\b"#
    )
    private static let email = try! NSRegularExpression(
        pattern: #"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"#
    )
```
**Description**: The L2 PII filter covers SSN (dashed only), email, US phone, credit card (Visa/MC/Discover/JCB), and AmEx. However, it does not filter file paths that contain usernames (e.g., `/Users/john.doe/Documents/Q4 Report.xlsx`), which are extremely common in macOS window titles for document-editing applications (TextEdit, Excel, Finder, Preview, etc.). The macOS username is often the employee's real name or a derivative of it (e.g., `jdoe`, `john.doe`, `jsmith`). Window titles in Finder, Terminal, and many applications display the full file path including `/Users/{username}/`.
**Risk**: Employee names are personal data under GDPR. Every window title from Finder, Terminal, or any application showing file paths will leak the macOS username to the backend. This is the most common PII type in macOS window titles and is completely unfiltered.
**Recommendation**: Add a regex pattern or explicit filter to redact the macOS home directory path segment. For example, replace `/Users/{any-word}/` with `/Users/[REDACTED]/` or use `NSHomeDirectory()` to dynamically detect and redact the current user's home path in all captured window titles.

---

### [HIGH] PII-005: L2 PII Filter Missing International PII Patterns

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/WindowTitleCapture.swift:12-54`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
    /// SSN with dashes: 123-45-6789
    private static let ssnDashed = try! NSRegularExpression(
        pattern: #"\b\d{3}-\d{2}-\d{4}\b"#
    )
    /// US phone numbers: (555) 123-4567, 555-123-4567, +1-555-123-4567
    private static let phone = try! NSRegularExpression(
        pattern: #"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"#
    )
```
**Description**: The Swift L2 filter only covers US-centric PII patterns: US SSN (dashed format only -- no undashed `123456789`), US phone numbers, and major US credit cards. The security whitepaper (Section 4) claims additional patterns including UK NI numbers, IP addresses, and dates of birth -- but these patterns are NOT present in the Swift code. The whitepaper pattern table includes 7 patterns; the Swift code implements only 5. For international deployments (DPA template supports EEA/UK), the following are missing from Swift: UK National Insurance Numbers (`AA123456C`), German Steuer-ID, French INSEE/NIR, international phone numbers (e.g., `+44 20 7946 0958`, `+91 98765 43210`), IBAN numbers, and IP addresses. The SSN pattern also misses the undashed format (`123456789`).
**Risk**: The PIA template explicitly contemplates deployment in multiple countries ("Geographic scope: [COUNTRIES / SITES]"). If deployed on UK or EU workstations, local PII types will pass through L2 unfiltered. The whitepaper claims these patterns exist (UK NI number, IP address, DOB), creating a discrepancy between documented and actual controls.
**Recommendation**: (1) Add the patterns documented in the whitepaper (UK NI, IP address, DOB) to the Swift L2PIIFilter. (2) Add patterns for IBAN, undashed SSN, and international phone number formats. (3) Consider making the PII pattern set configurable per engagement region. (4) Update the whitepaper to accurately reflect which patterns are implemented where (Swift vs. Python).

---

### [HIGH] PII-006: Window Titles Captured in Full -- Excessive Data Collection

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/WindowTitleCapture.swift:65-91`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
public struct WindowTitleCapture: Sendable {
    public static let maxTitleLength = 512
    public static func sanitize(
        title: String?, bundleId: String?
    ) -> String? {
        guard var t = title else { return nil }
        if PrivateBrowsingDetector.isPrivateBrowsing(bundleId: bundleId, windowTitle: t) {
            return "[PRIVATE_BROWSING]"
        }
        if t.count > maxTitleLength {
            t = String(t.prefix(maxTitleLength))
        }
        t = L2PIIFilter.scrub(t)
        return t
    }
}
```
**Description**: Window titles are captured up to 512 characters with only L2 regex scrubbing applied. Window titles in common applications contain highly sensitive information that regex cannot catch: email subject lines in Outlook/Mail ("RE: Your HIV Test Results"), document names ("Jane_Doe_Performance_Review_2026.docx"), browser tab titles ("Bank of America - Account Summary"), Slack conversation titles ("DM: John Smith"), CRM record titles ("Contact: Jane Smith - Acme Corp"), and terminal command output. The L2 regex only catches structured PII patterns (SSN, email, phone, CC) -- it cannot detect names, medical terms, financial information, or business confidential content embedded in freeform window title text.
**Risk**: Under GDPR Art. 5(1)(c) (data minimization), collecting full window titles is disproportionate to the stated purpose of "process mining." The PIA template states the purpose is "application usage patterns" and "transition sequences" -- for which the application name and window title are different things. Full window titles reveal the specific content employees are working on, far exceeding what is needed for process flow reconstruction. Special category data (health, trade union, political opinions) could be exposed via email subjects or document titles.
**Recommendation**: (1) For "action_level" capture scope, do not capture window titles at all -- use only app name and bundle ID. (2) For "content_level," consider capturing only the application-specific document type or a hash of the title (for deduplication) rather than the full title. (3) At minimum, add a configurable title truncation limit (e.g., 50 characters) and expand the PII filter to include name detection. (4) Document in the PIA which specific window title contents are expected and why full titles are necessary.

---

### [HIGH] CONSENT-001: Consent Not Granular Per Data Type -- GDPR Non-Compliance

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/Onboarding/ConsentView.swift:70-90`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
    private var consentCheckboxes: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Explicit Consent")
                .font(.headline)
            ConsentCheckbox(
                isChecked: $state.consentAcknowledgedObservation,
                label: "I understand that KMFlow will observe my application usage patterns"
            )
            ConsentCheckbox(
                isChecked: $state.consentAcknowledgedInformed,
                label: "I have been informed about data collection by my organization"
            )
            ConsentCheckbox(
                isChecked: $state.consentAcknowledgedMonitoring,
                label: "I consent to activity monitoring for the specified engagement"
            )
```
**Description**: The consent model requires three checkboxes but they are all-or-nothing acknowledgments -- all three must be checked to proceed. The user cannot consent to app-switch monitoring while declining window title capture, or consent to activity counts while declining idle time tracking. Although the UI offers a "Capture Scope" picker (action_level vs. content_level), there is no evidence in the codebase that the selected scope actually changes capture behavior. The `captureScope` value from `OnboardingState` is stored in `KeychainConsentStore` (line 91: `captureScope: nil`) -- it is hardcoded to `nil` and never propagated to the actual capture layer.
**Risk**: Under GDPR Art. 7, consent must be granular -- the data subject must be able to consent to individual purposes separately. The European Data Protection Board guidelines on consent (WP259 rev.01) explicitly state that bundled consent is not freely given. If consent is the legal basis for processing (rather than legitimate interest), this non-granular consent model may be invalid under GDPR, rendering all processing unlawful.
**Recommendation**: (1) Make consent granular: separate checkboxes for app monitoring, window title capture, input counts, and idle tracking. (2) Wire the `captureScope` selection to the actual capture behavior so "action_level" genuinely limits capture to counts only (no window titles). (3) Fix the `KeychainConsentStore.save()` to actually persist the `captureScope` and `authorizedBy` values from the onboarding flow instead of hardcoding them to `nil`.

---

### [HIGH] CONSENT-002: Capture Scope Selection Has No Effect on Actual Capture Behavior

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:86-93`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
    public func save(engagementId: String, state: ConsentState, at date: Date) {
        let record = ConsentRecord(
            engagementId: engagementId,
            state: state,
            consentedAt: date,
            authorizedBy: nil,
            captureScope: nil,
            consentVersion: "1.0"
        )
```
**Description**: The onboarding wizard presents users with a "Capture Scope" picker offering "Activity Level (counts only)" versus "Content Level (with PII filtering)." This implies that selecting "Activity Level" would limit capture to aggregate counts without window titles. However: (1) `KeychainConsentStore.save()` hardcodes `captureScope: nil` and `authorizedBy: nil`, discarding the user's selection. (2) There is no code in the capture layer (`AppSwitchMonitor`, `InputMonitor`, `WindowTitleCapture`) that reads or enforces the capture scope. (3) The `AgentConfig.captureGranularity` property exists but is never connected to the onboarding flow. The user believes they are choosing a lower level of monitoring, but all data types are captured regardless.
**Risk**: This is a deceptive practice. Users who select "Activity Level (counts only)" are told they are limiting data collection, but the system captures the same data as "Content Level." This undermines the validity of informed consent under GDPR Art. 7 and could constitute unfair processing under Art. 5(1)(a). If discovered during a regulatory audit or data subject access request, this would be a serious compliance finding.
**Recommendation**: (1) Wire the `OnboardingState.captureScope` value through to the consent record (fix the `nil` hardcodes). (2) In the capture layer, check the persisted scope before capturing window titles. If `action_level`, suppress window title capture entirely and capture only app name, bundle ID, and aggregate counts. (3) Until this is fixed, remove the capture scope picker from the UI to avoid presenting a non-functional privacy control.

---

### [HIGH] TRANSPARENCY-001: Transparency Log Cannot Show What Was Sent to Server

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogView.swift:96-109`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
    private var footer: some View {
        HStack {
            Image(systemName: "lock.shield")
                .font(.caption)
                .foregroundStyle(.secondary)
            Text("All data shown is local to this device. PII patterns have been redacted.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
        }
    }
```
**Description**: The Transparency Log reads from `buffer.db` and shows events "local to this device." There is no indication of which events have been uploaded to the backend versus which are still awaiting upload. There is no column for "upload status," no filter for "sent" vs. "pending," and no way for the user to verify what the server has received. The log also caps at 200 events (line 115: `.prefix(200)`) with no pagination or scrollback. Furthermore, the `TransparencyLogView` explicitly states it "deliberately offers no editing or deletion controls" (line 6 comment). The user cannot request deletion of specific events.
**Risk**: Under GDPR Art. 15 (right of access), the data subject has the right to know what data has been transmitted to third parties. The transparency log only shows local data and does not distinguish local-only from uploaded events. Under GDPR Art. 17 (right to erasure), the user has no mechanism to request deletion of specific captured events either locally or on the backend. The 200-event cap means the log may not show all captured data, undermining the transparency promise.
**Recommendation**: (1) Add an "uploaded" flag to events in buffer.db and display upload status in the log. (2) Remove the 200-event cap or add pagination so users can review all captured data. (3) Add a "Request Deletion" action per event or for a date range. (4) Add a "Data Sent Summary" showing total events uploaded, date range, and data volume sent to the backend.

---

### [HIGH] CONSENT-003: No "Withdraw Consent" Button in Menu Bar

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/StatusBarController.swift:61-133`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
    public func buildMenu(
        onPauseResume: @escaping () -> Void,
        onPreferences: @escaping () -> Void,
        onTransparencyLog: @escaping () -> Void,
        onWhatsBeingCaptured: @escaping () -> Void,
        onQuit: @escaping () -> Void
    ) -> NSMenu {
        // ...
        // Pause/Resume
        if stateManager.state == .capturing {
            let pauseItem = NSMenuItem(title: "Pause Capture", ...)
```
**Description**: The ConsentView's legal footer states "You can revoke consent at any time from the menu bar icon" (line 99). However, the menu bar controller offers only: Pause/Resume, What's Being Captured, Transparency Log, Preferences, and Quit. There is no "Withdraw Consent" or "Revoke Consent" menu item. The `ConsentManager.revokeConsent()` method exists but is never wired to any UI element. "Pause" is not the same as consent withdrawal -- pausing is temporary and does not trigger consent revocation, data deletion, or agent deregistration. The WelcomeView also states consent can be revoked, but no UI path exists to do so.
**Risk**: Under GDPR Art. 7(3), "It shall be as easy to withdraw as to give consent." Consent was given via a clear wizard flow with checkboxes. Withdrawing consent requires the user to... do what exactly? Quit the app? That does not invoke `revokeConsent()`. The absence of a withdrawal mechanism means consent is effectively irrevocable from the user's perspective, which is a GDPR violation.
**Recommendation**: Add a "Withdraw Consent" menu item to the status bar menu. When selected, it should: (1) Call `ConsentManager.revokeConsent()`, (2) Immediately stop all capture, (3) Delete the local buffer, (4) Notify the backend of consent withdrawal, (5) Present confirmation to the user. The withdrawal path should be as prominent and easy as the original consent flow.

---

## MEDIUM Findings

### [MEDIUM] PII-007: Mouse Coordinates Captured in InputEvent but Privacy Impact Undocumented

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/InputMonitor.swift:17-21`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
public enum InputEvent: Sendable {
    case keyDown(timestamp: Date)
    case keyUp(timestamp: Date)
    case mouseDown(button: MouseButton, x: Double, y: Double, timestamp: Date)
    case mouseUp(button: MouseButton, x: Double, y: Double, timestamp: Date)
    case mouseDrag(x: Double, y: Double, timestamp: Date)
```
**Description**: The `InputEvent` enum captures exact x,y screen coordinates for every mouse click and drag. While the `InputAggregator` currently only increments counts (and does not serialize coordinates to the IPC socket), the coordinates are present in the data model. If any future code change passes these events through to IPC before aggregation, pixel-level mouse tracking would be transmitted. Additionally, mouse coordinates combined with timestamps could theoretically reconstruct which UI elements were clicked, creating a detailed interaction record beyond "counts." The whitepaper and consent flow only disclose "mouse activity counts" -- not coordinates.
**Risk**: If coordinates are ever transmitted (intentionally or via regression), they would constitute undisclosed data collection. Even if currently aggregated away, the data model captures more than disclosed.
**Recommendation**: (1) If coordinates are not needed for process mining, remove the x/y parameters from `InputEvent` entirely. (2) If they are needed for future use, document them in the consent flow and PIA. (3) Add a static assert or unit test verifying that coordinates are never serialized to the IPC socket.

---

### [MEDIUM] PII-008: Idle Detection Timing Reveals Personal Patterns

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/IdleDetector.swift:14-41`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
public final class IdleDetector: @unchecked Sendable {
    private var lastActivityTime: Date
    private var isIdle: Bool = false
    private let timeoutSeconds: TimeInterval
    public init(timeoutSeconds: TimeInterval = 300) {
        self.timeoutSeconds = timeoutSeconds
        self.lastActivityTime = Date()
    }
    public func recordActivity() -> IdleTransition? {
        // ...
        if isIdle {
            isIdle = false
            return .idleEnd
        }
```
**Description**: The idle detector emits `idle_start` and `idle_end` events with timestamps. With a 5-minute idle timeout, the pattern of idle periods throughout the day reveals bathroom breaks, lunch timing, impromptu meetings, personal phone calls, and other non-work activities. The IPC `DesktopEventType` enum includes `.idleStart` and `.idleEnd` (lines 27-28 of EventProtocol.swift), and these events include timestamps at Date() precision. Over a multi-week engagement, this creates a behavioral fingerprint of the employee's daily routine patterns.
**Risk**: While idle time is disclosed in the consent flow and summary view, the privacy implications of idle pattern analysis are not explained to data subjects. An employer could use idle patterns to identify "unproductive" employees, contrary to the stated purpose of process mining. This is a proportionality concern under GDPR Art. 5(1)(c) -- idle timing granularity may exceed what is necessary for process flow reconstruction.
**Recommendation**: (1) Reduce idle event granularity -- emit idle duration aggregates (e.g., "15 minutes idle in past hour") rather than exact start/end timestamps. (2) Add idle time to the "What will NOT be captured" column if it is not essential for process mining, or explain its purpose in the consent flow. (3) Consider increasing the idle timeout to 15+ minutes to avoid capturing short breaks.

---

### [MEDIUM] CONSENT-004: MDM Can Pre-Configure Engagement ID Without Employee Knowledge

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/KMFlowAgentApp.swift:62-70`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
        // Detect MDM-configured engagement ID, fall back to UserDefaults or "default"
        let engagementId: String
        if let mdmDefaults = UserDefaults(suiteName: "com.kmflow.agent"),
           let mdmEngagement = mdmDefaults.string(forKey: "EngagementID"),
           !mdmEngagement.isEmpty {
            engagementId = mdmEngagement
        } else {
            engagementId = UserDefaults.standard.string(forKey: "engagementId") ?? "default"
        }
```
**Description**: The agent reads the engagement ID from MDM managed preferences first, falling back to UserDefaults. MDM profiles can also set `CapturePolicy`, `AppAllowlist`, `AppBlocklist`, `ScreenshotEnabled`, and other configuration values (per `AgentConfig.init?(fromMDMProfile:)`). An MDM admin could configure the agent with `CapturePolicy: content_level` and `ScreenshotEnabled: true` before the employee ever sees the consent screen. The employee's consent flow does not show them the MDM-configured values -- it shows a default scope picker that, as noted in CONSENT-002, has no effect anyway.
**Risk**: Under GDPR, consent must be "freely given." If the employer can pre-configure the monitoring parameters via MDM, and the employee consent flow does not reflect these configurations, the consent is not fully informed. The MDM can also silently grant Accessibility TCC (whitepaper Section 6), meaning the agent could begin operating with employer-chosen settings without the employee understanding the actual data collection scope.
**Recommendation**: (1) The onboarding wizard should display the MDM-configured values (especially `CapturePolicy` and `ScreenshotEnabled`) so the employee knows what they are consenting to. (2) If MDM sets `ScreenshotEnabled: true`, the consent flow must explicitly disclose this and require additional consent. (3) Consider preventing MDM from overriding employee-chosen scope to a more invasive level without re-consent.

---

### [MEDIUM] DATA-001: Uninstall Script Does Not Remove UserDefaults/Preferences Plist

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/uninstall.sh:89-101`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```bash
# Step 4: Remove Application Support data
APP_SUPPORT="${HOME}/Library/Application Support/KMFlowAgent"
if [[ -d "$APP_SUPPORT" ]]; then
    rm -rf "$APP_SUPPORT"
    echo "  Removed: $APP_SUPPORT"
else
    echo "  Not found (already removed): $APP_SUPPORT"
fi
```
**Description**: The uninstall script removes Application Support, Logs, LaunchAgent, Keychain items, and the .app bundle. However, it does not remove: (1) `~/Library/Preferences/com.kmflow.agent.plist` (UserDefaults for the standard suite), (2) `~/Library/Preferences/com.kmflow.agent.consent.plist` (if any), (3) `~/Library/Caches/com.kmflow.agent/` (if any cache directory exists), (4) `~/Library/HTTPStorages/com.kmflow.agent/` (URL session storage), (5) The macOS TCC database entry for Accessibility (acknowledged in whitepaper but not cleaned). The script also does not use secure deletion (e.g., `srm` or `shred`) -- it uses plain `rm -rf`.
**Risk**: Data residues remain on the device after uninstall. The UserDefaults plist may contain the engagement ID, backend URL, and other configuration that reveals the employee was monitored. Under GDPR Art. 17 (right to erasure), all personal data should be deleted when the processing purpose has ended.
**Recommendation**: (1) Add removal of `~/Library/Preferences/com.kmflow.agent.plist`. (2) Add removal of `~/Library/Caches/com.kmflow.agent/`. (3) Add removal of `~/Library/HTTPStorages/com.kmflow.agent/`. (4) Document that TCC entries require MDM profile removal.

---

### [MEDIUM] DATA-002: No Backend Data Deletion Mechanism Accessible to Users

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogView.swift:1-7`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
/// Read-only SwiftUI view that shows recent captured events from the
/// local SQLite buffer, with event-type filtering and PII redaction badges.
///
/// This view is the primary transparency surface for the end user.
/// It deliberately offers no editing or deletion controls -- the capture
/// buffer is managed solely by the Python layer.
```
**Description**: There is no mechanism in the agent for a user to request deletion of their data from the backend. The DPA template (Article 7.5) states the Processor must assist with data subject rights requests within 5 business days, but this is a manual process that requires the user to contact their employer, who then contacts the consulting firm. There is no in-app "Request My Data" or "Delete My Data" button. The agent does not even display contact information for data protection inquiries.
**Risk**: GDPR Art. 17 (right to erasure) and CCPA (right to delete) require that data subjects can exercise their rights. While the DPA assigns this responsibility to the Controller, providing no technical mechanism increases friction to the point where the right becomes impractical to exercise.
**Recommendation**: (1) Add a "Request Data Deletion" option in the menu bar or preferences. (2) This should send a deletion request event to the backend or provide the data protection contact email. (3) Display the engagement data protection contact in the "About" section.

---

### [MEDIUM] DATA-003: No Local Data Retention Limit by Age

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogController.swift:64-71`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
    public init() {
        let appSupport = FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask
        ).first!
        databaseURL = appSupport
            .appendingPathComponent("KMFlowAgent")
            .appendingPathComponent("buffer.db")
    }
```
**Description**: The whitepaper states a 100 MB FIFO cap on the local buffer, but there is no age-based retention limit in the Swift codebase. If the Python layer is not running (e.g., crashed, or the device is offline for weeks), captured data could accumulate on-device indefinitely within the 100 MB cap. There is no "delete events older than N days" mechanism visible in the audited code. The whitepaper claims "upload retry queue: Up to 7 days" but this is presumably in the Python layer.
**Risk**: Under GDPR Art. 5(1)(e) (storage limitation), personal data should not be kept longer than necessary. Local data sitting for weeks without upload serves no process mining purpose and increases exposure risk.
**Recommendation**: Add a time-based retention limit (e.g., 7 days) to the Swift capture layer. If the Python process has not consumed events within this period, the Swift layer should prune old events regardless of buffer size.

---

### [MEDIUM] WHITEPAPER-001: Whitepaper Claims Socket Path Does Not Match Code

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/IPC/SocketClient.swift:10-13`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
    public static let defaultSocketPath: String = {
        let home = NSHomeDirectory()
        return "\(home)/Library/Application Support/KMFlowAgent/agent.sock"
    }()
```
**Description**: The whitepaper (Section 2) states the Unix domain socket is at `/var/run/kmflow-capture.sock`. The actual code uses `~/Library/Application Support/KMFlowAgent/agent.sock`. The `/var/run/` path would require root permissions to create and would be world-readable by default. The actual path in user Application Support is more appropriate from a security standpoint (user-private, no root needed). However, the discrepancy means the whitepaper inaccurately describes the IPC channel location.
**Risk**: A CISO reviewing the whitepaper may make security assessments based on the wrong socket path. The `/var/run/` path implies different permission model considerations than the user-private Application Support path.
**Recommendation**: Update the whitepaper Section 2 architecture diagram to reflect the actual socket path: `~/Library/Application Support/KMFlowAgent/agent.sock`.

---

### [MEDIUM] WHITEPAPER-002: Whitepaper Uninstall Paths Do Not Match Code

**File**: `/Users/proth/repos/kmflow/docs/security/task-mining-agent-security-whitepaper.md:400-411`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```markdown
- The application bundle (`/Applications/KMFlow Task Mining.app`)
- The LaunchAgent plist (`~/Library/LaunchAgents/com.kmflow.taskmining.plist`)
- The Application Support directory (`~/Library/Application Support/KMFlow/`)
- All Keychain items (`com.kmflow.taskmining.*`)
- All log files (`~/Library/Logs/KMFlow/`)
```
**Description**: The whitepaper uses different naming conventions than the actual code: (1) App name: whitepaper says "KMFlow Task Mining.app", code says "KMFlow Agent.app". (2) LaunchAgent: whitepaper says "com.kmflow.taskmining.plist", code says "com.kmflow.agent.plist". (3) App Support: whitepaper says "KMFlow/", code says "KMFlowAgent/". (4) Keychain: whitepaper says "com.kmflow.taskmining.*", code says "com.kmflow.agent" and "com.kmflow.agent.consent". (5) Logs: whitepaper says "KMFlow/", code says "KMFlowAgent/".
**Risk**: If a security team or incident responder follows the whitepaper to locate agent artifacts, they will look in the wrong locations. During a security incident or forensic investigation, this wastes critical time. Data may not be properly removed during manual uninstall procedures.
**Recommendation**: Reconcile the whitepaper paths with the actual code paths. Use a single authoritative naming convention across all documentation and code.

---

## LOW Findings

### [LOW] PII-009: Private Browsing Detection is Browser-Specific and Brittle

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/PII/L1Filter.swift:54-90`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
    public static func isPrivateBrowsing(
        bundleId: String?, windowTitle: String?
    ) -> Bool {
        guard let title = windowTitle else { return false }
        if bundleId == "com.apple.Safari" {
            if title.contains("Private Browsing") { return true }
        }
        if bundleId == "com.google.Chrome" {
            if title.hasSuffix("- Incognito") { return true }
        }
```
**Description**: Private browsing detection relies on hardcoded bundle IDs and window title string matching. This approach has several gaps: (1) Brave Browser, Vivaldi, Opera, and other Chromium-based browsers are not covered. (2) Non-English localizations of browsers will show different private browsing strings (e.g., "Navigation privee" in French Safari). (3) Future browser versions may change their title format. (4) Users could use a browser not in this list for personal browsing.
**Risk**: Personal browsing in unsupported browsers will be captured as if it were work activity. Low severity because the agent also has L2 PII scrubbing and the blocklist mechanism.
**Recommendation**: (1) Add detection for Brave (`com.brave.Browser`), Vivaldi, Opera. (2) Consider a generic heuristic: any window title containing "private" or "incognito" (case-insensitive) across all browsers. (3) Document the limitations of private browsing detection in the PIA.

---

### [LOW] PII-010: BlocklistManager Returns true (Capture Allowed) When bundleId is nil

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Config/BlocklistManager.swift:33-45`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
    public func shouldCapture(bundleId: String?) -> Bool {
        guard let bid = bundleId else { return true }
        lock.lock()
        defer { lock.unlock() }
        if let allow = allowlist, !allow.isEmpty {
            return allow.contains(bid)
        }
        return !blocklist.contains(bid)
    }
```
**Description**: When `bundleId` is nil (which can occur with certain macOS processes, accessibility prompts, or system UI elements), the blocklist manager defaults to allowing capture. A more privacy-protective default would be to block capture when the application cannot be identified.
**Risk**: System dialogs, Spotlight, or other processes without bundle IDs may be captured when they should be excluded. Low risk because these typically have generic window titles.
**Recommendation**: Default to `return false` when `bundleId` is nil, following the principle of "deny by default."

---

### [LOW] CONSENT-005: Consent Version Hardcoded to "1.0" -- No Versioning Mechanism

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:86-93`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
        let record = ConsentRecord(
            engagementId: engagementId,
            state: state,
            consentedAt: date,
            authorizedBy: nil,
            captureScope: nil,
            consentVersion: "1.0"
        )
```
**Description**: The consent version is hardcoded to "1.0". If the consent text changes (e.g., new data types are captured, scope changes), there is no mechanism to detect that the employee consented to an older version and prompt for re-consent. The `ConsentRecord` has a `consentVersion` field, but it is never compared against a current version to trigger re-consent flows.
**Risk**: Under GDPR, if the processing materially changes, consent must be refreshed. Without version comparison, employees may be monitored under a consent given for a different scope.
**Recommendation**: (1) Define a `CURRENT_CONSENT_VERSION` constant. (2) At launch, compare the stored version against the current version. (3) If mismatched, trigger the consent flow again.

---

### [LOW] DATA-004: IPC Events Transmitted Over Unix Socket in Plaintext

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/IPC/SocketClient.swift:66-83`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
    public func send(_ event: CaptureEvent) throws {
        if !isConnected {
            try reconnect()
        }
        guard let fh = fileHandle else {
            throw SocketError.notConnected
        }
        do {
            var data = try encoder.encode(event)
            data.append(0x0A) // newline
            fh.write(data)
        }
```
**Description**: Events are sent as plaintext JSON (ndjson) over the Unix domain socket from the Swift process to the Python process. The whitepaper acknowledges this is a localhost-only channel and relies on OS process isolation. While this is a reasonable design choice (encrypting a localhost socket adds overhead with limited benefit), the events contain post-L2-filtered but pre-encryption data. Any local process with the same user permissions could potentially read the socket.
**Risk**: Low risk due to OS-level socket permissions (only the owning user can connect). However, if another application running under the same user account is compromised, it could listen on or connect to the socket.
**Recommendation**: (1) Set strict file permissions (0600) on the socket file. (2) Consider using XPC instead of Unix domain sockets for better OS-level process isolation. (3) Document this as an accepted risk in the whitepaper.

---

### [LOW] TRANSPARENCY-002: Transparency Log Shows Post-Filter Data Only

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogController.swift:125-129`
**Agent**: G2 (Privacy & Data Minimization Auditor)
**Evidence**:
```swift
        let sql = """
            SELECT id, timestamp, event_type, app_name, window_title, pii_redacted
            FROM events
            ORDER BY timestamp DESC
            LIMIT ?;
            """
```
**Description**: The transparency log reads from `buffer.db`, which contains post-L2-filtered data. If PII was redacted (shown by the `pii_redacted` flag and `PIIBadge`), the user cannot see what the original data was before redaction. This means the user cannot verify whether the PII filter is working correctly or over-aggressively. They see `[PII_REDACTED]` but cannot know if it was their SSN that was redacted or a false positive on a phone number in a project title.
**Risk**: Limited ability for users to verify that the PII filter is operating correctly. The user must trust that `[PII_REDACTED]` was genuinely PII. Low risk because showing unfiltered data in the log would defeat the purpose of filtering.
**Recommendation**: Consider adding a "Redaction reason" field (e.g., "matched: email pattern") so users can understand why data was redacted without seeing the original value.

---

## Regulatory Compliance Gap Summary

### GDPR Compliance Status

| Article | Requirement | Status | Finding(s) |
|---------|------------|--------|------------|
| Art. 5(1)(a) | Lawfulness, fairness, transparency | PARTIAL | CONSENT-002 (deceptive scope picker) |
| Art. 5(1)(c) | Data minimization | PARTIAL | PII-006 (full window titles excessive), PII-007 (mouse coordinates) |
| Art. 5(1)(e) | Storage limitation | PARTIAL | DATA-003 (no age-based local retention) |
| Art. 7 | Conditions for consent | NON-COMPLIANT | CONSENT-001 (not granular), CONSENT-003 (no withdrawal mechanism) |
| Art. 13-14 | Transparency | PARTIAL | TRANSPARENCY-001 (no upload status), PII-001 (misleading layer count) |
| Art. 17 | Right to erasure | NON-COMPLIANT | DATA-002 (no deletion mechanism), TRANSPARENCY-001 (no deletion controls) |
| Art. 25 | Data protection by design | PARTIAL | CONSENT-002 (scope picker non-functional), PII-002 (no encryption) |
| Art. 32 | Security of processing | NON-COMPLIANT | PII-002 (local encryption not implemented despite claims) |
| Art. 35 | DPIA | COMPLIANT | PIA template provided (KMF-SEC-003) |

### CCPA/CPRA Compliance Status

| Right | Status | Finding(s) |
|-------|--------|------------|
| Right to know | PARTIAL | TRANSPARENCY-001 (incomplete transparency log) |
| Right to delete | NON-COMPLIANT | DATA-002 (no deletion mechanism) |
| Right to opt-out | PARTIAL | CONSENT-003 (no withdrawal mechanism) |

### Whitepaper vs. Reality Discrepancies

| Whitepaper Claim | Reality | Finding |
|-----------------|---------|---------|
| "Four-layer PII protection" | Only L1 (context) + L2 (regex) implemented | PII-001, PII-003 |
| "AES-256-GCM encrypted SQLite buffer" | Buffer is plaintext; encryption is "no-op" | PII-002 |
| "No keystroke logging" | Correct -- InputMonitor captures counts only | Verified |
| "User-controlled pause" | Pause exists; consent withdrawal does not | CONSENT-003 |
| "Transparency log shows all captured data" | Shows last 200 events; no upload status | TRANSPARENCY-001 |
| "On-device encryption" | Not implemented; claimed as current | PII-002 |
| Socket path "/var/run/kmflow-capture.sock" | Actual: ~/Library/.../agent.sock | WHITEPAPER-001 |
| App name "KMFlow Task Mining.app" | Actual: "KMFlow Agent.app" | WHITEPAPER-002 |
| L2 patterns include UK NI, IP, DOB | Swift L2 only has SSN, email, phone, CC, AmEx | PII-005 |

---

## Recommendations Priority Matrix

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| P0 (Block deployment) | PII-002: Implement local encryption or correct whitepaper | High | Eliminates material misrepresentation |
| P0 (Block deployment) | PII-003: Add disclaimer for unimplemented L3/L4 layers | Low | Corrects compliance documentation |
| P0 (Block deployment) | CONSENT-003: Add consent withdrawal mechanism | Medium | GDPR Art. 7(3) compliance |
| P1 (Before production) | CONSENT-002: Wire capture scope to actual behavior | Medium | Eliminates deceptive control |
| P1 (Before production) | PII-004: Add file path username filtering | Low | Prevents most common PII leak |
| P1 (Before production) | CONSENT-001: Make consent granular | Medium | GDPR consent validity |
| P1 (Before production) | PII-006: Limit window title capture for action_level | Medium | Data minimization compliance |
| P2 (Near-term) | PII-005: Add international PII patterns | Medium | International deployment readiness |
| P2 (Near-term) | TRANSPARENCY-001: Add upload status to log | Medium | GDPR Art. 15 compliance |
| P2 (Near-term) | DATA-002: Add deletion request mechanism | Medium | GDPR Art. 17 compliance |
| P3 (Backlog) | All remaining MEDIUM and LOW findings | Various | Defense in depth |
