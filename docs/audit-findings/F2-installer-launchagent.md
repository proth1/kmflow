# F2: Installer & LaunchAgent Security Re-Audit

**Agent**: F2 (Installer & LaunchAgent Auditor)
**Original Audit Date**: 2026-02-25
**Re-Audit Date**: 2026-02-26
**Scope**: PKG installer scripts, LaunchAgent plist, uninstaller, MDM profile customization, Python launcher, app bundle build
**Status**: Re-audit complete (post Phase 1-3 remediation)

## Finding Summary

| Severity | Original Count | Current Count | Delta |
|----------|:-:|:-:|:-:|
| CRITICAL | 2 | 0 | -2 (both resolved) |
| HIGH | 5 | 2 | -3 (3 resolved, 0 new) |
| MEDIUM | 6 | 4 | -2 (3 resolved, 1 new) |
| LOW | 4 | 3 | -1 (2 resolved, 1 new) |
| **Total** | **17** | **9** | **-8** |

## Executive Summary

The Phase 1-3 remediation effort (PRs #248, #251, #254, #255, #257, #258) has materially improved the installer security posture. Both CRITICAL findings are resolved: the `eval` command injection in the postinstall script has been replaced with a safe `dscl`+fallback pattern, and the world-writable `/Users/Shared/` log paths are now rewritten at install time using PlistBuddy. The PYTHONPATH inheritance vulnerability is fixed (no longer appends caller's PYTHONPATH). The uninstaller now cleans `/Users/Shared/KMFlowAgent/`. The `customize-profiles.sh` script adds proper Team ID validation for MDM profiles, and the entitlements have been trimmed (unused `automation.apple-events` and unnecessary `files.user-selected.read-write` removed).

The remaining findings center on: (1) the plist template still shipping with `/Users/Shared/` default paths that would be insecure if installed outside the PKG flow, (2) DYLD_LIBRARY_PATH inheritance from the environment in the Python launcher, (3) the TOCTOU race in postinstall directory creation (partially addressed but not fully resolved), and (4) residual operational issues (crash loop potential, DMG notarization, LSUIElement in wrong plist).

**Security Score: 7.5 / 10** (up from 5.5 / 10)

---

## Resolved Findings

### [RESOLVED] Formerly CRITICAL: CWE-78 Command Injection via `eval` in postinstall

**Original File**: `agent/macos/installer/pkg/scripts/postinstall:23`
**Resolved In**: PR #248
**Evidence of Fix**:
```bash
# postinstall lines 12, 23-27 (current)
CONSOLE_USER="$(stat -f '%Su' /dev/console 2>/dev/null || echo "")"
...
USER_HOME="$(dscl . -read "/Users/$CONSOLE_USER" NFSHomeDirectory 2>/dev/null | awk '{print $2}' || echo "")"
if [[ -z "$USER_HOME" ]]; then
    echo "WARNING: Could not determine home directory for $CONSOLE_USER via dscl." >&2
    USER_HOME="/Users/$CONSOLE_USER"
fi
```
**Assessment**: The dangerous `eval echo "~$CONSOLE_USER"` fallback has been completely removed. The current implementation uses `dscl` as the primary lookup with a safe `/Users/$CONSOLE_USER` string concatenation fallback. No shell metacharacter interpretation occurs. This finding is fully resolved.

---

### [RESOLVED] Formerly CRITICAL: CWE-377 World-Writable Log Paths Rewriting Now Implemented

**Original File**: `agent/macos/installer/launchagent/com.kmflow.agent.plist:47-58`
**Resolved In**: PR #248
**Evidence of Fix**:
```bash
# postinstall lines 61-66 (current)
if [[ -n "$USER_HOME" ]]; then
    /usr/libexec/PlistBuddy -c "Set :StandardOutPath ${USER_HOME}/Library/Logs/KMFlowAgent/agent.log" "$PLIST_DEST" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Set :StandardErrorPath ${USER_HOME}/Library/Logs/KMFlowAgent/agent-error.log" "$PLIST_DEST" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:HOME ${USER_HOME}" "$PLIST_DEST" 2>/dev/null || true
    echo "  Rewrote plist paths to ${USER_HOME}/Library/Logs/KMFlowAgent/"
fi
```
**Assessment**: The postinstall script now rewrites all three dangerous paths (StandardOutPath, StandardErrorPath, HOME environment variable) using PlistBuddy, exactly as the original audit recommended. The comments in the plist template (lines 48-55) now match reality. Log and Application Support directories are created with `0700` permissions (line 87). This finding is fully resolved for the PKG installer flow.

**Residual note**: The plist template file itself (`com.kmflow.agent.plist`) still contains `/Users/Shared/` as defaults (lines 47, 58, 67). This is documented in the file's comments as intentional fallback for MDM deployment, but see MEDIUM finding F2-M1 below regarding the risk of the template being deployed without rewriting.

---

### [RESOLVED] Formerly HIGH: CWE-426 PYTHONPATH Inheritance

**Original File**: `agent/macos/Resources/python-launcher.sh:87`
**Resolved In**: PR #255 (referenced in audit as #256)
**Evidence of Fix**:
```bash
# python-launcher.sh lines 87-89 (current)
# Do NOT inherit the caller's PYTHONPATH — it may contain incompatible packages
# or inject untrusted code into the embedded interpreter.
export PYTHONPATH="${RESOURCES_DIR}/python:${RESOURCES_DIR}/python/site-packages"
```
**Assessment**: The `${PYTHONPATH:+:${PYTHONPATH}}` suffix has been removed. The embedded Python interpreter now uses a fixed, isolated PYTHONPATH containing only the bundle's own directories. Combined with `PYTHONNOUSERSITE=1` (line 93) and `PYTHONHOME` (line 80), the Python environment is well-isolated. This finding is fully resolved.

---

### [RESOLVED] Formerly HIGH: CWE-665 Incomplete Uninstall

**Original File**: `agent/macos/installer/uninstall.sh`
**Resolved In**: PR #258
**Evidence of Fix**:
```bash
# uninstall.sh lines 119-130 (current)
# Step 6: Remove shared data directory
SHARED_DIR="/Users/Shared/KMFlowAgent"
if [[ -d "$SHARED_DIR" ]]; then
    rm -rf "$SHARED_DIR"
    echo "  Removed: $SHARED_DIR"
else
    echo "  Not found (already removed): $SHARED_DIR"
fi
```
And keychain cleanup (lines 135-150):
```bash
for SERVICE in "com.kmflow.agent" "com.kmflow.agent.consent"; do
    DELETED=0
    while security delete-generic-password -s "$SERVICE" 2>/dev/null; do
        (( DELETED++ )) || true
    done
    ...
done
```
**Assessment**: The uninstaller now cleans 7 artifact categories: LaunchAgent plist, .app bundle, Application Support, logs, `/Users/Shared/KMFlowAgent/`, and Keychain items for both the agent and consent service names. The `--force` flag supports scripted/MDM removal. This finding is substantially resolved.

---

### [RESOLVED] Formerly HIGH: CWE-494 Supply Chain (Python Tarball Integrity)

**Original File**: `agent/macos/scripts/embed-python.sh:128-150`
**Resolved In**: PR #251
**Evidence of Fix**:
```bash
# embed-python.sh lines 40-52 (current)
declare -A PBS_CHECKSUMS=(
    ["aarch64"]=""
    ["x86_64"]=""
)
```
And verification logic (lines 169-195):
```bash
local expected_hash="${PBS_CHECKSUMS[$pbs_arch]:-}"
if [[ -n "$expected_hash" ]]; then
    local actual_hash
    actual_hash=$(shasum -a 256 "$cached" | awk '{print $1}')
    if [[ "$actual_hash" != "$expected_hash" ]]; then
        ...
        die "SHA-256 verification failed — possible supply chain attack or corrupt download. Removed cached file."
    fi
    ...
else
    ...
    if [[ "${KMFLOW_RELEASE_BUILD:-0}" == "1" ]]; then
        rm -f "$cached"
        die "SHA-256 checksum verification is mandatory for release builds. Populate PBS_CHECKSUMS and retry."
    fi
fi
```
**Assessment**: SHA-256 verification infrastructure is now in place. The script will refuse to proceed with a release build (`KMFLOW_RELEASE_BUILD=1`) if checksums are not populated. For development builds, it warns but continues. However, the actual hash values in `PBS_CHECKSUMS` are currently empty strings. See MEDIUM finding F2-M4 below.

---

### [RESOLVED] Formerly MEDIUM: CWE-1188 Plist Comment/Code Inconsistency

**Original File**: `agent/macos/installer/launchagent/com.kmflow.agent.plist:48-55`
**Resolved In**: PR #248
**Assessment**: The plist comments now accurately describe the postinstall behavior. The postinstall script does rewrite the paths as the comments claim. The documentation-implementation gap that was the root cause of the original CRITICAL finding no longer exists.

---

### [RESOLVED] Formerly MEDIUM: CWE-1104 TCC Profile Placeholder Without Customization Tool

**Original File**: `agent/macos/installer/profiles/com.kmflow.agent.tcc.mobileconfig:104-107`
**Resolved In**: PR #258 (customize-profiles.sh added)
**Evidence of Fix**:
```bash
# customize-profiles.sh lines 61-65
if [[ ! "$TEAM_ID" =~ ^[A-Z0-9]{10}$ ]]; then
    echo "ERROR: Team ID must be a 10-character alphanumeric string (got: '$TEAM_ID')." >&2
    exit 1
fi
```
And substitution (lines 98-100):
```bash
CONTENT="$(cat "$TEMPLATE")"
CONTENT="${CONTENT//REPLACE_TEAM_ID/$TEAM_ID}"
CONTENT="${CONTENT//REPLACE_ORG_NAME/$ORG_NAME}"
```
**Assessment**: The `customize-profiles.sh` script validates Team ID format (10 alphanumeric characters), replaces both `REPLACE_TEAM_ID` and `REPLACE_ORG_NAME` placeholders, and writes output to a `customized/` subdirectory. The risk of deploying a profile with literal `REPLACE_TEAM_ID` is reduced since there is now an official workflow. The TCC profile has also had ScreenCapture removed (PR #245, Phase 0).

---

### [RESOLVED] Formerly HIGH: CWE-250 App Sandbox Disabled with Excess Entitlements

**Original File**: `agent/macos/Resources/KMFlowAgent.entitlements`
**Resolved In**: PR #248
**Evidence of Fix**:
```xml
<!-- Current KMFlowAgent.entitlements (entire file) -->
<dict>
    <key>com.apple.security.cs.allow-jit</key>
    <false/>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <false/>
    <key>com.apple.security.cs.disable-library-validation</key>
    <false/>
    <key>com.apple.security.network.client</key>
    <true/>
    <key>com.apple.security.app-sandbox</key>
    <false/>
</dict>
```
**Assessment**: The unused `com.apple.security.automation.apple-events` entitlement has been removed (it was never used in code). The meaningless `com.apple.security.files.user-selected.read-write` entitlement (no effect outside sandbox) has been removed. The remaining entitlements are the minimum required: network client (backend communication), and sandbox disabled with a comment explaining why. The entitlement surface is now minimal and intentional.

---

## Remaining Findings

### [HIGH] F2-H1: CWE-367 TOCTOU Race in Postinstall Plist Ownership (Partially Addressed)

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/pkg/scripts/postinstall:56-72`
**Severity**: HIGH
**Evidence**:
```bash
mkdir -p "$LAUNCH_AGENTS_DIR"                    # Line 56 — runs as root
cp "$PLIST_SRC" "$PLIST_DEST"                     # Line 57 — file owned by root
# PlistBuddy rewriting occurs here (lines 62-64) # file still owned by root
if [[ -n "$CONSOLE_USER" ]]; then
    chown "${CONSOLE_USER}" "$PLIST_DEST"         # Line 70 — ownership transferred
fi
chmod 644 "$PLIST_DEST"                           # Line 72 — permissions set
```
**Description**: The postinstall script still has a multi-step sequence where the plist file is created as root, modified by PlistBuddy, then ownership is transferred to the console user. Two sub-issues remain:

1. **Directory ownership**: `mkdir -p "$LAUNCH_AGENTS_DIR"` creates the directory as root if it does not exist. The script never `chown`s the directory itself (only the file). This leaves `~/Library/LaunchAgents/` owned by root, which would prevent the user from managing their own LaunchAgents afterward.

2. **File race window**: Between `cp` (line 57) and `chown` (line 70), the plist is owned by root for the duration of the PlistBuddy operations. While this window is short (a few milliseconds), the directory containing the file may be writable by the console user if it pre-existed, allowing a potential file replacement attack.

**What was addressed in Phase 1-3**: The addition of PlistBuddy rewriting (PR #248) means the file contents are now correct before ownership transfer. The core security improvement (correct paths in the plist) is in place.

**Remaining risk**: The directory ownership issue is the primary remaining concern. A user whose `~/Library/LaunchAgents/` is left root-owned will be unable to install or modify their own LaunchAgents, which is a functional impact. The file race is a theoretical concern with low exploitability in practice.

**Recommendation**:
```bash
mkdir -p "$LAUNCH_AGENTS_DIR"
if [[ -n "$CONSOLE_USER" ]]; then
    chown "${CONSOLE_USER}" "$LAUNCH_AGENTS_DIR"
fi
```
Or use `install` for atomic ownership:
```bash
install -d -o "$CONSOLE_USER" -m 755 "$LAUNCH_AGENTS_DIR"
install -o "$CONSOLE_USER" -m 644 "$PLIST_SRC" "$PLIST_DEST"
```

---

### [HIGH] F2-H2: CWE-426 DYLD_LIBRARY_PATH Still Inherits from Environment

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/python-launcher.sh:116-117`
**Severity**: HIGH
**Evidence**:
```bash
DYLD_LIBRARY_PATH="${PYTHON_HOME}/lib${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
export DYLD_LIBRARY_PATH
```
**Description**: While the PYTHONPATH inheritance was fixed (no longer appends the caller's PYTHONPATH), the `DYLD_LIBRARY_PATH` still appends any existing `DYLD_LIBRARY_PATH` from the environment via the `${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}` construct. This is the same pattern that was correctly identified and fixed for PYTHONPATH in PR #255, but the parallel fix was not applied to `DYLD_LIBRARY_PATH`.

In practice, launchd strips `DYLD_*` environment variables for LaunchAgents, so this is not exploitable in the normal launch path. However, if the Python launcher shim is invoked manually (e.g., for debugging, from a compromised `.zshrc`, or from another context where `DYLD_LIBRARY_PATH` is set), the embedded Python interpreter could be made to load malicious dynamic libraries from an attacker-controlled path.

**Risk**: Dynamic library injection if an attacker can influence the launch environment. Lower severity than the PYTHONPATH issue because launchd strips DYLD variables, but the inconsistency between PYTHONPATH (fixed) and DYLD_LIBRARY_PATH (not fixed) suggests this was an oversight.

**Recommendation**: Apply the same fix pattern as PYTHONPATH:
```bash
export DYLD_LIBRARY_PATH="${PYTHON_HOME}/lib"
```

---

### [MEDIUM] F2-M1: Plist Template Still Ships with /Users/Shared/ Default Paths

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/launchagent/com.kmflow.agent.plist:47,58,67`
**Severity**: MEDIUM (downgraded from CRITICAL since postinstall now rewrites)
**Evidence**:
```xml
<key>StandardOutPath</key>
<string>/Users/Shared/KMFlowAgent/Logs/agent.log</string>

<key>StandardErrorPath</key>
<string>/Users/Shared/KMFlowAgent/Logs/agent-error.log</string>

<key>EnvironmentVariables</key>
<dict>
    <key>HOME</key>
    <string>/Users/Shared</string>
</dict>
```
**Description**: Although the postinstall script now correctly rewrites these paths (resolving the original CRITICAL finding), the template plist file itself still contains `/Users/Shared/` as the default values. There are two scenarios where these defaults would persist into the installed plist:

1. **MDM deployment without postinstall**: If an MDM solution deploys the plist directly (without running the PKG postinstall script), the world-writable paths would be active. The plist comments mention MDM deployment with `$(HOME)` variable substitution, but this is not what the default values contain.

2. **PlistBuddy failure**: The postinstall suppresses PlistBuddy errors with `2>/dev/null || true` (lines 62-64). If PlistBuddy fails for any reason (corrupt plist, permissions issue), the rewriting silently fails and the `/Users/Shared/` paths remain.

**Risk**: Medium. The PKG installer path is now safe. The risk exists only for alternative deployment methods or PlistBuddy failure scenarios. The plist comments (lines 48-55) do explain this is a fallback, but the fallback itself is unsafe.

**Recommendation**: Change the template defaults to obviously-broken sentinel values that force failure if not rewritten:
```xml
<key>StandardOutPath</key>
<string>/UNCONFIGURED/MUST_BE_SET_BY_POSTINSTALL/agent.log</string>
```
This ensures that any deployment path that skips rewriting will fail with a clear error rather than silently writing to a world-writable location.

---

### [MEDIUM] F2-M2: CWE-920 Crash Loop Protection Still Limited at launchd Level

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/launchagent/com.kmflow.agent.plist:42-44`
**Severity**: MEDIUM
**Evidence**:
```xml
<key>ThrottleInterval</key>
<integer>10</integer>

<key>KeepAlive</key>
<dict>
    <key>SuccessfulExit</key>
    <false/>
</dict>
```
**Description**: This finding is unchanged from the original audit. The `ThrottleInterval` of 10 seconds combined with `KeepAlive.SuccessfulExit = false` means launchd will restart the agent indefinitely with a 10-second minimum interval, even after clean exits. The Swift-level circuit breaker (5 restarts in 60 seconds) provides some protection, but after the circuit breaker trips and the Swift process exits, launchd restarts the entire cycle. There is no launchd-level maximum retry count.

**Risk**: Sustained CPU and battery drain from a crash-looping agent on devices where the Python layer is broken (missing framework, corrupted dependencies, incompatible macOS version). The 10-second interval prevents a tight spin but does not prevent indefinite cycling.

**Recommendation**: Consider one or more of:
1. Increase `ThrottleInterval` to 30 seconds
2. Add `KeepAlive.PathState` keyed on a sentinel file, giving administrators a kill switch
3. Have the Swift circuit breaker write a "disabled" marker file that the process checks on next launch, breaking the launchd restart cycle permanently until user intervention

---

### [MEDIUM] F2-M3: CWE-295 Shell Variable Interpolation in Heredoc Python Script

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/build-app-bundle.sh:290-325`
**Severity**: MEDIUM
**Evidence**:
```bash
python3 - <<PYEOF
import hashlib, hmac, json, os, pathlib, secrets, sys

python_dir = pathlib.Path("${PYTHON_RESOURCES}")
...
output = pathlib.Path("${INTEGRITY_FILE}")
...
sig_output = pathlib.Path("${INTEGRITY_SIG_FILE}")
PYEOF
```
**Description**: The heredoc is unquoted (`<<PYEOF` rather than `<<'PYEOF'`), so shell variables `${PYTHON_RESOURCES}`, `${INTEGRITY_FILE}`, and `${INTEGRITY_SIG_FILE}` are interpolated before the Python script executes. If these paths contain characters significant in Python string literals (quotes, backslashes), the interpolation could break the script or produce incorrect integrity manifests.

The build script has been improved in Phase 3 (PR #257): an HMAC signature was added to the integrity manifest, and the `integrity.sig` file is now generated alongside the manifest. This adds defense-in-depth. However, the heredoc interpolation pattern was not changed.

**Risk**: Low in practice (macOS paths rarely contain problematic characters), but the pattern is a code injection anti-pattern in build scripts. A path containing a double-quote would break the Python string literal and could execute arbitrary Python code during the build.

**Recommendation**: Use a quoted heredoc and pass paths as arguments:
```bash
python3 - "$PYTHON_RESOURCES" "$INTEGRITY_FILE" "$INTEGRITY_SIG_FILE" <<'PYEOF'
import hashlib, hmac, json, pathlib, secrets, sys
python_dir = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])
sig_output = pathlib.Path(sys.argv[3])
PYEOF
```

---

### [MEDIUM] F2-M4 (NEW): CWE-494 Python Tarball SHA-256 Checksums Are Empty

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/embed-python.sh:40-52`
**Severity**: MEDIUM
**Evidence**:
```bash
declare -A PBS_CHECKSUMS=(
    # Placeholder hashes — MUST be replaced with real values from the release
    # SHA256SUMS file before any production build.
    ["aarch64"]=""
    ["x86_64"]=""
)
```
**Description**: The SHA-256 verification infrastructure was added in PR #251, which resolved the original HIGH supply chain finding. However, the actual checksum values for both architectures are empty strings. The script correctly blocks release builds (`KMFLOW_RELEASE_BUILD=1`) when checksums are empty, but development builds proceed with only a warning. This means every development build currently downloads and uses the Python framework without integrity verification.

The defense-in-depth value of SHA-256 verification is only realized once the hashes are populated. Until then, a compromised cached tarball in `~/.cache/kmflow-python/` would silently be used on every subsequent build.

**Risk**: Supply chain risk for development builds. The release build guard is the correct safety net, but development machines are often where initial testing and debugging occur with elevated privileges.

**Recommendation**: Populate the checksums immediately:
```bash
# Download the tarball, then:
shasum -a 256 ~/.cache/kmflow-python/cpython-3.12.*-aarch64-apple-darwin-install_only.tar.gz
shasum -a 256 ~/.cache/kmflow-python/cpython-3.12.*-x86_64-apple-darwin-install_only.tar.gz
```
Paste the resulting hashes into `PBS_CHECKSUMS`. Consider adding a CI check that fails if `PBS_CHECKSUMS` values are empty.

---

### [LOW] F2-L1: Missing LowPriorityIO and Nice for Background Agent

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/launchagent/com.kmflow.agent.plist`
**Severity**: LOW
**Evidence**: The plist sets `ProcessType` to `Background` (line 73) but does not include `LowPriorityIO` or `Nice` keys.
**Description**: Unchanged from original audit. For a background monitoring agent that writes to a local SQLite database and log files, setting `LowPriorityIO` to `true` and `Nice` to a positive value (e.g., 10) would reduce the agent's scheduling priority, minimizing interference with user foreground applications.
**Recommendation**: Add `<key>LowPriorityIO</key><true/>` and `<key>Nice</key><integer>10</integer>` to the plist.

---

### [LOW] F2-L2: LSUIElement in LaunchAgent Plist Has No Effect

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/launchagent/com.kmflow.agent.plist:76-77`
**Severity**: LOW
**Evidence**:
```xml
<key>LSUIElement</key>
<true/>
```
**Description**: Unchanged from original audit. `LSUIElement` is an `Info.plist` key (Launch Services framework), not a valid `launchd.plist` key. Including it in the LaunchAgent plist has no effect. The dock icon suppression must be set in the app bundle's `Contents/Resources/Info.plist`.
**Recommendation**: Remove `LSUIElement` from the LaunchAgent plist. Verify the app bundle's `Info.plist` contains either `LSUIElement` or `LSBackgroundOnly`.

---

### [LOW] F2-L3 (NEW): CWE-665 Preinstall User Resolution Inconsistency

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/pkg/scripts/preinstall:59`
**Severity**: LOW
**Evidence**:
```bash
CURRENT_USER_UID="$(id -u "${USER:-$(stat -f '%Su' /dev/console)}")"
```
**Description**: The preinstall script uses `${USER}` environment variable (which is `root` in PKG installer context) with a fallback to `stat -f '%Su' /dev/console`. The postinstall script correctly uses `stat -f '%Su' /dev/console` directly (line 12). This inconsistency means the preinstall may attempt to `launchctl bootout` for the root GUI domain (which likely does not exist), causing the bootout to silently fail. The `pkill` fallback on lines 66-74 mitigates this.
**Recommendation**: Use the same user resolution method as postinstall:
```bash
CONSOLE_USER="$(stat -f '%Su' /dev/console 2>/dev/null || echo "")"
CURRENT_USER_UID="$(id -u "$CONSOLE_USER" 2>/dev/null || echo "")"
```

---

## Out-of-Scope Findings (Tracked Elsewhere)

The following findings from the original F2 audit are now tracked in other agent reports and are not duplicated here:

| Finding | Tracked In | Status |
|---------|-----------|--------|
| CWE-532 Log Exposure (stdout/stderr to file) | G2 (Privacy) | Open (MEDIUM) |
| CWE-250 App Sandbox disabled | E1 (Entitlements) | Documented (ADR planned) |
| DMG not notarized | F1 (Signing) | Open (LOW) |

---

## Remediation Summary: Original 17 Findings

| # | Original Finding | Severity | Status | Resolution |
|---|-----------------|:--------:|:------:|------------|
| 1 | `eval` command injection in postinstall | CRITICAL | RESOLVED | PR #248: replaced with safe dscl+fallback |
| 2 | World-writable log paths in plist | CRITICAL | RESOLVED | PR #248: PlistBuddy rewriting implemented |
| 3 | No SHA-256 for Python tarball | HIGH | RESOLVED | PR #251: verification infrastructure added |
| 4 | PYTHONPATH inherits from environment | HIGH | RESOLVED | PR #255: caller's PYTHONPATH no longer appended |
| 5 | App Sandbox disabled + excess entitlements | HIGH | RESOLVED | PR #248: excess entitlements removed, documented |
| 6 | TOCTOU race in postinstall | HIGH | PARTIAL | Directory ownership not chowned; file race window shortened |
| 7 | Incomplete uninstall | HIGH | RESOLVED | PR #258: /Users/Shared cleanup + Keychain items added |
| 8 | Crash loop (ThrottleInterval=10s) | MEDIUM | OPEN | No change; launchd-level retry still unlimited |
| 9 | Log exposure (stdout to file) | MEDIUM | TRACKED | Moved to G2 report |
| 10 | DYLD_LIBRARY_PATH inheritance | MEDIUM | OPEN | Not addressed; same pattern as PYTHONPATH |
| 11 | Plist comment/code inconsistency | MEDIUM | RESOLVED | PR #248: comments now match implementation |
| 12 | TCC profile placeholder without tool | MEDIUM | RESOLVED | PR #258: customize-profiles.sh added |
| 13 | Shell heredoc interpolation | MEDIUM | OPEN | Unquoted heredoc persists |
| 14 | Missing LowPriorityIO | LOW | OPEN | No change |
| 15 | LSUIElement in wrong plist | LOW | OPEN | No change |
| 16 | DMG not notarized | LOW | TRACKED | Moved to F1 report |
| 17 | Preinstall user resolution inconsistency | LOW | OPEN | No change |

---

## New Findings Since Original Audit

| # | Finding | Severity | Source |
|---|---------|:--------:|--------|
| F2-M4 | Python tarball SHA-256 checksums are empty strings | MEDIUM | PR #251 added infrastructure but hashes not populated |

---

## Positive Security Practices (New or Improved)

1. **PlistBuddy path rewriting**: The postinstall now rewrites all three insecure default paths before installing the plist -- the most operationally impactful fix in this scope.
2. **Entitlement minimization**: Removed unused `automation.apple-events` (eliminated Apple Events attack surface) and meaningless `files.user-selected.read-write`.
3. **PYTHONPATH isolation**: Embedded Python no longer inherits any external Python path, making module injection significantly harder.
4. **SHA-256 verification infrastructure**: Release builds now refuse to proceed without hash verification. The guard exists even though the hashes are not yet populated.
5. **Profile customization script**: The `customize-profiles.sh` validates Team ID format and provides an official workflow for MDM profile preparation.
6. **Comprehensive uninstall**: Now covers 7 artifact categories including `/Users/Shared/` fallback location and Keychain items for both service names.
7. **No `--deep` signing**: The `build-app-bundle.sh` and `sign-all.sh` scripts sign components individually with `--options runtime --timestamp`, then sign the bundle without `--deep`.
8. **Ad-hoc signing guard**: `sign-all.sh` now refuses ad-hoc signing for release builds (`KMFLOW_RELEASE_BUILD=1`).
9. **HMAC-signed integrity manifest**: The integrity manifest now includes an HMAC-SHA256 signature (PR #257), adding defense-in-depth against manifest tampering.
10. **Backend URL validation**: `PythonProcessManager.swift` validates that `KMFLOW_BACKEND_URL` is `https://` with a non-nil host before passing it to the Python process.

---

## Checkbox Verification Results

- [x] **NO HARDCODED SECRETS** -- No credentials, API keys, or sensitive data hardcoded in any audited file.
- [x] **INPUT VALIDATION** -- Shell scripts validate file existence, required arguments, and Team ID format. No unsafe `eval` usage remains.
- [x] **PRIVILEGE MANAGEMENT** -- Excess entitlements removed. Minimal entitlement set. LaunchAgent runs as user, not root.
- [ ] **ENVIRONMENT ISOLATION** -- PYTHONPATH isolated. DYLD_LIBRARY_PATH still inherits from caller (F2-H2).
- [x] **SUPPLY CHAIN INTEGRITY** -- SHA-256 verification framework in place. Release builds blocked without hashes. (Hashes unpopulated for dev builds -- F2-M4.)
- [x] **DATA PROTECTION** -- Log paths rewritten to user-private directories (0700). /Users/Shared fallback no longer active in PKG installer flow.
- [x] **COMPLETE UNINSTALL** -- 7 artifact categories cleaned including /Users/Shared, Keychain, and Application Support.
- [ ] **CRASH RESILIENCE** -- Circuit breaker in Swift (good). No launchd-level retry limit (F2-M2).
- [ ] **ATOMIC FILE OPERATIONS** -- Postinstall directory and file creation still has TOCTOU window (F2-H1).

---

## Overall Security Score: 7.5 / 10

The installer infrastructure has improved from 5.5 to 7.5, reflecting the resolution of both CRITICAL findings, the supply chain verification addition, PYTHONPATH isolation, and entitlement minimization. The remaining issues (DYLD_LIBRARY_PATH inheritance, TOCTOU race, empty checksums, crash loop) are lower-severity and have clear remediation paths. The most impactful remaining action item is populating the SHA-256 checksums and fixing the DYLD_LIBRARY_PATH inheritance to match the PYTHONPATH fix.
