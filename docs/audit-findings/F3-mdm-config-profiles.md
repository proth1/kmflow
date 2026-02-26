# F3: MDM & Configuration Profile Audit

**Agent**: F3 (MDM & Configuration Profile Auditor)
**Date**: 2026-02-25
**Scope**: MDM configuration profiles, TCC/PPPC profile, profile signing, config injection surface, blocklist security, enterprise MDM compatibility, whitepaper claim verification
**Classification**: Confidential — Security Audit Finding

---

## Finding Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 3 |
| MEDIUM   | 5 |
| LOW      | 4 |
| **Total** | **13** |

---

## Findings

### [CRITICAL] TCC-001: ScreenCapture TCC Pre-Authorized Despite "No Screenshot" Claim

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.tcc.mobileconfig:130-151`
**Agent**: F3 (MDM & Configuration Profile Auditor)
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
**Description**: The TCC/PPPC profile ships with ScreenCapture pre-authorized (`Allowed = true`) by default. The security whitepaper (KMF-SEC-001, Section 1) explicitly states: "It does **not** record the content of keystrokes, the content of screenshots, clipboard data, files accessed, or communications content." Section 6 states Screen Recording is "Optional (Phase 2)" and "Disabled by default." The PIA template (KMF-SEC-003, Section 2.2) lists "Screenshots (pixel content)" under "Data NOT Collected" with the explanation "Screen Recording permission not requested in Phase 1; excluded by default."

However, the shipped TCC profile silently grants ScreenCapture permission to the agent binary without any user prompt. A CISO reviewing the whitepaper would conclude that screen capture is architecturally impossible in Phase 1. The profile contradicts this by pre-authorizing the very permission that makes it possible. The comment says to "comment out this block" for action_level policy, but the default profile includes it active. An MDM admin deploying the profile as-shipped will silently grant screen capture.

**Risk**: A CISO approves deployment based on the whitepaper's claim of no screen capture. The MDM profile silently enables the permission. If `screenshotEnabled` is later toggled via server config or MDM, the agent can begin capturing screenshots without any user-visible prompt — because the TCC grant was already silently applied. This is a trust violation between the security documentation and the shipped artifact. Regulatory exposure under GDPR Article 35(3)(b) if screen capture begins without a DPIA update.

**Recommendation**: Remove the ScreenCapture block from the default TCC profile entirely. Create a separate, clearly-named profile (`com.kmflow.agent.tcc.screencapture.mobileconfig`) that MDM admins must explicitly deploy as a second profile when content_level capture is approved. This makes the permission grant a deliberate, auditable MDM action rather than a silent default.

---

### [HIGH] CFG-001: No Input Validation on MDM-Configurable Values in AgentConfig

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Config/AgentConfig.swift:48-68`
**Agent**: F3 (MDM & Configuration Profile Auditor)
**Evidence**:
```swift
public init?(fromMDMProfile suiteName: String = "com.kmflow.agent") {
    guard let defaults = UserDefaults(suiteName: suiteName) else { return nil }

    let policyString = defaults.string(forKey: "CapturePolicy") ?? "action_level"
    self.captureGranularity = CaptureGranularity(rawValue: policyString) ?? .actionLevel
    self.appAllowlist = defaults.stringArray(forKey: "AppAllowlist")
    self.appBlocklist = defaults.stringArray(forKey: "AppBlocklist")
    ...
    self.screenshotIntervalSeconds = defaults.object(forKey: "ScreenshotIntervalSeconds") != nil
        ? defaults.integer(forKey: "ScreenshotIntervalSeconds") : 30
    self.batchSize = defaults.object(forKey: "BatchSize") != nil
        ? defaults.integer(forKey: "BatchSize") : 1000
```
**Description**: All MDM-configurable integer values (`screenshotIntervalSeconds`, `batchSize`, `batchIntervalSeconds`, `idleTimeoutSeconds`) are read from UserDefaults without any bounds validation. There are no minimum or maximum checks. A rogue or misconfigured MDM profile could set:
- `ScreenshotIntervalSeconds` to `1` (one screenshot per second, extreme resource consumption and privacy violation)
- `BatchSize` to `0` (potential division-by-zero or infinite loop in batch assembler)
- `BatchSize` to `999999999` (memory exhaustion)
- `IdleTimeoutSeconds` to `0` (never idle, constant monitoring)
- `BatchIntervalSeconds` to `0` (immediate continuous upload, network flooding)

No string validation exists for `AppBlocklist` or `AppAllowlist` entries. A crafted MDM profile could inject path-traversal strings or other malformed bundle identifiers into these arrays, which are later used in Set lookups.

**Risk**: A compromised or misconfigured MDM server could push an aggressive capture configuration that exhausts device resources, floods the network, or violates the proportionality claims in the PIA. A batch size of 0 could cause runtime crashes.

**Recommendation**: Add bounds validation to all integer MDM configuration values:
```swift
self.screenshotIntervalSeconds = max(10, min(300, defaults.integer(forKey: "ScreenshotIntervalSeconds")))
self.batchSize = max(100, min(10000, defaults.integer(forKey: "BatchSize")))
self.batchIntervalSeconds = max(10, min(300, defaults.integer(forKey: "BatchIntervalSeconds")))
self.idleTimeoutSeconds = max(60, min(3600, defaults.integer(forKey: "IdleTimeoutSeconds")))
```
Document the valid ranges in the mobileconfig profile comments and in the security whitepaper.

---

### [HIGH] CFG-002: Backend URL Not Validated in MDM Config Path — Data Exfiltration Risk

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/PythonProcessManager.swift:81-87`
**Agent**: F3 (MDM & Configuration Profile Auditor)
**Evidence**:
```swift
let defaults = UserDefaults.standard
if let agentId = defaults.string(forKey: "KMFLOW_AGENT_ID"), !agentId.isEmpty {
    environment["KMFLOW_AGENT_ID"] = agentId
}
if let backendURL = defaults.string(forKey: "KMFLOW_BACKEND_URL"), !backendURL.isEmpty {
    environment["KMFLOW_BACKEND_URL"] = backendURL
}
```
**Description**: The backend URL is read from UserDefaults and passed directly to the Python subprocess as an environment variable without any validation of the URL scheme, host, or format. The onboarding wizard's `ConnectionView` performs a health check on the user-entered URL, but the MDM path bypasses this entirely. When an MDM profile sets `BackendURL`, the value flows through `UserDefaults(suiteName: "com.kmflow.agent")` and ultimately to the Python process as `KMFLOW_BACKEND_URL`. There is no check that:
- The scheme is `https://` (an `http://` URL would send captured data unencrypted)
- The host is a legitimate KMFlow backend (a rogue MDM admin could redirect to `https://evil.attacker.com`)
- The value is a well-formed URL at all (a string like `; rm -rf /` would be passed as an environment variable)

Additionally, AgentConfig.swift does not read or validate the BackendURL at all — the `BackendURL` key in the mobileconfig is consumed by PythonProcessManager via a different UserDefaults path (`UserDefaults.standard` with key `KMFLOW_BACKEND_URL`), creating a confusing dual-path configuration architecture.

**Risk**: A rogue MDM administrator (or an attacker who has compromised the MDM server) can redirect all captured activity data to an attacker-controlled server by pushing a profile with a modified `BackendURL`. The data would include PII-scrubbed window titles, application names, and activity patterns — all sent to an unauthorized endpoint. If `http://` is used, data is transmitted in cleartext.

**Recommendation**:
1. Add URL validation that enforces `https://` scheme, checks against an allow-list of known KMFlow API domains, or at minimum validates URL structure.
2. Add certificate pinning or at least hostname verification against a compiled-in allow-list for Phase 1.
3. Log a security event when the backend URL changes via MDM.
4. Consolidate the backend URL config path so it flows through a single validated code path.

---

### [HIGH] TCC-002: CodeRequirement Contains Placeholder "REPLACE_TEAM_ID" — Profile Unusable as Shipped

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.tcc.mobileconfig:107`
**Agent**: F3 (MDM & Configuration Profile Auditor)
**Evidence**:
```xml
<key>CodeRequirement</key>
<string>identifier "com.kmflow.agent" and anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] and certificate leaf[field.1.2.840.113635.100.6.1.13] and certificate leaf[subject.OU] = "REPLACE_TEAM_ID"</string>
```
**Description**: Both the Accessibility and ScreenCapture CodeRequirement strings contain `REPLACE_TEAM_ID` as a placeholder. This placeholder must be replaced with the actual Apple Developer Team ID before deployment. If deployed as-is, the TCC grant will not match the signed binary (because no binary will have an OU of "REPLACE_TEAM_ID"), and the profile will silently fail to grant permissions. This is not a security vulnerability per se, but it creates a deployment failure mode where MDM admins may:
1. Deploy the profile as-is and wonder why permissions are not granted
2. Remove the CodeRequirement entirely to "fix" the problem, creating a security vulnerability where ANY binary named `com.kmflow.agent` would receive Accessibility access
3. Weaken the CodeRequirement to match only the identifier without the certificate check

The file comments at line 100-104 explain the need to replace this, but the comment is buried inside XML and easy to miss during deployment.

**Risk**: Profile deployment failure leads to support escalation or, worse, MDM admins weakening CodeRequirement to work around the issue. A weakened CodeRequirement could allow a malicious binary with the same bundle ID to receive Accessibility permissions.

**Recommendation**:
1. Add a prominent `<!-- DEPLOYMENT REQUIRED: Replace REPLACE_TEAM_ID ... -->` comment at the top of the file, not just inline.
2. Add a validation step to the deployment documentation that checks the CodeRequirement is not a placeholder.
3. Consider providing a `prepare-profiles.sh` script that takes the Team ID as an argument and performs the substitution, preventing partial-placeholder deployments.

---

### [MEDIUM] SIGN-001: Profile Verification Uses -noverify Flag

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/sign-profile.sh:123`
**Agent**: F3 (MDM & Configuration Profile Auditor)
**Evidence**:
```bash
if openssl smime -verify -inform der -noverify -in "$SIGNED_PROFILE" -out /dev/null 2>&1; then
    echo "  Signature structure: valid"
else
    echo "  WARNING: openssl smime -verify returned non-zero." >&2
    echo "           This may be expected if the cert is not in the system trust store." >&2
```
**Description**: The post-signing verification step uses the `-noverify` flag, which skips certificate chain validation. This means the verification only checks that the CMS structure is syntactically valid — it does not verify that the signing certificate is trusted, not expired, or not revoked. Furthermore, when verification fails, the script does not exit with a non-zero status code. It merely prints a warning to stderr and continues to the "Profile Signing Complete" success message. A CI/CD pipeline would see exit code 0 (success) even when the profile signature is invalid.

**Risk**: An expired, revoked, or untrusted signing certificate could produce a signed profile that passes the script's verification but is rejected by macOS on installation, or worse, displays an "Unsigned" or "Unverified" identity to the user in System Settings. The non-failing exit code means automated pipelines will not catch the issue.

**Recommendation**:
1. Remove the `-noverify` flag and instead provide the CA certificate chain via `-CAfile` for proper chain validation.
2. If the signing certificate may not be in the system trust store, add a separate verification path that validates the chain explicitly.
3. Exit with a non-zero status code on verification failure:
```bash
if ! openssl smime -verify -inform der -CAfile "$CHAIN" -in "$SIGNED_PROFILE" -out /dev/null 2>&1; then
    echo "ERROR: Profile signature verification failed." >&2
    exit 2
fi
```

---

### [MEDIUM] PROF-001: PayloadOrganization Hardcoded to "KMFlow" in Both Profiles

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.mobileconfig:29-30`
**Agent**: F3 (MDM & Configuration Profile Auditor)
**Evidence**:
```xml
<key>PayloadOrganization</key>
<string>KMFlow</string>
```
**Description**: Both the application configuration profile (line 29) and the TCC profile (line 39) have `PayloadOrganization` hardcoded to `KMFlow`. In enterprise MDM deployments, the `PayloadOrganization` field is displayed to end users in System Settings > Profiles. The user sees "KMFlow" rather than their own employer's name (e.g., "Acme Corporation IT"). This creates a confusing user experience and may cause security-conscious employees to question or refuse the profile installation because they do not recognize "KMFlow" as their employer's IT department.

**Risk**: Employee confusion during deployment. Potential support escalation. In organizations with strict profile naming policies, the profile may be rejected by IT governance review. Minor trust issue — employees expect profiles from their employer, not from a vendor they may not have heard of.

**Recommendation**: Change `PayloadOrganization` to a placeholder like `[DEPLOYING_ORGANIZATION]` with a comment instructing the MDM admin to replace it, or provide the `prepare-profiles.sh` script mentioned in TCC-002 that substitutes this value along with the Team ID.

---

### [MEDIUM] PROF-002: No ConsentText Dictionary in Either Profile

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.mobileconfig` (entire file)
**Agent**: F3 (MDM & Configuration Profile Auditor)
**Evidence**:
```xml
<!-- No ConsentText key present in either profile -->
```
**Description**: Neither profile includes a `ConsentText` dictionary. Apple Configuration Profiles support a `ConsentText` key at the top-level profile dict, which displays a consent message to the user before profile installation. For the application config profile (which has `PayloadRemovalDisallowed = false` and can be installed manually via `open com.kmflow.agent.mobileconfig`), this is a missed opportunity to present a privacy notice at the moment of installation. While the TCC profile is MDM-only (no user installation prompt), the application config profile explicitly supports manual installation (per the file's header comment at line 8-9).

**Risk**: Users who manually install the profile receive no privacy explanation at the installation moment. For GDPR compliance (transparency principle, Art. 12), presenting a consent text at profile installation strengthens the evidence of informed consent.

**Recommendation**: Add a `ConsentText` dictionary to the application configuration profile with at minimum an English-language explanation of what the profile configures:
```xml
<key>ConsentText</key>
<dict>
    <key>default</key>
    <string>This profile configures the KMFlow Task Mining Agent on your device. It will set the backend server URL, engagement identifier, and data capture policy. By installing this profile, you acknowledge that desktop activity monitoring will be active during the engagement period.</string>
</dict>
```

---

### [MEDIUM] SCOPE-001: TCC Profile Uses PayloadScope "System" but App Config Uses "User" — Scope Mismatch

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.tcc.mobileconfig:55-56` and `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.mobileconfig:47-48`
**Agent**: F3 (MDM & Configuration Profile Auditor)
**Evidence**:
```xml
<!-- TCC profile -->
<key>PayloadScope</key>
<string>System</string>

<!-- App config profile -->
<key>PayloadScope</key>
<string>User</string>
```
**Description**: The TCC/PPPC profile uses `PayloadScope = System` while the application configuration profile uses `PayloadScope = User`. The System scope for the TCC profile is technically correct (PPPC payloads must be System-scoped to be effective), but the documentation and whitepaper (Section 6) state the agent "runs as a LaunchAgent" (user-scoped). The System-scoped TCC profile means the Accessibility and ScreenCapture grants apply to ALL users on the machine, not just the user who has the agent installed. On shared workstations, this means the agent binary could run under any user account and receive Accessibility access.

**Risk**: On multi-user macOS machines (e.g., shared lab workstations, training environments), the TCC grant applies system-wide. If the agent binary is accessible to other users, they could exploit the pre-authorized Accessibility permission. This is a minor risk in typical single-user consultant laptop deployments but could be significant in shared environments.

**Recommendation**: Document in the deployment guide that the TCC profile grants system-wide permissions and that on multi-user machines, the agent binary should be installed per-user rather than in `/Applications/`. Consider whether the deployment architecture should enforce single-user installation on shared machines.

---

### [MEDIUM] BLK-001: Null BundleId Bypasses Blocklist Check

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/Config/BlocklistManager.swift:33-34`
**Agent**: F3 (MDM & Configuration Profile Auditor)
**Evidence**:
```swift
public func shouldCapture(bundleId: String?) -> Bool {
    guard let bid = bundleId else { return true }
    lock.lock()
    defer { lock.unlock() }
```
**Description**: When `bundleId` is `nil`, `shouldCapture` returns `true` (allow capture). Some macOS processes (particularly background daemons, XPC services, or processes launched from Terminal) may not have a bundle identifier. The function defaults to capturing data from these unidentified processes. This is a permissive default that contradicts the least-privilege principle — unidentifiable processes should be treated as potentially sensitive and blocked by default.

Additionally, the L1Filter at `/Users/proth/repos/kmflow/agent/macos/Sources/PII/L1Filter.swift:36` has the same pattern:
```swift
public static func isBlockedApp(bundleId: String?, blocklist: Set<String>) -> Bool {
    guard let bid = bundleId else { return false }
```
A `nil` bundle ID causes `isBlockedApp` to return `false` (not blocked), allowing capture.

**Risk**: Processes without bundle identifiers bypass all blocklist filtering. If a sensitive application (e.g., a custom internal tool, a CLI-based password manager) runs without a bundle ID, its activity would be captured despite potentially being sensitive.

**Recommendation**: Change the default behavior for `nil` bundle IDs to deny capture:
```swift
guard let bid = bundleId else { return false }  // Unknown apps are not captured
```
Or add a configurable policy (`captureUnidentifiedApps: Bool`) that defaults to `false`.

---

### [LOW] PROF-003: PayloadUUID Values Are Sequential Placeholders — Not Cryptographically Random

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.mobileconfig:40` and `com.kmflow.agent.tcc.mobileconfig:49,78`
**Agent**: F3 (MDM & Configuration Profile Auditor)
**Evidence**:
```xml
<!-- mobileconfig profile -->
<string>A1B2C3D4-E5F6-7890-ABCD-EF1234567890</string>
<!-- mobileconfig payload -->
<string>B2C3D4E5-F6A7-8901-BCDE-F12345678901</string>
<!-- tcc profile -->
<string>C3D4E5F6-A7B8-9012-CDEF-123456789012</string>
<!-- tcc payload -->
<string>D4E5F6A7-B8C9-0123-DEFA-234567890123</string>
```
**Description**: All four PayloadUUID values across both profiles are clearly sequential placeholders (A1B2C3D4, B2C3D4E5, C3D4E5F6, D4E5F6A7) rather than cryptographically random UUIDs. While the Apple documentation does not strictly require random UUIDs, the `PayloadUUID` is used by MDM systems to track profile identity. Sequential/predictable UUIDs are a code smell and could cause profile collision issues if multiple KMFlow deployments are managed by the same MDM server without re-generating UUIDs per engagement.

The mobileconfig header comment at line 38 says "regenerate for each new engagement" but this instruction is easily missed. The TCC profile has no such instruction.

**Risk**: Low. If two engagements use the same PayloadUUIDs, MDM systems may overwrite one profile with the other, causing configuration cross-contamination between engagements.

**Recommendation**: Add a `prepare-profiles.sh` script that generates fresh UUIDs (`uuidgen`) for all PayloadUUID fields before deployment. Add the same "regenerate" instruction to the TCC profile header.

---

### [LOW] PROF-004: Application Config Profile PayloadRemovalDisallowed Is False — Profile Can Be Silently Removed

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.mobileconfig:43-44`
**Agent**: F3 (MDM & Configuration Profile Auditor)
**Evidence**:
```xml
<!-- Remove profile when MDM un-enrolls the device -->
<key>PayloadRemovalDisallowed</key>
<false/>
```
**Description**: The application configuration profile allows user removal (`PayloadRemovalDisallowed = false`). When removed, the `UserDefaults(suiteName: "com.kmflow.agent")` managed preferences are deleted by macOS. However, there is no code in the agent that detects profile removal and reacts appropriately. A search for profile removal detection, KVO on UserDefaults, or any change observation mechanism found no results. The agent does not observe changes to its managed preferences domain.

The whitepaper (Section 7) describes a heartbeat-based state machine for lifecycle management, but this applies to server-side revocation. There is no mention of what happens when the local MDM profile is removed while the agent is running. The agent would continue running with its last-known configuration (cached in memory) until the next heartbeat cycle, and even then, the heartbeat updates server-side state — it does not re-read local MDM preferences.

**Risk**: A user removes the MDM configuration profile. The agent continues running with stale configuration (including the last-known backend URL and engagement ID). The agent has no mechanism to detect this state change and fall back to safe defaults or halt capture.

**Recommendation**: Add KVO (Key-Value Observing) on the `com.kmflow.agent` UserDefaults suite to detect when managed preferences are removed. On removal, the agent should either halt capture and require re-onboarding, or fall back to safe defaults and notify the backend via the next heartbeat.

---

### [LOW] SIGN-002: No Passphrase Protection Option for Private Key

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/sign-profile.sh:96-105`
**Agent**: F3 (MDM & Configuration Profile Auditor)
**Evidence**:
```bash
OPENSSL_ARGS=(
    smime
    -sign
    -signer  "$CERT"
    -inkey   "$KEY"
    -outform der
    -nodetach           # embed the content in the signature (required for profiles)
    -in      "$PROFILE_PATH"
    -out     "$SIGNED_PROFILE"
)
```
**Description**: The signing script does not support passphrase-protected private keys. The `openssl smime -sign` command accepts `-passin` for encrypted private keys, but this option is not included. The script assumes the private key file is unencrypted on disk. Additionally, the script prints the path to the private key in its summary output (line 88: `echo "  Key:     $KEY"`), which in CI/CD logs could expose the key file location.

**Risk**: Low. If the signing key is stored unencrypted on a CI/CD server, anyone with access to that server can sign arbitrary profiles. The key path being logged is a minor information disclosure.

**Recommendation**: Add `-passin` support (e.g., `PASSPHRASE` env var) for encrypted keys. Mask the key path in log output or replace it with a redacted placeholder.

---

### [LOW] COMPAT-001: TCC Profile Uses `Allowed` Key Instead of `Authorization` — Modern macOS Compatibility Note

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.tcc.mobileconfig:110-111`
**Agent**: F3 (MDM & Configuration Profile Auditor)
**Evidence**:
```xml
<key>Allowed</key>
<true/>
```
**Description**: The TCC profile uses the `Allowed` boolean key (true/false) rather than the `Authorization` string key (`Allow`/`Deny`/`AllowStandardUserToSetSystemService`). The `Allowed` boolean key is the older style supported since macOS 10.14 Mojave. Apple introduced the `Authorization` string key in macOS 11 Big Sur, which provides the additional option `AllowStandardUserToSetSystemService` — this value grants the user the ability to approve or deny the permission themselves, rather than silently granting it. Using `AllowStandardUserToSetSystemService` would be more transparent and align with the whitepaper's claim of "transparent to the employee" (Section 1).

Both key formats work on current macOS versions. Jamf Pro, Intune, Kandji, Mosyle, and Fleet all support both formats. No vendor-specific keys are present in the profiles, making them portable across MDM solutions.

**Risk**: Low. The `Allowed = true` format silently grants permissions without user awareness. Using `Authorization = AllowStandardUserToSetSystemService` for Accessibility would give users a prompt they can approve — strengthening the transparency claim and GDPR consent evidence.

**Recommendation**: For deployments where user transparency is prioritized over silent deployment, consider switching to:
```xml
<key>Authorization</key>
<string>AllowStandardUserToSetSystemService</string>
```
Document the trade-off in the deployment guide: silent grant (current) vs. user-prompted grant (more transparent).

---

## Whitepaper Claims Verification

### Claim 1: "No Screen Capture" (Sections 1, 6)

| Claim | Whitepaper Text | Actual State | Verdict |
|-------|----------------|--------------|---------|
| No screenshots | "It does **not** record the content of screenshots" (Sec. 1) | TCC profile ships with ScreenCapture pre-authorized; `AgentConfig.swift` has `screenshotEnabled` property; `EventProtocol.swift` has `screenCapture` event type | **MISMATCH** - See TCC-001 |
| Screen Recording optional | "Screen Recording: Optional (Phase 2)" (Sec. 6) | ScreenCapture is pre-authorized in the default TCC profile | **MISMATCH** - Profile enables what documentation says is Phase 2 |
| Disabled by default | "Disabled by default" (Sec. 6) | `screenshotEnabled: Bool = false` in code defaults | **PARTIAL MATCH** - Code default is false, but TCC permission is pre-authorized |

### Claim 2: "AES-256-GCM Encryption" (Section 5)

| Claim | Whitepaper Text | Actual State | Verdict |
|-------|----------------|--------------|---------|
| AES-256-GCM at rest | "Algorithm: AES-256-GCM" (Sec. 5) | CryptoKit imported in KMFlowAgentApp.swift; encryption implementation not in audited files (not in scope of F3 audit) | **UNVERIFIABLE** from F3 scope — defer to other audit agents |

### Claim 3: "4-Layer PII Protection" (Section 4)

| Layer | Claimed | Evidence | Verdict |
|-------|---------|----------|---------|
| L1: Capture Prevention | Password field, secure input, blocklist, private browsing | L1Filter.swift, PrivateBrowsingDetector.swift, BlocklistManager.swift | **MATCH** |
| L2: Regex Scrubbing | SSN, email, phone, CC, NI, IP, DOB patterns | Not in F3 audit scope (PII module) | **UNVERIFIABLE** from F3 scope |
| L3: ML NER | Backend NER scan | Described as "future phase" / "planned for Phase 3" | **NOT IMPLEMENTED** (documented as future) |
| L4: Human Review | Quarantine queue | Backend feature, not in agent code | **UNVERIFIABLE** from F3 scope |

### Claim 4: "Least Privilege — Only Accessibility" (Section 6)

| Claim | Whitepaper Text | Actual State | Verdict |
|-------|----------------|--------------|---------|
| Only Accessibility | "Agent requests only the macOS permissions required for its function (Accessibility)" (Sec. 1) | TCC profile also pre-authorizes ScreenCapture | **MISMATCH** - See TCC-001 |
| No Full Disk Access | "Full Disk Access is not required and not requested" | No SystemPolicyAllFiles in TCC profile | **MATCH** |
| No Contacts/Calendar/Camera/Mic | "Not requested. Not used." | Not present in TCC profile | **MATCH** |

---

## Enterprise MDM Compatibility Assessment

| MDM Solution | Compatible? | Notes |
|--------------|-------------|-------|
| Jamf Pro | Yes | Standard PPPC payload format; no vendor-specific keys |
| Microsoft Intune | Yes | Intune supports custom mobileconfig upload; standard payload types |
| Kandji | Yes | Standard Configuration/PPPC payloads |
| Mosyle | Yes | Standard payloads; referenced in TCC profile header comment |
| Fleet (osquery) | Partial | Fleet deploys profiles via Apple MDM protocol; compatible, but Fleet's PPPC UI may not parse the `Allowed` key natively |

No vendor-specific payload keys, custom identifiers, or proprietary extensions were found in either profile. The profiles are portable across all major macOS MDM solutions.

---

## Profile Structure Compliance Summary

| Check | App Config Profile | TCC Profile |
|-------|-------------------|-------------|
| PayloadType correct | Yes (`Configuration` / `com.kmflow.agent`) | Yes (`Configuration` / `com.apple.TCC.configuration-profile-policy`) |
| PayloadUUID unique within profile | Yes (A1B2... and B2C3...) | Yes (C3D4... and D4E5...) |
| PayloadUUID unique across profiles | Yes (all four values are distinct) | Yes |
| PayloadUUID cryptographically random | No (sequential placeholders) | No (sequential placeholders) |
| PayloadScope appropriate | Yes (`User` for managed prefs) | Yes (`System` required for PPPC) |
| PayloadRemovalDisallowed documented | Yes (false, with comment) | Yes (true, appropriate for PPPC) |
| PayloadOrganization correct | No (hardcoded to "KMFlow") | No (hardcoded to "KMFlow") |
| ConsentText present | No | No (N/A for MDM-only profile) |
| CodeRequirement has all 3 checks | Yes (identifier + anchor + cert OU) | Yes (same) |
| IdentifierType = bundleID | Yes | Yes |
| StaticCode = false | Yes (re-validates on each use) | Yes |

---

## Risk Assessment

**Overall MDM Profile Security Posture**: MEDIUM RISK

The profiles are structurally well-designed and follow Apple's PPPC specification correctly. The CodeRequirement strings include all three recommended checks (identifier, anchor, certificate OU). The profile separation between application configuration and TCC permissions is appropriate. Enterprise MDM compatibility is strong.

However, the critical finding (TCC-001) represents a significant trust gap between what the security documentation tells the CISO and what the shipped profile actually enables. This is the kind of discrepancy that erodes trust during a security review and can block deployment approval. The lack of input validation on MDM-configurable values (CFG-001, CFG-002) creates a real attack surface for compromised MDM servers.

**Priority remediation order**:
1. TCC-001 (CRITICAL) — Remove ScreenCapture from default TCC profile
2. CFG-002 (HIGH) — Add backend URL validation
3. CFG-001 (HIGH) — Add bounds checking on all integer config values
4. TCC-002 (HIGH) — Address placeholder CodeRequirement deployment risk
5. Remaining MEDIUM and LOW findings in severity order
