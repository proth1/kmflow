# E1: Entitlements & TCC Re-Audit Report

**Agent**: E1 (Entitlements & TCC Re-Auditor)
**Date**: 2026-02-26
**Scope**: macOS Task Mining Agent entitlements, TCC profiles, Hardened Runtime, Info.plist, signing scripts
**Auditor Model**: Claude Opus 4.6
**Audit Type**: Post-remediation re-audit (Phases 1-3 remediation in PRs #248, #251, #255, #256, #258)

---

## Summary: Previous vs. Current Findings

| Severity | Previous (2026-02-25) | Current (2026-02-26) | Change |
|----------|:---------------------:|:--------------------:|:------:|
| CRITICAL | 1 | 0 | -1 (RESOLVED) |
| HIGH | 3 | 0 | -3 (RESOLVED / DOWNGRADED) |
| MEDIUM | 5 | 3 | -2 (2 RESOLVED, 1 DOWNGRADED to LOW, 2 OPEN) |
| LOW | 3 | 3 | 0 (1 RESOLVED, 1 DOWNGRADED from MEDIUM, 1 NEW) |
| **Total** | **12** | **6** | **-6** |

### Disposition of All 12 Original Findings

| ID | Original Severity | Finding | Status | Notes |
|----|:-----------------:|---------|:------:|-------|
| ENTITLEMENT-001 | CRITICAL | Apple Events entitlement unused | RESOLVED | Removed in PR #248 |
| ENTITLEMENT-002 | HIGH | files.user-selected.read-write without sandbox | RESOLVED | Removed in PR #255; comment documents rationale |
| ENTITLEMENT-003 | HIGH | Hardened Runtime missing in build script | RESOLVED | `--options runtime` added to all codesign invocations in PR #251 |
| TCC-001 | HIGH | REPLACE_TEAM_ID placeholder in CodeRequirement | PARTIALLY_RESOLVED | customize-profiles.sh added in PR #258; see MEDIUM finding below |
| ENTITLEMENT-004 | MEDIUM | App Sandbox disabled without ADR | RESOLVED | ADR 001 created in PR #258 |
| TCC-002 | MEDIUM | ScreenCapture pre-authorized for unimplemented feature | RESOLVED | Removed from TCC profile; clear comment marks it as Phase 2 |
| SIGNING-001 | MEDIUM | Inconsistent Hardened Runtime between scripts | RESOLVED | Both scripts now use `--options runtime`; `--deep` removed from sign-all.sh |
| KEYCHAIN-001 | MEDIUM | KeychainHelper missing kSecAttrAccessible | RESOLVED | Now sets `kSecAttrAccessibleAfterFirstUnlock` and `kSecAttrSynchronizable` |
| LOGGING-001 | MEDIUM | All logger messages privacy: .public | PARTIALLY_RESOLVED | AgentLogger fixed; IntegrityChecker and PythonProcessManager still use .public |
| PLIST-001 | LOW | NSScreenCaptureUsageDescription for unimplemented feature | OPEN | Still present in Info.plist |
| PLATFORM-001 | LOW | Platform version alignment | RESOLVED | Positive finding; still correct |
| CONFIG-001 | LOW | Placeholder engagement ID | RESOLVED | By-design template placeholder; customize-profiles.sh covers deployment |

---

## Current Risk Score

**Overall Entitlement & TCC Security Score: 8.5 / 10** (up from 6.5/10)

The CRITICAL and all HIGH findings have been resolved. The remaining issues are MEDIUM and LOW severity items that do not block deployment but should be addressed before general availability. The entitlements file is now minimal (network.client only, sandbox explicitly off with documented ADR), the TCC profile is scoped to Accessibility only, and all signing scripts consistently apply Hardened Runtime.

---

## Remaining Findings (6)

### [MEDIUM] TCC-001-R: TCC CodeRequirement Placeholder Remains in Source Template

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.tcc.mobileconfig:107`
**Agent**: E1 (Entitlements & TCC Re-Auditor)
**Status**: PARTIALLY_RESOLVED
**Evidence**:
```xml
<key>CodeRequirement</key>
<string>identifier "com.kmflow.agent" and anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] and certificate leaf[field.1.2.840.113635.100.6.1.13] and certificate leaf[subject.OU] = "REPLACE_TEAM_ID"</string>
```
**Description**: The `customize-profiles.sh` script (added in PR #258) correctly validates the Team ID format (10-character alphanumeric) and performs string substitution across all `.mobileconfig` files. This is a significant improvement -- there is now a documented, validated path from template to deployment-ready profile. However, two gaps remain: (1) there is no CI gate that prevents the raw template from being deployed to MDM without running `customize-profiles.sh`, and (2) the customized profiles are written to a `customized/` subdirectory that is not committed to source control, so the deployment-ready profile exists only as a local artifact with no version-controlled audit trail.

**Risk**: An MDM administrator could deploy the raw template from source control rather than the customized output, resulting in silent TCC authorization failure. The probability is reduced by the clear REPLACE_TEAM_ID placeholder and the script's documentation, but enterprise deployments with automated MDM pipelines remain at risk.

**Recommendation**: (1) Add a CI check (e.g., `grep -r REPLACE_TEAM_ID installer/profiles/customized/` that fails the build if the customized output still contains placeholders). (2) Consider adding a `--verify` flag to `customize-profiles.sh` that checks the output directory for remaining placeholders. (3) Document the profile customization step in the deployment runbook with a verification checklist.

---

### [MEDIUM] LOGGING-001-R: IntegrityChecker and PythonProcessManager Still Use privacy: .public

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/IntegrityChecker.swift:143,172,182,190,197,200`
**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/PythonProcessManager.swift:67,117,123,143,159,180,187,199`
**Agent**: E1 (Entitlements & TCC Re-Auditor)
**Status**: PARTIALLY_RESOLVED
**Evidence from IntegrityChecker.swift**:
```swift
log.error("integrity.json not found at \(manifestURL.path, privacy: .public)")
log.error("Integrity violation — digest mismatch: \(relativePath, privacy: .public) expected=\(expectedHex, privacy: .public) actual=\(actualHex, privacy: .public)")
```
**Evidence from PythonProcessManager.swift**:
```swift
log.error("kmflow-python shim not found at \(shimURL.path, privacy: .public)")
log.error("Failed to launch Python subprocess: \(error.localizedDescription, privacy: .public)")
log.info("Python subprocess started with PID \(proc.processIdentifier, privacy: .public)")
```
**Description**: The `AgentLogger` wrapper (used by most of the codebase) was correctly updated to use `privacy: .private` in all methods (PR #256). However, `IntegrityChecker.swift` and `PythonProcessManager.swift` use `os.Logger` directly (bypassing `AgentLogger`) and retain 14 occurrences of `privacy: .public`. The data logged includes file paths (which may contain usernames in `~/Library/...` paths), error descriptions, and process identifiers.

The current content being logged (file paths, PIDs, hash digests) is relatively low-risk. File paths could leak the macOS username (`/Users/jsmith/...`) which is PII under GDPR. Error descriptions from the system could theoretically contain sensitive context.

**Risk**: System logs on macOS are readable by any admin user and are included in sysdiagnose archives. Leaking the local username via file paths in system-wide logs is a minor GDPR concern. The risk is lower than the original finding because the most dangerous call sites (in the capture layer) now use the private `AgentLogger`.

**Recommendation**: Migrate `IntegrityChecker` and `PythonProcessManager` to use `AgentLogger` instead of `os.Logger` directly. If direct `os.Logger` usage is preferred for these modules (e.g., for subsystem separation), change all interpolations to `privacy: .private` and selectively mark only safe values (PID integers, file counts) as `.public`.

---

### [MEDIUM] INTEGRITY-001: HMAC Key Co-located With Signature Provides Limited Tamper Protection

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/build-app-bundle.sh:308-324`
**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/IntegrityChecker.swift:147-165`
**Agent**: E1 (Entitlements & TCC Re-Auditor)
**Status**: NEW
**Evidence from build-app-bundle.sh**:
```python
# Compute HMAC-SHA256 signature with a per-build random key.
# The key is embedded in the signature file alongside the HMAC.
hmac_key = secrets.token_bytes(32)
sig = hmac.new(hmac_key, manifest_json.encode(), hashlib.sha256).hexdigest()
sig_payload = {
    "hmac_sha256": sig,
    "key_hex": hmac_key.hex(),
    "manifest_sha256": hashlib.sha256(manifest_json.encode()).hexdigest(),
}
```
**Evidence from IntegrityChecker.swift**:
```swift
// Threat model: the HMAC key is co-located with the signature inside
// the code-signed bundle. This protects against accidental corruption
// and naive file replacement, NOT against a sophisticated attacker who
// can regenerate both files.
```
**Description**: The integrity manifest HMAC signature stores the HMAC key alongside the HMAC value in `integrity.sig`. An attacker who can write to the bundle's Resources directory can trivially regenerate both the manifest and its signature. The code comments correctly acknowledge this limitation (lines 148-155 of IntegrityChecker.swift), and full tamper protection is delegated to macOS code signing. This is a sound design for a code-signed bundle.

However, the `IntegrityChecker.verify()` method logs a warning and continues if `integrity.sig` is missing (line 163-164: "HMAC verification skipped"). This means an attacker could delete the `.sig` file and modify the manifest, and the checker would only log a warning rather than treating the missing signature as a failure. The HMAC check is effectively opt-out.

**Risk**: In scenarios where code signing is not enforced (development builds, CI pipelines, or if Gatekeeper is bypassed), the integrity check provides the primary tamper detection. Allowing the HMAC verification to be skipped by deleting one file weakens this defense-in-depth layer.

**Recommendation**: Treat a missing `integrity.sig` as a verification failure when the build is a release build (e.g., check for a `KMFLOW_RELEASE_BUILD` environment variable or a build configuration flag embedded in Info.plist). In development builds, the warning-and-continue behavior is acceptable. Alternatively, fail closed: if `integrity.sig` is expected to exist (as it is generated by the build script), its absence should be treated as an integrity violation.

---

### [LOW] PLIST-001-R: NSScreenCaptureUsageDescription Still Present for Unimplemented Feature

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/Info.plist:34-35`
**Agent**: E1 (Entitlements & TCC Re-Auditor)
**Status**: OPEN
**Evidence**:
```xml
<key>NSScreenCaptureUsageDescription</key>
<string>KMFlow Agent needs Screen Recording access for optional screenshot-based process analysis (Phase 2).</string>
```
**Description**: The ScreenCapture TCC authorization was correctly removed from the PPPC profile (TCC-002 RESOLVED). However, the `NSScreenCaptureUsageDescription` key remains in `Info.plist`. While this does not grant any permission by itself, it means macOS may still present a "KMFlow Agent would like to record the contents of your screen" dialog if certain APIs are invoked. The text references "Phase 2" -- an internal milestone label that should not appear in user-facing strings.

The `EventProtocol.swift` still defines `case screenCapture = "screen_capture"` (line 25) and `TransparencyLogView.swift` still has a display case for it (line 239). These are enum definitions for a future feature and do not trigger any permission prompts on their own.

**Risk**: Low. The description alone does not grant permission. However, on some macOS versions, the PermissionsManager's screen recording check heuristic could trigger the prompt. Users seeing an unexpected screen recording dialog for a "Phase 2" feature would understandably distrust the agent.

**Recommendation**: Remove `NSScreenCaptureUsageDescription` from `Info.plist` until the screen capture feature is implemented. If kept for forward-compatibility, at minimum change the text to remove the "Phase 2" internal reference and write a user-appropriate description.

---

### [LOW] TCC-003: TCC Profile Header Comment Still References Screen Capture

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.tcc.mobileconfig:8`
**Agent**: E1 (Entitlements & TCC Re-Auditor)
**Status**: NEW
**Evidence**:
```xml
<!--
  com.kmflow.agent.tcc.mobileconfig — TCC/PPPC Configuration Profile
  ...
  This profile pre-authorises the KMFlow Agent for Accessibility and
  (optionally) Screen Capture access via MDM-pushed Privacy Preferences
  Policy Control (PPPC).
-->
```
**Description**: The XML header comment on line 8 still states the profile authorizes "Accessibility and (optionally) Screen Capture access." The ScreenCapture block was correctly removed from the profile payload (the body now only contains Accessibility), but the header comment was not updated to reflect this. This is a documentation inconsistency that could confuse MDM administrators reviewing the profile.

**Risk**: Low. This is a comment-only issue with no functional impact. An MDM administrator reading the header might expect to find a ScreenCapture block and wonder if it was accidentally removed.

**Recommendation**: Update the header comment to read: "This profile pre-authorises the KMFlow Agent for Accessibility access via MDM-pushed Privacy Preferences Policy Control (PPPC)." Remove the Screen Capture reference.

---

### [LOW] CONFIG-002: Sequential Placeholder PayloadUUIDs in MDM Profiles

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.tcc.mobileconfig:49,78`
**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.mobileconfig:40,70`
**Agent**: E1 (Entitlements & TCC Re-Auditor)
**Status**: OPEN
**Evidence from tcc.mobileconfig**:
```xml
<key>PayloadUUID</key>
<string>C3D4E5F6-A7B8-9012-CDEF-123456789012</string>
...
<key>PayloadUUID</key>
<string>D4E5F6A7-B8C9-0123-DEFA-234567890123</string>
```
**Evidence from com.kmflow.agent.mobileconfig**:
```xml
<key>PayloadUUID</key>
<string>A1B2C3D4-E5F6-7890-ABCD-EF1234567890</string>
...
<key>PayloadUUID</key>
<string>B2C3D4E5-F6A7-8901-BCDE-F12345678901</string>
```
**Description**: All four PayloadUUID values across both profiles use visually sequential hex patterns (A1B2C3D4, B2C3D4E5, C3D4E5F6, D4E5F6A7). While these are syntactically valid UUIDs, they are not RFC 4122 compliant (no version/variant bits set) and their sequential pattern makes it obvious they are placeholders. If two different organizations deploy profiles with these same UUIDs, MDM systems may treat them as the same profile, causing conflicts.

The `customize-profiles.sh` script replaces `REPLACE_TEAM_ID` and `REPLACE_ORG_NAME` but does not regenerate PayloadUUIDs. Each deployment should have unique UUIDs.

**Risk**: Low. PayloadUUID collisions between different organizations would cause MDM profile management confusion but no direct security impact. Within a single organization deploying to multiple engagement groups, reusing UUIDs could cause profile update conflicts.

**Recommendation**: Add UUID regeneration to `customize-profiles.sh` using `uuidgen` for each PayloadUUID. Alternatively, document that MDM administrators must regenerate UUIDs before deployment.

---

## Resolved Findings Detail

### [RESOLVED] ENTITLEMENT-001: Apple Events Entitlement (was CRITICAL)

**Resolved in**: PR #248
**Evidence**: The `com.apple.security.automation.apple-events` key has been completely removed from `KMFlowAgent.entitlements`. The entitlements file now contains only:
- `com.apple.security.cs.allow-jit` = false
- `com.apple.security.cs.allow-unsigned-executable-memory` = false
- `com.apple.security.cs.disable-library-validation` = false
- `com.apple.security.network.client` = true
- `com.apple.security.app-sandbox` = false

This is a minimal, correct entitlement set for a Hardened Runtime monitoring agent that requires network access and cannot run in sandbox.

### [RESOLVED] ENTITLEMENT-002: files.user-selected.read-write (was HIGH)

**Resolved in**: PR #255
**Evidence**: The entitlement has been removed. A descriptive comment replaces it:
```xml
<!-- App Sandbox is disabled; files.user-selected.read-write entitlement
     removed because it has no effect outside the sandbox. -->
```

### [RESOLVED] ENTITLEMENT-003: Hardened Runtime Missing in Build Script (was HIGH)

**Resolved in**: PR #251
**Evidence**: All codesign invocations in `build-app-bundle.sh` now include `--options runtime`:
- Line 344-346: dylib/so signing includes `--options runtime`
- Line 351: Python binary signing includes `--options runtime`
- Line 361-366: Swift binary signing includes `--options runtime`
- Line 370-376: Bundle signing includes `--options runtime`

The `--deep` flag has also been removed from the bundle-level signing. Components are signed individually (inside-out), and the bundle is signed as a whole without re-traversing nested code. This matches Apple's recommended practice.

### [RESOLVED] ENTITLEMENT-004: App Sandbox Disabled Without ADR (was MEDIUM)

**Resolved in**: PR #258
**Evidence**: ADR 001 (`agent/macos/docs/adr/001-sandbox-disabled.md`) provides a thorough architectural decision record documenting:
- Why sandbox is incompatible (AXUIElement, CGEventTap, Unix socket IPC, Python.framework)
- Compensating controls (Hardened Runtime, notarization, entitlement minimization, TCC enforcement)
- Alternatives considered (temporary exceptions, split architecture)
- Distribution implications (no App Store, Developer ID + notarization path)

### [RESOLVED] TCC-002: ScreenCapture Pre-Authorized (was MEDIUM)

**Resolved in**: PR #258 (or related)
**Evidence**: The ScreenCapture block has been completely removed from `com.kmflow.agent.tcc.mobileconfig`. Lines 125-130 now contain only a comment explaining the removal and referencing a future separate profile for Phase 2.

### [RESOLVED] SIGNING-001: Inconsistent Hardened Runtime Between Scripts (was MEDIUM)

**Resolved in**: PR #251
**Evidence**: Both `build-app-bundle.sh` and `sign-all.sh` now consistently use `--options runtime` in all codesign invocations. The `sign-all.sh` script no longer uses `--deep` -- it signs nested binaries individually (deepest-first) then signs the bundle, matching the pattern in `build-app-bundle.sh`.

### [RESOLVED] KEYCHAIN-001: Missing kSecAttrAccessible (was MEDIUM)

**Resolved in**: PR #256
**Evidence**: `KeychainHelper.save()` now sets both protection attributes:
```swift
kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
kSecAttrSynchronizable as String: kCFBooleanFalse!,
```
This matches the `KeychainConsentStore` implementation, establishing a consistent Keychain protection posture across the codebase.

---

## Positive Security Observations (Unchanged or Improved)

1. **Minimal entitlement surface**: Only `network.client` is actively granted. All Hardened Runtime dangerous capabilities explicitly disabled (JIT, unsigned memory, library validation all false).

2. **TCC profile scoped to Accessibility only**: ScreenCapture removed. StaticCode=false provides runtime re-validation of binary signatures.

3. **Consistent Hardened Runtime**: All codesign invocations across both build and re-signing scripts include `--options runtime`.

4. **No `--deep` flag**: Components are signed individually in inside-out order, then the bundle is signed as a whole. This prevents the masking of individual signing failures that `--deep` can cause.

5. **Release build guard**: `release.sh` and `sign-all.sh` both refuse ad-hoc signing (`-`) for release builds.

6. **Consent records HMAC-signed**: `KeychainConsentStore` now implements HMAC-SHA256 signing of consent records with a per-install random key, preventing local consent forgery.

7. **Profile customization tooling**: `customize-profiles.sh` validates Team ID format (10-character alphanumeric regex) and processes all templates in a single pass.

8. **ADR documentation**: The sandbox-disabled decision is formally documented with context, consequences, and alternatives considered.

9. **Privacy-default logging**: `AgentLogger` now uses `privacy: .private` for all log levels, preventing PII leakage through the primary logging path.

10. **Periodic integrity checking**: `IntegrityChecker` supports configurable-interval background re-verification (default 5 minutes), not just startup-only checks.

11. **Python environment isolation**: `python-launcher.sh` explicitly sets `PYTHONPATH` to bundle-internal paths only, sets `PYTHONNOUSERSITE=1`, and does not inherit the caller's `PYTHONPATH`.

12. **PrivacyInfo.xcprivacy properly declared**: Privacy manifest correctly documents Product Interaction data collection and Required Reason API usage.

---

## Risk Assessment

| Category | Score | Notes |
|----------|:-----:|-------|
| Entitlement minimization | 9/10 | Only network.client granted; all dangerous HR flags disabled |
| TCC profile correctness | 8/10 | Accessibility-only; placeholder remains in template (mitigated by customize-profiles.sh) |
| Hardened Runtime | 10/10 | Consistent across all signing paths; verified by verify-signing.sh |
| Keychain security | 9/10 | Consistent protection class, sync disabled, HMAC-signed consent |
| Logging hygiene | 7/10 | Primary logger fixed; 2 modules still use .public |
| Build pipeline security | 8/10 | Release guard, individual signing, integrity manifest; HMAC skip-on-missing is a gap |
| Documentation | 9/10 | ADR for sandbox, clear profile comments, script documentation |

**Overall: 8.5 / 10**

The agent's entitlement and TCC posture has improved significantly. The remaining findings are low-to-medium severity and primarily concern defense-in-depth improvements rather than exploitable vulnerabilities. No finding blocks deployment to a supervised MDM environment, provided the `customize-profiles.sh` workflow is followed before pushing profiles.

**Priority remediation order for remaining items**:
1. Migrate IntegrityChecker and PythonProcessManager to use `AgentLogger` or switch to `privacy: .private` (MEDIUM)
2. Harden integrity.sig missing-file handling for release builds (MEDIUM)
3. Add CI validation for customize-profiles.sh output (MEDIUM)
4. Remove NSScreenCaptureUsageDescription from Info.plist (LOW)
5. Update TCC profile header comment (LOW)
6. Add UUID regeneration to customize-profiles.sh (LOW)
