# G2: Privacy & Data Minimization Re-Audit

**Agent**: G2 (Privacy & Data Minimization Auditor)
**Date**: 2026-02-26
**Original Audit Date**: 2026-02-25
**Scope**: KMFlow macOS Task Mining Agent -- PII protection, consent model, data minimization, transparency, regulatory compliance
**Auditor Model**: claude-opus-4-6
**Re-Audit Trigger**: Post-remediation review following PRs #245, #248, #255, #256, #258

---

## Remediation Summary

| Original ID | Severity | Finding | Status | PR | Notes |
|-------------|----------|---------|--------|----|-------|
| PII-001 | CRITICAL | L1 Filter name misleading | **CLOSED** | #245, #248 | Renamed to `CaptureContextFilter`; moved to `PII` module; whitepaper updated to distinguish context blocking from PII scrubbing |
| PII-002 | CRITICAL | "All data is encrypted" false claim in WelcomeView + whitepaper | **CLOSED** | #245 | WelcomeView line 72 now reads "Data is transmitted securely and PII is automatically redacted"; whitepaper Sec. 5 now explicitly states buffer is plaintext with encryption planned |
| PII-003 | CRITICAL | L3/L4 claimed as implemented | **CLOSED** | #245 | Whitepaper Sec. 4 headers now read "NOT YET IMPLEMENTED"; DPA and PIA updated with disclaimers; data flow diagram annotated |
| PII-004 | HIGH | Missing file path username detection | **CLOSED** | #248 | `L2PIIFilter` now includes `filePath` regex matching `/Users/{name}/` and `C:\Users\{name}\` patterns (lines 45-48) |
| PII-005 | HIGH | Missing international PII patterns | **CLOSED** | #248 | Added IBAN (line 40-43), UK NINO (line 50-53); whitepaper pattern table reconciled with Swift code |
| PII-006 | HIGH | Window title not truncated / excessive capture | **PARTIAL** | #248 | `maxTitleLength` added at 512 chars (line 93); truncation implemented (lines 108-109). However, 512 chars is still generous and window titles are captured even in `action_level` mode |
| CONSENT-001 | HIGH | Consent not granular per data type | **OPEN** | -- | No change; all three checkboxes remain all-or-nothing |
| CONSENT-002 | HIGH | Capture scope picker no-op | **CLOSED** | #256 | Scope picker disabled in UI (lines 63-68 of ConsentView); commented out "Content Level" option; picker set to `disabled(true)` |
| CONSENT-003 | HIGH | No "Withdraw Consent" in menu bar | **PARTIAL** | #256 | `ConsentManager.onRevocation()` handler added (line 40); `revokeConsent()` calls handlers (lines 56-62). Menu bar still lacks an explicit "Withdraw Consent" item |
| PII-007 | MEDIUM | Mouse coordinates in InputEvent | **CLOSED** | #255 | `InputEvent` enum no longer carries x/y coordinates (confirmed: lines 16-23 of InputMonitor.swift) |
| PII-008 | MEDIUM | Idle detection timing reveals personal patterns | **OPEN** | -- | No change; `IdleDetector` still emits exact timestamps |
| CONSENT-004 | MEDIUM | MDM pre-configures without employee knowledge | **OPEN** | -- | No change; onboarding does not display MDM-configured values |
| DATA-001 | MEDIUM | Uninstall script incomplete | **PARTIAL** | #258 | Uninstall script updated with more artifact paths; still missing `~/Library/Preferences/com.kmflow.agent.plist` |
| DATA-002 | MEDIUM | No backend deletion mechanism | **OPEN** | -- | No change |
| DATA-003 | MEDIUM | No local retention limit by age | **OPEN** | -- | No change |
| WHITEPAPER-001 | MEDIUM | Socket path discrepancy | **CLOSED** | #245 | Whitepaper Sec. 2 diagram now shows `~/Library/Application Support/KMFlowAgent/agent.sock` |
| WHITEPAPER-002 | MEDIUM | Whitepaper uninstall paths wrong | **CLOSED** | #245 | Whitepaper Sec. 9 paths reconciled with actual code paths |
| PII-009 | LOW | Private browsing detection brittle | **PARTIAL** | #248 | Arc and Edge added to `PrivateBrowsingDetector`; Brave and Vivaldi still missing |
| PII-010 | LOW | BlocklistManager returns true for nil bundleId | **CLOSED** | #255 | Now returns `false` for nil bundleId (line 34 of BlocklistManager.swift) |
| CONSENT-005 | LOW | Consent version hardcoded | **OPEN** | -- | Still hardcoded to "1.0" (line 120 of KeychainConsentStore.swift) |
| DATA-004 | LOW | IPC plaintext over socket | **ACCEPTED** | -- | Whitepaper documents this as accepted risk; symlink check and auth handshake added (PR #255) |
| TRANSPARENCY-001 | HIGH | Transparency log missing upload status | **OPEN** | -- | No change; log still reads from local buffer only, 200-event cap, no upload status |
| TRANSPARENCY-002 | LOW | Log shows post-filter data only | **OPEN** | -- | No change |

---

## Updated Finding Summary

| Severity | Original Count | Closed | Remaining |
|----------|---------------|--------|-----------|
| CRITICAL | 3 | 3 | **0** |
| HIGH | 7 | 3 | **4** |
| MEDIUM | 8 | 3 | **5** |
| LOW | 5 | 2 | **3** |
| **Total** | **23** | **11** | **12** |

**New findings identified in re-audit**: 3

| Severity | New | Carried | Total Open |
|----------|-----|---------|------------|
| CRITICAL | 0 | 0 | **0** |
| HIGH | 1 | 3 | **4** |
| MEDIUM | 2 | 5 | **7** |
| LOW | 0 | 3 | **3** |
| **Total** | **3** | **11** | **14** |

---

## CRITICAL Findings

All three original CRITICAL findings have been remediated.

### [CRITICAL] PII-001: CLOSED

**Original**: L1 Filter name misleading; conflated context blocking with PII scrubbing.
**Remediation**: Renamed to `CaptureContextFilter` in `/Users/proth/repos/kmflow/agent/macos/Sources/PII/CaptureContextFilter.swift`. The whitepaper now distinguishes "L1 -- Capture Prevention" (context blocking) from "L2 -- Regex Scrubbing" (PII content filtering). The data flow diagram labels L1 as preventing capture rather than filtering PII content.
**Verification**: CaptureContextFilter.swift lines 1-11 correctly describe the struct as a "context-blocking filter" that "determines WHETHER to capture, not WHAT to redact."

### [CRITICAL] PII-002: CLOSED

**Original**: WelcomeView claimed "All data is encrypted"; whitepaper claimed AES-256-GCM was implemented.
**Remediation**: WelcomeView line 72 now reads: "Data is transmitted securely and PII is automatically redacted" -- which is accurate (TLS in transit, L2 PII scrubbing). Whitepaper Sec. 5 heading now reads "AES-256-GCM (Planned -- Not Yet Implemented)" with a status box stating the buffer is plaintext. The "Data States Summary" table (Sec. 3) now reads "Plaintext SQLite (AES-256-GCM encryption planned)" for local storage.
**Verification**: WelcomeView.swift line 72 confirmed; whitepaper Sec. 5 header and table confirmed at lines 228-242.

### [CRITICAL] PII-003: CLOSED

**Original**: L3 and L4 PII layers claimed as implemented in whitepaper, DPA, and PIA.
**Remediation**: Whitepaper Sec. 4 subsections for L3 and L4 now carry bold "NOT YET IMPLEMENTED" headers (lines 212-222). The DPA Sec. 7.3 now includes the parenthetical "Additional layers (L3 ML-based NER and L4 human quarantine review) are planned for a future phase and are not yet implemented" (line 176). The PIA risk matrix R1 and mitigation table explicitly state L3/L4 are planned only (lines 195, 222-223).
**Verification**: All three documents confirmed.

---

## HIGH Findings (4 Open)

### [HIGH] CONSENT-001: Consent Not Granular Per Data Type -- GDPR Non-Compliance (OPEN)

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/Onboarding/ConsentView.swift:74-93`
**Status**: OPEN -- No remediation applied.
**Evidence**:
```swift
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
**Analysis**: The three consent checkboxes remain bundled acknowledgments. All must be checked to proceed (`canAdvance` at OnboardingState.swift line 115-117 requires `allConsentChecked`). Users cannot consent to app-switch monitoring while declining window title capture, or consent to activity counts while declining idle time tracking. The EDPB Guidelines on Consent (WP259 rev.01) require granularity when processing serves multiple purposes or involves distinct data categories.
**Risk**: If consent is the legal basis (GDPR Art. 6(1)(a)), bundled consent is not "freely given" under Art. 7. This is mitigated when legitimate interest is the legal basis, but the consent flow is presented as if consent is being collected, which creates confusion about the legal basis.
**Recommendation**: Either make consent granular (separate toggles for window title capture, input counts, idle tracking) or clearly label the checkboxes as "acknowledgments" rather than "consent" to avoid conflation with GDPR Art. 6(1)(a) consent.

---

### [HIGH] CONSENT-003: No "Withdraw Consent" Button in Menu Bar (PARTIALLY REMEDIATED)

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/StatusBarController.swift:61-133`
**Status**: PARTIAL -- Backend handler wired; UI path still missing.
**Evidence**:
```swift
    // Menu items available:
    // - "Pause Capture" / "Resume Capture"
    // - "What's Being Captured"
    // - "Transparency Log"
    // - "Preferences..."
    // - "Quit KMFlow Agent"
    // NO "Withdraw Consent" or "Revoke Consent" item exists.
```
**Progress**: `ConsentManager.onRevocation()` (line 40 of ConsentManager.swift) and `revokeConsent()` (lines 56-62) now correctly notify registered handlers, enabling cleanup on revocation. The `ConsentRevocationHandler` type alias (line 23) documents that implementors should "stop capture, delete local buffer, disconnect IPC."
**Remaining Gap**: There is no UI path for the user to trigger `revokeConsent()`. The `buildMenu()` method in StatusBarController.swift does not include a "Withdraw Consent" menu item. The legal footer in ConsentView.swift line 102 still states "You can revoke consent at any time from the menu bar icon" -- which is false because no such menu item exists. "Quit" does not invoke `revokeConsent()`; it calls `stateManager.stopCapture()` (KMFlowAgentApp.swift line 90).
**Risk**: GDPR Art. 7(3) requires withdrawal to be "as easy" as granting consent. Users were told withdrawal is available from the menu bar but it is not.
**Recommendation**: Add a "Withdraw Consent" menu item to `buildMenu()` that calls `ConsentManager.revokeConsent()`. The item should be visible whenever the agent is in `.capturing` or `.paused` state. On selection: confirm with the user, invoke revocation handlers, delete the local buffer, and show a confirmation dialog.

---

### [HIGH] TRANSPARENCY-001: Transparency Log Cannot Show Upload Status (OPEN)

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogView.swift:96-109`
**Status**: OPEN -- No remediation applied.
**Evidence**:
```swift
    private var footer: some View {
        HStack {
            Image(systemName: "lock.shield")
            Text("All data shown is local to this device. PII patterns have been redacted.")
            Spacer()
        }
    }
```
**Analysis**: The transparency log reads from `buffer.db` and displays up to 200 events (line 115) with no pagination. There is no "uploaded" vs. "pending" status column. The footer states data is "local to this device" but does not tell the user which events have been sent to the server. Under GDPR Art. 15, data subjects have the right to know what data has been transmitted to third parties.
**Risk**: Users cannot verify what was sent to the backend. The 200-event cap may hide relevant data. No deletion controls exist.
**Recommendation**: (1) Add an `uploaded_at` column or flag to events. (2) Display upload status per event row. (3) Add pagination or infinite scroll. (4) Consider a "Data Sent Summary" section showing total events uploaded, date range, and volume.

---

### [HIGH] NEW-001: HMAC Key Fallback to UUID Weakens Consent Tamper Detection

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:239-242`
**Evidence**:
```swift
    private func loadOrCreateHMACKey() -> Data {
        if let existing = keychainLoad(account: hmacKeyAccount) {
            return existing
        }
        // Generate a 256-bit random key
        var key = Data(count: 32)
        let result = key.withUnsafeMutableBytes { ptr in
            SecRandomCopyBytes(kSecRandomDefault, 32, ptr.baseAddress!)
        }
        if result != errSecSuccess {
            // Fallback: use a UUID-based key (weaker but functional)
            key = Data(UUID().uuidString.utf8)
        }
        keychainSave(account: hmacKeyAccount, data: key)
        return key
    }
```
**Description**: The HMAC signing key for consent record tamper detection falls back to `UUID().uuidString` (36 bytes of hex characters, approximately 122 bits of entropy) when `SecRandomCopyBytes` fails. While `SecRandomCopyBytes` failure is extremely rare (it requires a kernel entropy pool exhaustion), the fallback is weaker than the intended 256-bit key. More critically, the UUID-based key is predictable if the attacker knows the UUID generation time, as `UUID()` on Apple platforms uses UUIDv4 which relies on the same `SecRandomCopyBytes` that just failed -- meaning the fallback may also produce a weak key.
**Risk**: If `SecRandomCopyBytes` fails and the UUID fallback produces a predictable key, an attacker with local access could forge consent records, making it appear that consent was granted when it was not. The HMAC is the only tamper-detection mechanism for consent records in the Keychain.
**Recommendation**: If `SecRandomCopyBytes` fails, refuse to create the HMAC key and return an error state rather than falling back to a weaker key. A consent record without tamper protection is safer than one with a false sense of tamper protection. Log the `SecRandomCopyBytes` failure as a security event.

---

## MEDIUM Findings (7 Open)

### [MEDIUM] PII-008: Idle Detection Timing Reveals Personal Patterns (OPEN)

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/IdleDetector.swift:8-41`
**Status**: OPEN -- No remediation applied.
**Analysis**: `IdleDetector` emits `.idleStart` and `.idleEnd` transitions with `Date()` precision. With a 300-second (5-minute) default timeout, every bathroom break, personal phone call, or impromptu meeting is recorded with second-level precision. Over a multi-week engagement, this creates a behavioral fingerprint.
**Risk**: Proportionality concern under GDPR Art. 5(1)(c). Idle patterns could be used for individual performance evaluation, contrary to the stated purpose.
**Recommendation**: Reduce granularity to 15-minute bins, or emit idle durations rather than exact start/end timestamps.

---

### [MEDIUM] CONSENT-004: MDM Can Pre-Configure Engagement Without Employee Knowledge (OPEN)

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/KMFlowAgentApp.swift:62-70`
**Status**: OPEN -- No remediation applied.
**Analysis**: `AgentConfig.init?(fromMDMProfile:)` reads `CapturePolicy`, `ScreenshotEnabled`, `AppAllowlist`, and other values from MDM managed preferences. The onboarding wizard does not display these values. An MDM admin could set `ScreenshotEnabled: true` without the employee knowing.
**Risk**: Consent is not fully informed if the employee does not see the MDM-configured parameters.
**Recommendation**: Display MDM-configured values in the consent flow, especially `ScreenshotEnabled` and `CapturePolicy`.

---

### [MEDIUM] DATA-001: Uninstall Script Missing UserDefaults Plist (PARTIALLY REMEDIATED)

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/uninstall.sh`
**Status**: PARTIAL -- Script now removes Keychain items and shared data, but still omits:
- `~/Library/Preferences/com.kmflow.agent.plist` (UserDefaults standard suite)
- `~/Library/HTTPStorages/com.kmflow.agent/` (URL session storage)
- `~/Library/Caches/com.kmflow.agent/` (if any cache exists)
**Risk**: UserDefaults plist may contain engagement ID, backend URL, and other metadata revealing that the employee was monitored.
**Recommendation**: Add removal of Preferences plist and HTTPStorages directory.

---

### [MEDIUM] DATA-002: No Backend Data Deletion Mechanism Accessible to Users (OPEN)

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogView.swift:1-7`
**Status**: OPEN -- No remediation applied.
**Analysis**: The transparency log explicitly states "It deliberately offers no editing or deletion controls" (comment line 6). The DPA Article 7.5 assigns deletion to a manual process (5 business days), but no in-app mechanism exists. No data protection contact is displayed.
**Risk**: GDPR Art. 17 right to erasure requires practical means of exercising the right.
**Recommendation**: Add a "Request Data Deletion" option in the menu bar or transparency log footer.

---

### [MEDIUM] DATA-003: No Local Data Retention Limit by Age (OPEN)

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogController.swift:67-73`
**Status**: OPEN -- No remediation applied.
**Analysis**: The whitepaper states a 100 MB FIFO cap, but there is no age-based retention limit in the Swift layer. If the Python process crashes or the device is offline for weeks, data accumulates on-device indefinitely within the size cap.
**Risk**: GDPR Art. 5(1)(e) storage limitation principle violated if data persists locally beyond its useful life.
**Recommendation**: Add a time-based retention limit (7 days) in the Swift capture layer.

---

### [MEDIUM] NEW-002: KeychainConsentStore HMAC Verification Failure Logged with Engagement ID

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:94`
**Evidence**:
```swift
    guard signed.hmac == expectedHmac else {
        // HMAC mismatch -- record may have been tampered with
        fputs("[KeychainConsentStore] HMAC verification failed for engagement \(engagementId)\n", stderr)
        return .neverConsented
    }
```
**Description**: When HMAC verification fails (indicating potential consent record tampering), the engagement ID is written to stderr. While the `AgentLogger` wrapper correctly uses `privacy: .private` for all log levels (Logger.swift lines 13-27), this `fputs` call bypasses the logger entirely and writes the engagement ID to stderr in plaintext. The engagement ID could be considered organizational metadata that should not appear in system logs accessible to other processes.
**Risk**: The engagement ID in stderr could be captured by system-level log aggregation tools or crash reporters, potentially revealing the engagement relationship to unintended parties. Low-to-medium severity because the engagement ID alone is not PII, but it links the device to a specific consulting engagement.
**Recommendation**: Replace the `fputs` call with `AgentLogger` to ensure privacy annotations are applied consistently. Similarly, the `fputs` at line 180 (SecItemAdd failure) should use the logger.

---

### [MEDIUM] NEW-003: TransparencyLogController Buffer Encryption Key Also Serves as Provisioning Endpoint

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogController.swift:244-269`
**Evidence**:
```swift
    @discardableResult
    public func provisionEncryptionKey() -> Data? {
        // Don't overwrite an existing key
        if let existing = loadBufferKeyFromKeychain() {
            return existing
        }
        // Generate 256-bit random key
        var keyData = Data(count: 32)
        let result = keyData.withUnsafeMutableBytes { ptr in
            SecRandomCopyBytes(kSecRandomDefault, 32, ptr.baseAddress!)
        }
        guard result == errSecSuccess else { return nil }
        // ... saves to Keychain
    }
```
**Description**: The `TransparencyLogController` -- a UI controller -- contains a `public` method `provisionEncryptionKey()` that generates and stores a 256-bit AES key in the Keychain. This is a security-sensitive operation (cryptographic key provisioning) exposed as a public API on a view controller. Any code that instantiates `TransparencyLogController` can call this method. The comment block at the top of the file states the controller opens a "read-only" SQLite connection, but it also provisions encryption keys, which is a write operation to the Keychain and a violation of the stated read-only contract.
**Risk**: Key provisioning should be performed by a dedicated security module with controlled access, not by a UI controller that is instantiated whenever the transparency log window opens. If `provisionEncryptionKey()` is called multiple times by different code paths, the "don't overwrite" guard prevents duplication, but the architectural placement is inappropriate for a security-sensitive operation.
**Recommendation**: Move `provisionEncryptionKey()` to a dedicated `BufferEncryptionManager` or the existing `KeychainHelper` module. The `TransparencyLogController` should only read the key, never provision it.

---

## LOW Findings (3 Open)

### [LOW] PII-009: Private Browsing Detection Missing Brave and Vivaldi (PARTIALLY REMEDIATED)

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/PII/CaptureContextFilter.swift:56-92`
**Status**: PARTIAL -- Arc (`company.thebrowser.Browser`) and Edge (`com.microsoft.edgemac`) added. Brave (`com.brave.Browser`), Vivaldi (`com.vivaldi.Vivaldi`), and Opera (`com.operasoftware.Opera`) still missing. Non-English localizations remain undetected.
**Recommendation**: Add Brave, Vivaldi, and Opera. Consider a generic case-insensitive check for "private" or "incognito" in window titles across all browsers.

---

### [LOW] CONSENT-005: Consent Version Hardcoded to "1.0" (OPEN)

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:120`
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
**Analysis**: `consentVersion` is still hardcoded to "1.0". Additionally, `authorizedBy` and `captureScope` are still hardcoded to `nil`, meaning the onboarding flow's "Authorized By" text field and scope selection are discarded when the consent record is persisted. While the scope picker was disabled in the UI (CONSENT-002 fix), the `authorizedBy` field is still collected in the UI but never stored.
**Risk**: No mechanism to trigger re-consent when the consent text or data collection scope changes. The `authorizedBy` field collected from the user is silently discarded.
**Recommendation**: (1) Define a `CURRENT_CONSENT_VERSION` constant. (2) Compare stored version at launch. (3) Pass `authorizedBy` from onboarding state through to the consent store.

---

### [LOW] TRANSPARENCY-002: Transparency Log Shows Post-Filter Data Only (OPEN)

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogView.swift`
**Status**: OPEN -- No change. Users see `[PII_REDACTED]` tokens but cannot determine what was redacted or why.
**Recommendation**: Add a "Redaction reason" annotation (e.g., "matched: email pattern") so users understand why data was redacted.

---

## Verified Positive Controls

The following controls were verified as correctly implemented during this re-audit:

| Control | File | Verification |
|---------|------|-------------|
| L2 PII regex scrubbing (8 patterns) | `WindowTitleCapture.swift:14-88` | SSN, email, phone, credit card, AmEx, IBAN, file paths, UK NINO all implemented with compiled regex and `assert` on compilation failure |
| Window title truncation | `WindowTitleCapture.swift:93,108-109` | `maxTitleLength = 512`; titles truncated before L2 scrub |
| Private browsing suppression | `CaptureContextFilter.swift:56-92` | Safari, Chrome, Firefox, Arc, Edge covered |
| Password field blocking | `CaptureContextFilter.swift:32-34` | `isSecureTextField()` check on `AccessibilityProvider` |
| Password manager blocklist | `CaptureContextFilter.swift:43-51` | 1Password (both IDs), LastPass, Bitwarden, Dashlane, Keychain Access |
| Nil bundleId blocked | `BlocklistManager.swift:34` | `guard let bid = bundleId else { return false }` -- deny by default |
| Logger privacy annotations | `Logger.swift:13-27` | All four log levels use `privacy: .private` |
| Input events count-only | `InputMonitor.swift:16-23` | No x/y coordinates; only timestamps and button type |
| Consent revocation handler | `ConsentManager.swift:40-42,56-62` | `onRevocation()` registration; `revokeConsent()` iterates handlers |
| Consent HMAC tamper detection | `KeychainConsentStore.swift:89-96,213-227` | HMAC-SHA256 with per-install 256-bit Keychain key |
| IPC symlink protection | `SocketClient.swift:41-49` | `lstat` check rejects symlinked socket paths |
| IPC auth handshake | `SocketClient.swift:84-96` | Shared secret sent as JSON to prevent injection |
| Capture state gating | `CaptureStateManager.swift:96-98` | `isCapturePermitted` enforces per-event consent check |
| Keychain sync disabled | `KeychainConsentStore.swift:174` | `kSecAttrSynchronizable: kCFBooleanFalse` prevents iCloud sync |
| MDM config value clamping | `AgentConfig.swift:59-78` | All numeric MDM values clamped to safe ranges |
| SQLite read-only for transparency | `TransparencyLogController.swift:118` | `SQLITE_OPEN_READONLY` flag prevents corruption |
| Whitepaper accuracy (post-remediation) | `task-mining-agent-security-whitepaper.md` | L3/L4 marked "NOT YET IMPLEMENTED"; encryption marked "Planned"; socket path corrected; paths reconciled |
| DPA accuracy (post-remediation) | `task-mining-agent-dpa-template.md:174-177` | Disclaimers on L3/L4 and encryption status |
| PIA accuracy (post-remediation) | `task-mining-agent-pia-template.md:195,222-224` | Risk matrix and mitigation table updated |

---

## Regulatory Compliance Gap Summary (Updated)

### GDPR Compliance Status

| Article | Requirement | Status (Original) | Status (Re-Audit) | Open Finding(s) |
|---------|------------|-------------------|--------------------|-----------------|
| Art. 5(1)(a) | Lawfulness, fairness, transparency | PARTIAL | **IMPROVED** | CONSENT-002 closed (scope picker disabled). CONSENT-003 still partial (no withdrawal UI). |
| Art. 5(1)(c) | Data minimization | PARTIAL | **IMPROVED** | PII-007 closed (no coordinates). PII-006 partial (512-char titles still captured in action_level). |
| Art. 5(1)(e) | Storage limitation | PARTIAL | **PARTIAL** | DATA-003 open (no age-based retention). |
| Art. 7 | Conditions for consent | NON-COMPLIANT | **PARTIAL** | CONSENT-001 open (not granular). CONSENT-003 partial (revocation handler exists but no UI). |
| Art. 13-14 | Transparency | PARTIAL | **IMPROVED** | PII-001 closed. TRANSPARENCY-001 open (no upload status). |
| Art. 17 | Right to erasure | NON-COMPLIANT | **NON-COMPLIANT** | DATA-002 open (no deletion mechanism). |
| Art. 25 | Data protection by design | PARTIAL | **IMPROVED** | PII-002 closed (accurate documentation). CONSENT-002 closed. |
| Art. 32 | Security of processing | NON-COMPLIANT | **IMPROVED** | Documentation now accurately reflects plaintext buffer status. Encryption still not implemented but no longer falsely claimed. Compliance gap shifts from "misrepresentation" to "planned control." |
| Art. 35 | DPIA | COMPLIANT | **COMPLIANT** | PIA template accurate post-remediation. |

### Whitepaper vs. Reality Discrepancies (Updated)

| Whitepaper Claim | Reality | Status |
|-----------------|---------|--------|
| "Two-layer on-device PII architecture (L1+L2)" | L1 context blocking + L2 regex scrubbing -- accurately described | **ACCURATE** |
| "L3 ML NER and L4 human review planned" | Not implemented; clearly marked as planned | **ACCURATE** |
| "AES-256-GCM planned, currently plaintext" | Buffer is plaintext; accurately stated | **ACCURATE** |
| "TLS 1.3 in transit" | Correct | **ACCURATE** |
| "No keystroke logging" | Correct -- InputMonitor captures counts only | **ACCURATE** |
| "User-controlled pause" | Pause exists via menu bar | **ACCURATE** |
| "Consent withdrawal via menu bar" | ConsentView footer claims this; menu bar lacks the item | **INACCURATE** |
| "Transparency log shows captured data" | Shows last 200 events; no upload status | **PARTIAL** |
| Socket path | `~/Library/Application Support/KMFlowAgent/agent.sock` | **ACCURATE** |
| App/path naming | Reconciled to "KMFlow Agent" / "KMFlowAgent" | **ACCURATE** |
| L2 patterns | SSN, email, phone, CC, AmEx, IBAN, file paths, UK NINO | **ACCURATE** |

---

## Recommendations Priority Matrix (Updated)

| Priority | Finding | Effort | Impact | Status |
|----------|---------|--------|--------|--------|
| ~~P0~~ | ~~PII-002: Correct whitepaper claims~~ | ~~Low~~ | ~~Eliminates misrepresentation~~ | **DONE** |
| ~~P0~~ | ~~PII-003: Add L3/L4 disclaimers~~ | ~~Low~~ | ~~Corrects compliance docs~~ | **DONE** |
| P0 (Block deployment) | CONSENT-003: Add consent withdrawal UI in menu bar | Medium | GDPR Art. 7(3) compliance | **IN PROGRESS** -- handler wired, UI missing |
| P1 (Before production) | CONSENT-001: Make consent granular or relabel as acknowledgment | Medium | GDPR consent validity | OPEN |
| P1 (Before production) | TRANSPARENCY-001: Add upload status to transparency log | Medium | GDPR Art. 15 compliance | OPEN |
| P1 (Before production) | DATA-002: Add deletion request mechanism | Medium | GDPR Art. 17 compliance | OPEN |
| P1 (Before production) | NEW-001: Remove HMAC UUID fallback | Low | Prevents weak tamper detection | NEW |
| P2 (Near-term) | PII-006: Suppress window titles in action_level mode | Medium | Data minimization | PARTIAL |
| P2 (Near-term) | CONSENT-004: Display MDM config in consent flow | Medium | Informed consent | OPEN |
| P2 (Near-term) | DATA-003: Add age-based local retention | Low | Storage limitation compliance | OPEN |
| P2 (Near-term) | NEW-002: Route fputs through AgentLogger | Low | Consistent privacy logging | NEW |
| P2 (Near-term) | NEW-003: Move key provisioning out of UI controller | Medium | Architectural separation | NEW |
| P3 (Backlog) | PII-008, PII-009, CONSENT-005, TRANSPARENCY-002, DATA-001 | Various | Defense in depth | OPEN |

---

## Security Score

| Category | Score (Original) | Score (Re-Audit) | Max |
|----------|-----------------|-------------------|-----|
| PII Protection (L1+L2) | 5/10 | **8/10** | 10 |
| Encryption at Rest | 1/10 | **2/10** (documentation now accurate; encryption still absent) | 10 |
| Encryption in Transit | 8/10 | **8/10** | 10 |
| Consent Model | 3/10 | **5/10** | 10 |
| Transparency | 4/10 | **5/10** | 10 |
| Data Minimization | 4/10 | **6/10** | 10 |
| Documentation Accuracy | 2/10 | **9/10** | 10 |
| Uninstall / Data Cleanup | 5/10 | **6/10** | 10 |
| **Overall** | **32/80 (40%)** | **49/80 (61%)** | 80 |

---

## Executive Summary

The Phase 1-3 remediation effort addressed all three CRITICAL findings and approximately half of the total findings. The most significant improvements are:

1. **Documentation accuracy is now strong.** The whitepaper, DPA, and PIA no longer misrepresent unimplemented controls as active. This was the highest-risk issue in the original audit and it is fully resolved.

2. **PII filtering coverage expanded materially.** L2 now covers 8 pattern types (up from 5), including IBAN, file paths, and UK NINO. Window titles are truncated. Mouse coordinates removed from input events.

3. **Consent revocation infrastructure is in place** but the user-facing path is incomplete. The `onRevocation()` handler pattern is well-designed and the revocation logic is correct, but no menu item triggers it.

4. **Logger privacy annotations are consistently applied** across the `AgentLogger` wrapper. The remaining gap is two `fputs` calls in `KeychainConsentStore` that bypass the logger.

The remaining deployment-blocking issue is **CONSENT-003**: the absence of a consent withdrawal UI path. The ConsentView footer promises withdrawal from the menu bar, but no such menu item exists. This is a GDPR Art. 7(3) compliance gap that should be closed before any deployment where consent is the legal basis.

The four HIGH findings and seven MEDIUM findings represent genuine but non-critical gaps. They should be addressed before production deployment but do not represent material misrepresentations (which was the core issue in the original audit).
