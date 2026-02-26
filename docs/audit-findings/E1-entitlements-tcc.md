# E1: Entitlements & TCC Audit Report

**Agent**: E1 (Entitlements & TCC Auditor)
**Date**: 2026-02-25
**Scope**: macOS Task Mining Agent entitlements, TCC profiles, Hardened Runtime, Info.plist, signing scripts
**Auditor Model**: Claude Opus 4.6

---

## Finding Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1     |
| HIGH     | 3     |
| MEDIUM   | 5     |
| LOW      | 3     |
| **Total** | **12** |

---

## CRITICAL Findings

### [CRITICAL] ENTITLEMENT-001: Apple Events Entitlement Granted Without Any Code Usage

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/KMFlowAgent.entitlements:14-15`
**Agent**: E1 (Entitlements & TCC Auditor)
**Evidence**:
```xml
    <!-- Accessibility API access (CGEventTap, AXUIElement) -->
    <key>com.apple.security.automation.apple-events</key>
    <true/>
```
**Description**: The `com.apple.security.automation.apple-events` entitlement is set to `true`, granting this monitoring agent the ability to send Apple Events to other applications and control them via AppleScript/OSA. A comprehensive search of all 29 Swift source files under `Sources/` found zero usage of `NSAppleEventDescriptor`, `NSAppleScript`, `osascript`, or any Apple Events API. There is also no `NSAppleEventsUsageDescription` key in `Info.plist`, which means if the entitlement were exercised macOS would show a blank-reason dialog to the user. The comment in the entitlements file ("Accessibility API access") is misleading -- Accessibility APIs (`AXUIElement`, `CGEventTap`) do not require the Apple Events entitlement; they require TCC Accessibility authorization, which is handled separately via the PPPC profile. This entitlement is entirely unnecessary and represents an over-privileged surface.

**Risk**: The `automation.apple-events` entitlement allows a compromised agent to programmatically control any application on the system -- opening files, sending keystrokes, executing shell commands via `do shell script`, and exfiltrating data from other apps. For a workplace monitoring agent deployed to regulated enterprise endpoints, this is an unacceptable escalation path. An attacker who gains code execution within the agent process could use Apple Events to read email, open browser tabs, access password managers, or exfiltrate documents -- all without any additional permission prompts (the entitlement pre-authorizes the capability). This is especially dangerous combined with the lack of App Sandbox (see ENTITLEMENT-004).

**Recommendation**: Remove the entitlement entirely. Set `com.apple.security.automation.apple-events` to `<false/>` or delete the key. Accessibility API access (AXUIElement, CGEventTap, AXIsProcessTrusted) does not depend on this entitlement.

---

## HIGH Findings

### [HIGH] ENTITLEMENT-002: File Access Entitlement Without Sandbox Provides Unrestricted Filesystem Access

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/KMFlowAgent.entitlements:22-25`
**Agent**: E1 (Entitlements & TCC Auditor)
**Evidence**:
```xml
    <!-- File access for local SQLite buffer -->
    <key>com.apple.security.files.user-selected.read-write</key>
    <true/>
    <key>com.apple.security.app-sandbox</key>
    <false/>
```
**Description**: The `com.apple.security.files.user-selected.read-write` entitlement is declared but is functionally meaningless because the App Sandbox is disabled (`com.apple.security.app-sandbox` is `false`). When sandboxing is off, the process already has full filesystem access inherited from the user's POSIX permissions. The `user-selected.read-write` entitlement only extends Powerbox-mediated file access within a sandboxed environment. Including it without sandbox creates a misleading security posture -- it looks like file access is scoped, but it is not.

The actual file access patterns in code are narrow and well-defined:
- SQLite buffer at `~/Library/Application Support/KMFlowAgent/buffer.db` (TransparencyLogController.swift:70)
- Unix domain socket at `~/Library/Application Support/KMFlowAgent/agent.sock` (SocketClient.swift:12)
- Bundle resources read at `Bundle.main.resourceURL` (IntegrityChecker.swift, PythonProcessManager.swift)

**Risk**: Without sandbox, any code execution vulnerability in the agent or the embedded Python layer has unrestricted filesystem access -- reading SSH keys, browser profiles, Keychain database files, and any other user-accessible files on disk. The `files.user-selected.read-write` entitlement provides no mitigation when sandbox is off.

**Recommendation**: Either (a) remove the `user-selected.read-write` entitlement since it has no effect without sandbox, or (b) enable App Sandbox and scope file access to the specific directories needed (Application Support, bundle resources). If sandboxing is infeasible due to CGEventTap/AXUIElement requirements (which currently cannot run in sandbox on macOS), document this explicitly and remove the misleading entitlement. See also ENTITLEMENT-004.

---

### [HIGH] ENTITLEMENT-003: Build Script Does Not Enable Hardened Runtime Flag

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/build-app-bundle.sh:336-341`
**Agent**: E1 (Entitlements & TCC Auditor)
**Evidence**:
```bash
# 4. Sign the Swift binary with entitlements
codesign \
    --force \
    --sign "$CODESIGN_IDENTITY" \
    --timestamp \
    --entitlements "${RESOURCES}/KMFlowAgent.entitlements" \
    "${MACOS_BUNDLE}/${SWIFT_BINARY_NAME}"
```
**Description**: The `build-app-bundle.sh` script performs codesigning of both the Swift binary (lines 336-341) and the bundle (lines 344-350) but neither invocation includes `--options runtime`, which is the flag that enables Hardened Runtime. In contrast, the standalone `sign-all.sh` script correctly includes `--options runtime` at line 77. This means builds produced by `build-app-bundle.sh` (the primary build pipeline) will NOT have Hardened Runtime enabled, while re-signing with `sign-all.sh` would enable it. This inconsistency creates two problems: (1) the primary build artifact lacks Hardened Runtime protections, and (2) the entitlements file's Hardened Runtime declarations (lines 6-11, disabling JIT, unsigned memory, and library validation) are inert without the runtime flag.

**Risk**: Without Hardened Runtime: (a) the binary cannot be notarized by Apple, blocking enterprise deployment via standard channels; (b) DYLD environment variable injection attacks become possible; (c) code injection via `DYLD_INSERT_LIBRARIES` is not blocked; (d) the explicit disablement of JIT, unsigned memory, and library validation in the entitlements file has no effect. For a monitoring agent handling sensitive employee activity data, this leaves the process unprotected against the most common macOS code injection techniques.

**Recommendation**: Add `--options runtime` to both codesign invocations in `build-app-bundle.sh`:
```bash
codesign \
    --force \
    --sign "$CODESIGN_IDENTITY" \
    --options runtime \
    --timestamp \
    --entitlements "${RESOURCES}/KMFlowAgent.entitlements" \
    "${MACOS_BUNDLE}/${SWIFT_BINARY_NAME}"
```
Apply the same fix to the bundle-level signing at line 344-350.

---

### [HIGH] TCC-001: TCC Profile Contains Placeholder CodeRequirement That Would Fail Validation

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.tcc.mobileconfig:107`
**Agent**: E1 (Entitlements & TCC Auditor)
**Evidence**:
```xml
<key>CodeRequirement</key>
<string>identifier "com.kmflow.agent" and anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] and certificate leaf[field.1.2.840.113635.100.6.1.13] and certificate leaf[subject.OU] = "REPLACE_TEAM_ID"</string>
```
**Description**: Both the Accessibility (line 107) and ScreenCapture (line 140) CodeRequirement strings contain the literal placeholder `REPLACE_TEAM_ID` instead of an actual Apple Developer Team ID. If this profile is deployed to production MDM without replacing this placeholder, the CodeRequirement will never match the signed binary, and TCC pre-authorization will silently fail. Users would be prompted for manual Accessibility approval -- defeating the purpose of the MDM-managed PPPC profile.

While the file header contains a comment (lines 97-105) instructing replacement, there is no build-time or CI validation to prevent deployment with the placeholder intact. For a profile that is `PayloadRemovalDisallowed: true` (line 53), deploying a broken profile requires MDM intervention to remove and redeploy.

**Risk**: Silent failure of enterprise permission pre-authorization. Employees would see unexpected permission prompts, and in supervised MDM environments where users cannot grant TCC permissions themselves, the agent would simply not work. This would result in a failed enterprise deployment. Additionally, if the team ID were replaced incorrectly, TCC would pre-authorize a different application -- potentially one controlled by an attacker with the wrong team ID.

**Recommendation**: (1) Add a CI validation step that checks for `REPLACE_TEAM_ID` and fails the build if found in release artifacts. (2) Consider parameterizing the team ID as a build variable rather than embedding a placeholder in source control. (3) Add a `verify-profiles.sh` script that validates CodeRequirement strings match the actual signing identity before MDM deployment.

---

## MEDIUM Findings

### [MEDIUM] ENTITLEMENT-004: App Sandbox Explicitly Disabled -- Enterprise Risk Accepted Without Documentation

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/KMFlowAgent.entitlements:24-25`
**Agent**: E1 (Entitlements & TCC Auditor)
**Evidence**:
```xml
    <key>com.apple.security.app-sandbox</key>
    <false/>
```
**Description**: The App Sandbox is explicitly disabled. For this particular agent, this is likely a necessary technical decision -- `CGEventTap` and `AXUIElement` APIs required for input monitoring and window title capture are not available to sandboxed apps on macOS. However, the decision to disable sandbox carries significant security implications that are not documented anywhere in the codebase or entitlements file.

The agent accesses: Keychain (consent/secrets), filesystem (SQLite buffer), network (backend communication), process creation (Python subprocess), and low-level input APIs. Without sandbox, all of these capabilities are unrestricted.

**Risk**: An unsandboxed monitoring agent running with Accessibility permissions is one of the highest-privilege user-space processes on macOS. Any code execution vulnerability (in the Swift layer, the embedded Python layer, or vendored Python dependencies) grants the attacker the full privileges of the running user plus Accessibility control of the entire GUI. Enterprise CISOs will flag this during security review.

**Recommendation**: Document the sandbox exclusion in an Architecture Decision Record (ADR) explaining: (1) why sandbox is incompatible with the required Accessibility APIs, (2) what compensating controls exist (integrity checking, PII filtering, blocklist, consent management), and (3) the residual risk accepted. Include this ADR reference in the entitlements file comment. Investigate whether macOS 15+ Sequoia has expanded sandbox compatibility for Accessibility APIs.

---

### [MEDIUM] TCC-002: Screen Capture TCC Authorization Pre-Approved for Unimplemented Feature

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.tcc.mobileconfig:130-151`
**Agent**: E1 (Entitlements & TCC Auditor)
**Evidence**:
```xml
<key>ScreenCapture</key>
<array>
    <dict>
        <key>Identifier</key>
        <string>com.kmflow.agent</string>
        ...
        <key>Allowed</key>
        <true/>
        ...
        <key>Comment</key>
        <string>KMFlow Agent optionally captures screenshots when content_level capture policy is enabled. Disable this block if action_level policy is used.</string>
    </dict>
</array>
```
**Description**: The TCC profile pre-authorizes Screen Capture (`ScreenCapture` service, line 130) with `Allowed: true`. However, a comprehensive search of all Swift source files found zero usage of screen capture APIs (`SCStream`, `SCShareableContent`, `CGWindowListCreateImage`, `CGImage` capture, or any screenshot functionality). The `Info.plist` declares `NSScreenCaptureUsageDescription` referencing "Phase 2" (line 35), and `PermissionsView.swift` (line 150) explicitly states it is "optional and only needed for screenshot analysis (Phase 2)". The `AgentConfig` has `screenshotEnabled: Bool` defaulting to `false`, but there is no implementation behind this flag.

The only usage of `CGWindowListCopyWindowInfo` is in `PermissionsManager.swift:35` as a permission-detection heuristic, not actual screen capture.

**Risk**: Pre-authorizing Screen Capture via MDM PPPC means the TCC database will silently grant this capability without user consent. If the agent is compromised before the feature is actually implemented, an attacker could add screen capture code (especially through the unsandboxed Python subprocess) and capture screenshots without any user-visible permission prompt. This violates the principle of least privilege -- pre-authorizing capabilities before they are needed.

**Recommendation**: Remove the ScreenCapture block from the TCC profile. The profile's own comment says "Comment out this block if screen capture is not needed." Add the ScreenCapture authorization in a future profile version when the Phase 2 feature is actually implemented. Also remove `NSScreenCaptureUsageDescription` from `Info.plist` until the feature exists.

---

### [MEDIUM] SIGNING-001: Inconsistent Hardened Runtime Between Build and Re-signing Scripts

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/sign-all.sh:73-80` vs `/Users/proth/repos/kmflow/agent/macos/scripts/build-app-bundle.sh:336-350`
**Agent**: E1 (Entitlements & TCC Auditor)
**Evidence from sign-all.sh**:
```bash
codesign \
    --deep \
    --force \
    --sign "$IDENTITY" \
    --options runtime \
    --entitlements "$ENTITLEMENTS_PATH" \
    --timestamp \
    "$APP_PATH"
```
**Evidence from build-app-bundle.sh**:
```bash
codesign \
    --force \
    --deep \
    --sign "$CODESIGN_IDENTITY" \
    --timestamp \
    --entitlements "${RESOURCES}/KMFlowAgent.entitlements" \
    "$APP_BUNDLE"
```
**Description**: The `sign-all.sh` script includes `--options runtime` (line 77), enabling Hardened Runtime. The `build-app-bundle.sh` script does NOT include this flag in either of its two codesign invocations (lines 336-341 for the binary, lines 344-350 for the bundle). This means:
- Fresh builds (`build-app-bundle.sh`) lack Hardened Runtime
- Re-signed builds (`sign-all.sh`) have Hardened Runtime

The build script also uses `--deep` on line 346 (signing the bundle), which Apple deprecates for production builds because it re-signs nested code items that may already have correct signatures, potentially introducing mismatches.

**Risk**: If the standard build pipeline is `build-app-bundle.sh`, production artifacts will lack Hardened Runtime. Developers might assume the build is protected because the entitlements file explicitly disables dangerous capabilities (JIT, unsigned memory, library validation), but those declarations are only enforced when Hardened Runtime is active. This creates a false sense of security.

**Recommendation**: Standardize on a single signing approach. Add `--options runtime` to `build-app-bundle.sh`. Consider removing the `--deep` flag from the bundle-level sign and instead signing each component individually (which the script already does in steps 1-4), relying on `--deep` only for verification.

---

### [MEDIUM] KEYCHAIN-001: KeychainHelper Does Not Set kSecAttrAccessible Protection Class

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Utilities/KeychainHelper.swift:15-20`
**Agent**: E1 (Entitlements & TCC Auditor)
**Evidence**:
```swift
    public func save(key: String, data: Data) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
        ]
```
**Description**: The `KeychainHelper` utility (used for general agent secrets) does not set `kSecAttrAccessible` when saving Keychain items. Without this attribute, the system defaults to `kSecAttrAccessibleWhenUnlocked`, which is reasonable but inconsistent with the `KeychainConsentStore` implementation that explicitly sets `kSecAttrAccessibleAfterFirstUnlock` (line 141 in `KeychainConsentStore.swift`). This inconsistency means: (a) general agent secrets are only accessible when the device is unlocked, while consent records persist after first unlock, and (b) the security posture of Keychain items depends on which storage path is used, creating unpredictable behavior.

**Risk**: If the agent needs to operate during a user session where the screensaver is active (device locked), secrets stored via `KeychainHelper` would be inaccessible while consent records via `KeychainConsentStore` would still work. This could cause silent failures. The lack of explicit accessibility class also means the default could change with OS updates. For enterprise deployments, having undocumented Keychain behavior creates audit concerns.

**Recommendation**: Add `kSecAttrAccessibleAfterFirstUnlock` to `KeychainHelper.save()` for consistency with `KeychainConsentStore`, or document the intentional difference. Standardize on one Keychain protection class across the codebase.

---

### [MEDIUM] LOGGING-001: All Logger Messages Use privacy: .public, Risking PII in System Logs

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Utilities/Logger.swift:14-26`
**Agent**: E1 (Entitlements & TCC Auditor)
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
**Description**: The `AgentLogger` wrapper marks ALL log message content as `privacy: .public`, which means every log message is visible in cleartext in `Console.app`, `log stream`, sysdiagnose bundles, and crash reports -- even on non-development devices. The same pattern appears in `PythonProcessManager.swift` and `IntegrityChecker.swift`. While the agent currently logs operational messages (PID numbers, file paths, integrity violations), any future code that logs window titles, application names, engagement IDs, or user names through this logger would expose that data in system logs accessible to any admin on the machine.

**Risk**: System logs on macOS are readable by any admin user and are included in sysdiagnose archives that may be shared with Apple or IT support. If a developer inadvertently logs captured event data (window titles, app names) through `AgentLogger`, PII from the monitored employee would leak into system-wide logs, violating the data minimization guarantees the agent promises. For regulated enterprises (GDPR, HIPAA), this could constitute a compliance violation.

**Recommendation**: Change the default privacy level to `.private` (which redacts in production logs but shows in debug builds). Provide a separate `publicInfo()` method for messages that are explicitly safe for system logs (e.g., version strings, startup confirmations). Audit all existing log call sites to ensure no sensitive data is logged.

---

## LOW Findings

### [LOW] PLIST-001: NSScreenCaptureUsageDescription Present for Unimplemented Feature

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/Info.plist:34-35`
**Agent**: E1 (Entitlements & TCC Auditor)
**Evidence**:
```xml
    <key>NSScreenCaptureUsageDescription</key>
    <string>KMFlow Agent needs Screen Recording access for optional screenshot-based process analysis (Phase 2).</string>
```
**Description**: `Info.plist` declares a usage description for Screen Recording, but no screen capture code exists in the current codebase. While this is not a vulnerability per se, it means macOS may present a "KMFlow Agent would like to record the contents of your screen" dialog if certain APIs are invoked (even the permission-check heuristic in `PermissionsManager.swift` could trigger this on some macOS versions). The description referencing "Phase 2" in a production plist is confusing for end users.

**Risk**: User confusion. Employees seeing a screen recording permission prompt for an agent that does not actually capture screenshots may distrust the tool or refuse to grant the real (Accessibility) permission.

**Recommendation**: Remove `NSScreenCaptureUsageDescription` until the screen capture feature is implemented. Update the usage description text to remove internal phase references before any production deployment.

---

### [LOW] PLATFORM-001: Platform Version Alignment Is Correct

**File**: `/Users/proth/repos/kmflow/agent/macos/Package.swift:9` and `/Users/proth/repos/kmflow/agent/macos/Resources/Info.plist:27-28`
**Agent**: E1 (Entitlements & TCC Auditor)
**Evidence from Package.swift**:
```swift
    platforms: [
        .macOS(.v13),
    ],
```
**Evidence from Info.plist**:
```xml
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
```
**Description**: The minimum macOS version is consistent between `Package.swift` (`.macOS(.v13)`) and `Info.plist` (`LSMinimumSystemVersion: 13.0`). macOS 13 Ventura is a reasonable minimum for an agent using modern Swift concurrency, SwiftUI, and Accessibility APIs. No finding to report here -- this is a verification of correct alignment.

**Risk**: None -- this check passes.

**Recommendation**: No action needed. When raising the minimum version, update both files simultaneously.

---

### [LOW] PLIST-002: LSUIElement Correctly Configured as Menu Bar Agent

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/Info.plist:23-24`
**Agent**: E1 (Entitlements & TCC Auditor)
**Evidence**:
```xml
    <key>LSUIElement</key>
    <true/>
```
**Description**: The app is correctly configured as an LSUIElement (no Dock icon, no menu bar entry from AppKit's perspective). This is the expected behavior for a background monitoring agent that operates from the system menu bar. The StatusBarController creates an NSStatusItem independently. This is correct and expected.

**Risk**: None -- this is a positive finding.

**Recommendation**: No action needed.

---

### [LOW] CONFIG-001: MDM Configuration Profile Uses Placeholder Engagement ID

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.mobileconfig:87`
**Agent**: E1 (Entitlements & TCC Auditor)
**Evidence**:
```xml
            <key>EngagementID</key>
            <string>eng-REPLACE-ME</string>
```
**Description**: The MDM configuration profile contains a placeholder engagement ID (`eng-REPLACE-ME`). While this is expected for a template file in source control, there is no build-time or deployment-time validation to prevent pushing this template directly to MDM without customization. If deployed as-is, all agents would report to engagement "eng-REPLACE-ME", contaminating data.

**Risk**: Low severity because the value is obviously a placeholder and MDM administrators would typically customize profiles before deployment. However, automated deployment pipelines could push the template without review.

**Recommendation**: Add a CI check or deployment script that validates placeholder values are replaced before MDM deployment. Consider using MDM variable substitution (e.g., Jamf's `$PROFILE_IDENTIFIER` syntax) instead of static placeholders.

---

## Positive Security Observations

The following aspects of the entitlements and TCC configuration are well-implemented:

1. **Hardened Runtime dangerous capabilities explicitly disabled**: The entitlements file sets `allow-jit`, `allow-unsigned-executable-memory`, and `disable-library-validation` all to `<false/>` (lines 6-11). These are the correct restrictive values.

2. **Network entitlement correctly scoped**: Only `com.apple.security.network.client` is declared (outbound only). No `network.server` entitlement exists. The Unix domain socket IPC uses POSIX socket APIs that do not require a server entitlement since both endpoints are local processes owned by the same user.

3. **TCC StaticCode set to false**: Both Accessibility and ScreenCapture TCC entries set `StaticCode: false` (lines 117-118, 145-146), which means macOS re-validates the binary's code signature on each access. This is the more secure option -- it detects binary tampering at runtime rather than only at profile installation time.

4. **TCC PayloadRemovalDisallowed**: The TCC profile cannot be removed by the user (line 53), which is correct for enterprise-managed permission profiles.

5. **Accessibility usage description is honest and specific**: The `NSAccessibilityUsageDescription` (Info.plist line 32) clearly states what the agent does with Accessibility access, including the specific data types observed.

6. **PrivacyInfo.xcprivacy properly declared**: The privacy manifest correctly declares Product Interaction data collection, non-tracking status, and Required Reason API usage for File Timestamps and UserDefaults.

7. **Python integrity checking at startup**: The `IntegrityChecker` verifies SHA-256 hashes of all Python files before the Python subprocess launches, providing defense-in-depth against tampering with the unsandboxed Python layer.

8. **Consent-gated capture**: No capture occurs until explicit consent is granted through the onboarding wizard and persisted to the Keychain.

---

## Risk Score

**Overall Entitlement & TCC Security Score: 6.5 / 10**

The architecture shows strong security thinking (integrity checking, consent management, PII filtering, honest usage descriptions), but the CRITICAL finding of an unnecessary Apple Events entitlement and the HIGH finding of missing Hardened Runtime in the primary build pipeline significantly weaken the security posture. Resolving the CRITICAL and HIGH findings would raise this score to approximately 8.5/10.

**Priority remediation order**:
1. Remove `com.apple.security.automation.apple-events` entitlement (CRITICAL)
2. Add `--options runtime` to `build-app-bundle.sh` (HIGH)
3. Replace TCC CodeRequirement placeholder with CI validation (HIGH)
4. Remove ScreenCapture from TCC profile and NSScreenCaptureUsageDescription from Info.plist (MEDIUM)
5. Remove misleading `files.user-selected.read-write` entitlement (HIGH)
6. Standardize Keychain protection class and logger privacy levels (MEDIUM)
