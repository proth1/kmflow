# E2: Capture Layer Security Re-Audit

**Agent**: E2 (Capture Layer Auditor)
**Original Audit Date**: 2026-02-25
**Re-Audit Date**: 2026-02-26
**Scope**: macOS Task Mining Agent — Swift capture layer and supporting modules
**Auditor Model**: Claude Opus 4.6
**Remediation PRs Reviewed**: #248, #255, #256, #258

---

## Re-Audit Summary

The original audit on 2026-02-25 identified **13 findings** (1 CRITICAL, 3 HIGH, 6 MEDIUM, 3 LOW) in the capture layer. PRs #248, #255, #256, and #258 addressed a significant portion of these findings. This re-audit verifies which fixes landed, assesses their completeness, and identifies any residual or newly introduced risks.

### Before/After Comparison

| Severity | Original Count | Resolved | Partially Resolved | Open | New |
|----------|:-:|:-:|:-:|:-:|:-:|
| CRITICAL | 1 | 1 | 0 | 0 | 0 |
| HIGH | 3 | 3 | 0 | 0 | 0 |
| MEDIUM | 6 | 3 | 1 | 2 | 1 |
| LOW | 3 | 0 | 0 | 2 | 0 |
| **Total** | **13** | **7** | **1** | **4** | **1** |

**Net finding count**: 6 open (4 original + 1 partially resolved + 1 new)

### Remediation Scorecard

| # | Original Finding | Severity | Status | Evidence |
|---|-----------------|----------|--------|----------|
| 1 | Mouse X/Y coordinates in InputEvent | CRITICAL | RESOLVED | `InputMonitor.swift:17-23` — no x/y parameters |
| 2 | content_level mode in UI | HIGH | RESOLVED | `ConsentView.swift:61-64` — option commented out and picker disabled |
| 3 | nil bundleId bypasses blocklist | HIGH | RESOLVED | `BlocklistManager.swift:33-34` — `guard let bid = bundleId else { return false }` |
| 4 | Logger privacy: .public on all messages | HIGH | RESOLVED | `Logger.swift:13-27` — all levels now `privacy: .private` |
| 5 | L2 PII filter missing patterns | MEDIUM | RESOLVED | `WindowTitleCapture.swift:40-53` — IBAN, file path, UK NINO added |
| 6 | try! regex crash risk | MEDIUM | RESOLVED | `WindowTitleCapture.swift:16-53` — all patterns use lazy `try?` with assert guard |
| 7 | Per-event consent guard missing | MEDIUM | RESOLVED | `CaptureStateManager.swift:92-98` — `isCapturePermitted` property added |
| 8 | Pause/resume not wired to monitors | MEDIUM | PARTIAL | `CaptureStateManager.swift:30-48` — handler infrastructure added, but AppDelegate does not register handlers |
| 9 | Private browsing detection fragile | MEDIUM | OPEN | `CaptureContextFilter.swift:56-92` — still English-only, still string-based |
| 10 | Event Protocol sensitive types without guards | MEDIUM | OPEN | `EventProtocol.swift:11-29` — unchanged, no compile-time gates |
| 11 | CaptureState not persisted across restarts | LOW | OPEN | `CaptureStateManager.swift:23` — still defaults to `.idle` |
| 12 | Blocked-app dwell time leaked | LOW | OPEN | `AppSwitchMonitor.swift:72-73` — `lastSwitchTime` still set to `Date()` |
| 13 | No CGEventTap implementation to audit | LOW | OPEN | Still no concrete `InputEventSource` implementation |

---

## Verified Remediations

### [CRITICAL-1] RESOLVED: Mouse Coordinate Capture Removed

**Original**: `InputEvent` enum carried `x: Double, y: Double` for mouseDown, mouseUp, and mouseDrag cases.
**Current code** (`/Users/proth/repos/kmflow/agent/macos/Sources/Capture/InputMonitor.swift:16-23`):
```swift
public enum InputEvent: Sendable {
    case keyDown(timestamp: Date)
    case keyUp(timestamp: Date)
    case mouseDown(button: MouseButton, timestamp: Date)
    case mouseUp(button: MouseButton, timestamp: Date)
    case mouseDrag(timestamp: Date)
    case scroll(deltaX: Double, deltaY: Double, timestamp: Date)
}
```
**Verification**: All mouse event cases now carry only a `timestamp` (and `button` for click events). The `scroll` case retains `deltaX`/`deltaY` which represent scroll magnitude, not screen position — this is acceptable for process mining (measures scroll intensity, not cursor location). The `InputAggregator` only increments counters, confirming no coordinate data flows through the pipeline.

**Assessment**: Fully resolved. Data minimization for mouse events is now compliant.

---

### [HIGH-2] RESOLVED: content_level UI Option Disabled

**Original**: The onboarding `ConsentView` showed a picker allowing users to select "Content Level (with PII filtering)" — a mode with no implementation.
**Current code** (`/Users/proth/repos/kmflow/agent/macos/Sources/UI/Onboarding/ConsentView.swift:57-69`):
```swift
LabeledFormField(label: "Capture Scope", isRequired: false) {
    Picker("Capture Scope", selection: $state.captureScope) {
        Text("Activity Level (counts only)")
            .tag("action_level")
        // Content Level is disabled until L2+ PII filtering is fully
        // validated.  See audit finding E2-HIGH.
        // Text("Content Level (with PII filtering)")
        //     .tag("content_level")
    }
    .pickerStyle(.segmented)
    .labelsHidden()
    .disabled(true)
}
```
**Verification**: The content_level option is commented out with an explicit reference to this audit finding. The picker is additionally `.disabled(true)`, providing belt-and-suspenders protection. The `CaptureGranularity` enum still contains `contentLevel` in `AgentConfig.swift:101-103`, which is acceptable — the enum defines the wire protocol and MDM can still technically set it, but the UI prevents user selection.

**Residual concern**: An MDM profile could still set `CapturePolicy = "content_level"` and the `AgentConfig.init?(fromMDMProfile:)` initializer at line 52-53 would accept it. Since no code path reads `captureGranularity` to change behavior today, this is informational, not a finding. However, when content-level capture is implemented, the MDM path must be gated on the same readiness checks.

**Assessment**: Fully resolved for user-facing risk. Residual MDM concern documented.

---

### [HIGH-3] RESOLVED: nil bundleId Now Denied by Default

**Original**: `BlocklistManager.shouldCapture(bundleId:)` returned `true` for `nil` bundleId, allowing unidentified apps to be captured.
**Current code** (`/Users/proth/repos/kmflow/agent/macos/Sources/Config/BlocklistManager.swift:30-43`):
```swift
/// Apps with a nil bundle identifier are blocked by default (least
/// privilege) to prevent unidentified processes from being captured.
public func shouldCapture(bundleId: String?) -> Bool {
    guard let bid = bundleId else { return false }

    // If allowlist is set, only allow listed apps
    if let allow = allowlist, !allow.isEmpty {
        return allow.contains(bid)
    }

    // Otherwise, block listed apps
    return !blocklist.contains(bid)
}
```
**Verification**: The `guard let bid = bundleId else { return false }` now correctly denies capture for apps without bundle identifiers. The comment explains the rationale. The allowlist logic is also correct — if an allowlist is configured, only explicitly listed apps pass through.

**Additional improvement noted**: `BlocklistManager` was converted from a class with NSLock to a Swift `actor`, which is a thread-safety improvement (verified at line 6: `public actor BlocklistManager`).

**Assessment**: Fully resolved. Principle of least privilege now applied to unknown apps.

---

### [HIGH-4] RESOLVED: Logger Privacy Level Changed to .private

**Original**: All `AgentLogger` methods used `privacy: .public`, exposing all log messages in macOS Console.app and sysdiagnose bundles.
**Current code** (`/Users/proth/repos/kmflow/agent/macos/Sources/Utilities/Logger.swift:13-27`):
```swift
public func info(_ message: String) {
    logger.info("\(message, privacy: .private)")
}

public func debug(_ message: String) {
    logger.debug("\(message, privacy: .private)")
}

public func warning(_ message: String) {
    logger.warning("\(message, privacy: .private)")
}

public func error(_ message: String) {
    logger.error("\(message, privacy: .private)")
}
```
**Verification**: All four log levels now use `privacy: .private`. Messages will be redacted in Console.app unless a logging profile is installed, protecting against PII leakage in system logs.

**Residual concern**: Other files that use `os.Logger` directly (not through `AgentLogger`) still use explicit privacy annotations. Spot-checking `IntegrityChecker.swift` shows mixed usage — line 143 uses `privacy: .public` for the manifest path, and lines 189-191 log expected and actual digests with `privacy: .public`. File paths and SHA hashes are not PII, so this is acceptable. `PythonProcessManager.swift` logs PID with `privacy: .public` (acceptable). However, `KMFlowAgentApp.swift:50` uses `NSLog` which always logs publicly: `NSLog("KMFlowAgent: Python integrity check failed: \(violations)")`. This should be migrated to `AgentLogger` but is outside the E2 scope (it logs file paths from violations, not user data).

**Assessment**: Fully resolved for the `AgentLogger` wrapper. The NSLog call in `KMFlowAgentApp.swift:50` is a residual from E1/G1 scope.

---

### [MEDIUM-5] RESOLVED: L2 PII Filter Expanded with IBAN, File Path, UK NINO

**Original**: L2PIIFilter covered only 5 patterns (SSN-dashed, email, phone, Visa/MC/Discover/JCB, AmEx).
**Current code** (`/Users/proth/repos/kmflow/agent/macos/Sources/Capture/WindowTitleCapture.swift:14-66`):
```swift
// 8 patterns total:
private static let ssnDashed: NSRegularExpression?     // SSN with dashes
private static let email: NSRegularExpression?          // Email addresses
private static let phone: NSRegularExpression?          // US phone numbers
private static let creditCard: NSRegularExpression?     // Visa/MC/Discover/JCB
private static let amex: NSRegularExpression?           // AmEx
private static let iban: NSRegularExpression?           // IBAN (international)
private static let filePath: NSRegularExpression?       // Absolute file paths
private static let ukNino: NSRegularExpression?         // UK National Insurance
```
**Verification**: Three new patterns added: IBAN (line 41-43), file paths covering both Unix `/Users/` and Windows `C:\Users\` (lines 46-48), and UK NINO (lines 51-53). The `allPatterns` array at line 58-66 includes all 8 patterns with a debug-mode assertion that all compiled successfully.

**Test coverage** (`/Users/proth/repos/kmflow/agent/macos/Tests/PIITests/L2PIIFilterTests.swift`): Dedicated tests for IBAN (compact and spaced), file paths (Unix and Windows), UK NINO, and negative cases (short numbers, normal text). Test coverage for the new patterns is thorough.

**Still missing** (informational, not a regression): SSN without dashes, IP addresses, Canadian SIN, Mastercard 2-series. These were noted in the original audit as "nice to have" for international deployments. The `piiPatternsVersion` field in `AgentConfig` could enable server-side pattern updates in the future.

**Assessment**: Fully resolved. Coverage expanded from 5 to 8 patterns with appropriate test coverage.

---

### [MEDIUM-6] RESOLVED: try! Regex Crash Risk Eliminated

**Original**: L2PIIFilter regex patterns used `try!` which would crash the app if any pattern had a syntax error.
**Current code** (`/Users/proth/repos/kmflow/agent/macos/Sources/Capture/WindowTitleCapture.swift:16-66`):
```swift
private static let ssnDashed: NSRegularExpression? = {
    try? NSRegularExpression(pattern: #"\b\d{3}-\d{2}-\d{4}\b"#)
}()
// ... all patterns follow the same lazy try? pattern
```

The `allPatterns` computed property at line 58-66 uses `compactMap` to filter out nil entries (patterns that failed compilation) and includes a debug-mode assertion:
```swift
private static let allPatterns: [NSRegularExpression] = {
    let optionals = [ssnDashed, email, phone, creditCard, amex, iban, filePath, ukNino]
    let compiled = optionals.compactMap { $0 }
    assert(compiled.count == optionals.count,
           "L2PIIFilter: \(optionals.count - compiled.count) regex pattern(s) failed to compile")
    return compiled
}()
```
**Verification**: All patterns use `try?` with optional typing. The `compactMap` gracefully degrades in release builds if a pattern fails to compile (that pattern is skipped but others still run). The `assert` catches compilation failures during development. This is the correct pattern for defense-in-depth regex initialization.

**Assessment**: Fully resolved.

---

### [MEDIUM-7] RESOLVED: Per-Event Consent Guard Added

**Original**: No mechanism existed for monitors to check consent state before emitting each event. Consent was only checked at startup.
**Current code** (`/Users/proth/repos/kmflow/agent/macos/Sources/Capture/CaptureStateManager.swift:92-98`):
```swift
/// Returns `true` if the current state permits event capture.
///
/// Monitors should call this before emitting each event to enforce
/// per-event consent checking (defense-in-depth — even if the monitor
/// was started correctly, consent could be revoked between events).
public var isCapturePermitted: Bool {
    state == .capturing
}
```
**Verification**: The `isCapturePermitted` property provides a synchronous check that monitors can call before emitting events. Since `CaptureStateManager` is `@MainActor`-isolated, this property is safe to read from the main thread. The documentation correctly positions this as a defense-in-depth measure.

**Note**: The effectiveness of this guard depends on monitors actually calling it. Since no concrete `InputEventSource` implementation exists yet, verifying call-site usage is deferred to the CGEventTap implementation audit.

**Assessment**: Fully resolved at the API level. Usage verification deferred.

---

## Partially Resolved Findings

### [MEDIUM-8] PARTIAL: Pause/Resume State Change Handler Infrastructure

**Original**: `pauseCapture()` set a state flag but did not signal monitors to stop. Events continued flowing while the UI showed "Paused".
**Current code** (`/Users/proth/repos/kmflow/agent/macos/Sources/Capture/CaptureStateManager.swift:30-48`):
```swift
/// Registered handlers notified on every state transition.
/// Monitors register here to actually stop/start their event taps.
private var stateChangeHandlers: [CaptureStateChangeHandler] = []

public func onStateChange(_ handler: @escaping CaptureStateChangeHandler) {
    stateChangeHandlers.append(handler)
}

private func transition(to newState: CaptureState) {
    let oldState = state
    state = newState
    for handler in stateChangeHandlers {
        handler(oldState, newState)
    }
}
```
**Verification**: The `CaptureStateChangeHandler` pattern and `onStateChange` registration method provide the correct architectural hook. All state transitions now route through `transition(to:)` which notifies registered handlers. This is the right design.

**Gap**: `KMFlowAgentApp.swift` (the `AppDelegate`) does not register any state change handlers. Lines 37-87 show that `stateManager` is created and passed to `StatusBarController`, but no `stateManager.onStateChange { ... }` call exists to wire up `SystemAppSwitchMonitor.stopObserving()` or future `InputEventSource.stop()`. The handler array will be empty at runtime.

Similarly, `ConsentManager` now has a `ConsentRevocationHandler` pattern (line 22-23 in `ConsentManager.swift`) but `AppDelegate` does not register any revocation handlers.

**Impact**: Pressing "Pause" in the menu bar will set `state = .paused` and update the icon, but `SystemAppSwitchMonitor` will continue delivering notifications. The `isCapturePermitted` per-event guard (Finding 7) mitigates this if monitors check it, but the monitor itself is not stopped.

**Assessment**: Architecture is correct, wiring is incomplete. Severity remains MEDIUM.

---

## Open Findings (Carried Forward)

### [MEDIUM-9] OPEN: Private Browsing Detection Remains Fragile

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/PII/CaptureContextFilter.swift:56-92`
**Current state**: Five browsers covered (Safari, Chrome, Firefox, Arc, Edge). Detection still relies on English-language string matching against window titles.

**Unchanged risks**:
1. **Localization bypass**: A user with macOS set to German sees "Privates Surfen" (Safari), "Inkognito" (Chrome), "Privater Modus" (Firefox). None of these match the English strings. Private browsing sessions in non-English locales will be captured.
2. **Missing browsers**: Brave (`com.brave.Browser`), Vivaldi (`com.vivaldi.Vivaldi`), Opera (`com.operasoftware.Opera`), and Tor Browser are not covered.
3. **nil windowTitle**: `guard let title = windowTitle else { return false }` — a private browsing window with a nil title during page loading is not detected.
4. **Browser update fragility**: If Chrome changes from "- Incognito" suffix to "(Incognito)" or any other format, detection breaks.

**Recommendation** (unchanged): Use the macOS Accessibility API's `AXPrivate` attribute for locale-independent detection. Expand browser coverage. Default nil windowTitle to suppressed when bundleId matches a known browser.

---

### [MEDIUM-10] OPEN: Event Protocol Defines Sensitive Types Without Guards

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/IPC/EventProtocol.swift:11-29`
**Current state**: The `DesktopEventType` enum still declares 17 event types including `copyPaste`, `urlNavigation`, `fileOpen`, `fileSave`, `screenCapture`, and `uiElementInteraction` — none of which have Swift-side producers.

**Unchanged risk**: These event types normalize privacy-sensitive capabilities (clipboard access, URL history, pixel capture) in the protocol layer, making future implementation easier to ship without a dedicated security review gate. A developer implementing `copyPaste` would find the event type "pre-approved" in the protocol.

**Recommendation** (unchanged): Add compile-time guards or move unimplemented event types to a separate enum that cannot be used in `CaptureEvent` construction.

---

### [LOW-11] OPEN: CaptureState Not Persisted Across Restarts

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/CaptureStateManager.swift:23`
**Current state**: `@Published public private(set) var state: CaptureState = .idle` — always initializes to `.idle`. If a user pauses the agent and it restarts (crash, reboot, macOS update), capture resumes through the consent-check flow in `AppDelegate.applicationDidFinishLaunching`.

**Impact**: A user who paused monitoring loses their pause state on restart. The consent-first architecture mitigates this partially (consent must still be granted), but the specific user intent to pause is lost.

**Recommendation** (unchanged): Persist `CaptureState` to UserDefaults, respecting the paused state on relaunch.

---

### [LOW-12] OPEN: Blocked-App Dwell Time Still Leaked

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/AppSwitchMonitor.swift:70-74`
```swift
guard self.blocklistManager.shouldCapture(bundleId: bundleId) else {
    self.lastAppName = nil
    self.lastBundleId = nil
    self.lastSwitchTime = Date()  // <-- sets to current time
    return
}
```
**Current state**: When a blocklisted app becomes frontmost, `lastSwitchTime` is set to `Date()`. When the user subsequently switches to a non-blocked app, the emitted event's `dwellMs` reveals exactly how long the user spent in the blocked application.

**Example**: Safari -> 1Password (blocked, lastSwitchTime = now) -> Slack (dwellMs = time in 1Password). The app name "1Password" is correctly suppressed, but the dwell time leaks behavioral metadata about password manager usage.

**Recommendation** (unchanged): Set `lastSwitchTime` to `nil` (not `Date()`) when a blocklisted app is detected, so the subsequent event reports `dwellMs: 0`.

---

### [LOW-13] OPEN: No CGEventTap Implementation to Audit

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/InputMonitor.swift:10-14`
**Current state**: The `InputEventSource` protocol exists, and `InputAggregator` processes events, but no concrete implementation creates a CGEventTap. The most security-critical component of the agent — the system-wide event tap — has not been written.

**Status**: This remains a blocking audit prerequisite for GA. When implemented, a mandatory E2 re-audit must verify: (1) `.listenOnly` placement, (2) `.cgSessionEventTap` scope, (3) minimal event mask, (4) no keycode/character access in the callback, (5) tap disabled during pause state.

---

## New Finding

### [MEDIUM-NEW-1] DESIGN: ConsentManager Revocation Handlers Not Wired in AppDelegate

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/KMFlowAgentApp.swift:37-87`
**Agent**: E2 (Capture Layer Auditor)
**Evidence**:
```swift
func applicationDidFinishLaunching(_ notification: Notification) {
    stateManager = CaptureStateManager()
    blocklistManager = BlocklistManager()
    statusBarController = StatusBarController(stateManager: stateManager)
    // ...
    let consentManager = ConsentManager(engagementId: engagementId, store: consentStore)

    if consentManager.state == .neverConsented {
        onboardingWindow = OnboardingWindow()
        onboardingWindow?.show()
        stateManager.requireConsent()
    } else if !consentManager.captureAllowed {
        stateManager.requireConsent()
    } else {
        startPythonSubprocess()
    }
}
```
**Description**: The `ConsentManager` now provides an `onRevocation(_:)` handler registration method (verified in `ConsentManager.swift:40-42`), and `CaptureStateManager` provides `onStateChange(_:)` (verified in `CaptureStateManager.swift:38-39`). However, `AppDelegate.applicationDidFinishLaunching` does not call either registration method. This means:

1. When consent is revoked via the UI, `ConsentManager.revokeConsent()` will fire handlers — but the handler array is empty, so no cleanup occurs (Python process continues running, socket stays connected, buffer is not deleted).
2. When the user pauses via the menu bar, `CaptureStateManager.pauseCapture()` transitions state and fires handlers — but the handler array is empty, so monitors continue running.

The `consentManager` variable is also local to `applicationDidFinishLaunching` and will be deallocated when the method returns, making future revocation impossible through this instance.

**Risk**: The revocation and pause infrastructure was built (Findings 7, 8) but never connected. Users who revoke consent or pause capture will see the UI reflect their choice, but the underlying system continues operating. This is a consent integrity issue.

**Recommendation**: In `AppDelegate`, retain `consentManager` as an instance property, register a revocation handler that calls `stateManager.stopCapture()` and `pythonManager.stop()`, and register a state change handler that calls `SystemAppSwitchMonitor.stopObserving()` and flushes/discards the `InputAggregator` buffer when transitioning away from `.capturing`.

---

## Security Checklist Verification (Updated)

### Credentials & Secrets
- [x] No hardcoded passwords, API keys, or secrets in capture layer code
- [x] Consent stored in macOS Keychain with HMAC signing (`KeychainConsentStore`)
- [x] Keychain items use `kSecAttrAccessibleAfterFirstUnlock` and `kSecAttrSynchronizable: false`
- [x] Logger uses `privacy: .private` by default (Finding 4 resolved)

### OWASP Verification (adapted for native client)
- [x] No SQL injection (parameterized SQLite queries in TransparencyLogController)
- [x] No XSS (native app, no web views in capture layer)
- [x] No CSRF (no HTTP endpoints)
- [x] Authentication: Consent-first with three explicit checkboxes
- [x] Authorization: nil bundleId now denied by default (Finding 3 resolved)
- [x] Backend URL validated: https-only with host check (`PythonProcessManager.swift:87-94`)
- [x] No third-party dependencies in capture layer (pure Apple frameworks)
- [ ] **PARTIAL**: Logging hygiene — `AgentLogger` fixed; `NSLog` in `KMFlowAgentApp.swift:50` still public (E1/G1 scope)
- [ ] **PARTIAL**: Config validation — MDM integers clamped (`AgentConfig.swift:59-79`), but `screenshotIntervalSeconds` floor is 5s (consider 30s minimum)

### Data Minimization (GDPR Article 5(1)(c))
- [x] Mouse coordinates removed from event model (Finding 1 resolved)
- [x] Window titles truncated to 512 characters
- [x] PII scrubbed before IPC transmission (8 patterns)
- [ ] **OPEN**: Dwell time in blocked apps leaked (Finding 12)
- [ ] **OPEN**: Private browsing detection is locale-dependent (Finding 9)

### Consent Integrity
- [x] Per-event consent guard available (`isCapturePermitted`)
- [x] State change handler infrastructure in place
- [x] Revocation handler infrastructure in place
- [ ] **OPEN**: Neither handler infrastructure is wired in AppDelegate (New Finding 1)
- [ ] **OPEN**: Capture state not persisted across restarts (Finding 11)

### IPC Security
- [x] Symlink attack prevention on socket path (`SocketClient.swift:41-49`)
- [x] Auth token handshake support (`SocketClient.swift:86-96`)
- [x] ndjson serialization with schema versioning
- [x] Idempotency keys supported
- [x] Exponential backoff reconnection with cap (`SocketClient.swift:122-133`)

---

## Risk Assessment (Updated)

**Overall Security Posture**: MODERATE-GOOD (improved from MODERATE)

The remediation PRs addressed all CRITICAL and HIGH findings from the original audit. The capture layer now demonstrates stronger data minimization, safer PII filtering, correct access control defaults, and proper logging hygiene. The remaining findings are design-level issues (unpersisted state, locale-dependent detection, unwired handler infrastructure) that do not represent immediate exploitation risks but affect consent integrity and international deployment readiness.

**Risk Score**: 7.5 / 10 (improved from 6.5 / 10)

| Category | Before | After | Change | Notes |
|----------|:------:|:-----:|:------:|-------|
| Data Minimization | 5/10 | 8/10 | +3 | Mouse coords removed; dwell time leak remains |
| PII Protection | 7/10 | 8/10 | +1 | 8 patterns; locale gap in private browsing |
| Consent Integrity | 6/10 | 7/10 | +1 | Guard + handler infra added; wiring missing |
| Access Control | 7/10 | 9/10 | +2 | nil bundleId denied; socket symlink check; HMAC signing |
| Logging Hygiene | 4/10 | 8/10 | +4 | All AgentLogger now .private |
| Implementation Completeness | 6/10 | 6/10 | 0 | CGEventTap still unimplemented |
| Thread Safety | 8/10 | 9/10 | +1 | BlocklistManager converted to actor |

**Priority Remediation Order (remaining items)**:
1. Wire `ConsentManager.onRevocation` and `CaptureStateManager.onStateChange` handlers in AppDelegate (MEDIUM, before beta)
2. Fix blocked-app dwell time leak — set `lastSwitchTime = nil` (LOW, before beta)
3. Improve private browsing detection with AXPrivate and locale-independent checks (MEDIUM, before international deployments)
4. Add compile-time guards on unimplemented event types (MEDIUM, before GA)
5. Persist capture state across restarts (LOW, before GA)
6. Mandatory re-audit when CGEventTap is implemented (blocking for GA)

---

## Positive Security Improvements Since Original Audit

The following improvements were observed beyond the specific finding remediations:

1. **BlocklistManager converted to Swift actor** — eliminates manual NSLock synchronization (thread safety improvement)
2. **IdleDetector converted to Swift actor** — same benefit
3. **ConsentManager revocation handler pattern** — extensible cleanup architecture
4. **CaptureStateManager transition handler pattern** — extensible monitor lifecycle architecture
5. **HMAC-signed consent records** — `KeychainConsentStore` now signs records with HMAC-SHA256 using a per-install key
6. **Keychain items prevent iCloud sync** — `kSecAttrSynchronizable: false` explicitly set
7. **Backend URL validation** — `PythonProcessManager` validates https scheme and host before setting `KMFLOW_BACKEND_URL`
8. **MDM config bounds clamping** — `AgentConfig.init?(fromMDMProfile:)` uses `clamp()` to enforce min/max on all integer config values
9. **Integrity manifest HMAC verification** — `IntegrityChecker` now verifies `integrity.sig` HMAC before trusting the manifest
10. **SocketClient symlink protection** — `lstat()` check rejects symlinked socket paths
11. **SocketClient auth handshake** — optional shared-secret authentication on IPC connection
12. **L2PIIFilter debug assertion** — asserts all regex patterns compiled in debug builds, gracefully degrades in release

---

*Re-audit completed 2026-02-26. Next mandatory audit trigger: CGEventTap implementation landing.*
