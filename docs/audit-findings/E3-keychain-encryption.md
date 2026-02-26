# E3: Keychain & Encryption Re-Audit — KMFlow macOS Task Mining Agent

**Auditor**: E3 (Keychain & Encryption Auditor)
**Original Audit Date**: 2026-02-25
**Re-Audit Date**: 2026-02-26
**Scope**: Swift source files in `agent/macos/Sources/` — Keychain, IPC, consent, encryption, integrity
**Remediation PRs Reviewed**: #248, #255, #256
**Status**: RE-AUDIT COMPLETE

---

## Executive Summary

The Phase 1-3 remediation (PRs #248, #255, #256) addressed the two CRITICAL findings and four of the five HIGH findings from the original audit. The SQLite capture buffer now has AES-256-GCM column-level encryption with per-row nonces. The IPC socket validates against symlink attacks and performs a shared-secret authentication handshake. Consent records are HMAC-SHA256 signed with a per-install key auto-generated from `SecRandomCopyBytes`. The `KeychainHelper` now sets `kSecAttrAccessibleAfterFirstUnlock` and `kSecAttrSynchronizable: kCFBooleanFalse`. The `AgentLogger` defaults to `privacy: .private`. The consent revocation handler mechanism is in place. The false encryption claim in WelcomeView has been corrected. The unused entitlement was removed. The `IntegrityChecker` now supports HMAC-SHA256 manifest signature verification and periodic re-verification.

**The agent's security posture has materially improved.** The two CRITICAL findings are resolved. Four of five HIGH findings are fully resolved; one (sandbox rationale) remains partially addressed. Five MEDIUM and three LOW findings from the original audit are either resolved or have been downgraded. New residual findings have been identified during the re-audit, all at MEDIUM or LOW severity.

---

## Finding Disposition Summary

| ID | Original Severity | Original Title | Status | Notes |
|----|:-:|---|:-:|---|
| DATA-AT-REST-001 | CRITICAL | SQLite buffer stored in plaintext | **RESOLVED** | AES-256-GCM encryption implemented in TransparencyLogController (PR #256) |
| IPC-001 | CRITICAL | Unix socket no auth/encryption | **RESOLVED** | Symlink check + auth handshake in SocketClient (PR #256) |
| KEYCHAIN-001 | HIGH | KeychainHelper missing kSecAttrAccessible | **RESOLVED** | `kSecAttrAccessibleAfterFirstUnlock` added (PR #255) |
| CONSENT-001 | HIGH | Consent token unsigned | **RESOLVED** | HMAC-SHA256 signing via `SignedConsentRecord` (PR #256) |
| CONSENT-002 | HIGH | No data cleanup on consent revocation | **RESOLVED** | `onRevocation` handler mechanism added to `ConsentManager` (PR #256) |
| SANDBOX-001 | HIGH | App Sandbox disabled, no rationale | **PARTIALLY RESOLVED** | Unused entitlement removed; ADR still needed |
| LOGGING-001 | HIGH | AgentLogger marks all messages as .public | **RESOLVED** | `AgentLogger` now uses `privacy: .private` (PR #255) |
| KEYCHAIN-002 | MEDIUM | AfterFirstUnlock allows background access | **ACCEPTED RISK** | Intentional design for background agent; documented |
| KEYCHAIN-003 | MEDIUM | kSecAttrSynchronizable not set | **RESOLVED** | Explicitly set to `kCFBooleanFalse` across all three Keychain sites (PRs #255, #256) |
| INTEGRITY-001 | MEDIUM | Integrity check only at startup | **RESOLVED** | Periodic checking added via `IntegrityChecker` instance API (PR #256) |
| INTEGRITY-002 | MEDIUM | IntegrityChecker does not verify manifest | **RESOLVED** | HMAC-SHA256 signature verification via `integrity.sig` (PR #256) |
| CONSENT-003 | MEDIUM | Consent checked only at startup | **PARTIALLY RESOLVED** | `onRevocation` handler exists but `ConsentManager` not stored as AppDelegate property; no runtime subscription wired |
| KEYCHAIN-004 | LOW | Keychain error logged to stderr | **OPEN** | Still using `fputs` to stderr in `KeychainConsentStore` |
| KEY-LIFECYCLE-001 | LOW | No key rotation mechanism | **OPEN** | Still no rotation for buffer encryption key or HMAC key |
| ENTITLEMENT-001 | LOW | Unused entitlement | **RESOLVED** | `com.apple.security.files.user-selected.read-write` removed |

---

## Resolved Findings — Verification Details

### [RESOLVED] DATA-AT-REST-001: SQLite Capture Buffer Encryption

**Original Severity**: CRITICAL
**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogController.swift`

**Verification**: The `TransparencyLogController` now implements full AES-256-GCM decryption. The `decryptIfNeeded()` method (lines 277-319) correctly:
- Extracts 12-byte nonce, ciphertext, and 16-byte authentication tag from base64-encoded column values
- Uses `CCCryptorGCMOneshotDecrypt` with the Keychain-stored 256-bit key
- Falls back to plaintext for backward compatibility with pre-encryption rows
- Validates minimum ciphertext length (28 bytes) before attempting decryption

The `provisionEncryptionKey()` method (lines 245-269) generates a 256-bit key using `SecRandomCopyBytes` and stores it in the Keychain with `kSecAttrAccessibleAfterFirstUnlock` and `kSecAttrSynchronizable: kCFBooleanFalse`.

The WelcomeView (line 72) now reads "Data is transmitted securely and PII is automatically redacted" — the false "All data is encrypted" claim has been corrected.

**Residual**: See NEW-001 (backward compatibility plaintext fallback).

---

### [RESOLVED] IPC-001: Unix Domain Socket Authentication

**Original Severity**: CRITICAL
**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/IPC/SocketClient.swift`

**Verification**: The `connect()` method (lines 41-98) now implements:
1. **Symlink detection** (lines 44-49): Uses `lstat()` to check `S_IFLNK` before connecting, throwing `SocketError.connectionFailed` on detection
2. **Auth handshake** (lines 86-96): Sends a JSON `{"auth": token}` message using `JSONSerialization` (preventing JSON injection) followed by a newline delimiter

The `authToken` parameter is accepted at init and forwarded during connection. The use of `JSONSerialization.data(withJSONObject:)` rather than string interpolation prevents injection via malformed tokens.

**Residual**: See NEW-002 (no server-side response validation).

---

### [RESOLVED] KEYCHAIN-001: kSecAttrAccessible Added to KeychainHelper

**Original Severity**: HIGH
**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Utilities/KeychainHelper.swift`

**Verification**: Line 20 now includes `kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock`. Line 21 includes `kSecAttrSynchronizable as String: kCFBooleanFalse!`. All three Keychain access sites (`KeychainHelper`, `KeychainConsentStore`, `TransparencyLogController`) are now consistent.

---

### [RESOLVED] CONSENT-001: HMAC-SHA256 Consent Token Signing

**Original Severity**: HIGH
**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift`

**Verification**: The `SignedConsentRecord` wrapper (lines 49-53) pairs each `ConsentRecord` with a hex-encoded HMAC-SHA256 signature. The `save()` method (lines 113-127) computes the HMAC before storage. The `load()` method (lines 83-107) verifies the HMAC and returns `.neverConsented` on mismatch (tamper detection). The HMAC key is 256-bit, generated via `SecRandomCopyBytes`, and stored in the Keychain under the same service namespace.

The encoder uses `.sortedKeys` output formatting (line 149), ensuring canonical JSON for deterministic HMAC computation.

**Residual**: See NEW-003 (legacy unsigned record migration bypass) and NEW-004 (UUID fallback key).

---

### [RESOLVED] CONSENT-002: Consent Revocation Handler

**Original Severity**: HIGH
**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/ConsentManager.swift`

**Verification**: The `ConsentManager` now has:
- `ConsentRevocationHandler` type alias (line 23) as `@MainActor (String) -> Void`
- `onRevocation(_:)` registration method (line 40)
- `revokeConsent()` (lines 56-62) iterates all registered handlers after persisting the revoked state

The handlers are invoked with the `engagementId` so cleanup actions can be engagement-scoped.

**Residual**: See CONSENT-003 update below — handlers exist but are not wired in `KMFlowAgentApp`.

---

### [RESOLVED] LOGGING-001: AgentLogger Now Uses privacy: .private

**Original Severity**: HIGH
**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Utilities/Logger.swift`

**Verification**: All four log level methods (info, debug, warning, error) at lines 13-27 now use `privacy: .private`. This is the Apple-recommended default that redacts interpolated values in log output.

**Residual**: See NEW-005 (`IntegrityChecker` and `PythonProcessManager` still use direct `os.Logger` with `.public`).

---

### [RESOLVED] KEYCHAIN-003: kSecAttrSynchronizable Explicitly Disabled

**Original Severity**: MEDIUM
**Verification**: All three Keychain write sites now explicitly include `kSecAttrSynchronizable: kCFBooleanFalse`:
- `KeychainHelper.swift` line 21
- `KeychainConsentStore.swift` line 174
- `TransparencyLogController.swift` line 264

---

### [RESOLVED] INTEGRITY-001 & INTEGRITY-002: Periodic Checks and Manifest Signature

**Original Severity**: MEDIUM (both)
**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/IntegrityChecker.swift`

**Verification**:
- **Periodic checking** (lines 96-120): `startPeriodicChecks()` runs a detached `Task` that re-verifies at configurable intervals (default 300 seconds / 5 minutes). The `ViolationHandler` callback enables the app delegate to react to runtime tampering.
- **Manifest signature** (lines 147-165, 217-246): `verify()` now looks for an `integrity.sig` file containing an HMAC-SHA256 of the manifest, verifies it using CryptoKit's `HMAC<SHA256>.isValidAuthenticationCode` (constant-time comparison), and fails the check on mismatch.

**Residual**: See NEW-006 (manifest signature verification is gracefully skipped when `.sig` file is missing).

---

### [RESOLVED] ENTITLEMENT-001: Unused Entitlement Removed

**Original Severity**: LOW
**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/KMFlowAgent.entitlements`

**Verification**: The `com.apple.security.files.user-selected.read-write` entitlement has been removed. The entitlements file now contains only hardened runtime flags, network client, and sandbox-disabled.

---

## Open & Partially Resolved Findings

### [PARTIALLY RESOLVED] SANDBOX-001: App Sandbox Disabled — ADR Still Needed

**Original Severity**: HIGH | **Current Severity**: MEDIUM (downgraded — unused entitlement removed)
**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/KMFlowAgent.entitlements:19-20`

**Current State**: The unused `files.user-selected.read-write` entitlement was removed (good). The entitlements file now has a comment (line 17) noting the sandbox is disabled. However, there is no formal Architecture Decision Record documenting:
- Why the sandbox is disabled (CGEventTap requires it)
- What compensating controls exist (hardened runtime, directory permissions, integrity checking)
- What the residual risk is

**Recommendation**: Create an ADR in `docs/adrs/` documenting the sandbox-disabled decision and compensating controls.

---

### [PARTIALLY RESOLVED] CONSENT-003: Consent Not Enforced at Runtime

**Original Severity**: MEDIUM | **Current Severity**: MEDIUM (unchanged)
**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/KMFlowAgentApp.swift:72`

**Current State**: The `ConsentManager` is still created as a local variable in `applicationDidFinishLaunching` (line 72) rather than stored as a property on `AppDelegate`. No `onRevocation` handler is registered. No Combine subscription observes `ConsentManager.$state`. The revocation handler infrastructure exists in `ConsentManager` but is not wired to the app lifecycle.

**Evidence** (current code):
```swift
// Line 72 — local variable, not stored as property
let consentManager = ConsentManager(engagementId: engagementId, store: consentStore)

if consentManager.state == .neverConsented {
    // ...
} else if !consentManager.captureAllowed {
    // ...
} else {
    startPythonSubprocess()
}
```

The `ConsentManager` goes out of scope after this block, meaning:
- No runtime consent enforcement occurs after startup
- The `onRevocation` handler mechanism cannot be utilized
- If consent is revoked via another process writing to the Keychain, the agent continues capturing

**Recommendation**:
1. Store `ConsentManager` as a property on `AppDelegate`
2. Register an `onRevocation` handler that calls `pythonManager.stop()` and deletes `buffer.db`
3. Subscribe to `ConsentManager.$state` via Combine to react to changes

---

### [OPEN] KEYCHAIN-004: Keychain Error Logged to stderr

**Original Severity**: LOW | **Current Severity**: LOW (unchanged)
**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:178-181`

**Current State**: Still uses `fputs` to stderr. The `AgentLogger` is available but importing the `Utilities` module would add a dependency to the `Consent` target, which the code comments explicitly note is designed for zero-dependency footprint.

```swift
fputs("[KeychainConsentStore] SecItemAdd failed: \(status)\n", stderr)
```

**Recommendation**: Accept as-is given the zero-dependency design, or import `os` directly (it is a system framework, not an external dependency) for structured logging.

---

### [OPEN] KEY-LIFECYCLE-001: No Key Rotation Mechanism

**Original Severity**: LOW | **Current Severity**: LOW (unchanged)
**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogController.swift:57`
**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:70`

**Current State**: Both the buffer encryption key (`buffer_encryption_key`) and the HMAC signing key (`consent.hmac_key`) are stored under fixed account names with no versioning or rotation mechanism. `provisionEncryptionKey()` (TransparencyLogController line 247) explicitly does not overwrite an existing key.

**Recommendation**: Design key rotation for a future release. Low urgency for an agent that runs per-engagement with finite lifetime.

---

## New Findings from Re-Audit

### [MEDIUM] NEW-001: Backward Compatibility Plaintext Fallback Weakens Encryption Guarantee

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/UI/TransparencyLogController.swift:277-283, 317-318`
**Severity**: MEDIUM

**Evidence**:
```swift
private func decryptIfNeeded(_ value: String, key: Data?) -> String {
    guard let key = key,
          let cipherData = Data(base64Encoded: value),
          cipherData.count > 28
    else {
        return value // plaintext or no key — return as-is
    }
    // ... decryption ...
    // Line 317-318:
    // Decryption failed — likely plaintext data from before encryption was enabled
    return value
}
```

**Description**: The `decryptIfNeeded` method silently falls back to returning the raw value whenever decryption fails or the value is not valid base64. This is intended for backward compatibility with pre-encryption data, but it means an attacker who gains write access to the SQLite database can insert plaintext rows that will be displayed without any tamper indication. The method cannot distinguish between "legitimate pre-encryption data" and "attacker-injected plaintext."

Additionally, if the encryption key is missing from the Keychain (line 115 returns nil), all rows are returned as plaintext without any warning to the user or log entry.

**Risk**: The backward compatibility path undermines the encryption guarantee. An attacker who can write to `buffer.db` can inject plaintext rows that bypass decryption entirely. The transparency log would display them as normal events with no visual indicator that they were not encrypted.

**Recommendation**:
1. After a migration period, remove the plaintext fallback and treat decryption failures as errors (skip the row or display "[decryption failed]").
2. Add a column or flag to the SQLite schema indicating whether a row is encrypted, rather than inferring from base64 validity.
3. Log a warning when `loadBufferKeyFromKeychain()` returns nil after the agent has been running for more than one session.

---

### [MEDIUM] NEW-002: IPC Auth Handshake Is Fire-and-Forget — No Server Response Validation

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/IPC/SocketClient.swift:86-96`
**Severity**: MEDIUM

**Evidence**:
```swift
if let token = authToken, let fh = fileHandle {
    let authDict: [String: String] = ["auth": token]
    guard let jsonData = try? JSONSerialization.data(withJSONObject: authDict),
          let authData = String(data: jsonData, encoding: .utf8)?.appending("\n").data(using: .utf8)
    else {
        close(fd)
        fileHandle = nil
        throw SocketError.connectionFailed("Failed to encode auth token")
    }
    fh.write(authData)
}
isConnected = true
```

**Description**: The client sends the auth token but never reads a response from the server to confirm the handshake succeeded. The `isConnected` flag is set to `true` immediately after writing the token. If the server rejects the token (wrong secret, expired, etc.), the client will believe it is authenticated and proceed to send event data. The server may silently drop this data, or worse, the data may be queued in the kernel socket buffer and eventually discarded.

**Risk**: A misconfigured auth token would not produce any client-side error. Events could be silently lost. The agent would report "connected" status to the user while data is being dropped.

**Recommendation**:
1. Read a response line from the server after sending the auth token (e.g., `{"status": "ok"}` or `{"status": "rejected"}`).
2. Only set `isConnected = true` after receiving a success response.
3. Throw `SocketError.connectionFailed("Authentication rejected")` on failure.

---

### [MEDIUM] NEW-003: Legacy Unsigned Consent Record Migration Bypasses HMAC Verification

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:99-106`
**Severity**: MEDIUM

**Evidence**:
```swift
} catch {
    // Try loading legacy unsigned records for migration
    do {
        let record = try jsonDecoder().decode(ConsentRecord.self, from: data)
        return record.state
    } catch {
        return .neverConsented
    }
}
```

**Description**: When the outer `SignedConsentRecord` decode or HMAC verification fails, the code falls back to trying to decode the data as an unsigned `ConsentRecord`. This migration path is necessary for upgrading from pre-HMAC installations, but it creates a permanent bypass: an attacker who writes a plain `ConsentRecord` JSON blob to the Keychain (without an HMAC wrapper) will have it accepted without any integrity verification.

The fallback is not time-bounded (no "only accept legacy records created before version X" check) and produces no log warning when a legacy record is loaded.

**Risk**: The HMAC integrity check can be trivially bypassed by writing consent records in the legacy unsigned format. This undermines the tamper detection that HMAC signing was intended to provide.

**Recommendation**:
1. Log a warning when a legacy unsigned record is loaded: `fputs("[KeychainConsentStore] WARNING: Loading unsigned legacy consent record for \(engagementId)\n", stderr)`
2. Immediately re-sign and re-save the record with an HMAC after successful legacy load (one-time migration).
3. Set a deadline (e.g., version 2026.04) after which legacy unsigned records are rejected.

---

### [LOW] NEW-004: HMAC Key Fallback Uses UUID — Weak Entropy

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Consent/KeychainConsentStore.swift:239-241`
**Severity**: LOW

**Evidence**:
```swift
if result != errSecSuccess {
    // Fallback: use a UUID-based key (weaker but functional)
    key = Data(UUID().uuidString.utf8)
}
```

**Description**: If `SecRandomCopyBytes` fails (which should be exceedingly rare on macOS), the HMAC key falls back to a UUID string. A UUID v4 has 122 bits of entropy, but the UTF-8 encoding of its string representation (`"XXXXXXXX-XXXX-4XXX-YXXX-XXXXXXXXXXXX"`) is 36 bytes of ASCII with a constrained character set. This is weaker than the intended 256-bit random key and has a predictable format that could assist brute-force attacks on the HMAC.

**Risk**: Very low probability of occurrence (SecRandomCopyBytes failure on macOS is essentially theoretical). If triggered, the HMAC key would be weaker than intended but still provide some tamper detection.

**Recommendation**: If `SecRandomCopyBytes` fails, consider failing hard rather than falling back to a weak key. A system where the CSPRNG is broken has larger problems.

---

### [LOW] NEW-005: IntegrityChecker and PythonProcessManager Use Direct os.Logger with privacy: .public

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/IntegrityChecker.swift` (multiple lines)
**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/PythonProcessManager.swift` (multiple lines)
**Severity**: LOW

**Description**: While the `AgentLogger` wrapper was fixed to use `privacy: .private`, the `IntegrityChecker` and `PythonProcessManager` use `os.Logger` directly and still mark interpolated values as `privacy: .public`. The exposed values include:
- File paths (IntegrityChecker lines 143, 182, 190)
- Error descriptions (IntegrityChecker line 172, PythonProcessManager line 117)
- Process IDs (PythonProcessManager lines 123, 143, 159)
- Restart counts and exit codes (PythonProcessManager lines 180, 187, 199)

These values are generally non-sensitive (file paths, PIDs, counts), but the error descriptions could contain unexpected content.

**Risk**: Low. The values logged are mostly operational metadata rather than employee behavioral data. File paths within the app bundle are not sensitive. PIDs and exit codes are routine operational data.

**Recommendation**: Consider migrating `IntegrityChecker` and `PythonProcessManager` to use `AgentLogger` for consistency, or mark only error description strings as `.private` while keeping numeric values as `.public`.

---

### [LOW] NEW-006: Manifest Signature Verification Gracefully Skipped When .sig Missing

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/IntegrityChecker.swift:163-164`
**Severity**: LOW

**Evidence**:
```swift
} else {
    log.warning("integrity.sig not found — HMAC verification skipped")
}
```

**Description**: When `integrity.sig` does not exist, the integrity checker logs a warning but proceeds with the file-level SHA-256 verification only. This means a build that ships without a signature file has no manifest-level integrity protection. An attacker who can modify files in the bundle could replace both `integrity.json` and the Python files with matching hashes.

The code comments (lines 149-155) acknowledge this explicitly: "This protects against accidental corruption and naive file replacement, NOT against a sophisticated attacker who can regenerate both files. Full tamper protection relies on macOS code signing."

**Risk**: Low, given that macOS code signing and notarization are the primary tamper protection mechanisms. The HMAC is a defense-in-depth layer.

**Recommendation**: In release/production builds, consider treating a missing `.sig` file the same as a signature mismatch. Development builds can skip via a `#if DEBUG` gate.

---

## Positive Observations (Updated)

The following security-positive patterns were confirmed or newly identified in this re-audit:

1. **AES-256-GCM with per-row nonces**: The `decryptIfNeeded` method correctly handles the nonce-ciphertext-tag format produced by Python's `cryptography` library. Per-row nonces are inherent in the design since each encrypted value has its own 12-byte nonce prefix.

2. **Deterministic HMAC via sorted-keys JSON**: The `JSONEncoder` in `KeychainConsentStore` uses `.sortedKeys` (line 149), ensuring that the same `ConsentRecord` always produces the same JSON byte sequence. This eliminates the class of bugs where key ordering differences cause HMAC verification failures.

3. **HMAC key generated from SecRandomCopyBytes**: The 256-bit HMAC key (line 235) uses Apple's CSPRNG, and the key itself is stored in the Keychain with the same `kSecAttrAccessibleAfterFirstUnlock` + `kSecAttrSynchronizable: false` protections as other secrets.

4. **JSON injection prevention in IPC auth**: The `SocketClient` uses `JSONSerialization.data(withJSONObject:)` (line 88) rather than string interpolation to construct the auth message, preventing an attacker from crafting a token that breaks out of the JSON structure.

5. **Consistent Keychain attributes**: All three Keychain write sites (`KeychainHelper`, `KeychainConsentStore`, `TransparencyLogController.provisionEncryptionKey`) now use identical `kSecAttrAccessibleAfterFirstUnlock` and `kSecAttrSynchronizable: kCFBooleanFalse` settings.

6. **Backend URL validation**: The `PythonProcessManager` (lines 87-94) validates that `KMFLOW_BACKEND_URL` uses the `https` scheme and has a host before forwarding to the Python subprocess. This prevents data exfiltration via a rogue MDM configuration profile.

7. **Hardened runtime correctly configured**: JIT disabled, unsigned executable memory disabled, library validation enabled. These protections are critical given that the app sandbox is disabled.

8. **Sendable and actor isolation**: `SocketClient` is an `actor`, `KeychainConsentStore` is `Sendable`, `ConsentManager` is `@MainActor`-isolated. Swift concurrency safety is properly applied.

9. **HMAC verification uses constant-time comparison**: The `IntegrityChecker` uses CryptoKit's `HMAC<SHA256>.isValidAuthenticationCode` (line 241), which performs constant-time comparison to prevent timing side-channel attacks.

10. **Periodic integrity checking**: The `IntegrityChecker` instance API supports configurable-interval background verification with a violation handler callback, addressing the original concern that integrity was only verified at startup.

---

## Risk Assessment (Updated)

| Category | Original Score | Current Score | Delta | Notes |
|----------|:---:|:---:|:---:|---|
| Keychain Configuration | 5/10 | **8/10** | +3 | Consistent attributes across all sites; no `kSecAttrAccessControl` biometric |
| Data-at-Rest Encryption | 1/10 | **7/10** | +6 | AES-256-GCM implemented; plaintext fallback weakens guarantee |
| IPC Channel Security | 2/10 | **7/10** | +5 | Symlink check + auth handshake; no response validation |
| Consent Integrity | 3/10 | **7/10** | +4 | HMAC-signed; legacy bypass open; runtime enforcement incomplete |
| Integrity Verification | 6/10 | **8/10** | +2 | HMAC signature + periodic checks; .sig optional |
| Secret Handling in Logs | 4/10 | **7/10** | +3 | AgentLogger fixed; 2 modules still use direct os.Logger |
| Key Lifecycle | 2/10 | **4/10** | +2 | Keys generated properly; no rotation mechanism |
| Process Isolation | 5/10 | **6/10** | +1 | Unused entitlement removed; ADR still needed |

**Overall Security Score: 6.8 / 10** (up from 3.5 / 10)

The 3.3-point improvement reflects the closure of both CRITICAL findings and most HIGH findings. The remaining gap to 8+ is driven by the plaintext fallback path, incomplete runtime consent enforcement, and the absence of key rotation and biometric-protected Keychain access controls.

---

## Current Finding Summary

| Severity | Count | Change from Original |
|----------|:-----:|:--------------------:|
| CRITICAL | 0     | -2 (both resolved)   |
| HIGH     | 0     | -5 (all resolved or downgraded) |
| MEDIUM   | 5     | +0 net (2 original open, 3 new) |
| LOW      | 5     | +2 net (2 original open, 3 new) |
| **Total** | **10** | **-5** |

### Open Findings by Severity

| ID | Severity | Title | Priority |
|----|:--------:|-------|:--------:|
| SANDBOX-001 | MEDIUM | App Sandbox disabled — ADR needed | Short-term |
| CONSENT-003 | MEDIUM | Consent not enforced at runtime | Short-term |
| NEW-001 | MEDIUM | Plaintext fallback weakens encryption | Medium-term |
| NEW-002 | MEDIUM | IPC auth handshake fire-and-forget | Medium-term |
| NEW-003 | MEDIUM | Legacy unsigned consent record bypass | Short-term |
| KEYCHAIN-004 | LOW | Keychain error logged to stderr | Long-term |
| KEY-LIFECYCLE-001 | LOW | No key rotation mechanism | Long-term |
| NEW-004 | LOW | HMAC key UUID fallback — weak entropy | Long-term |
| NEW-005 | LOW | Direct os.Logger with privacy: .public | Long-term |
| NEW-006 | LOW | Manifest signature skipped when .sig missing | Medium-term |

---

## Priority Remediation Roadmap (Updated)

### Short-Term (Next Sprint)
1. **Wire ConsentManager to AppDelegate** — store as property, register `onRevocation` handler, subscribe to `$state` [CONSENT-003]
2. **Re-sign legacy consent records on load** — one-time migration to close the unsigned bypass [NEW-003]
3. **Create ADR for sandbox-disabled decision** [SANDBOX-001]

### Medium-Term (Within 1 Month)
4. **Add server response validation to IPC auth handshake** [NEW-002]
5. **Add encrypted/plaintext flag to SQLite schema** and remove plaintext fallback after migration [NEW-001]
6. **Require integrity.sig in release builds** via `#if DEBUG` gate [NEW-006]

### Long-Term (Backlog)
7. **Design key rotation** for buffer encryption key and HMAC key [KEY-LIFECYCLE-001]
8. **Migrate IntegrityChecker and PythonProcessManager to AgentLogger** [NEW-005]
9. **Consider kSecAttrAccessControl with biometric protection** for high-value keys [KEYCHAIN-004 context]
10. **Fail hard on SecRandomCopyBytes failure** rather than UUID fallback [NEW-004]
