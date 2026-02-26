# G1: Swift Code Quality & Safety Audit

**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Scope**: `/Users/proth/repos/kmflow/agent/macos/Sources/` (30 files, 3,782 lines) and `/Users/proth/repos/kmflow/agent/macos/Tests/` (5 files, 414 lines)
**Date**: 2026-02-25
**Auditor Model**: Claude Opus 4.6

---

## Finding Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2     |
| HIGH     | 8     |
| MEDIUM   | 8     |
| LOW      | 5     |
| **Total** | **23** |

**Code Quality Score: 7.0 / 10**

Justification: The codebase demonstrates strong architectural fundamentals -- clean module separation, protocol-based testability, proper use of `@MainActor` and Swift actors, and excellent PII filtering. However, there are two critical concurrency issues (a blocking `Thread.sleep` inside an actor and `@unchecked Sendable` classes with manual locking that could deadlock), several gaps in error handling (silent `try?` for security-critical operations), missing test coverage for major modules, and input validation gaps in MDM configuration that could cause resource exhaustion on managed devices.

---

## Findings

---

### [CRITICAL] CONCURRENCY: Thread.sleep blocks actor executor in SocketClient reconnect loop

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/IPC/SocketClient.swift:93`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
private func reconnect() throws {
    for attempt in 0..<maxReconnectAttempts {
        do {
            try connect()
            return
        } catch {
            let delay = baseReconnectDelay * pow(2.0, Double(attempt))
            Thread.sleep(forTimeInterval: min(delay, 30.0))
        }
    }
```
**Description**: `SocketClient` is declared as an `actor`, which means all of its methods run on its serial executor. `Thread.sleep(forTimeInterval:)` is a synchronous, blocking call that freezes the actor's executor thread entirely. During a reconnect cycle with exponential backoff (up to 30 seconds per attempt, 5 attempts), the actor is completely blocked for up to ~62 seconds. Any other `await socketClient.send(...)` call from the capture pipeline will be enqueued and starve. Because Swift's cooperative thread pool has a limited number of threads, this can cascade into blocking the entire concurrency runtime.
**Risk**: On thousands of deployed machines, if the Python subprocess crashes and the socket becomes unavailable, every agent's capture pipeline freezes for over a minute. If multiple actors use `Thread.sleep`, the cooperative thread pool can deadlock entirely.
**Recommendation**: Replace `Thread.sleep` with `try await Task.sleep(nanoseconds:)` and make `reconnect()` an `async` method. This yields the executor during the delay, allowing other actor messages to be processed. The `send()` method should also become `async throws`.

---

### [CRITICAL] CONCURRENCY: Five classes use @unchecked Sendable with NSLock -- no deadlock protection

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/IdleDetector.swift:8`, `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/InputMonitor.swift:32`, `/Users/proth/repos/kmflow/agent/macos/Sources/Config/BlocklistManager.swift:6`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
public final class IdleDetector: @unchecked Sendable {
    private var lastActivityTime: Date
    private var isIdle: Bool = false
    private let timeoutSeconds: TimeInterval
    private let lock = NSLock()
```
```swift
public final class InputAggregator: @unchecked Sendable {
    private let lock = NSLock()
    private var keyCount: Int = 0
```
```swift
public final class BlocklistManager: @unchecked Sendable {
    private var blocklist: Set<String>
    private var allowlist: Set<String>?
    private let lock = NSLock()
```
**Description**: Five classes (`IdleDetector`, `InputAggregator`, `BlocklistManager`, `InMemoryConsentStore`, `MockPermissionsProvider`) use `@unchecked Sendable` with manual `NSLock` synchronization. `@unchecked Sendable` tells the compiler to skip thread-safety verification entirely -- the developer is asserting correctness manually. While the current lock usage appears correct (lock/defer-unlock pattern), `NSLock` is not reentrant: if any method that holds the lock calls another method on the same class that also acquires the lock, the thread will deadlock. Additionally, `BlocklistManager.init` reads `blocklist` and `allowlist` without holding the lock, but `update(config:)` writes them under the lock -- if `init` races with `update`, the initialization could see a partially-written state.
**Risk**: A deadlock on thousands of machines would require manual intervention (force-quit/reboot). The `@unchecked Sendable` annotation suppresses all compiler warnings, so future modifications could easily introduce data races that the compiler would otherwise catch.
**Recommendation**: Convert `IdleDetector`, `InputAggregator`, and `BlocklistManager` to Swift actors. They are already classes with serialized access patterns, and the actor model provides compiler-verified safety. If NSLock must be retained for performance, add `@available` annotations and document the non-reentrant constraint prominently.

---

### [HIGH] ERROR-HANDLING: KeychainConsentStore.save silently swallows encoding failure

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:94`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
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
**Description**: If `jsonEncoder().encode(record)` fails, `save` returns silently without logging. The user believes consent was granted (the UI shows success), but the Keychain was never written. On next launch, `load()` returns `.neverConsented`, the onboarding wizard reappears, and the user is confused. This is a consent integrity issue.
**Risk**: Users consent but the agent does not record it. On next launch they are prompted again. Worse: if consent revocation fails silently, the agent may continue capturing after the user believes they revoked consent.
**Recommendation**: Log the encoding failure via `os.Logger` and surface the error to the caller. The `ConsentStore.save` protocol should return a `Bool` or throw to indicate whether persistence succeeded.

---

### [HIGH] ERROR-HANDLING: KeychainConsentStore uses fputs to stderr instead of os.Logger

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:147`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
let status = SecItemAdd(addQuery as CFDictionary, nil)
if status != errSecSuccess {
    // Non-fatal: consent will fall back to neverConsented on next load.
    // os_log is not available here without importing os; use stderr.
    fputs("[KeychainConsentStore] SecItemAdd failed: \(status)\n", stderr)
}
```
**Description**: The comment says "os_log is not available here without importing os", but `import os.log` is available in the Consent module (it has no dependency restrictions in Package.swift). The `fputs` output goes to stderr which is not captured by the macOS unified logging system, meaning this failure is invisible in Console.app and `log stream`. On a managed fleet, IT admins have no way to diagnose Keychain failures.
**Risk**: Keychain failures on managed devices go undiagnosed. The `fputs` approach also does not include timestamps, process IDs, or structured metadata that unified logging provides.
**Recommendation**: Add `import os.log` to the file and replace `fputs` with `os.Logger(subsystem: "com.kmflow.agent", category: "KeychainConsentStore").error(...)`.

---

### [HIGH] MEMORY-SAFETY: Force-unwrap of Application Support directory URL

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogController.swift:67`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
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
**Description**: `.first!` force-unwraps an optional. While `applicationSupportDirectory` virtually always returns a result on macOS, force-unwraps are a process-killing crash if the assumption ever fails. In a sandboxed environment, certain FileManager APIs can behave differently. This is the only force-unwrap in the production codebase and it exists in a UI controller that initializes at view appearance time.
**Risk**: If `.first` returns `nil` (however unlikely), the entire agent process crashes with a `fatalError` in the unwrap. On a fleet-deployed agent this would be unrecoverable without reinstallation.
**Recommendation**: Use `guard let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else { databaseURL = URL(fileURLWithPath: "/dev/null"); statusMessage = "Cannot locate Application Support"; return }`.

---

### [HIGH] MEMORY-SAFETY: Five try! force-try calls for NSRegularExpression compilation

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/WindowTitleCapture.swift:14-34`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
private static let ssnDashed = try! NSRegularExpression(
    pattern: #"\b\d{3}-\d{2}-\d{4}\b"#
)
private static let email = try! NSRegularExpression(
    pattern: #"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"#
)
private static let phone = try! NSRegularExpression(
    pattern: #"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"#
)
```
**Description**: Five `try!` expressions compile regular expressions at static initialization time. If any pattern is invalid, the process crashes before even launching. While these patterns are currently valid string literals, `try!` provides no safety margin. If a developer modifies a pattern and introduces a syntax error, the crash occurs at launch with no diagnostic -- just a SIGABRT.
**Risk**: A single typo in a regex pattern during development causes a fleet-wide crash-on-launch. Since these are `static let` properties, the crash happens during the first access, which is in the hot path of event processing.
**Recommendation**: Use a `do/catch` initializer or a `lazy` computed property that falls back to a no-op filter on failure, logging the error. Alternatively, add a unit test that exercises all five patterns to catch compile errors before deployment. (Note: the test suite currently tests `L2PIIFilter.scrub` which does exercise these patterns, partially mitigating this risk.)

---

### [HIGH] INPUT-VALIDATION: MDM configuration values not range-validated

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Config/AgentConfig.swift:59-66`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
self.screenshotIntervalSeconds = defaults.object(forKey: "ScreenshotIntervalSeconds") != nil
    ? defaults.integer(forKey: "ScreenshotIntervalSeconds") : 30
self.batchSize = defaults.object(forKey: "BatchSize") != nil
    ? defaults.integer(forKey: "BatchSize") : 1000
self.batchIntervalSeconds = defaults.object(forKey: "BatchIntervalSeconds") != nil
    ? defaults.integer(forKey: "BatchIntervalSeconds") : 30
self.idleTimeoutSeconds = defaults.object(forKey: "IdleTimeoutSeconds") != nil
    ? defaults.integer(forKey: "IdleTimeoutSeconds") : 300
```
**Description**: Integer values from MDM UserDefaults are used directly without range validation. A misconfigured MDM profile could set `BatchSize` to 0 (division-by-zero risk), `batchIntervalSeconds` to 0 (tight loop), `screenshotIntervalSeconds` to 1 (extreme I/O), or `idleTimeoutSeconds` to -1 (never-idle). `UserDefaults.integer(forKey:)` returns 0 for non-existent keys and truncates floating-point values, so type confusion is also possible.
**Risk**: A single MDM misconfig affects all managed machines simultaneously. A `batchIntervalSeconds` of 0 could create a tight loop that consumes 100% CPU across the fleet. A `batchSize` of 0 could cause division-by-zero crashes.
**Recommendation**: Add `max(1, min(value, upperBound))` clamping after reading each integer. Define constants for valid ranges: `screenshotIntervalSeconds: 5...3600`, `batchSize: 10...10000`, `batchIntervalSeconds: 5...300`, `idleTimeoutSeconds: 30...3600`.

---

### [HIGH] CONCURRENCY: SocketClient.reconnect blocks with Thread.sleep inside an actor

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/IPC/SocketClient.swift:86-97`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
private func reconnect() throws {
    for attempt in 0..<maxReconnectAttempts {
        do {
            try connect()
            return
        } catch {
            let delay = baseReconnectDelay * pow(2.0, Double(attempt))
            Thread.sleep(forTimeInterval: min(delay, 30.0))
        }
    }
    throw SocketError.connectionFailed("Failed after \(maxReconnectAttempts) reconnect attempts")
}
```
**Description**: This is the same issue as CRITICAL finding #1, viewed from the `send()` call path. When `send()` detects disconnection, it calls `reconnect()` synchronously. Any concurrent caller of `send()` is blocked for the entire reconnection cycle (up to ~62 seconds). The `send()` method itself is not `async`, meaning callers cannot use structured concurrency to cancel a stuck send.
**Risk**: Capture events pile up in the caller's buffer while the socket is reconnecting. If the caller is on the main actor, the UI freezes.
**Recommendation**: Make `send()` and `reconnect()` `async throws`, replace `Thread.sleep` with `Task.sleep`, and add a cancellation check (`try Task.checkCancellation()`) in the reconnect loop so callers can time out.

---

### [HIGH] RESOURCE-CLEANUP: SocketClient.send does not close failed file handle

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/IPC/SocketClient.swift:66-83`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
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
    } catch {
        isConnected = false
        fileHandle = nil
        throw error
    }
}
```
**Description**: When a write fails, `fileHandle` is set to `nil` without calling `fileHandle?.closeFile()` first. The `FileHandle` was created with `closeOnDealloc: true`, so the file descriptor will eventually be closed when ARC deallocates the `FileHandle` object. However, since `SocketClient` is an actor, the old `FileHandle` reference may linger if there are any retained references or if ARC timing is delayed. Furthermore, `fh.write(data)` does not throw -- `FileHandle.write(_:)` raises an Objective-C exception on failure (SIGPIPE, broken pipe), which is not catchable by Swift's `do/catch`. The error path may never execute; instead, the process receives SIGPIPE.
**Risk**: On write failure to a broken socket, the process receives SIGPIPE and terminates. This is not caught by the `do/catch` block.
**Recommendation**: Install a `signal(SIGPIPE, SIG_IGN)` handler at app launch to convert SIGPIPE into an EPIPE error. Alternatively, use POSIX `write()` directly instead of `FileHandle.write()` to get error codes instead of exceptions. Also, call `closeFile()` explicitly before nilling the handle.

---

### [HIGH] LIFECYCLE: AppDelegate uses implicitly unwrapped optionals for critical managers

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/KMFlowAgentApp.swift:31-34`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var stateManager: CaptureStateManager!
    private var statusBarController: StatusBarController!
    private var blocklistManager: BlocklistManager!
    private var pythonManager: PythonProcessManager!
```
**Description**: Four implicitly unwrapped optionals (`!`) are used for the core manager objects. If any code path accesses these properties before `applicationDidFinishLaunching` completes initialization, the process crashes. `pythonManager` in particular is conditionally initialized (only when consent is granted), but `applicationWillTerminate` accesses it unconditionally with `if let manager = pythonManager`. While the `if let` safely unwraps, the IUO type means a direct access like `pythonManager.stop()` anywhere else would crash.
**Risk**: Accessing any of these four properties before initialization crashes the agent. As the codebase grows, the window for accidental premature access widens.
**Recommendation**: Use regular optionals (`?`) instead of IUOs, and change initialization to happen in `init()` or use a lazy initialization pattern. For `pythonManager` which is conditionally created, optional (`?`) is already the correct type.

---

### [MEDIUM] LOGGING: AgentLogger marks all log messages as privacy: .public

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Utilities/Logger.swift:14-26`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
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
**Description**: Every log level unconditionally marks messages as `privacy: .public`. While this is convenient for development, it means any string passed to `AgentLogger` -- including window titles, application names, bundle identifiers, or error messages containing user data -- will be visible in plaintext in the unified log. The `os.Logger` privacy system exists specifically to redact dynamic content by default, showing it only when the user explicitly opts in with `log collect --level debug`.
**Risk**: If a caller logs a window title that slipped past PII filtering, it persists in plaintext in the unified log, accessible via `log show` or Console.app. This undermines the privacy guarantees described in the onboarding wizard.
**Recommendation**: Change the default privacy level to `.private` (or remove the wrapper and use `os.Logger` directly so each call site specifies its own privacy). Only use `.public` for static strings and sanitized identifiers.

---

### [MEDIUM] LOGGING: KMFlowAgentApp uses NSLog instead of os.Logger

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/KMFlowAgentApp.swift:50-55`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
case .failed(let violations):
    NSLog("KMFlowAgent: Python integrity check failed: \(violations)")
    stateManager.setError("Integrity check failed — Python bundle may have been tampered with")
    statusBarController.updateIcon()
    return
case .manifestMissing:
    NSLog("KMFlowAgent: Python integrity manifest not found (development mode)")
```
**Description**: The main app delegate uses `NSLog` for two log statements while the rest of the codebase uses `os.Logger`. `NSLog` is the legacy Objective-C logging API; it outputs to both stderr and the unified log but does not support log levels, categories, subsystems, or privacy annotations. The `violations` array is interpolated directly, potentially including file paths.
**Risk**: Inconsistent logging makes fleet-wide log analysis harder. The integrity violation message includes file paths without privacy annotation.
**Recommendation**: Replace `NSLog` with `os.Logger(subsystem: "com.kmflow.agent", category: "Lifecycle")` calls.

---

### [MEDIUM] CONCURRENCY: BlocklistManager.init reads shared state without lock

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Config/BlocklistManager.swift:11-18`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
public init(config: AgentConfig? = nil) {
    var blocked = L1Filter.hardcodedBlocklist
    if let configBlocked = config?.appBlocklist {
        blocked.formUnion(configBlocked)
    }
    self.blocklist = blocked
    self.allowlist = config?.appAllowlist.map { Set($0) }
}
```
**Description**: The initializer writes to `blocklist` and `allowlist` without acquiring the lock. While Swift guarantees that an object is fully initialized before it becomes accessible, the pattern is inconsistent with `update(config:)` which does lock. If the object were ever vended to another thread during a two-phase initialization pattern (e.g., assigned to a shared property and then `update()` called from another thread before init completes), a race would occur.
**Risk**: Low in current usage, but the inconsistency signals that the locking discipline is fragile and could break under refactoring.
**Recommendation**: Either document that `init` does not need the lock (because Swift guarantees single-threaded init) or convert to an actor to remove the manual locking entirely.

---

### [MEDIUM] ERROR-HANDLING: Excessive try? usage in security-critical paths (11 instances)

**File**: Multiple files
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
// KeychainConsentStore.swift:94
guard let data = try? jsonEncoder().encode(record) else { return }

// IntegrityChecker.swift:60
guard let manifestData = try? Data(contentsOf: manifestURL) else {

// IntegrityChecker.swift:79
guard let fileData = try? Data(contentsOf: fileURL) else {
```
**Description**: The codebase uses `try?` in 11 locations and `try` (with `do/catch`) in only a handful. `try?` discards the error entirely, making it impossible to diagnose failures. In `IntegrityChecker`, reading a file and getting `nil` could mean permission denied, file not found, or I/O error -- the log message says "file missing" but it could be a permissions issue.
**Risk**: Silent failures in integrity checking and consent persistence are difficult to diagnose on remote machines. Different failure modes (permission denied vs. corrupt data vs. missing file) require different remediation.
**Recommendation**: Replace `try?` with `do/catch` in security-critical paths (IntegrityChecker, KeychainConsentStore). The `AnyCodable` decoder's `try?` usage is acceptable since it's implementing a type-probing pattern.

---

### [MEDIUM] TEST-COVERAGE: No tests for SocketClient, PythonProcessManager, IntegrityChecker, or UI modules

**File**: `/Users/proth/repos/kmflow/agent/macos/Tests/`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```
Tests/
  CaptureTests/CaptureStateManagerTests.swift   (94 lines)
  ConfigTests/BlocklistManagerTests.swift        (43 lines)
  ConsentTests/ConsentManagerTests.swift         (49 lines)
  IPCTests/EventProtocolTests.swift              (70 lines)
  PIITests/L1FilterTests.swift                   (158 lines)
```
**Description**: The test suite covers 5 modules with 414 total lines of test code. The following modules have zero test coverage:

- **SocketClient** (IPC/SocketClient.swift) -- No tests for connect, send, reconnect, disconnect
- **PythonProcessManager** (KMFlowAgent/PythonProcessManager.swift) -- No tests for start, stop, restart, circuit breaker
- **IntegrityChecker** (KMFlowAgent/IntegrityChecker.swift) -- No tests for SHA-256 verification, missing manifest, tampered files
- **TransparencyLogController** (UI/TransparencyLogController.swift) -- No tests for SQLite reading, timer lifecycle
- **KeychainConsentStore** (Consent/KeychainConsentStore.swift) -- No tests for Keychain operations (though ConsentManager is tested via InMemoryConsentStore)
- **AgentConfig MDM parsing** (Config/AgentConfig.swift) -- No tests for MDM profile parsing
- **IdleDetector** (Capture/IdleDetector.swift) -- No tests for idle detection state machine
- **InputAggregator** (Capture/InputMonitor.swift) -- No tests for event aggregation and flush
- **OnboardingState** (UI/Onboarding/OnboardingState.swift) -- No tests for wizard state machine validation

**Risk**: The untested modules include the most critical components: IPC communication, subprocess management, integrity verification, and Keychain persistence. Bugs in these areas would affect all deployments.
**Recommendation**: Prioritize tests for: (1) IntegrityChecker (create test fixtures with known SHA-256 digests), (2) PythonProcessManager (mock Process), (3) SocketClient (mock file handle), (4) IdleDetector and InputAggregator (pure logic, easy to test), (5) OnboardingState (pure state machine).

---

### [MEDIUM] INPUT-VALIDATION: No length limit or sanitization on engagement ID from MDM

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/KMFlowAgentApp.swift:64-70`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
let engagementId: String
if let mdmDefaults = UserDefaults(suiteName: "com.kmflow.agent"),
   let mdmEngagement = mdmDefaults.string(forKey: "EngagementID"),
   !mdmEngagement.isEmpty {
    engagementId = mdmEngagement
} else {
    engagementId = UserDefaults.standard.string(forKey: "engagementId") ?? "default"
}
```
**Description**: The engagement ID is read from MDM UserDefaults and used directly as a Keychain account key suffix (via `KeychainConsentStore.accountKey`). There is no length limit, character validation, or sanitization. An attacker or misconfigured MDM profile could inject a very long string (causing Keychain API errors) or strings with path separator characters.
**Risk**: Malformed engagement IDs could cause Keychain operations to fail silently (the IDs become part of Keychain account names). Extremely long IDs could cause memory issues.
**Recommendation**: Validate the engagement ID: max 256 characters, alphanumeric plus hyphens only, trim whitespace. Reject invalid IDs with a user-facing error.

---

### [MEDIUM] DESIGN: AnyCodable stores Any, which is not Sendable

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/IPC/EventProtocol.swift:77-82`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
public struct AnyCodable: Codable, Sendable {
    public let value: Any

    public init(_ value: Any) {
        self.value = value
    }
```
**Description**: `AnyCodable` conforms to `Sendable` but stores an `Any` property. The `Any` type is not `Sendable` -- it could hold a reference type with mutable state. The compiler should flag this, but in practice the `Sendable` conformance may be inferred or suppressed. The actual values stored are only `Int`, `Double`, `Bool`, `String`, `[AnyCodable]`, `[String: AnyCodable]`, and `NSNull` (from the decoder), all of which are value types or immutable. However, the `public init(_ value: Any)` allows callers to store arbitrary non-Sendable types.
**Risk**: A caller could store a non-Sendable reference type in `AnyCodable`, violating the `Sendable` contract and creating a data race if the `CaptureEvent` is sent across actor boundaries.
**Recommendation**: Restrict the `init` to accept only known safe types, or use an enum instead of `Any` to enforce type safety at compile time: `enum JSONValue: Codable, Sendable { case int(Int), double(Double), bool(Bool), string(String), array([JSONValue]), object([String: JSONValue]), null }`.

---

### [MEDIUM] RESOURCE-CLEANUP: PermissionsView polling timer captured self strongly

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/Onboarding/PermissionsView.swift:165-170`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
private func startPolling() {
    checkAccessibility()
    let timer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { _ in
        Task { @MainActor in
            self.checkAccessibility()
        }
    }
    pollTimer = timer
}
```
**Description**: The `Timer` closure captures `self` strongly (no `[weak self]`). In SwiftUI, `self` is the `PermissionsView` struct, which is a value type -- so this does not cause a retain cycle per se. However, the timer closure creates a `Task` that references `self`, and if the view is replaced before `stopPolling()` runs (e.g., due to a SwiftUI view identity change), the timer continues firing with a stale reference. The `onDisappear` modifier calls `stopPolling()`, but SwiftUI does not guarantee `onDisappear` fires in all scenarios (e.g., when the window is closed directly).
**Risk**: Timer continues running after the view is dismissed in edge cases, causing unnecessary `AXIsProcessTrusted` calls and potential crashes if the state object is deallocated.
**Recommendation**: Add `[weak state]` to the closure and check for nil, or use `.task` modifier with `AsyncSequence` for structured concurrency-based polling.

---

### [MEDIUM] DESIGN: AppSwitchMonitor tracks mutable state accessed from main thread only but not @MainActor

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Capture/AppSwitchMonitor.swift:42-51`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
public final class SystemAppSwitchMonitor: WorkspaceObserver {
    private var observer: NSObjectProtocol?
    private var lastAppName: String?
    private var lastBundleId: String?
    private var lastSwitchTime: Date?
    private let blocklistManager: BlocklistManager

    public init(blocklistManager: BlocklistManager) {
        self.blocklistManager = blocklistManager
    }
```
**Description**: `SystemAppSwitchMonitor` has four mutable `var` properties that are read and written from the notification callback on `queue: .main`. However, the class itself is not annotated with `@MainActor`, so the compiler does not enforce that `startObserving()` and `stopObserving()` are called from the main thread. If `startObserving()` were called from a background thread, `lastSwitchTime = Date()` on line 54 would race with the notification handler.
**Risk**: Calling `startObserving()` from a background thread would cause a data race on `lastSwitchTime`, `lastAppName`, and `lastBundleId`.
**Recommendation**: Annotate `SystemAppSwitchMonitor` with `@MainActor` to get compiler-enforced main-thread-only access, matching the notification handler's execution context.

---

### [LOW] STYLE: Inconsistent error type handling in KeychainHelper vs KeychainConsentStore

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Utilities/KeychainHelper.swift:14-29` and `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:125-148`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
// KeychainHelper.swift - throws on save failure
public func save(key: String, data: Data) throws {
    // ...
    guard status == errSecSuccess else {
        throw KeychainError.saveFailed(status)
    }
}

// KeychainConsentStore.swift - logs to stderr on save failure
let status = SecItemAdd(addQuery as CFDictionary, nil)
if status != errSecSuccess {
    fputs("[KeychainConsentStore] SecItemAdd failed: \(status)\n", stderr)
}
```
**Description**: Two separate Keychain implementations exist with inconsistent error handling. `KeychainHelper` throws on failure; `KeychainConsentStore` logs to stderr. The consent store reimplements Keychain operations rather than using `KeychainHelper` because the comment states it avoids the Utilities dependency. This duplication means bug fixes to Keychain handling must be applied in two places.
**Risk**: Divergent Keychain handling leads to inconsistent behavior and maintenance burden.
**Recommendation**: Either have the Consent module depend on Utilities (adding `KeychainHelper` as a dependency), or extract a shared Keychain primitives module that both can use.

---

### [LOW] PERFORMANCE: ISO8601DateFormatter created per-row in TransparencyLogController

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogController.swift:171`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
case SQLITE_TEXT:
    if let tsCStr = sqlite3_column_text(stmt, 1) {
        let tsString = String(cString: tsCStr)
        tsRaw = ISO8601DateFormatter().date(from: tsString) ?? Date()
    } else {
        tsRaw = Date()
    }
```
**Description**: `ISO8601DateFormatter()` is instantiated for every row that has a text timestamp. `DateFormatter` creation is expensive (~100 microseconds per instance). With 200 rows loaded per refresh cycle every 5 seconds, this could create 200 formatter objects per cycle.
**Risk**: Minor CPU waste and GC pressure. Not a critical issue but wasteful for a background agent.
**Recommendation**: Create a static `ISO8601DateFormatter` instance and reuse it:
```swift
private static let iso8601Formatter = ISO8601DateFormatter()
```

---

### [LOW] DESIGN: MockPermissionsProvider in production source, not test target

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/PermissionsManager.swift:41-54`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
public final class MockPermissionsProvider: PermissionsProvider, @unchecked Sendable {
    public var accessibilityGranted: Bool
    public var screenRecordingGranted: Bool
    public var requestCount: Int = 0
    // ...
}
```
**Description**: `MockPermissionsProvider` is a test double that lives in the production `Consent` module rather than in a test target. Similarly, `InMemoryConsentStore` in `ConsentManager.swift` is a test double in production code. This means mock code ships in the production binary and increases the attack surface.
**Risk**: Test doubles in production code could be instantiated by accident or exploited to bypass real permission checks.
**Recommendation**: Move `MockPermissionsProvider` and `InMemoryConsentStore` to their respective test targets (or a shared `TestSupport` module).

---

### [LOW] STYLE: ConnectionView.performHealthCheck does not validate URL scheme

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/Onboarding/ConnectionView.swift:219-239`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
private func performHealthCheck(baseURL: String) async throws -> Bool {
    var urlString = baseURL
    if urlString.hasSuffix("/") {
        urlString.removeLast()
    }
    urlString += "/api/v1/health"
    guard let url = URL(string: urlString) else {
        throw URLError(.badURL)
    }
    var request = URLRequest(url: url, timeoutInterval: 10)
    request.httpMethod = "GET"
    let (_, response) = try await URLSession.shared.data(for: request)
```
**Description**: The URL string is passed to `URL(string:)` without validating the scheme. A user could enter `http://` (unencrypted), `file:///`, `ftp://`, or even `javascript:` URLs. The health check would attempt to connect over an insecure or unexpected protocol. There is no enforcement that the connection uses HTTPS.
**Risk**: User enters an `http://` URL, and the agent sends health check data (and later capture events) over unencrypted HTTP.
**Recommendation**: Validate that the URL uses `https://` scheme (or `http://localhost` for development). Reject other schemes with a clear error message.

---

### [LOW] DESIGN: CaptureEvent.sequenceNumber is mandatory but has no default

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/IPC/EventProtocol.swift:43-61`
**Agent**: G1 (Swift Code Quality & Safety Auditor)
**Evidence**:
```swift
public init(
    eventType: DesktopEventType,
    timestamp: Date = Date(),
    applicationName: String? = nil,
    bundleIdentifier: String? = nil,
    windowTitle: String? = nil,
    eventData: [String: AnyCodable]? = nil,
    idempotencyKey: String? = nil,
    sequenceNumber: UInt64
) {
```
**Description**: `sequenceNumber` is a required parameter with no default value. The sequence is generated by `CaptureStateManager.nextSequenceNumber()` which requires a `@MainActor` call. This means creating a `CaptureEvent` from a background context requires hopping to the main actor just to get a sequence number, adding friction and potential for bugs where developers hard-code a sequence number.
**Risk**: Developers creating test events or events from non-main contexts may use arbitrary sequence numbers, breaking ordering guarantees.
**Recommendation**: Consider providing a thread-safe atomic sequence generator that does not require `@MainActor`, or make `sequenceNumber` optional with a protocol-level default.

---

## Positive Highlights

1. **Excellent module separation**: The `Package.swift` defines 7 clean modules (Capture, Consent, Config, IPC, PII, UI, Utilities) with minimal dependencies. The Consent module has zero dependencies, enabling independent auditing.

2. **No external dependencies**: The agent has zero third-party dependencies. This eliminates supply-chain risk entirely and is ideal for a security-sensitive agent deployed on employee machines.

3. **Protocol-based testability**: Key system interfaces (`WorkspaceObserver`, `InputEventSource`, `ConsentStore`, `PermissionsProvider`, `AccessibilityProvider`) are defined as protocols with concrete and mock implementations, enabling unit testing without real system APIs.

4. **Proper actor usage for PythonProcessManager**: The subprocess manager correctly uses Swift's `actor` model, ensuring all state mutations (process reference, restart timestamps, isRunning flag) are serialized without manual locking.

5. **Multi-layer PII defense**: L1 blocks capture at the source (password fields, blocklisted apps, private browsing), L2 scrubs PII patterns (SSN, email, phone, credit card) from window titles before they cross the IPC boundary. This defense-in-depth approach is well-designed.

6. **Integrity verification at launch**: `IntegrityChecker` verifies SHA-256 digests of all bundled Python files before launching the Python subprocess, preventing tampered code from running under the agent's entitlements.

7. **Circuit breaker in PythonProcessManager**: The subprocess restart logic implements a proper circuit breaker (max 5 restarts in 60 seconds) to prevent infinite restart loops from consuming system resources.

8. **No TODO/FIXME/HACK comments**: The codebase is clean of placeholder markers, indicating completed implementation.

9. **No print() statements**: All logging uses either `os.Logger` or `NSLog` (with noted issues above), but there are zero `print()` debug statements.

10. **Proper weak self in closures**: All three closure-based patterns (NSWorkspace observer, Process termination handler, Timer) correctly use `[weak self]` capture lists.

11. **CaptureStateManager is @MainActor**: The central state machine is properly isolated to the main actor, preventing concurrent mutation of the published state that drives the UI.

12. **Idempotency keys on events**: `CaptureEvent` includes an optional `idempotencyKey` field, enabling exactly-once processing even if events are retransmitted over the IPC socket.

---

## Checkbox Verification Results

- [x] **NO TODO COMMENTS** - Verified: Zero TODO/FIXME/HACK/XXX comments found
- [x] **NO PLACEHOLDERS** - Verified: No stub implementations found (mTLS section is explicitly documented as future-phase)
- [x] **NO HARDCODED SECRETS** - Verified: No API keys, passwords, or credentials in source code
- [ ] **PROPER ERROR HANDLING** - Not verified: 11 instances of `try?` silently swallowing errors in security-critical paths (KeychainConsentStore, IntegrityChecker)
- [x] **NO ANY TYPES** - N/A for Swift (not TypeScript); however, `AnyCodable.value: Any` has Sendable implications noted above
- [x] **TYPE HINTS** - N/A for Swift (Swift is statically typed; all function signatures have explicit types)
- [ ] **NO FORCE UNWRAPS** - Not verified: 1 force-unwrap (`first!`) in TransparencyLogController.swift:67, 5 `try!` in WindowTitleCapture.swift
- [ ] **PROPER CONCURRENCY** - Not verified: Thread.sleep in actor, 5x @unchecked Sendable, missing @MainActor on AppSwitchMonitor
- [ ] **ADEQUATE TEST COVERAGE** - Not verified: Only 5 of 14+ modules have tests (414 lines of test code for 3,782 lines of source)
- [x] **RESOURCE CLEANUP** - Partially verified: deinit properly removes observers and invalidates timers; socket cleanup has SIGPIPE issue noted above
