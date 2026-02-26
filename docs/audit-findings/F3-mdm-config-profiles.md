# F3: MDM & Configuration Profile Re-Audit

**Agent**: F3 (MDM & Configuration Profile Auditor)
**Date**: 2026-02-26 (Re-audit)
**Original Audit Date**: 2026-02-25
**Scope**: MDM configuration profiles, TCC/PPPC profile, profile signing, config injection surface, blocklist security, enterprise MDM compatibility, whitepaper claim verification
**Classification**: Confidential -- Security Audit Finding

---

## Re-Audit Context

The original F3 audit (2026-02-25) identified 13 findings (1 CRITICAL, 3 HIGH, 5 MEDIUM, 4 LOW). Remediation was performed across PRs #245, #248, #255, and #258. This re-audit verifies each finding's current status and identifies any new or residual issues.

---

## Finding Summary (Post-Remediation)

| ID | Original Severity | Finding | Status | Current Severity |
|----|:-:|------|--------|:-:|
| TCC-001 | CRITICAL | ScreenCapture TCC pre-authorized | **FIXED** | -- |
| CFG-001 | HIGH | No bounds validation on MDM config values | **FIXED** | -- |
| CFG-002 | HIGH | Backend URL not validated (data exfil risk) | **FIXED** | -- |
| TCC-002 | HIGH | REPLACE_TEAM_ID placeholder unusable | **PARTIALLY FIXED** | MEDIUM |
| SIGN-001 | MEDIUM | Profile verification uses -noverify | **OPEN** | MEDIUM |
| PROF-001 | MEDIUM | PayloadOrganization hardcoded | **PARTIALLY FIXED** | LOW |
| PROF-002 | MEDIUM | No ConsentText in config profile | **OPEN** | MEDIUM |
| SCOPE-001 | MEDIUM | TCC System scope vs User config scope | **OPEN** (Accepted Risk) | LOW |
| BLK-001 | MEDIUM | Null bundleId bypasses blocklist | **SPLIT** -- see below | -- |
| BLK-001a | -- | BlocklistManager: nil bundleId | **FIXED** | -- |
| BLK-001b | -- | CaptureContextFilter.isBlockedApp: nil bundleId | **OPEN** | MEDIUM |
| PROF-003 | LOW | Sequential placeholder PayloadUUIDs | **OPEN** | LOW |
| PROF-004 | LOW | PayloadRemovalDisallowed=false, no detection | **OPEN** | LOW |
| SIGN-002 | LOW | No passphrase support for signing key | **OPEN** | LOW |
| COMPAT-001 | LOW | Allowed key vs Authorization key | **OPEN** (Accepted Risk) | LOW |
| **NEW** CUST-001 | -- | customize-profiles.sh org-name substitution is a no-op | **NEW** | MEDIUM |

### Post-Remediation Totals

| Severity | Count |
|----------|:-----:|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 4 |
| LOW | 6 |
| **Open Total** | **10** |
| Fixed | 4 |
| Accepted Risk | 2 |

---

## Verified FIXED Findings

### [FIXED] TCC-001: ScreenCapture TCC Pre-Authorized (was CRITICAL)

**Remediation PR**: #245
**Verification**: The ScreenCapture block has been removed from `com.kmflow.agent.tcc.mobileconfig`. Lines 125-130 now contain a clear comment stating that screen capture is NOT enabled by default and that a separate profile (`com.kmflow.agent.screencapture.mobileconfig`) must be deployed if content_level capture is approved.

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.tcc.mobileconfig:125-130`
**Evidence**:
```xml
<!-- ScreenCapture — REMOVED from default profile.           -->
<!-- Screen capture is NOT enabled by default. If needed     -->
<!-- for Phase 2 content_level capture, deploy a separate    -->
<!-- profile: com.kmflow.agent.screencapture.mobileconfig   -->
```

**Verdict**: The TCC profile now grants only Accessibility -- consistent with the whitepaper's "only Accessibility" claim. The trust gap between documentation and shipped artifact is closed. **FIXED.**

---

### [FIXED] CFG-001: No Input Validation on MDM-Configurable Values (was HIGH)

**Remediation PR**: #255
**Verification**: `AgentConfig.swift` now applies `Self.clamp()` bounds validation to all four integer MDM-configurable values.

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Config/AgentConfig.swift:59-78`
**Evidence**:
```swift
self.screenshotIntervalSeconds = Self.clamp(
    defaults.object(forKey: "ScreenshotIntervalSeconds") != nil
        ? defaults.integer(forKey: "ScreenshotIntervalSeconds") : 30,
    min: 5, max: 3600
)
self.batchSize = Self.clamp(
    defaults.object(forKey: "BatchSize") != nil
        ? defaults.integer(forKey: "BatchSize") : 1000,
    min: 1, max: 10000
)
self.batchIntervalSeconds = Self.clamp(
    defaults.object(forKey: "BatchIntervalSeconds") != nil
        ? defaults.integer(forKey: "BatchIntervalSeconds") : 30,
    min: 5, max: 3600
)
self.idleTimeoutSeconds = Self.clamp(
    defaults.object(forKey: "IdleTimeoutSeconds") != nil
        ? defaults.integer(forKey: "IdleTimeoutSeconds") : 300,
    min: 30, max: 3600
)
```

The `clamp` helper is defined at line 83-85:
```swift
private static func clamp(_ value: Int, min: Int, max: Int) -> Int {
    Swift.max(min, Swift.min(value, max))
}
```

**Assessment of bounds**:
- `screenshotIntervalSeconds`: min 5, max 3600 -- reasonable. Min of 5 seconds prevents extreme resource consumption. Could argue min should be 10 for privacy proportionality, but 5 is acceptable.
- `batchSize`: min 1, max 10000 -- fixes the division-by-zero / memory exhaustion risk. Min of 1 is safe (no zero).
- `batchIntervalSeconds`: min 5, max 3600 -- prevents continuous upload flooding.
- `idleTimeoutSeconds`: min 30, max 3600 -- prevents "never idle" configuration.

**Verdict**: All integer values are bounds-clamped. The original risk of resource exhaustion, division-by-zero, and network flooding via misconfigured MDM values is mitigated. **FIXED.**

---

### [FIXED] CFG-002: Backend URL Not Validated -- Data Exfiltration Risk (was HIGH)

**Remediation PR**: #255
**Verification**: `PythonProcessManager.swift` now validates the backend URL before passing it to the Python subprocess.

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/PythonProcessManager.swift:85-94`
**Evidence**:
```swift
if let backendURL = defaults.string(forKey: "KMFLOW_BACKEND_URL"), !backendURL.isEmpty {
    // Validate URL scheme to prevent data exfiltration via rogue MDM config
    if let url = URL(string: backendURL),
       let scheme = url.scheme?.lowercased(),
       scheme == "https",
       url.host != nil {
        environment["KMFLOW_BACKEND_URL"] = backendURL
    } else {
        log.error("Invalid KMFLOW_BACKEND_URL — must be a valid https:// URL with a host")
    }
}
```

**Assessment**:
- HTTPS scheme enforced -- `http://` URLs are rejected, preventing cleartext data transmission.
- URL structure validated -- malformed strings (e.g., `; rm -rf /`) are rejected by `URL(string:)` + host check.
- Error logged when validation fails -- provides diagnostic visibility.

**Residual observation (informational, not a finding)**: There is no domain allow-list or certificate pinning. A rogue MDM admin could still redirect to `https://evil.attacker.com`. However, this requires MDM server compromise -- which represents a different threat model (a compromised MDM can do far worse than redirect a URL). The HTTPS enforcement is the appropriate Phase 1 control. Domain pinning or mTLS (noted as future in ConnectionView) would strengthen this in Phase 2.

**Verdict**: The data exfiltration risk from plaintext HTTP and malformed URLs is closed. The HTTPS enforcement is correctly implemented. **FIXED.**

---

### [FIXED] BLK-001a: Null BundleId Bypasses BlocklistManager (was part of MEDIUM BLK-001)

**Remediation PR**: Not identified in PR list; present in current codebase.
**Verification**: `BlocklistManager.shouldCapture` now returns `false` for nil bundle identifiers.

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Config/BlocklistManager.swift:33-34`
**Evidence**:
```swift
public func shouldCapture(bundleId: String?) -> Bool {
    guard let bid = bundleId else { return false }
```

**Verdict**: The `BlocklistManager` actor correctly blocks processes with unknown bundle identifiers. The least-privilege default is applied. **FIXED.** However, `CaptureContextFilter.isBlockedApp` remains unfixed -- see BLK-001b below.

---

## Open Findings (Carried Forward or Residual)

### [MEDIUM] TCC-002: REPLACE_TEAM_ID Placeholder (was HIGH, downgraded)

**Original Severity**: HIGH
**Current Severity**: MEDIUM (downgraded because customize-profiles.sh partially mitigates)
**Remediation PR**: #258 (customize-profiles.sh created)

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.tcc.mobileconfig:107`
**Evidence**:
```xml
<key>CodeRequirement</key>
<string>identifier "com.kmflow.agent" and anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] and certificate leaf[field.1.2.840.113635.100.6.1.13] and certificate leaf[subject.OU] = "REPLACE_TEAM_ID"</string>
```

**Remediation assessment**: `customize-profiles.sh` (PR #258) addresses this by providing a script that replaces `REPLACE_TEAM_ID` with the actual Apple Developer Team ID. The script includes robust validation:
- Team ID is required (`--team-id` flag)
- Format validation: must be a 10-character alphanumeric string matching `^[A-Z0-9]{10}$`
- Template discovery and bulk replacement

**Why downgraded to MEDIUM**: The existence of `customize-profiles.sh` provides a documented, validated substitution path. An MDM admin who follows the documented workflow will get a correctly customized profile. The risk of deploying an un-substituted profile is reduced (though not eliminated -- the templates are still directly deployable without running the script).

**Remaining gaps**:
1. No runtime validation that `REPLACE_TEAM_ID` has been substituted. The script does not verify its own output for residual placeholders.
2. No prominent warning at the top of the TCC profile file. The placeholder instruction is still buried at line 100-104 inside XML comments.
3. The script does not regenerate PayloadUUID values (see PROF-003).

**Recommendation**: Add a post-substitution verification step to `customize-profiles.sh`:
```bash
if grep -q "REPLACE_" "$OUTPUT_FILE"; then
    echo "ERROR: Residual placeholders found in $OUTPUT_FILE" >&2
    exit 1
fi
```

---

### [MEDIUM] BLK-001b: CaptureContextFilter.isBlockedApp Returns false for nil BundleId

**Original Finding**: Part of BLK-001
**Current Severity**: MEDIUM

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/PII/CaptureContextFilter.swift:37-39`
**Evidence**:
```swift
public static func isBlockedApp(bundleId: String?, blocklist: Set<String>) -> Bool {
    guard let bid = bundleId else { return false }
    return blocklist.contains(bid)
}
```

**Description**: While `BlocklistManager.shouldCapture` was fixed to return `false` for nil bundle IDs (BLK-001a), the static method `CaptureContextFilter.isBlockedApp` still returns `false` (not blocked) when `bundleId` is nil. This method is a separate code path from BlocklistManager.

**Mitigating factor**: The primary capture path (`AppSwitchMonitor`) calls `BlocklistManager.shouldCapture`, which IS fixed. `CaptureContextFilter.isBlockedApp` appears to be the older static implementation. A search of the codebase shows it is not called in the active capture path -- `AppSwitchMonitor.swift:69` uses `blocklistManager.shouldCapture`, not `CaptureContextFilter.isBlockedApp`. However, the static method exists as a public API and could be called by future code or tests without the nil-safe behavior.

**Risk**: Low-to-medium. The active capture path is protected by the fixed `BlocklistManager`. The static method is a latent inconsistency that could cause a regression if used in new code.

**Recommendation**: Align `CaptureContextFilter.isBlockedApp` with `BlocklistManager.shouldCapture`:
```swift
guard let bid = bundleId else { return true }  // nil bundleId = blocked
```

---

### [MEDIUM] SIGN-001: Profile Verification Uses -noverify Flag

**Status**: OPEN (no remediation attempted)
**Current Severity**: MEDIUM

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/sign-profile.sh:123`
**Evidence**:
```bash
if openssl smime -verify -inform der -noverify -in "$SIGNED_PROFILE" -out /dev/null 2>&1; then
    echo "  Signature structure: valid"
else
    echo "  WARNING: openssl smime -verify returned non-zero." >&2
    echo "           This may be expected if the cert is not in the system trust store." >&2
```

**Description**: Unchanged from original audit. The `-noverify` flag skips certificate chain validation. The verification only checks CMS structure -- not certificate trust, expiry, or revocation. When verification fails, the script does not exit with a non-zero status code. It prints a warning and proceeds to the "Profile Signing Complete" success message. A CI/CD pipeline would see exit code 0 regardless of signature validity.

**Risk**: An expired, revoked, or untrusted signing certificate produces a signed profile that passes this script's verification. Automated pipelines will not catch the issue.

**Recommendation**: Unchanged from original audit. Remove `-noverify`, validate chain via `-CAfile`, and exit non-zero on failure.

---

### [MEDIUM] PROF-002: No ConsentText Dictionary in Config Profile

**Status**: OPEN (no remediation attempted)
**Current Severity**: MEDIUM

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.mobileconfig` (entire file)

**Description**: Unchanged from original audit. The application configuration profile (which supports manual installation per its header comment at line 8-9) does not include a `ConsentText` dictionary. Users who manually install the profile receive no privacy explanation at installation time.

**Risk**: Missed opportunity for GDPR transparency evidence at the moment of profile installation.

**Recommendation**: Unchanged from original audit. Add a `ConsentText` dictionary with at minimum an English-language explanation.

---

### [MEDIUM] CUST-001: customize-profiles.sh --org-name Substitution Is a No-Op (NEW)

**Severity**: MEDIUM
**Status**: NEW finding discovered during re-audit

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/customize-profiles.sh:100`
**Evidence**:
```bash
CONTENT="${CONTENT//REPLACE_ORG_NAME/$ORG_NAME}"
```

**Description**: The `customize-profiles.sh` script (introduced in PR #258) accepts a `--org-name` argument and performs a string substitution of `REPLACE_ORG_NAME` in the template profiles. However, **neither mobileconfig template contains the token `REPLACE_ORG_NAME`**. Both profiles have `PayloadOrganization` hardcoded to `KMFlow`:

`com.kmflow.agent.mobileconfig:29-30`:
```xml
<key>PayloadOrganization</key>
<string>KMFlow</string>
```

`com.kmflow.agent.tcc.mobileconfig:39-40`:
```xml
<key>PayloadOrganization</key>
<string>KMFlow</string>
```

The substitution line in the script (`CONTENT="${CONTENT//REPLACE_ORG_NAME/$ORG_NAME}"`) matches zero occurrences and is a silent no-op. An MDM admin running `customize-profiles.sh --team-id ABCDE12345 --org-name "Acme Corporation"` would receive profiles that still display "KMFlow" as the organization in System Settings.

**Risk**: MDM admins who use the customization script with `--org-name` believe the organization name has been customized. In reality, the profiles still show "KMFlow" to end users. This creates employee confusion and potential support escalation, as described in the original PROF-001 finding. The customization script gives a false sense of completeness.

**Recommendation**: Replace the hardcoded `KMFlow` in `PayloadOrganization` with `REPLACE_ORG_NAME` in both mobileconfig templates so the substitution actually works. Alternatively, change the default value in the templates to `REPLACE_ORG_NAME` and make `--org-name` a required argument (or default to "KMFlow" as the script already does).

---

### [LOW] PROF-001: PayloadOrganization Hardcoded (was MEDIUM, downgraded)

**Original Severity**: MEDIUM
**Current Severity**: LOW (downgraded due to customize-profiles.sh intent, but see CUST-001)
**Status**: PARTIALLY FIXED (script infrastructure exists but substitution is broken)

**Description**: The `customize-profiles.sh` script was created to address this (PR #258), demonstrating intent to make PayloadOrganization customizable. The `--org-name` flag and substitution logic exist. However, the templates were not updated to use the `REPLACE_ORG_NAME` token, making the fix incomplete. See CUST-001 for the specific bug.

Downgraded from MEDIUM to LOW because the fix infrastructure is in place -- only the template token is missing.

---

### [LOW] SCOPE-001: TCC System Scope vs User Config Scope

**Status**: OPEN (Accepted Risk)
**Current Severity**: LOW

**Description**: Unchanged from original audit. The TCC profile uses `PayloadScope = System` (required for PPPC) while the app config uses `PayloadScope = User`. On multi-user machines, the TCC grant applies system-wide.

**Assessment**: This is an inherent limitation of Apple's PPPC mechanism. TCC profiles MUST be System-scoped to function. The risk is limited to shared workstation environments, which are uncommon for task mining deployments. Accepted as a known limitation.

---

### [LOW] PROF-003: Sequential Placeholder PayloadUUIDs

**Status**: OPEN (no remediation attempted)
**Current Severity**: LOW

**File**: Both mobileconfig profiles
**Evidence**: PayloadUUID values remain sequential placeholders: `A1B2C3D4-...`, `B2C3D4E5-...`, `C3D4E5F6-...`, `D4E5F6A7-...`

**Description**: Unchanged. The `customize-profiles.sh` script does NOT regenerate UUIDs. No `uuidgen` call exists in the script. Multi-engagement deployments through the same MDM server risk UUID collisions.

**Recommendation**: Add UUID regeneration to `customize-profiles.sh`:
```bash
for uuid_placeholder in A1B2C3D4-E5F6-7890-ABCD-EF1234567890 B2C3D4E5-F6A7-8901-BCDE-F12345678901 \
                         C3D4E5F6-A7B8-9012-CDEF-123456789012 D4E5F6A7-B8C9-0123-DEFA-234567890123; do
    CONTENT="${CONTENT//$uuid_placeholder/$(uuidgen)}"
done
```

---

### [LOW] PROF-004: PayloadRemovalDisallowed=false, No Detection

**Status**: OPEN (no remediation attempted)
**Current Severity**: LOW

**Description**: Unchanged from original audit. The config profile allows user removal, but the agent has no KVO or change detection on the managed preferences domain. The agent continues running with stale configuration after profile removal.

---

### [LOW] SIGN-002: No Passphrase Support for Signing Key

**Status**: OPEN (no remediation attempted)
**Current Severity**: LOW

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/sign-profile.sh:88,96-105`
**Description**: Unchanged. No `-passin` support for encrypted keys. Key path printed in log output.

---

### [LOW] COMPAT-001: Allowed Key vs Authorization Key

**Status**: OPEN (Accepted Risk)
**Current Severity**: LOW

**Description**: The TCC profile uses the `Allowed` boolean key rather than the modern `Authorization` string key. Both work on all supported macOS versions. The `Allowed = true` format silently grants without user awareness. Using `Authorization = AllowStandardUserToSetSystemService` would be more transparent but changes the deployment UX. Accepted as a design decision -- silent grant is appropriate for supervised MDM deployments.

---

## Whitepaper Claims Verification (Updated)

### Claim 1: "No Screen Capture" (Sections 1, 6)

| Claim | Whitepaper Text | Actual State (Post-Remediation) | Verdict |
|-------|----------------|------|---------|
| No screenshots | "It does **not** record the content of screenshots" (Sec. 1) | ScreenCapture REMOVED from TCC profile. `screenshotEnabled` defaults to `false` in code. | **MATCH** |
| Screen Recording optional | "Screen Recording: Optional (Phase 2)" (Sec. 6) | Separate profile required for ScreenCapture. Not included in default deployment. | **MATCH** |
| Disabled by default | "Disabled by default" (Sec. 6) | `screenshotEnabled: Bool = false` in code. No TCC pre-authorization. | **MATCH** |

**Status change**: All three ScreenCapture claims now match the shipped artifacts. The trust gap is closed.

### Claim 2: "Only Accessibility" (Section 6)

| Claim | Whitepaper Text | Actual State | Verdict |
|-------|----------------|------|---------|
| Only Accessibility | "Agent requests only Accessibility" (Sec. 1) | TCC profile grants only Accessibility. | **MATCH** |
| No Full Disk Access | "Not required and not requested" | No SystemPolicyAllFiles in TCC profile | **MATCH** |
| No Contacts/Calendar/Camera/Mic | "Not requested. Not used." | Not present in TCC profile | **MATCH** |

**Status change**: The "Only Accessibility" claim now fully matches. Previous mismatch (ScreenCapture was present) is resolved.

### Claim 3: "AES-256-GCM Encryption" (Section 5)

| Claim | Whitepaper Text | Actual State | Verdict |
|-------|----------------|------|---------|
| AES-256-GCM at rest | "Algorithm: AES-256-GCM" (Sec. 5) | Out of F3 scope -- defer to E3 agent | **UNVERIFIABLE** from F3 scope |

### Claim 4: "4-Layer PII Protection" (Section 4)

| Layer | Claimed | Evidence | Verdict |
|-------|---------|----------|---------|
| L1: Capture Prevention | Blocklist, password fields, private browsing | `BlocklistManager.swift` (fixed nil handling), `CaptureContextFilter.swift`, `PrivateBrowsingDetector` | **MATCH** (with BLK-001b caveat) |
| L2: Regex Scrubbing | SSN, email, phone, CC patterns | Out of F3 scope | **UNVERIFIABLE** from F3 scope |
| L3: ML NER | Backend NER | Out of F3 scope (documented as future) | **NOT IMPLEMENTED** |
| L4: Human Review | Quarantine queue | Out of F3 scope | **NOT IMPLEMENTED** |

---

## Enterprise MDM Compatibility Assessment (Unchanged)

| MDM Solution | Compatible? | Notes |
|--------------|:-:|-------|
| Jamf Pro | Yes | Standard PPPC payload format; no vendor-specific keys |
| Microsoft Intune | Yes | Standard mobileconfig upload; standard payload types |
| Kandji | Yes | Standard Configuration/PPPC payloads |
| Mosyle | Yes | Standard payloads; referenced in TCC profile header |
| Fleet (osquery) | Partial | Compatible via Apple MDM protocol; Fleet PPPC UI may not parse `Allowed` key natively |

---

## Risk Assessment (Updated)

**Overall MDM Profile Security Posture**: LOW-MEDIUM RISK (improved from MEDIUM RISK)

The critical finding (TCC-001) has been fully remediated. All three HIGH findings have been addressed: two fully fixed (CFG-001, CFG-002) and one substantially mitigated (TCC-002, downgraded to MEDIUM). The trust gap between the security whitepaper and shipped TCC profile is closed.

Remaining issues are operational (no ConsentText, placeholder UUIDs, broken org-name substitution, sign-profile verification gap) rather than security-critical. None represent immediate data exfiltration, privilege escalation, or compliance violation risks.

**Remediation progress**: 4 of 13 original findings fully fixed. 1 new finding discovered (CUST-001). 10 findings remain open at MEDIUM or LOW severity with no CRITICAL or HIGH findings outstanding.

**Priority for next remediation cycle**:
1. CUST-001 (MEDIUM) -- Fix REPLACE_ORG_NAME token in templates (trivial fix, unblocks the entire customize-profiles workflow)
2. BLK-001b (MEDIUM) -- Align CaptureContextFilter.isBlockedApp with BlocklistManager behavior
3. SIGN-001 (MEDIUM) -- Remove -noverify from sign-profile.sh verification
4. PROF-002 (MEDIUM) -- Add ConsentText to config profile
5. PROF-003 (LOW) -- Add UUID regeneration to customize-profiles.sh
