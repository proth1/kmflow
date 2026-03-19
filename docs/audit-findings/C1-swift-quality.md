# C1: Swift Code Quality Audit

**Agent**: C1 (Swift Code Quality Auditor)
**Scope**: `/Users/proth/repos/kmflow/agent/macos/Sources/` (31 files, 4,690 lines)
**Audit Date**: 2026-02-28
**Auditor Model**: Claude Sonnet 4.6

---

## Executive Summary

The macOS Swift agent codebase is well-structured overall. The concurrency model has been substantially improved through consistent use of Swift actors (`IdleDetector`, `InputAggregator`, `BlocklistManager`, `VCECaptureManager`, `PythonProcessManager`, `IntegrityChecker`, `SocketClient`) and `@MainActor` on all UI classes. No `try!` or `as!` force-casts exist. No `print()` or `NSLog()` calls exist — all logging uses `os.Logger` via `AgentLogger`. No `Thread.sleep` blocking calls exist.

The primary remaining issues are: one force-unwrap in a security path that can silently degrade HMAC protection, an `@unchecked Sendable` in a shared test-helper class that ships in production targets, a blocking `FileHandle.availableData` call in the IPC auth handshake, and several lower-severity issues around error surfacing and API deprecation.

---

## Finding Summary

| ID | Severity | Category | Title | File |
|----|----------|----------|-------|------|
| C1-H1 | HIGH | MEMORY-SAFETY | Force-unwrap of baseAddress in HMAC key generation | `KeychainConsentStore.swift:268`, `TransparencyLogController.swift:362` |
| C1-H2 | HIGH | CONCURRENCY | Blocking FileHandle.availableData in actor async context | `SocketClient.swift:102` |
| C1-H3 | HIGH | ERROR-HANDLING | KeychainConsentStore.save silently discards encoding failures | `KeychainConsentStore.swift:137,140` |
| C1-H4 | HIGH | CONCURRENCY | AppSwitchMonitor defers @MainActor without enforcement | `AppSwitchMonitor.swift:44-45` |
| C1-M1 | MEDIUM | SENDABILITY | InMemoryConsentStore ships in production with @unchecked Sendable | `ConsentManager.swift:76` |
| C1-M2 | MEDIUM | CONCURRENCY | Task.detached in IntegrityChecker.startPeriodicChecks may outlive actor | `IntegrityChecker.swift:105` |
| C1-M3 | MEDIUM | API-DEPRECATION | NSApp.activate(ignoringOtherApps:) deprecated in macOS 14 | `OnboardingWindow.swift:80` |
| C1-M4 | MEDIUM | DESIGN | AnyCodable.value typed as `any Sendable` loses type erasure safety | `EventProtocol.swift:80` |
| C1-M5 | MEDIUM | ERROR-HANDLING | HMAC key generation returns empty Data() on CSPRNG failure | `KeychainConsentStore.swift:275` |
| C1-L1 | LOW | STYLE | displayName(for:) duplicated in TransparencyLogView and EventRow | `TransparencyLogView.swift:139,220` |
| C1-L2 | LOW | DESIGN | CaptureContextFilter.chromiumRaw bundle ID likely incorrect | `CaptureContextFilter.swift:49` |
| C1-L3 | LOW | STYLE | ConnectionView health check does not validate URL scheme | `ConnectionView.swift:219-238` |
| C1-L4 | LOW | DESIGN | AgentLogger wraps every message with privacy: .private losing context | `Logger.swift:14,18,22,26` |

---

## Findings

---

### [HIGH] MEMORY-SAFETY: Force-unwrap of UnsafeMutableRawBufferPointer.baseAddress

**File**: `agent/macos/Sources/Consent/KeychainConsentStore.swift:268`
**Also at**: `agent/macos/Sources/UI/TransparencyLogController.swift:362`
**Agent**: C1 (Swift Code Quality Auditor)
**Evidence**:
```swift
let result = key.withUnsafeMutableBytes { ptr in
    SecRandomCopyBytes(kSecRandomDefault, 32, ptr.baseAddress!)
}
```
**Description**: `ptr.baseAddress` is force-unwrapped with `!`. For a non-empty `Data` buffer (count: 32), `baseAddress` will never be nil in practice because `withUnsafeMutableBytes` on a non-empty `Data` guarantees a non-nil pointer. However, the Swift API contract does not document this as guaranteed for all `Data` implementations, making this technically undefined behaviour territory. The same pattern appears in `BufferEncryptionManager.provisionKey()`.
**Risk**: In the extremely unlikely event `Data.withUnsafeMutableBytes` returns a nil `baseAddress`, the agent crashes rather than returning a recoverable error. This path is in the HMAC key generation and buffer encryption key provisioning routines — both are security-critical.
**Recommendation**: Replace the force-unwrap with a guard and return an error:
```swift
let result = key.withUnsafeMutableBytes { ptr -> OSStatus in
    guard let base = ptr.baseAddress else { return errSecMemoryError }
    return SecRandomCopyBytes(kSecRandomDefault, 32, base)
}
```

---

### [HIGH] CONCURRENCY: Blocking FileHandle.availableData in actor async context

**File**: `agent/macos/Sources/IPC/SocketClient.swift:102`
**Agent**: C1 (Swift Code Quality Auditor)
**Evidence**:
```swift
// Read server response to validate authentication was accepted.
let responseData = fh.availableData
if responseData.isEmpty {
    cleanupFileHandle()
    throw SocketError.connectionFailed("Server closed connection during auth handshake")
}
```
**Description**: `FileHandle.availableData` is a synchronous, blocking read. It returns whatever data is immediately in the kernel buffer. If the Python server has not yet written its auth response when this line executes (a common race condition over a Unix socket), `availableData` returns empty data — causing the client to erroneously conclude the server closed the connection and fail the auth handshake. Additionally, calling a blocking API inside a Swift actor method monopolizes the actor's executor thread for the duration of the read.
**Risk**: This is a race condition that can cause spurious connection failures during startup. When the auth handshake fails incorrectly, the agent falls back to plain event delivery — and if reconnect logic triggers, the backoff delay blocks the actor executor.
**Recommendation**: Replace the synchronous `availableData` with a proper async read using `NWConnection` or a `DispatchIO`-based approach. At minimum, use a read-with-timeout pattern:
```swift
// Use continuation-based async wrapper or NWConnection
let responseData = try await fh.readAvailableDataAsync(timeout: 5.0)
```

---

### [HIGH] ERROR-HANDLING: KeychainConsentStore.save silently discards encoding failures

**File**: `agent/macos/Sources/Consent/KeychainConsentStore.swift:137,140`
**Agent**: C1 (Swift Code Quality Auditor)
**Evidence**:
```swift
guard let recordData = try? jsonEncoder().encode(record) else { return }
let hmac = computeHMAC(data: recordData)
let signed = SignedConsentRecord(record: record, hmac: hmac)
guard let data = try? jsonEncoder().encode(signed) else { return }
keychainSave(account: accountKey(for: engagementId), data: data)
```
**Description**: Both `try?` calls on `jsonEncoder().encode()` silently swallow failures, returning without persisting consent state and without logging any error. If JSON encoding fails (e.g. due to a non-encodable value or an internal serialization bug), the user's consent grant is silently lost. On the next app launch, the consent state defaults to `.neverConsented` and the onboarding wizard re-appears — a confusing UX failure with no diagnostic information.
**Risk**: Silent consent record loss leads to users being repeatedly prompted for consent, potentially creating compliance audit gaps where consent was granted but not persisted. With no log output, this is very difficult to diagnose.
**Recommendation**: Convert `save` to a throwing function or add explicit error logging:
```swift
do {
    let recordData = try jsonEncoder().encode(record)
    let hmac = computeHMAC(data: recordData)
    let signed = SignedConsentRecord(record: record, hmac: hmac)
    let data = try jsonEncoder().encode(signed)
    keychainSave(account: accountKey(for: engagementId), data: data)
} catch {
    Self.log.error("Failed to encode consent record for \(engagementId): \(error)")
}
```

---

### [HIGH] CONCURRENCY: AppSwitchMonitor defers @MainActor annotation without enforcement

**File**: `agent/macos/Sources/Capture/AppSwitchMonitor.swift:44-46`
**Agent**: C1 (Swift Code Quality Auditor)
**Evidence**:
```swift
/// Concrete NSWorkspace-based observer.
///
/// All NSWorkspace notification observation and state updates run on the main
/// queue (`queue: .main`). Full `@MainActor` annotation is deferred until
/// BlocklistManager's `shouldCapture` is made nonisolated or async-compatible.
public final class SystemAppSwitchMonitor: WorkspaceObserver {
    private var observer: NSObjectProtocol?
    private var lastAppName: String?
    private var lastBundleId: String?
    private var lastSwitchTime: Date?
```
**Description**: The class comment acknowledges that `@MainActor` annotation is "deferred" because `BlocklistManager.shouldCapture` is now an actor method requiring `await`. However, the mutable state (`observer`, `lastAppName`, `lastBundleId`, `lastSwitchTime`) is mutated inside a `queue: .main` callback without compiler-verified isolation. This is documented-but-unresolved tech debt that relies on runtime behavior (`queue: .main`) rather than Swift's static concurrency checking.
**Risk**: If `startObserving` is ever called from a non-main thread, the mutation of `lastAppName`, `lastBundleId`, and `lastSwitchTime` becomes a data race. The `BlocklistManager` (an actor) is called synchronously via `self.blocklistManager.shouldCapture(bundleId:)` — but `BlocklistManager` is now an actor, meaning this call would not compile if `shouldCapture` were `async`. The comment indicates this is known and the actual call must be to a non-actor version.
**Recommendation**: Annotate `SystemAppSwitchMonitor` with `@MainActor` and make `BlocklistManager.shouldCapture` `nonisolated` for synchronous fast-path reads:
```swift
@MainActor
public final class SystemAppSwitchMonitor: WorkspaceObserver { ... }
// In BlocklistManager:
public nonisolated func shouldCaptureSync(bundleId: String?) -> Bool { ... }
```

---

### [MEDIUM] SENDABILITY: InMemoryConsentStore ships in production binary with @unchecked Sendable

**File**: `agent/macos/Sources/Consent/ConsentManager.swift:71-92`
**Agent**: C1 (Swift Code Quality Auditor)
**Evidence**:
```swift
/// In-memory consent store for testing.
///
/// Marked `@unchecked Sendable` because this is only used in single-threaded
/// test contexts. ...
public final class InMemoryConsentStore: ConsentStore, @unchecked Sendable {
    private var storage: [String: ConsentState] = [:]
    public init() {}
    public func load(engagementId: String) -> ConsentState {
        return storage[engagementId] ?? .neverConsented
    }
```
**Description**: `InMemoryConsentStore` is documented as a test helper but is declared `public` and lives in the production `Consent` module, not in a test target. It uses `@unchecked Sendable` to bypass the compiler's thread-safety checks, and its mutable `storage` dictionary is not protected by any lock, actor, or synchronization primitive. If accessed from multiple threads (which the `@unchecked Sendable` annotation explicitly allows callers to assume is safe), it is a data race.
**Risk**: Test code shipping in production binary increases attack surface and binary size. If a dependency or caller ever uses `InMemoryConsentStore` in a concurrent context (relying on its `@unchecked Sendable` claim), it is a data race crash waiting to happen.
**Recommendation**: Move `InMemoryConsentStore` to `ConsentTests/` or a dedicated `TestUtilities` module. If it must remain in the production target for dependency reasons, convert it to an actor.

---

### [MEDIUM] CONCURRENCY: Task.detached in IntegrityChecker.startPeriodicChecks references actor state unsafely

**File**: `agent/macos/Sources/KMFlowAgent/IntegrityChecker.swift:105-119`
**Agent**: C1 (Swift Code Quality Auditor)
**Evidence**:
```swift
periodicTask = Task.detached {
    while !Task.isCancelled {
        try? await Task.sleep(nanoseconds: UInt64(interval * 1_000_000_000))
        guard !Task.isCancelled else { break }

        let result = IntegrityChecker.verify(bundleResourcesPath: path)
        switch result {
```
**Description**: The `Task.detached` block captures `path`, `interval`, and `handler` by value (copied before the block executes), which is correct. However, `periodicTask` itself is an actor-isolated property, and the `Task.detached` block runs outside actor isolation. The `deinit` cancels `periodicTask`, but if `stopPeriodicChecks()` is called concurrently with the task reading `periodicTask`, there is no guarantee that cancellation is received atomically. More importantly, `Task.detached` runs on the global executor, not the actor's executor — if the violation handler captures actor state, it would be a cross-actor reference without `await`.
**Risk**: The `ViolationHandler` closure (type: `@Sendable (IntegrityResult) -> Void`) could capture non-Sendable values if callers aren't careful. The `@Sendable` annotation helps but does not prevent capturing actor-isolated state without `await`.
**Recommendation**: Prefer `Task { ... }` (inherits actor context) over `Task.detached { ... }` when calling from within an actor method. This gives the compiler the ability to enforce actor isolation boundaries on captured values.

---

### [MEDIUM] API-DEPRECATION: NSApp.activate(ignoringOtherApps:) deprecated in macOS 14

**File**: `agent/macos/Sources/UI/Onboarding/OnboardingWindow.swift:80`
**Agent**: C1 (Swift Code Quality Auditor)
**Evidence**:
```swift
win.makeKeyAndOrderFront(nil)
NSApp.activate(ignoringOtherApps: true)

self.window = win
```
**Description**: `NSApp.activate(ignoringOtherApps:)` was deprecated in macOS 14.0 (Sonoma). The replacement is `NSApp.activate()` (without the parameter) or using the newer `NSApplication.shared.activate()` pattern. While this will still compile and work on macOS 13+, it will generate deprecation warnings and may exhibit different behavior on future macOS versions.
**Risk**: Deprecation warnings in production code obscure genuine issues. On future macOS versions, the deprecated path may be removed, causing a crash or linker failure.
**Recommendation**: Replace with the macOS 14+ API with an availability guard:
```swift
if #available(macOS 14.0, *) {
    NSApp.activate()
} else {
    NSApp.activate(ignoringOtherApps: true)
}
```

---

### [MEDIUM] DESIGN: AnyCodable.value typed as `any Sendable` loses structural type information

**File**: `agent/macos/Sources/IPC/EventProtocol.swift:80-81`
**Agent**: C1 (Swift Code Quality Auditor)
**Evidence**:
```swift
public struct AnyCodable: Codable, Sendable {
    /// The stored value. Only primitive Sendable types (Int, Double, Bool,
    /// String, [AnyCodable], [String: AnyCodable], NSNull) are stored.
    public let value: any Sendable
```
**Description**: Using `any Sendable` (an existential) as the storage type for `AnyCodable` means every access to `value` requires dynamic dispatch and boxing overhead. More critically, callers who receive an `AnyCodable` and want to inspect its value must use runtime type checks (`value as? Int`, etc.) rather than compile-time type safety. The `encode(to:)` method already handles this via a `switch`, but any caller that reads `.value` directly faces the same pattern.
**Risk**: This is a design smell rather than a correctness issue. Performance overhead from existential boxing on every IPC event is measurable given high event volumes (keyboard/mouse events at tens per second). The `NSNull` case is also not `Sendable` in the strict sense (it's an ObjC class), though it is thread-safe in practice.
**Recommendation**: Consider replacing with a proper enum with associated values:
```swift
public enum AnyCodableValue: Codable, Sendable {
    case int(Int), double(Double), bool(Bool), string(String)
    case array([AnyCodableValue]), dict([String: AnyCodableValue]), null
}
```

---

### [MEDIUM] ERROR-HANDLING: HMAC key generation returns empty Data on CSPRNG failure

**File**: `agent/macos/Sources/Consent/KeychainConsentStore.swift:270-276`
**Agent**: C1 (Swift Code Quality Auditor)
**Evidence**:
```swift
if result != errSecSuccess {
    Self.log.error("SecRandomCopyBytes failed (\(result, privacy: .public)) — cannot generate HMAC key")
    return Data()
}
```
**Description**: When `SecRandomCopyBytes` fails, the function logs an error and returns an empty `Data()`. The calling function `computeHMAC(data:)` then uses this zero-length key for HMAC computation, producing a deterministic HMAC value with no entropy. This silently degrades the tamper-detection guarantee of the consent store: any attacker who discovers this code path can forge consent records whose HMAC will pass verification (using an empty key).
**Risk**: A CSPRNG failure is catastrophic for a cryptographic operation. Returning empty `Data()` instead of propagating the error means the calling code proceeds with silently broken tamper protection. The consent HMAC is a security boundary — its failure must be surfaced, not silently swallowed.
**Recommendation**: Make `loadOrCreateHMACKey()` a throwing function and propagate the error to `computeHMAC()` and ultimately to `save()`:
```swift
private func loadOrCreateHMACKey() throws -> Data {
    if let existing = keychainLoad(account: hmacKeyAccount) { return existing }
    var key = Data(count: 32)
    let result = key.withUnsafeMutableBytes { ptr in
        guard let base = ptr.baseAddress else { return errSecMemoryError }
        return SecRandomCopyBytes(kSecRandomDefault, 32, base)
    }
    guard result == errSecSuccess else {
        throw KeychainError.keyGenerationFailed(result)
    }
    keychainSave(account: hmacKeyAccount, data: key)
    return key
}
```

---

### [LOW] STYLE: displayName(for:) helper duplicated in two types

**File**: `agent/macos/Sources/UI/TransparencyLogView.swift:139` and `:220`
**Agent**: C1 (Swift Code Quality Auditor)
**Evidence**:
```swift
// In TransparencyLogView:
private func displayName(for rawType: String) -> String {
    rawType.replacingOccurrences(of: "_", with: " ").capitalized
}

// In EventRow (private struct):
private func displayName(for rawType: String) -> String {
    rawType.replacingOccurrences(of: "_", with: " ").capitalized
}
```
**Description**: The same one-liner function is copy-pasted into two types in the same file. This is a minor DRY violation.
**Risk**: If the display format changes (e.g., custom mappings for specific event types), both copies must be updated — risk of divergence.
**Recommendation**: Extract to a file-private or internal extension on `String`:
```swift
fileprivate extension String {
    var eventTypeDisplayName: String {
        replacingOccurrences(of: "_", with: " ").capitalized
    }
}
```

---

### [LOW] DESIGN: Chromium raw bundle ID in hardcoded blocklist is ambiguous

**File**: `agent/macos/Sources/PII/CaptureContextFilter.swift:49`
**Agent**: C1 (Swift Code Quality Auditor)
**Evidence**:
```swift
public static let hardcodedBlocklist: Set<String> = [
    "com.1password.1password",
    "com.agilebits.onepassword7",
    "org.chromium.chromium",  // Chromium raw (not Chrome)
    "com.lastpass.LastPass",
```
**Description**: The comment says "Chromium raw (not Chrome)" but `org.chromium.chromium` is actually the open-source Chromium browser bundle ID — it is not a password manager and is not installed by most users. It appears to be grouped here with password managers, but the justification is unclear. Chrome (`com.google.Chrome`) is conspicuously absent from this list.
**Risk**: If `org.chromium.chromium` was intended to block a specific application (perhaps a test runner or build artifact from the Chromium project), it may not capture the intended target. If Chrome should be blocked, it is missing.
**Recommendation**: Verify whether `org.chromium.chromium` is intentional. If it represents all Chromium-based browsers, the list needs Google Chrome, Brave, Edge, Arc, and Vivaldi added — all of which are already handled by `PrivateBrowsingDetector` for their private modes, but not blanket-blocked.

---

### [LOW] STYLE: ConnectionView health check accepts non-HTTPS URLs

**File**: `agent/macos/Sources/UI/Onboarding/ConnectionView.swift:219-238`
**Agent**: C1 (Swift Code Quality Auditor)
**Evidence**:
```swift
private func performHealthCheck(baseURL: String) async throws -> Bool {
    var urlString = baseURL
    if urlString.hasSuffix("/") { urlString.removeLast() }
    urlString += "/api/v1/health"
    guard let url = URL(string: urlString) else {
        throw URLError(.badURL)
    }
    var request = URLRequest(url: url, timeoutInterval: 10)
    request.httpMethod = "GET"
    let (_, response) = try await URLSession.shared.data(for: request)
```
**Description**: The health-check accepts any URL that `URL(string:)` can parse, including `http://` (unencrypted), `file://`, or custom scheme URLs. `PythonProcessManager.start()` correctly validates that `KMFLOW_BACKEND_URL` is an HTTPS URL with a host, but `ConnectionView.performHealthCheck` has no scheme validation. A user could configure an HTTP backend, pass the health check, and then have all activity data transmitted in plaintext.
**Risk**: Captured employee desktop activity transmitted over HTTP is a serious data confidentiality issue.
**Recommendation**: Add HTTPS scheme validation in `performHealthCheck`:
```swift
guard let url = URL(string: urlString),
      url.scheme?.lowercased() == "https",
      url.host != nil else {
    throw URLError(.badURL)
}
```

---

### [LOW] DESIGN: AgentLogger wraps all messages with privacy: .private

**File**: `agent/macos/Sources/Utilities/Logger.swift:13-27`
**Agent**: C1 (Swift Code Quality Auditor)
**Evidence**:
```swift
public func info(_ message: String) {
    logger.info("\(message, privacy: .private)")
}
public func debug(_ message: String) {
    logger.debug("\(message, privacy: .private)")
}
```
**Description**: `AgentLogger` marks every log message as `privacy: .private`, which means all messages are redacted in system logs unless the device is in developer mode. This is too conservative for non-sensitive informational messages. For example, `log.info("Python subprocess started with PID \(proc.processIdentifier)")` is redacted — making live troubleshooting and support very difficult.
**Risk**: Over-redaction of non-sensitive log messages makes it impossible to diagnose production issues from system logs. Ironically, security-relevant messages (like "integrity check passed") are also redacted, reducing the value of the audit trail.
**Recommendation**: Accept a `privacy` parameter (defaulting to `.private`) and let callers decide: non-sensitive messages like PIDs and status strings should use `.public`. The direct `os.Logger` calls in `KeychainConsentStore` and `IntegrityChecker` already do this correctly — `AgentLogger` should match that capability.

---

## Anti-Patterns Detected

| Pattern | Occurrence | Location |
|---------|------------|----------|
| Force-unwrap (`baseAddress!`) | 2 | `KeychainConsentStore.swift:268`, `TransparencyLogController.swift:362` |
| Silent error swallowing (`try?` in security path) | 2 | `KeychainConsentStore.swift:137,140` |
| `@unchecked Sendable` in production code | 1 | `ConsentManager.swift:76` |
| `Task.detached` where `Task { }` suffices | 1 | `IntegrityChecker.swift:105` |
| Deprecated API usage | 1 | `OnboardingWindow.swift:80` |
| Duplicate helper function | 1 | `TransparencyLogView.swift:139,220` |
| Blocking synchronous I/O in actor | 1 | `SocketClient.swift:102` |

---

## Positive Highlights

1. **Comprehensive actor adoption**: All stateful, shared components use Swift actors (`IdleDetector`, `InputAggregator`, `BlocklistManager`, `VCECaptureManager`, `PythonProcessManager`, `IntegrityChecker`, `SocketClient`) — this eliminates an entire class of data races.

2. **No force-try or force-cast**: Zero occurrences of `try!` or `as!` throughout the entire codebase — excellent discipline.

3. **No print/NSLog**: All logging uses `os.Logger` via `AgentLogger` or directly. Privacy annotations are used on all log statements.

4. **Structured concurrency throughout**: `Task.sleep` (not `Thread.sleep`) is used correctly. `weak self` captures are used where needed. The `deinit` in `IntegrityChecker` correctly cancels the periodic task.

5. **Well-documented security invariants**: The `VCECaptureManager` privacy contract ("image never touches disk"), `SocketClient` symlink attack prevention, and `KeychainConsentStore` HMAC tamper detection are clearly documented with threat model commentary.

6. **Protocol-based testability**: `ConsentStore`, `WorkspaceObserver`, `PermissionsProvider`, `AccessibilityProvider`, `InputEventSource` — all concrete implementations have protocol abstractions for testability.

7. **Proper resource cleanup**: `deinit` properly invalidates timers and cancels tasks. `SocketClient.cleanupFileHandle()` is called in error paths. `defer { sqlite3_close(...) }` is used consistently in `TransparencyLogController`.

8. **Defensive MDM input validation**: `AgentConfig.clamp()` bounds-checks all numeric MDM values. Engagement ID length is capped at 128 characters. Backend URL is validated for HTTPS scheme in `PythonProcessManager`.

---

## Code Quality Score: 7.8 / 10

**Justification**: Strong concurrency model with consistent actor adoption, no force-tries, no NSLog. The actor-based concurrency story is well-executed. The primary deductions are: (1) two force-unwraps in security-critical CSPRNG paths, (2) a blocking synchronous read in the IPC auth handshake that introduces a race condition, (3) silent failure modes in consent persistence that could cause compliance gaps, and (4) one production-shipped `@unchecked Sendable` class designed for test use. The codebase shows clear improvement from prior audits (G1 series) and is in good shape overall.

---

## Checkbox Verification Results

| Acceptance Criterion | Status | Details |
|---------------------|--------|---------|
| NO TODO COMMENTS - All code must be production-ready | PASS | No TODO comments found in any Swift file |
| NO PLACEHOLDERS - No stub implementations | PARTIAL | `ConnectionView.mtlsSection` has a disabled placeholder button with empty action `{}` (line 167) — intentional deferred feature, not a stub implementation |
| NO HARDCODED SECRETS - No credentials or API keys | PASS | No hardcoded secrets; Keychain is used exclusively |
| PROPER ERROR HANDLING - Every function handles failures | FAIL | `KeychainConsentStore.save` silently swallows encoding failures (C1-H3); HMAC key generation returns empty Data on CSPRNG failure (C1-M5) |
| NO ANY TYPES - Must use specific types | PARTIAL | `AnyCodable.value: any Sendable` is intentional type erasure for JSON; acceptable given the use case |
| Naming conventions followed | PASS | Consistent camelCase, PascalCase, UPPER_SNAKE_CASE throughout |
| Functions < 200 lines | PASS | Longest function (`TransparencyLogController.loadEvents`) is ~50 lines |
| No code duplication | PARTIAL | `displayName(for:)` duplicated in `TransparencyLogView` (C1-L1) |
| Proper @MainActor usage for UI | PASS | All UI controllers and views are properly `@MainActor` annotated |
| No blocking sync I/O in async context | FAIL | `FileHandle.availableData` in `SocketClient.connect()` (C1-H2) |
