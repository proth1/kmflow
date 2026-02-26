# E2: Capture Layer Security Audit

**Agent**: E2 (Capture Layer Auditor)
**Date**: 2026-02-25
**Scope**: macOS Task Mining Agent — Swift capture layer (10 source files, ~837 lines)
**Auditor Model**: Claude Opus 4.6

---

## Executive Summary

The KMFlow macOS Task Mining Agent capture layer demonstrates a **security-conscious design** with a multi-layered PII defense (L1 blocklist/prevention + L2 regex scrubbing), protocol-abstracted components for testability, and a consent-first lifecycle. However, the audit identified **13 findings** across severity levels that require attention, including a critical gap where mouse coordinate data is captured but not documented to users, a design-level concern about a `content_level` capture mode that references keystroke capture, and multiple medium-severity issues around blocklist bypass, logging hygiene, and missing socket file permissions.

### Finding Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1     |
| HIGH     | 3     |
| MEDIUM   | 6     |
| LOW      | 3     |
| **Total** | **13** |

### Positive Security Observations

Before detailing findings, several design decisions deserve recognition:

- **No keystroke content captured in current code**: `InputMonitor.swift` only counts events; no `getIntegerValueField(.keyboardEventKeycode)` or `keyboardString` calls exist in the codebase.
- **No screenshot implementation exists**: Despite config flags, no actual `CGWindowListCreateImage`, `SCStream`, or pixel-capture code was found in the Swift sources.
- **No clipboard access**: No `NSPasteboard` or `UIPasteboard` usage found in capture code.
- **No screen recording implementation**: The `screenCapture` event type exists in the protocol enum but has no producer code.
- **L1 + L2 PII defense in depth**: Password fields blocked at L1 (AXSecureTextField), PII scrubbed at L2 (regex) before IPC transmission.
- **Hardcoded password manager blocklist**: 1Password, LastPass, Bitwarden, Dashlane, Keychain Access always blocked.
- **Private browsing detection**: Safari, Chrome, Firefox, Arc, Edge private windows suppressed.
- **Consent-first architecture**: No capture occurs until explicit three-checkbox consent is granted.
- **Window title length limit**: 512-character truncation prevents memory exhaustion.
- **Thread safety**: NSLock used consistently in IdleDetector, InputAggregator, BlocklistManager.
- **Protocol-based testability**: WorkspaceObserver, InputEventSource, AccessibilityProvider, ConsentStore all abstracted.
- **Integrity checking**: SHA-256 manifest verification of Python bundle at launch.

---

## Findings

### [CRITICAL] DATA MINIMIZATION: Mouse Coordinate Capture Exceeds Stated Purpose

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/InputMonitor.swift:19-21`
**Agent**: E2 (Capture Layer Auditor)
**Evidence**:
```swift
public enum InputEvent: Sendable {
    case keyDown(timestamp: Date)
    case keyUp(timestamp: Date)
    case mouseDown(button: MouseButton, x: Double, y: Double, timestamp: Date)
    case mouseUp(button: MouseButton, x: Double, y: Double, timestamp: Date)
    case mouseDrag(x: Double, y: Double, timestamp: Date)
```
**Description**: The `InputEvent` enum captures exact mouse X/Y coordinates for `mouseDown`, `mouseUp`, and `mouseDrag` events. While the `InputAggregator` currently only increments counters (discarding coordinates), the data model itself carries precise screen coordinates through the type system. This is a data minimization violation under GDPR Article 5(1)(c) and represents an undisclosed capability. The consent UI tells users "KMFlow will observe my application usage patterns" — it does not disclose mouse position tracking. If any future code path serializes raw `InputEvent` values instead of going through `InputAggregator.flush()`, exact mouse positions would be transmitted. The `CaptureEvent.eventData` field (`[String: AnyCodable]?`) is a generic dictionary that could trivially carry these coordinates.

**Risk**: (1) Mouse coordinates can reveal what a user clicked on within a UI — password fields, specific form elements, text selections. Combined with window titles and timestamps, this constitutes a detailed behavioral reconstruction capability that exceeds what is disclosed. (2) Any future contributor who wires raw `InputEvent` values to IPC will inadvertently transmit coordinate data without additional review gates.

**Recommendation**: Remove `x: Double, y: Double` parameters from `mouseDown`, `mouseUp`, and `mouseDrag` cases in `InputEvent`. If coordinates are truly needed in the future, they should be (a) explicitly disclosed in the consent flow, (b) quantized/binned to reduce precision (e.g., screen quadrant only), and (c) gated behind a separate consent toggle.

---

### [HIGH] UNDISCLOSED CAPABILITY: content_level Mode References Keystroke Capture

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/InputMonitor.swift:1-5`
**Agent**: E2 (Capture Layer Auditor)
**Evidence**:
```swift
/// Keyboard and mouse action counting via CGEventTap.
///
/// In ACTION_LEVEL mode (default), only counts and timing are captured.
/// In CONTENT_LEVEL mode, actual keystrokes are captured (with L2 PII filtering).
/// Password fields (AXSecureTextField) are NEVER captured at any level.
```
**Also**: `/Users/proth/repos/kmflow/agent/macos/Sources/Config/AgentConfig.swift:84-87`
```swift
public enum CaptureGranularity: String, Codable, Sendable {
    case actionLevel = "action_level"
    case contentLevel = "content_level"
}
```
**Also**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/Onboarding/ConsentView.swift:58-63`
```swift
Picker("Capture Scope", selection: $state.captureScope) {
    Text("Activity Level (counts only)")
        .tag("action_level")
    Text("Content Level (with PII filtering)")
        .tag("content_level")
}
```
**Description**: The codebase explicitly references a `content_level` capture mode that would capture "actual keystrokes" (per the InputMonitor.swift header comment). While no implementation of keystroke content capture exists in the current code, the infrastructure is in place: (1) the `CaptureGranularity` enum defines `contentLevel`, (2) the onboarding UI allows users to select it, (3) the MDM profile supports it, and (4) the `DesktopEventType` enum includes `copyPaste`, `urlNavigation`, `fileOpen`, `fileSave` event types that imply content-level capture. This means the agent can be configured to a mode that promises keystroke capture even though no implementation exists yet — creating a misleading consent flow and a future surface area for keystroke logging.

**Risk**: (1) A user who selects "Content Level" expects a specific behavior that does not exist, creating informed consent issues. (2) When keystroke capture is eventually implemented, it will be a keylogger — one of the most privacy-sensitive capabilities possible. The current code establishes the scaffolding for this without the corresponding security controls (key content PII filtering, per-field suppression beyond password fields, data retention limits on keystroke data).

**Recommendation**: Either (a) remove the `content_level` option from the UI until implementation is complete with full security review, or (b) clearly mark it as "Coming Soon" in the UI and disable it as a selectable option. The consent UI label "Content Level (with PII filtering)" is dangerously vague about what "content" means — if retained, it must explicitly state "captures typed text".

---

### [HIGH] PRIVACY: Blocklist Bypass via nil bundleIdentifier

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Config/BlocklistManager.swift:33-34`
**Agent**: E2 (Capture Layer Auditor)
**Evidence**:
```swift
public func shouldCapture(bundleId: String?) -> Bool {
    guard let bid = bundleId else { return true }
    lock.lock()
    defer { lock.unlock() }
```
**Description**: When `bundleId` is `nil`, `shouldCapture` returns `true` (allow capture). On macOS, applications launched from certain paths, command-line tools promoted to foreground, and some helper agents do not have a `bundleIdentifier`. This means an app without a bundle ID bypasses both the blocklist AND the allowlist. A user could launch a sensitive application (e.g., a password manager compiled from source without an Info.plist, or a CLI tool displaying secrets via a terminal window that loses its bundle ID context) and have it fully captured.

**Risk**: Applications without bundle IDs — which are by definition unidentifiable — should be treated as higher risk, not lower risk. Defaulting to "capture everything from unknown sources" inverts the security principle of least privilege.

**Recommendation**: Change the `nil` bundleId behavior to `return false` (deny by default). When the allowlist is in use (positive security model), unknown apps should never be captured. When only the blocklist is active, the decision is less clear-cut, but a conservative default of "do not capture unidentified apps" is safer.

---

### [HIGH] LOGGING: All os_log Messages Marked privacy: .public

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Utilities/Logger.swift:13-27`
**Agent**: E2 (Capture Layer Auditor)
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
**Description**: Every log level in `AgentLogger` uses `privacy: .public`, which means all log messages are visible in macOS Console.app, `log stream`, sysdiagnose bundles, and crash reports without any redaction. Apple's Unified Logging system redacts `privacy: .private` values by default, only exposing them when a logging profile is installed. By marking everything `.public`, any log message that accidentally includes a window title, engagement ID, backend URL, or user name will persist in plaintext in system logs accessible to any admin on the machine or via sysdiagnose submitted to Apple.

**Risk**: (1) If any caller passes user-identifiable data (window titles, app names, engagement IDs) through the logger, it persists in system logs with no time-based expiration control. (2) `NSLog` calls in `KMFlowAgentApp.swift:50` directly interpolate `violations` arrays which could contain file paths exposing the user's directory structure. (3) sysdiagnose bundles sent to Apple for crash analysis would include this data.

**Recommendation**: Change the default privacy level to `.private` for `info` and `debug` levels. Use `.public` only for `error` and only for messages that are known to contain no user data. Audit all call sites to ensure no PII-adjacent data (window titles, URLs, engagement IDs) is logged.

---

### [MEDIUM] RACE CONDITION: CaptureStateManager Lacks Atomic Pause Synchronization

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/CaptureStateManager.swift:18-41`
**Agent**: E2 (Capture Layer Auditor)
**Evidence**:
```swift
@MainActor
public final class CaptureStateManager: ObservableObject {
    @Published public private(set) var state: CaptureState = .idle

    public func startCapture() {
        guard state == .idle || state == .paused else { return }
        state = .capturing
        errorMessage = nil
    }

    public func pauseCapture() {
        guard state == .capturing else { return }
        state = .paused
    }
```
**Description**: `CaptureStateManager` is `@MainActor`-isolated, meaning state transitions run on the main thread. However, the actual capture monitors (`SystemAppSwitchMonitor`, `InputAggregator`, `IdleDetector`) use their own NSLock-based synchronization and run on background threads/run loops. When `pauseCapture()` sets `state = .paused` on the main thread, there is no mechanism to signal the CGEventTap run loop, NSWorkspace notification observer, or InputAggregator to stop. The `AppDelegate` does not wire `pauseCapture` to call `stopObserving()` on the monitors. This means events continue to be captured and processed even while the UI shows "Paused".

**Risk**: Users who pause monitoring expect all capture to stop immediately. If the monitors continue running and feeding events to the IPC socket, the user's expectation of control is violated. This is a consent integrity issue — the user revoked ongoing consent by pausing, but capture continues.

**Recommendation**: Wire `CaptureStateManager.pauseCapture()` to a coordinated shutdown sequence that calls `stopObserving()` on `SystemAppSwitchMonitor`, stops the CGEventTap (when implemented), and flushes/discards the `InputAggregator` buffer. Use a `didSet` observer on `state` or a Combine publisher to trigger monitor lifecycle changes.

---

### [MEDIUM] PRIVACY: Event Protocol Defines Sensitive Event Types Without Producers

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/IPC/EventProtocol.swift:11-29`
**Agent**: E2 (Capture Layer Auditor)
**Evidence**:
```swift
public enum DesktopEventType: String, Codable, CaseIterable, Sendable {
    case appSwitch = "app_switch"
    case windowFocus = "window_focus"
    case mouseClick = "mouse_click"
    case mouseDoubleClick = "mouse_double_click"
    case mouseDrag = "mouse_drag"
    case keyboardAction = "keyboard_action"
    case keyboardShortcut = "keyboard_shortcut"
    case copyPaste = "copy_paste"
    case scroll = "scroll"
    case tabSwitch = "tab_switch"
    case fileOpen = "file_open"
    case fileSave = "file_save"
    case urlNavigation = "url_navigation"
    case screenCapture = "screen_capture"
    case uiElementInteraction = "ui_element_interaction"
```
**Description**: The event type enum declares 17 event types, but the current capture layer only produces a subset (app_switch, keyboard_action, mouse_click, scroll, idle_start, idle_end). The remaining types — `copyPaste`, `urlNavigation`, `fileOpen`, `fileSave`, `screenCapture`, `uiElementInteraction`, `keyboardShortcut`, `tabSwitch` — have no Swift-side producers but define a contract with the Python layer. Several of these types (`copyPaste` requires clipboard access, `screenCapture` requires pixel capture, `urlNavigation` captures browsing history) represent significant privacy escalations that would each warrant their own security review if implemented. Their presence in the protocol creates implicit authorization for future implementation without an additional review gate.

**Risk**: A developer implementing `copyPaste` could add `NSPasteboard.general.string(forKey: .string)` and wire it to this existing event type without recognizing the privacy implications, because the event type already exists and appears "approved." Similarly, `screenCapture` normalizes the concept of pixel capture in the protocol layer.

**Recommendation**: Add a `@available(*, unavailable, message: "Not yet implemented — requires security review")` annotation (or equivalent compile-time guard) to event types that have no producer. Alternatively, move unimplemented event types to a separate `FutureDesktopEventType` enum that cannot be used in `CaptureEvent` construction.

---

### [MEDIUM] PRIVACY: Screenshot Configuration Present Without Implementation Guardrails

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Config/AgentConfig.swift:13-14, 25-26`
**Agent**: E2 (Capture Layer Auditor)
**Evidence**:
```swift
public var screenshotEnabled: Bool
public var screenshotIntervalSeconds: Int
// ...
screenshotEnabled: Bool = false,
screenshotIntervalSeconds: Int = 30,
```
**Description**: `AgentConfig` includes `screenshotEnabled` and `screenshotIntervalSeconds` fields that can be set via backend config or MDM profile. While `screenshotEnabled` defaults to `false` and no screenshot implementation exists in the Swift capture layer, the MDM profile (`com.kmflow.agent.tcc.mobileconfig`) pre-provisions Screen Recording TCC permissions. This means an MDM administrator could set `screenshotEnabled = true` and `screenshotIntervalSeconds = 5` via managed preferences, and when screenshot capture is eventually implemented, it would activate silently without additional user consent — the TCC permission was already granted during enrollment.

**Risk**: MDM-managed devices could have screenshot capture enabled remotely without the user being informed, because the TCC permission was pre-approved. A 5-second screenshot interval on a 1920x1080 display at PNG quality would generate ~2-5 MB per frame, or 360-900 MB per hour — a significant data exfiltration vector.

**Recommendation**: (1) Add a minimum floor to `screenshotIntervalSeconds` (e.g., 30 seconds minimum, enforced in the `init`). (2) When screenshot capture is implemented, require a separate, explicit user consent acknowledgment beyond the initial onboarding flow. (3) Add a `screenshotMaxDailyCount` limit. (4) Validate config values from MDM/backend: reject intervals below the floor, reject `screenshotEnabled = true` if Screen Recording permission is not granted.

---

### [MEDIUM] IPC SECURITY: Unix Domain Socket Created Without Explicit Permission Enforcement

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/IPC/SocketClient.swift:10-13`
**Agent**: E2 (Capture Layer Auditor)
**Evidence**:
```swift
public static let defaultSocketPath: String = {
    let home = NSHomeDirectory()
    return "\(home)/Library/Application Support/KMFlowAgent/agent.sock"
}()
```
**Description**: The Unix domain socket is created at `~/Library/Application Support/KMFlowAgent/agent.sock`. The `SocketClient` connects to this path but does not verify or set file permissions on the socket file or its parent directory. While macOS user home directories default to `0o700` permissions, the `Application Support` directory is `0o755` and the `KMFlowAgent` subdirectory permissions depend on how it was created. If another application on the same user account (or a compromised process) can connect to this socket, it could inject fabricated events into the Python intelligence layer, potentially poisoning process mining analysis or exfiltrating data by reading socket traffic.

**Risk**: (1) A malicious local process could connect to the socket and inject fake `CaptureEvent` records (e.g., fake app switches, fake window titles) to manipulate process mining results. (2) If the Python layer echoes data back on the socket, a listener could capture the stream.

**Recommendation**: (1) Set the `KMFlowAgent` directory permissions to `0o700` at creation time. (2) Verify the socket file permissions are `0o600` (owner-only read/write) before connecting. (3) Consider implementing a shared secret or nonce handshake between the Swift and Python layers to authenticate the socket connection.

---

### [MEDIUM] RESILIENCE: Private Browsing Detection is Fragile and Bypass-Prone

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/PII/L1Filter.swift:54-89`
**Agent**: E2 (Capture Layer Auditor)
**Evidence**:
```swift
public static func isPrivateBrowsing(
    bundleId: String?,
    windowTitle: String?
) -> Bool {
    guard let title = windowTitle else { return false }

    // Safari private browsing
    if bundleId == "com.apple.Safari" {
        if title.contains("Private Browsing") { return true }
    }

    // Chrome incognito
    if bundleId == "com.google.Chrome" {
        if title.hasSuffix("- Incognito") { return true }
    }
```
**Description**: Private browsing detection relies on hardcoded string matching against window titles. This approach has several weaknesses: (1) Browser localization: "Private Browsing" and "Incognito" are English strings. A user with macOS set to German, French, Japanese, or any other language will have localized window titles that bypass this check entirely. (2) Browser updates: if Chrome changes its title format from "Page Title - Incognito" to "Page Title (Incognito)", the `hasSuffix` check fails. (3) Missing browsers: Brave (`com.brave.Browser`), Vivaldi (`com.vivaldi.Vivaldi`), Opera (`com.operasoftware.Opera`), and Tor Browser are not covered. (4) `nil` windowTitle returns `false` (not detected), but a private browsing window could have a nil title during loading.

**Risk**: Users in non-English locales, using uncovered browsers, or when browser title formats change will have their private browsing sessions captured — violating the privacy guarantee displayed in the consent flow and the transparency log UI.

**Recommendation**: (1) Add the Accessibility API check for the `AXPrivate` attribute on browser windows, which is locale-independent. (2) Expand browser coverage to include Brave, Vivaldi, Opera, Tor Browser. (3) Default `nil` windowTitle to "detected" (suppressed) when the bundleId matches a known browser. (4) Consider maintaining private browsing patterns as a server-updateable configuration rather than hardcoded strings.

---

### [MEDIUM] DATA INTEGRITY: L2 PII Filter Missing Common PII Patterns

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/WindowTitleCapture.swift:12-54`
**Agent**: E2 (Capture Layer Auditor)
**Evidence**:
```swift
public struct L2PIIFilter: Sendable {
    /// SSN with dashes: 123-45-6789
    private static let ssnDashed = try! NSRegularExpression(
        pattern: #"\b\d{3}-\d{2}-\d{4}\b"#
    )
    /// Email address
    private static let email = try! NSRegularExpression(...)
    /// US phone numbers
    private static let phone = try! NSRegularExpression(...)
    /// Credit card
    private static let creditCard = try! NSRegularExpression(...)
    /// AmEx
    private static let amex = try! NSRegularExpression(...)
```
**Description**: The L2 PII filter covers 5 patterns: SSN (dashed only), email, US phone, Visa/MC/Discover/JCB credit cards, and AmEx. Notable gaps include: (1) SSN without dashes (e.g., `123456789` — common in URLs and document titles). (2) Non-US patterns: no IBAN, no NHS numbers, no Canadian SIN, no passport numbers. (3) No date-of-birth pattern (though this is admittedly hard to distinguish from other dates). (4) No IP addresses (which can appear in terminal/IDE window titles and identify internal infrastructure). (5) No Mastercard 2-series (`2[2-7]\d{2}`) credit card pattern. (6) Window titles from banking apps often show partial account numbers (last 4 digits with prefix) that don't match full card patterns.

**Risk**: PII in window titles that doesn't match any of the 5 patterns will pass through to the Python layer and be stored in the SQLite buffer. For a tool deployed internationally (consulting engagements may be in any country), US-only patterns are insufficient.

**Recommendation**: (1) Add SSN without dashes pattern. (2) Add `piiPatternsVersion` to AgentConfig (already exists but unused in Swift — wire it to load patterns from server). (3) Consider a more conservative approach: if a window title matches a financial application bundleId, redact the entire title rather than relying on pattern matching. (4) Add IP address pattern (`\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b`).

---

### [LOW] DESIGN: CaptureStateManager Does Not Persist State Across Restarts

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/CaptureStateManager.swift:20-27`
**Agent**: E2 (Capture Layer Auditor)
**Evidence**:
```swift
@MainActor
public final class CaptureStateManager: ObservableObject {
    @Published public private(set) var state: CaptureState = .idle
    @Published public private(set) var eventCount: UInt64 = 0
    @Published public private(set) var lastEventAt: Date?
    @Published public private(set) var errorMessage: String?

    private var sequenceCounter: UInt64 = 0

    public init() {}
```
**Description**: `CaptureStateManager` initializes to `.idle` state with a zero sequence counter on every app launch. State is not persisted to disk or Keychain. This means: (1) If a user pauses the agent and it restarts (crash, macOS update, reboot), capture resumes from `.idle` and the `KMFlowAgentApp.applicationDidFinishLaunching` flow checks consent and starts Python — effectively unpausing. (2) The `sequenceCounter` resets to 0 on every launch, which means sequence numbers are not globally unique and could cause deduplication issues in the Python layer if it relies on monotonic sequence numbers.

**Risk**: A user who paused monitoring loses their pause state on any app restart, violating the expectation that "paused means paused until I say otherwise." For compliance-sensitive deployments, this could constitute a consent violation.

**Recommendation**: (1) Persist `CaptureState` to UserDefaults or Keychain, defaulting to the persisted state on launch. (2) Persist `sequenceCounter` to ensure monotonic numbering across restarts, or use a UUID-based idempotency key (which `CaptureEvent` already supports via `idempotencyKey`).

---

### [LOW] DEFENSE IN DEPTH: AppSwitchMonitor Blocklist Check Does Not Cover fromApp Leakage

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/AppSwitchMonitor.swift:68-98`
**Agent**: E2 (Capture Layer Auditor)
**Evidence**:
```swift
// L1 blocklist check
guard self.blocklistManager.shouldCapture(bundleId: bundleId) else {
    // Update tracking but don't emit event
    self.lastAppName = nil
    self.lastBundleId = nil
    self.lastSwitchTime = Date()
    return
}
// ...
let event = AppSwitchEvent(
    fromApp: self.lastAppName,
    fromBundleId: self.lastBundleId,
    toApp: appName,
    toBundleId: bundleId,
    dwellMs: dwellMs,
    timestamp: now
)
```
**Description**: When a blocklisted app becomes frontmost, the monitor correctly suppresses the event and clears `lastAppName`/`lastBundleId` to `nil`. This means the NEXT switch (from blocklisted app to a non-blocklisted app) will emit an event with `fromApp: nil` and `fromBundleId: nil`. However, consider this sequence: (A) User is in Safari -> (B) User switches to 1Password (blocked) -> (C) User switches to Slack. At step C, `fromApp` is `nil`, which is correct. But the `dwellMs` field reveals exactly how long the user spent in the blocked app — the time between step B (when `lastSwitchTime` was set) and step C. This dwell time in a password manager is itself sensitive metadata (long dwell = complex password change? multiple account lookups?).

**Risk**: Dwell time in blocklisted applications leaks behavioral information about the user's interaction with sensitive apps, even though the app name is suppressed.

**Recommendation**: When a blocklisted app is detected, also reset `lastSwitchTime` to `nil` (not `Date()`) so that the subsequent event reports `dwellMs: 0` instead of revealing the time spent in the blocked app.

---

### [LOW] COMPLETENESS: No CGEventTap Implementation Exists for Audit

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/InputMonitor.swift:10-14`
**Agent**: E2 (Capture Layer Auditor)
**Evidence**:
```swift
/// Protocol for keyboard/mouse event sources (testable abstraction over CGEventTap).
public protocol InputEventSource: AnyObject {
    func start(handler: @escaping (InputEvent) -> Void) throws
    func stop()
}
```
**Description**: The `InputEventSource` protocol abstracts CGEventTap, and `InputAggregator` aggregates events, but no concrete implementation of `InputEventSource` (i.e., no actual `CGEventTapCreate` call) exists anywhere in the Swift source files. A search for `CGEventTapCreate`, `CGEventTap`, `cghidEventTap`, `cgSessionEventTap`, `.listenOnly`, `.defaultTap`, `keyboardEventKeycode`, `keyboardString`, and `getIntegerValueField` across the entire `agent/macos/` directory returned zero matches in Swift source files (only references in comments, entitlements, and mobileconfig files). This means the most security-critical component — the actual event tap that intercepts system-wide keyboard and mouse events — has not yet been written and therefore cannot be audited.

**Risk**: When the CGEventTap implementation is written, it will be the highest-risk component in the entire agent. The specific audit checks (passive `.listenOnly` vs active tap, event mask scope, keycode access, session vs global tap) cannot be performed until the implementation exists.

**Recommendation**: When implementing the concrete `InputEventSource`: (1) Use `CGEventTapCreate` with `.cgSessionEventTap` (session-level, not global), (2) Use `.listenOnly` placement (NEVER `.defaultTap` which can modify events), (3) Set the event mask to the minimum needed (`CGEventMask(1 << CGEventType.keyDown.rawValue) | CGEventMask(1 << CGEventType.leftMouseDown.rawValue)`), (4) NEVER call `event.getIntegerValueField(.keyboardEventKeycode)` or access `CGEvent` character data in the callback, (5) Disable the tap via `CGEvent.tapEnable(tap:, enable:)` when capture is paused. This finding should trigger a mandatory re-audit of the E2 scope when the implementation lands.

---

## Security Checklist Verification

### Credentials & Secrets
- [x] No hardcoded passwords, API keys, or secrets in capture layer code
- [x] Consent stored in macOS Keychain (not UserDefaults or files)
- [ ] **PARTIAL**: Secrets not logged — all log messages are `privacy: .public` (Finding #4)

### OWASP Top 10 Verification (adapted for native client)
- [x] No SQL injection risk (SQLite queries use parameterized statements in TransparencyLogController)
- [x] No XSS (native app, no web views in capture layer)
- [x] No CSRF (no HTTP endpoints)
- [x] Authentication: Consent-first design with three explicit checkboxes
- [ ] **PARTIAL**: Authorization — blocklist bypass via nil bundleId (Finding #3)
- [x] Data encryption: Buffer encryption key provisioned via Keychain (not yet active)
- [x] Security headers: N/A for native app
- [ ] **PARTIAL**: Input validation — no min/max validation on MDM config integers (Finding #7)
- [ ] **FAIL**: Logging without sensitive data — all logs marked public (Finding #4)
- [x] No third-party dependencies in capture layer (pure Apple frameworks)

### Data Minimization (GDPR Article 5(1)(c))
- [ ] **FAIL**: Mouse coordinates captured in event model (Finding #1)
- [ ] **FAIL**: Dwell time in blocked apps leaked (Finding #12)
- [x] Window titles truncated to 512 characters
- [x] PII scrubbed before IPC transmission

### API/IPC Security
- [ ] **PARTIAL**: Socket path in user directory but no permission enforcement (Finding #8)
- [x] ndjson serialization with schema versioning (IPCMessage.version = 1)
- [x] Idempotency keys supported in CaptureEvent

---

## Risk Assessment

**Overall Security Posture**: MODERATE

The capture layer demonstrates thoughtful security architecture with protocol-based abstraction, multi-layer PII filtering, consent-first lifecycle, and integrity checking. However, several design-level privacy issues (mouse coordinates in the data model, content_level scaffolding, blocklist bypass for nil bundleIDs) represent risks that compound when considered together. The most significant gap is the absence of the actual CGEventTap implementation, which is the highest-risk component and cannot be audited yet.

**Risk Score**: 6.5 / 10

| Category | Score | Notes |
|----------|-------|-------|
| Data Minimization | 5/10 | Mouse coords, dwell time leakage, broad event type enum |
| PII Protection | 7/10 | L1+L2 defense, but gaps in L2 patterns and locale coverage |
| Consent Integrity | 6/10 | Good initial flow, but pause doesn't stop monitors, state not persisted |
| Access Control | 7/10 | Keychain-backed consent, but socket lacks permission checks |
| Logging Hygiene | 4/10 | All public privacy, NSLog with interpolated data |
| Implementation Completeness | 6/10 | Core event tap not yet implemented, screenshot config without guardrails |
| Thread Safety | 8/10 | Consistent NSLock usage, actor isolation for IPC |

**Priority Remediation Order**:
1. Remove mouse coordinates from InputEvent enum (CRITICAL, immediate)
2. Disable content_level UI option until implemented (HIGH, immediate)
3. Fix nil bundleId blocklist bypass (HIGH, immediate)
4. Fix logger privacy levels (HIGH, before any production deployment)
5. Wire pause/resume to actual monitor lifecycle (MEDIUM, before beta)
6. Add socket permission checks (MEDIUM, before beta)
7. Expand PII patterns and private browsing detection (MEDIUM, before international deployments)
8. Persist capture state and sequence counter (LOW, before GA)
9. Mandatory re-audit when CGEventTap is implemented (blocking for GA)
