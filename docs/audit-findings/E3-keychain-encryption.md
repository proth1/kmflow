# E3: Keychain & Encryption Audit — KMFlow macOS Task Mining Agent

**Auditor**: E3 (Keychain & Encryption Auditor)
**Date**: 2026-02-25
**Scope**: All Swift source files in `agent/macos/Sources/`, entitlements, and installer scripts
**Status**: COMPLETE

## Executive Summary

The KMFlow macOS Task Mining Agent handles employee behavioral data (application usage, window titles, input patterns) and stores consent tokens in the macOS Keychain. This audit evaluates the cryptographic controls, Keychain configuration, IPC channel security, and data lifecycle management.

**The agent's trust model has significant gaps.** While the Keychain is used for consent storage (good), the primary data channel -- the SQLite capture buffer where all behavioral data resides -- has **no encryption implemented**. The code contains scaffolding for future encryption but currently reads and writes plaintext. The IPC channel between Swift and Python has no authentication or encryption. The `KeychainHelper` utility (used for general secrets) is missing the `kSecAttrAccessible` attribute entirely, defaulting to an overly permissive accessibility level. Consent tokens are stored as unsigned JSON, making forgery trivial for any process with Keychain access.

## Finding Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2     |
| HIGH     | 5     |
| MEDIUM   | 5     |
| LOW      | 3     |
| **Total** | **15** |

---

## CRITICAL Findings

### [CRITICAL] DATA-AT-REST-001: SQLite Capture Buffer Stored in Plaintext

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogController.swift:109-113`
**Agent**: E3 (Keychain & Encryption Auditor)
**Evidence**:
```swift
        // Load the buffer encryption key from Keychain (for future use when
        // the Python layer encrypts individual columns).  We retrieve it here
        // so the controller wires the full security contract even if decryption
        // is a no-op for plaintext rows today.
        _ = loadBufferKeyFromKeychain()
```
**Description**: The comments in TransparencyLogController explicitly state that encryption is "a no-op for plaintext rows today." The SQLite database at `~/Library/Application Support/KMFlowAgent/buffer.db` stores all captured behavioral data -- application names, window titles, timestamps, input patterns -- in cleartext. The `loadBufferKeyFromKeychain()` method retrieves a key but never uses it for decryption. The SQL query at line 125 reads raw columns directly with no decryption step.

Additionally, the onboarding wizard at `WelcomeView.swift:72` tells employees:
```swift
                text: "All data is encrypted and PII is automatically redacted"
```
This claim is false for data at rest. Employees are being told their data is encrypted when it is not.

**Risk**: Any process running as the same user can open and read the SQLite database. This includes malware, other employee-installed applications, or anyone with physical access to the machine. The false encryption claim in the onboarding UI creates a trust violation with employees who consented under the belief their data was encrypted. This could create legal liability under GDPR, CCPA, and similar privacy regulations where consent must be informed.

**Recommendation**:
1. Implement AES-256-GCM column-level encryption using CryptoKit `AES.GCM.SealedBox` before any production deployment.
2. Store the symmetric key in Keychain with `kSecAttrAccessControl` biometric protection.
3. Correct the WelcomeView claim to accurately reflect current encryption status, or implement encryption before shipping.
4. Use per-row nonces (provided automatically by `AES.GCM.seal()`).

---

### [CRITICAL] IPC-001: Unix Domain Socket Has No Authentication or Encryption

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/IPC/SocketClient.swift:10-13, 29-63`
**Agent**: E3 (Keychain & Encryption Auditor)
**Evidence**:
```swift
    public static let defaultSocketPath: String = {
        let home = NSHomeDirectory()
        return "\(home)/Library/Application Support/KMFlowAgent/agent.sock"
    }()
```
```swift
    public func connect() throws {
        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else {
            throw SocketError.connectionFailed("Failed to create socket: \(errno)")
        }
        // ... direct connect with no authentication handshake ...
```
**Description**: The Unix domain socket used to transmit all captured behavioral events from Swift to Python has three compounding security weaknesses:

1. **No authentication**: Any process running as the same user can connect to the socket and either inject fabricated events or eavesdrop. There is no challenge-response, shared secret, or peer credential check (`SO_PEERCRED` / `LOCAL_PEERCRED`).

2. **No encryption**: Data flows as plaintext ndjson over the socket. Window titles, application names, and all event data are readable by any local process that connects.

3. **No pre-existence check**: The `connect()` method does not verify whether the socket file already exists before connecting, nor does the server-side (Python) validate socket ownership. This opens a symlink attack vector where an attacker replaces `agent.sock` with a symlink to a controlled socket, intercepting all behavioral data.

**Risk**: A malicious or compromised process running as the same user could: (a) passively sniff all employee activity data, (b) inject fake events to manipulate process mining results, or (c) perform a symlink race to redirect the data stream. While the `postinstall` script sets the Application Support directory to `0700`, this only protects against other users, not same-user processes.

**Recommendation**:
1. Verify peer credentials using `getsockopt(fd, SOL_LOCAL, LOCAL_PEERCRED)` to confirm the connecting/connected process is the expected KMFlow binary.
2. Check for pre-existing socket files before binding (server-side) and validate the socket file is not a symlink before connecting (client-side).
3. Implement a shared-secret handshake using a Keychain-stored token exchanged at connection time.
4. Consider TLS over the Unix socket for defense-in-depth if content-level capture is enabled.

---

## HIGH Findings

### [HIGH] KEYCHAIN-001: KeychainHelper Missing kSecAttrAccessible — Defaults to kSecAttrAccessibleWhenUnlocked

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Utilities/KeychainHelper.swift:14-29`
**Agent**: E3 (Keychain & Encryption Auditor)
**Evidence**:
```swift
    public func save(key: String, data: Data) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
        ]
        // Delete existing item first
        SecItemDelete(query as CFDictionary)

        let status = SecItemAdd(query as CFDictionary, nil)
```
**Description**: Unlike `KeychainConsentStore` which explicitly sets `kSecAttrAccessibleAfterFirstUnlock`, the general-purpose `KeychainHelper` does not set any `kSecAttrAccessible` attribute. When omitted, macOS defaults to `kSecAttrAccessibleWhenUnlocked`. However, the inconsistency between the two Keychain implementations is a design defect -- the buffer encryption key (stored via the `com.kmflow.agent` service used by `KeychainHelper`) and consent records (stored via `com.kmflow.agent.consent`) have different protection levels. Neither implementation uses `kSecAttrAccessControl` with biometric or password protection, meaning any process running as the user can read all Keychain items without user interaction.

**Risk**: The buffer encryption key (when eventually implemented) and any other agent secrets stored via `KeychainHelper` can be read by any process running as the current user without requiring user authentication. Malware or a compromised application could silently extract the encryption key and decrypt the capture buffer.

**Recommendation**:
1. Add `kSecAttrAccessible: kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly` for maximum protection.
2. Add `kSecAttrAccessControl` with `SecAccessControlCreateWithFlags` using `.userPresence` or `.biometryCurrentSet` to require biometric/password confirmation for key access.
3. Standardize accessibility settings across both `KeychainHelper` and `KeychainConsentStore`.

---

### [HIGH] CONSENT-001: Consent Token Is Unsigned — Forgery by Any Local Process

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:85-96`
**Agent**: E3 (Keychain & Encryption Auditor)
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
        guard let data = try? jsonEncoder().encode(record) else { return }
        keychainSave(account: accountKey(for: engagementId), data: data)
    }
```
**Description**: Consent records are stored as plain JSON in the Keychain. There is no HMAC signature, no cryptographic binding to the device or user identity, and no integrity verification on load. The `authorizedBy` field is always set to `nil` even though the onboarding wizard collects this information. The consent version is hardcoded to `"1.0"`. Any process with Keychain access to the `com.kmflow.agent.consent` service can write a forged consent record to make it appear that consent was granted, or revert a revocation.

**Risk**: An administrator or malicious script could forge a consent record to enable monitoring without the employee's actual consent. Conversely, an employee could forge a revocation to stop monitoring while appearing to have revoked consent legitimately. Without cryptographic integrity (e.g., HMAC over the record contents with a server-held key), the consent audit trail is untrustworthy.

**Recommendation**:
1. Sign consent records with an HMAC using a key derived from the backend server (provisioned during onboarding).
2. Include the `authorizedBy` field from the onboarding wizard in the stored record.
3. Verify the HMAC on every `load()` call; treat tampered records as `neverConsented`.
4. Consider a server-side consent attestation where the backend countersigns the consent record.

---

### [HIGH] CONSENT-002: No Data Cleanup on Consent Revocation

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/ConsentManager.swift:39-43`
**Agent**: E3 (Keychain & Encryption Auditor)
**Evidence**:
```swift
    /// Revoke consent. Capture must stop immediately.
    public func revokeConsent() {
        state = .revoked
        store.save(engagementId: engagementId, state: .revoked, at: Date())
    }
```
**Description**: When consent is revoked, `ConsentManager.revokeConsent()` only updates the consent state in the Keychain. It does not:
- Delete or securely wipe the SQLite capture buffer (`buffer.db`)
- Remove the buffer encryption key from Keychain
- Close the IPC socket connection
- Terminate the Python subprocess
- Clean up temporary files in Application Support

The `KMFlowAgentApp.swift` does not observe consent state changes after startup -- it checks consent once during `applicationDidFinishLaunching` and never re-checks. There is no reactive mechanism to stop capture when consent is revoked at runtime.

**Risk**: After an employee revokes consent, all previously captured behavioral data remains on disk in plaintext. The agent may continue capturing data because there is no runtime consent enforcement. This violates the GDPR "right to erasure" and the trust promise made during onboarding ("You can revoke consent at any time from the menu bar icon").

**Recommendation**:
1. Implement `revokeConsent()` to trigger immediate data deletion: remove `buffer.db`, purge Keychain encryption keys, close socket, terminate Python subprocess.
2. Add a Combine subscription in `KMFlowAgentApp` to observe `ConsentManager.state` changes and react in real-time.
3. Implement secure file deletion (overwrite before unlink) for the SQLite database.
4. Provide the employee with confirmation that all local data has been destroyed.

---

### [HIGH] SANDBOX-001: App Sandbox Disabled — No Process-Level Isolation

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/KMFlowAgent.entitlements:24-25`
**Agent**: E3 (Keychain & Encryption Auditor)
**Evidence**:
```xml
    <key>com.apple.security.app-sandbox</key>
    <false/>
```
**Description**: The App Sandbox is explicitly disabled. While this is understandable given the agent's need for CGEventTap (Accessibility API) and broad system observation, it means there is no OS-level containment for the agent process. Combined with the absence of data-at-rest encryption and the unauthenticated IPC channel, this significantly expands the attack surface.

The hardened runtime protections are correctly configured (JIT disabled, unsigned executable memory disabled, library validation enabled), which provides some mitigation. However, without sandboxing, the agent has unrestricted filesystem access, and any vulnerability in the agent or its Python subprocess could be exploited to access arbitrary user data.

**Risk**: The unsandboxed agent runs with full user privileges. A vulnerability in the Python layer (which processes untrusted event data) could be leveraged for arbitrary file access or code execution with the user's full permissions. The `com.apple.security.files.user-selected.read-write` entitlement is also granted but serves no purpose without App Sandbox -- it is only meaningful in sandboxed apps.

**Recommendation**:
1. Document the security rationale for disabling the sandbox in an Architecture Decision Record.
2. Remove the unused `com.apple.security.files.user-selected.read-write` entitlement (it has no effect outside sandbox).
3. Implement mandatory code signing verification for the Python subprocess (the `IntegrityChecker` helps but only checks at startup).
4. Consider running the Python subprocess in a more restricted sandbox profile using `sandbox-exec` or a custom sandbox profile.

---

### [HIGH] LOGGING-001: AgentLogger Marks All Log Messages as privacy: .public

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Utilities/Logger.swift:13-27`
**Agent**: E3 (Keychain & Encryption Auditor)
**Evidence**:
```swift
    public func info(_ message: String) {
        logger.info("\(message, privacy: .public)")
    }

    public func debug(_ message: String) {
        logger.debug("\(message, privacy: .public)")
    }

    public func warning(_ message: String) {
        logger.warning("\(message, privacy: .public)")
    }

    public func error(_ message: String) {
        logger.error("\(message, privacy: .public)")
    }
```
**Description**: The `AgentLogger` wrapper marks every single log message as `privacy: .public` across all log levels (info, debug, warning, error). Apple's Unified Logging system (os_log) redacts interpolated values by default precisely to prevent sensitive data from appearing in system logs. By overriding this to `.public` on every message, any caller who passes sensitive data (window titles, engagement IDs, user names, error details containing PII) will have that data written in cleartext to the system log.

The system log is readable by:
- Any process using the `log` command or Console.app
- MDM solutions that collect diagnostic logs
- Apple's sysdiagnose bundles submitted for crash reports

This pattern is also used directly in `PythonProcessManager.swift` and `IntegrityChecker.swift` where file paths and process IDs are logged with `privacy: .public`.

**Risk**: Sensitive employee behavioral data (window titles containing document names, email subjects, URLs) could end up in the macOS Unified Log, persisting long after the agent is uninstalled. Log collection by MDM or diagnostic tools could expose this data to parties outside the agreed data-processing scope.

**Recommendation**:
1. Change the default `AgentLogger` to use `privacy: .private` (Apple's default).
2. Only use `privacy: .public` for values that are explicitly non-sensitive (error codes, counts, boolean states).
3. Create separate logging methods: `logPublic()` and `logSensitive()` to force callers to make an explicit privacy decision.
4. Audit all direct `os.Logger` usage in `PythonProcessManager.swift` and `IntegrityChecker.swift` for over-sharing.

---

## MEDIUM Findings

### [MEDIUM] KEYCHAIN-002: kSecAttrAccessibleAfterFirstUnlock Allows Background Access Without User Authentication

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:138-141`
**Agent**: E3 (Keychain & Encryption Auditor)
**Evidence**:
```swift
            kSecAttrAccessible as String:   kSecAttrAccessibleAfterFirstUnlock,
```
**Description**: The `kSecAttrAccessibleAfterFirstUnlock` accessibility level means Keychain items are available to any process after the first unlock of the device, even when the screen is locked. While this is a reasonable choice for a background agent that needs to check consent state, it offers less protection than `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly`. The consent records contain engagement IDs and consent decisions -- sensitive organizational data that should have the strongest available protection.

**Risk**: If the Mac is locked but has been unlocked at least once since boot, a process could still read consent records. This is a minor weakness given macOS Keychain's existing per-application access controls, but for enterprise monitoring data, defense-in-depth suggests a stronger setting.

**Recommendation**: For the consent records (which are only needed when the agent is actively running and the user is active), consider `kSecAttrAccessibleWhenUnlocked` combined with `kSecAttrAccessControl` requiring user presence.

---

### [MEDIUM] KEYCHAIN-003: kSecAttrSynchronizable Not Explicitly Disabled

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:133-142`
**Agent**: E3 (Keychain & Encryption Auditor)
**Evidence**:
```swift
        let addQuery: [String: Any] = [
            kSecClass as String:            kSecClassGenericPassword,
            kSecAttrService as String:      service,
            kSecAttrAccount as String:      account,
            kSecValueData as String:        data,
            kSecAttrAccessible as String:   kSecAttrAccessibleAfterFirstUnlock,
        ]
```
**Description**: Neither `KeychainConsentStore` nor `KeychainHelper` explicitly sets `kSecAttrSynchronizable` to `false`. While the default is `false` (items do not sync to iCloud Keychain), security-sensitive applications should explicitly disable it to prevent future macOS behavior changes or accidental enablement from causing consent tokens or encryption keys to sync to iCloud. This is especially important for enterprise monitoring data that must remain device-local per CISO requirements.

The same issue applies to `KeychainHelper.swift:14-28` and `TransparencyLogController.swift:221-227`.

**Risk**: If Apple changes the default behavior, or if a future code change accidentally adds `kSecAttrSynchronizable: true`, consent records and encryption keys would sync to iCloud, potentially violating data residency requirements and enterprise security policies.

**Recommendation**: Explicitly set `kSecAttrSynchronizable: kCFBooleanFalse` in all Keychain queries across `KeychainConsentStore`, `KeychainHelper`, and `TransparencyLogController`.

---

### [MEDIUM] INTEGRITY-001: Integrity Check Only Runs at Startup — Not Periodic

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/KMFlowAgentApp.swift:44-57`
**Agent**: E3 (Keychain & Encryption Auditor)
**Evidence**:
```swift
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
```
**Description**: The SHA-256 integrity verification of the Python bundle only runs once during `applicationDidFinishLaunching`. After startup, if the Python files are modified (e.g., by a post-exploitation tool replacing a Python module), the agent will continue executing the tampered code for the entire runtime of the process.

Additionally, when the manifest is missing (`.manifestMissing` case), the agent logs it as "development mode" and **continues execution**. This means a production build shipped without an integrity manifest would silently skip all integrity verification.

**Risk**: An attacker who gains write access to the app bundle after launch (or who removes `integrity.json`) can modify the Python intelligence layer to exfiltrate behavioral data, disable PII filtering, or inject false events without triggering any integrity alerts.

**Recommendation**:
1. Run integrity checks periodically (e.g., every 5 minutes) while the agent is running.
2. Treat `.manifestMissing` as a failure in release builds (use `#if DEBUG` to allow development bypass).
3. Verify the integrity manifest itself is signed (e.g., embed the manifest hash in the Swift binary at build time).
4. Consider using `SIGINFO` or `SIGUSR1` to trigger on-demand integrity checks.

---

### [MEDIUM] INTEGRITY-002: IntegrityChecker Does Not Verify Its Own Manifest Integrity

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/IntegrityChecker.swift:56-72`
**Agent**: E3 (Keychain & Encryption Auditor)
**Evidence**:
```swift
    public static func verify(bundleResourcesPath: URL) -> IntegrityResult {
        let manifestURL = bundleResourcesPath.appendingPathComponent("integrity.json")

        guard let manifestData = try? Data(contentsOf: manifestURL) else {
            log.error("integrity.json not found at \(manifestURL.path, privacy: .public)")
            return .manifestMissing
        }

        let manifest: ManifestPayload
        do {
            manifest = try JSONDecoder().decode(ManifestPayload.self, from: manifestData)
        } catch {
            log.error("Failed to decode integrity.json: \(error.localizedDescription, privacy: .public)")
            return .manifestMissing
        }
```
**Description**: The `integrity.json` manifest is the root of trust for verifying Python file integrity, but the manifest itself is not authenticated. An attacker who can modify files in the bundle can simply replace both the Python files AND the manifest with matching hashes. There is no signature verification (e.g., code signing, embedded hash in the Swift binary, or GPG signature check) on the manifest itself.

**Risk**: The integrity check provides TOCTOU (time-of-check-time-of-use) protection only against naive modifications. A sophisticated attacker will simply regenerate the manifest after modifying Python files.

**Recommendation**:
1. Embed the expected SHA-256 hash of `integrity.json` as a compile-time constant in the Swift binary.
2. Alternatively, sign `integrity.json` with a GPG key or X.509 certificate and verify the signature in `IntegrityChecker`.
3. Rely on macOS code signing as the primary integrity mechanism and use the manifest as a secondary check.

---

### [MEDIUM] CONSENT-003: Consent Checked Only at Startup — Not Enforced Per-Event

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/KMFlowAgentApp.swift:59-84`
**Agent**: E3 (Keychain & Encryption Auditor)
**Evidence**:
```swift
        let consentManager = ConsentManager(engagementId: engagementId, store: consentStore)

        if consentManager.state == .neverConsented {
            onboardingWindow = OnboardingWindow()
            onboardingWindow?.show()
            stateManager.requireConsent()
        } else if !consentManager.captureAllowed {
            stateManager.requireConsent()
        } else {
            // Consent granted — start Python subprocess
            startPythonSubprocess()
        }
```
**Description**: Consent state is loaded from the Keychain once during app launch and is not re-verified before each capture event. The `ConsentManager` instance is created as a local variable in `applicationDidFinishLaunching` and is not stored as a property or passed to the capture pipeline. The `CaptureStateManager` has a `consentRequired` state but no mechanism to transition back to it after the Python subprocess is already running.

The `AppSwitchMonitor` checks the blocklist per-event but does not check consent state. The `SocketClient.send()` method transmits events without any consent gate.

**Risk**: If consent is revoked while the agent is running (e.g., through another process writing to the Keychain, or a future UI that calls `revokeConsent()`), the agent will continue capturing and transmitting behavioral data until it is restarted. This violates the principle that consent revocation must take immediate effect.

**Recommendation**:
1. Store `ConsentManager` as a property of `AppDelegate` and pass it to the capture pipeline.
2. Check `consentManager.captureAllowed` before every `SocketClient.send()` call.
3. Subscribe to `ConsentManager.$state` using Combine and stop the Python subprocess immediately when consent changes to `.revoked`.

---

## LOW Findings

### [LOW] KEYCHAIN-004: Keychain Error Logged to stderr With No Structured Handling

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:144-148`
**Agent**: E3 (Keychain & Encryption Auditor)
**Evidence**:
```swift
        let status = SecItemAdd(addQuery as CFDictionary, nil)
        if status != errSecSuccess {
            // Non-fatal: consent will fall back to neverConsented on next load.
            // os_log is not available here without importing os; use stderr.
            fputs("[KeychainConsentStore] SecItemAdd failed: \(status)\n", stderr)
        }
```
**Description**: Keychain save failures are written to stderr using `fputs`, bypassing the structured Unified Logging system. The comment says os_log is not available because importing `os` would add a dependency, but the `OSStatus` error code is printed without any additional context (which Keychain item, what engagement). This makes debugging Keychain permission issues in production deployments difficult. More importantly, a silent failure to save consent means the agent might believe consent was stored when it was not.

**Risk**: A Keychain write failure could silently cause consent to revert to `neverConsented` on next load, which would block legitimate capture. In the opposite direction, if a revocation write fails, the old "consented" state would persist. The lack of structured logging makes it difficult for IT administrators to diagnose the issue.

**Recommendation**:
1. Import `os` and use structured logging (even if it adds a small dependency).
2. Return a `Result<Void, Error>` from `save()` so callers can react to failures.
3. Log the account name (not the data) for debugging context.

---

### [LOW] KEY-LIFECYCLE-001: No Key Rotation Mechanism

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogController.swift:54`
**Agent**: E3 (Keychain & Encryption Auditor)
**Evidence**:
```swift
    private let bufferEncryptionKeyKeychainKey = "buffer_encryption_key"
```
**Description**: The buffer encryption key (when eventually implemented) is stored under a fixed Keychain account name with no versioning or rotation mechanism. There is no code to generate a new key, re-encrypt data with the new key, or expire old keys. Key rotation is a standard cryptographic hygiene practice, especially for long-running agents that may operate for months.

**Risk**: Without key rotation, a compromised key remains valid indefinitely. If the key is leaked or the Keychain is backed up and restored, all historical and future data can be decrypted.

**Recommendation**:
1. Design key rotation into the encryption implementation from the start.
2. Use versioned key names (e.g., `buffer_encryption_key_v1`, `buffer_encryption_key_v2`).
3. Store the key version alongside each encrypted row so old data can be decrypted during a transition period.
4. Trigger rotation on engagement change or after a configurable time period.

---

### [LOW] ENTITLEMENT-001: Unused Entitlement Present

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/KMFlowAgent.entitlements:22-23`
**Agent**: E3 (Keychain & Encryption Auditor)
**Evidence**:
```xml
    <key>com.apple.security.files.user-selected.read-write</key>
    <true/>
```
**Description**: The `com.apple.security.files.user-selected.read-write` entitlement grants access to files the user has explicitly selected (e.g., via Open/Save panels). This entitlement only has meaning within the App Sandbox (`com.apple.security.app-sandbox: true`). Since the sandbox is disabled (line 25), this entitlement has no effect and should be removed to minimize the entitlement surface.

**Risk**: Minimal direct risk since the entitlement is non-functional. However, unnecessary entitlements clutter the security review and may confuse auditors or Apple's notarization review.

**Recommendation**: Remove the `com.apple.security.files.user-selected.read-write` entitlement since it serves no purpose with sandbox disabled.

---

## Positive Observations

The following security-positive patterns were identified:

1. **Hardened Runtime correctly configured**: JIT, unsigned executable memory, and library validation are all correctly restricted in the entitlements file.

2. **Consent-first architecture**: The agent requires explicit consent before starting the Python subprocess and will not capture data in the `neverConsented` or `revoked` states (at startup).

3. **L1/L2 PII filtering**: A two-layer PII filtering approach (L1 blocks password fields and password managers at the capture level; L2 scrubs SSN, email, phone, credit card patterns from window titles) is well-structured.

4. **Private browsing detection**: The agent correctly suppresses window titles from Safari Private Browsing, Chrome Incognito, Firefox Private Browsing, Arc Incognito, and Edge InPrivate modes.

5. **Python integrity verification**: SHA-256 manifest verification of the Python bundle at startup is a good defense-in-depth measure, despite the weaknesses noted above.

6. **Application Support directory permissions**: The postinstall script correctly creates `~/Library/Application Support/KMFlowAgent/` with `0700` permissions, restricting access to the owning user.

7. **Keychain service namespacing**: Using separate services (`com.kmflow.agent` and `com.kmflow.agent.consent`) for different types of secrets is good practice that enables independent auditing and targeted cleanup.

8. **Comprehensive uninstaller**: The `uninstall.sh` script correctly removes all artifacts including Keychain items for both service names, Application Support data, logs, and the LaunchAgent plist.

9. **Sendable conformance**: Proper use of Swift's `Sendable` protocol and actor isolation for thread safety.

---

## Risk Assessment

| Category | Score (1-10) | Notes |
|----------|:---:|-------|
| Keychain Configuration | 5/10 | Good use for consent; missing access controls, inconsistent attributes |
| Data-at-Rest Encryption | 1/10 | Not implemented despite claims to the contrary |
| IPC Channel Security | 2/10 | No auth, no encryption, no symlink protection |
| Consent Integrity | 3/10 | Unsigned tokens, no runtime enforcement, no data cleanup |
| Integrity Verification | 6/10 | Good startup check but bypassable and non-periodic |
| Secret Handling in Logs | 4/10 | All messages marked public; no redaction discipline |
| Key Lifecycle | 2/10 | No rotation, no generation, encryption not implemented |
| Process Isolation | 5/10 | Hardened runtime good; sandbox disabled with justification |

**Overall Security Score: 3.5 / 10**

The agent has a solid architectural foundation (consent-first, PII filtering, integrity checking) but the implementation has critical gaps in data protection that must be closed before production deployment. The two CRITICAL findings (plaintext data storage and unauthenticated IPC) represent fundamental violations of the privacy promises made to employees during onboarding.

---

## Priority Remediation Roadmap

### Immediate (Before Any Production Deployment)
1. Implement AES-256-GCM encryption for the SQLite capture buffer [CRITICAL DATA-AT-REST-001]
2. Add authentication and pre-existence checks to the IPC socket [CRITICAL IPC-001]
3. Fix the false "All data is encrypted" claim in WelcomeView [CRITICAL DATA-AT-REST-001]

### Short-Term (Within 2 Weeks)
4. Add `kSecAttrAccessControl` with biometric protection to `KeychainHelper` [HIGH KEYCHAIN-001]
5. Sign consent records with HMAC [HIGH CONSENT-001]
6. Implement data cleanup on consent revocation [HIGH CONSENT-002]
7. Fix `AgentLogger` to use `privacy: .private` by default [HIGH LOGGING-001]

### Medium-Term (Within 1 Month)
8. Add runtime consent enforcement per-event [MEDIUM CONSENT-003]
9. Make integrity checks periodic and fail-closed in release builds [MEDIUM INTEGRITY-001, INTEGRITY-002]
10. Explicitly disable iCloud sync on all Keychain items [MEDIUM KEYCHAIN-003]
11. Document sandbox-disabled rationale in ADR [HIGH SANDBOX-001]

### Long-Term
12. Implement key rotation mechanism [LOW KEY-LIFECYCLE-001]
13. Clean up unused entitlements [LOW ENTITLEMENT-001]
14. Migrate Keychain error logging to structured os_log [LOW KEYCHAIN-004]
