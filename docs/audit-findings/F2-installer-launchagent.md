# F2: Installer & LaunchAgent Security Audit

**Agent**: F2 (Installer & LaunchAgent Auditor)
**Date**: 2026-02-25
**Scope**: PKG installer scripts, LaunchAgent plist, uninstaller, Python launcher, app bundle build, Python process management
**Status**: Complete

## Finding Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2     |
| HIGH     | 5     |
| MEDIUM   | 6     |
| LOW      | 4     |
| **Total** | **17** |

## Executive Summary

The KMFlow macOS Task Mining Agent installer infrastructure is generally well-structured with good use of `set -euo pipefail`, proper `mktemp` patterns, and a thoughtful uninstall script. However, several significant security issues were identified. The most critical findings involve: (1) a `eval` command injection vector in the postinstall script that runs as root, and (2) the LaunchAgent plist shipping with fallback log paths in `/Users/Shared/` which is world-writable, creating a log injection and potential symlink attack surface. Additional concerns include the absence of download integrity verification for the embedded Python framework, a PYTHONPATH append that could inherit untrusted paths, the lack of App Sandbox, missing `LowPriorityIO` for a background monitoring agent, and the plist comment claiming postinstall "rewrites" paths when in fact it does not.

---

## CRITICAL Findings

### [CRITICAL] CWE-78 COMMAND INJECTION: `eval` in postinstall script running as root

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/pkg/scripts/postinstall:23`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```bash
USER_HOME="$(dscl . -read "/Users/$CONSOLE_USER" NFSHomeDirectory 2>/dev/null | awk '{print $2}' || eval echo "~$CONSOLE_USER")"
```
**Description**: The postinstall script runs as root (all PKG postinstall scripts execute in the root context). Line 23 contains a fallback that uses `eval echo "~$CONSOLE_USER"` where `CONSOLE_USER` is derived from `stat -f '%Su' /dev/console`. While `/dev/console` is typically a reliable source for the console user, `eval` interprets shell metacharacters. If `CONSOLE_USER` could ever be influenced to contain shell metacharacters (e.g., via a crafted username containing backticks, semicolons, or `$()` sequences), this becomes an arbitrary command execution as root. macOS usernames are normally restricted, but defense-in-depth demands avoiding `eval` in root-context scripts entirely.

**Risk**: Arbitrary command execution as root if the console username is influenced or if this pattern is copied into contexts where the input is less trustworthy. The `dscl` primary path mitigates this for most scenarios, but the `eval` fallback remains a dangerous pattern.

**Recommendation**: Replace `eval echo "~$CONSOLE_USER"` with a safe alternative:
```bash
USER_HOME="$(dscl . -read "/Users/$CONSOLE_USER" NFSHomeDirectory 2>/dev/null | awk '{print $2}')"
if [[ -z "$USER_HOME" ]]; then
    USER_HOME="/Users/$CONSOLE_USER"
fi
```
Or use `getent passwd` / `id -P` to resolve the home directory without `eval`.

---

### [CRITICAL] CWE-377 WORLD-WRITABLE LOG PATH: LaunchAgent writes to /Users/Shared/

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/launchagent/com.kmflow.agent.plist:47-58`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```xml
<key>StandardOutPath</key>
<string>/Users/Shared/KMFlowAgent/Logs/agent.log</string>

<key>StandardErrorPath</key>
<string>/Users/Shared/KMFlowAgent/Logs/agent-error.log</string>
```
**Description**: The plist template ships with log paths under `/Users/Shared/`, which is world-writable on macOS (permissions drwxrwxrwt). The plist comments on lines 48-55 state that "the postinstall script rewrites this plist with the actual home directory before installing it," but a thorough review of the actual postinstall script (`/Users/proth/repos/kmflow/agent/macos/installer/pkg/scripts/postinstall`) reveals **no such rewriting occurs**. The postinstall script simply copies the plist with `cp "$PLIST_SRC" "$PLIST_DEST"` (line 53) without any `sed`, `plutil`, `PlistBuddy`, or `defaults write` commands to substitute the paths. This means the `/Users/Shared/` paths remain in the installed plist.

Any local user can create the `/Users/Shared/KMFlowAgent/Logs/` directory first and place a symlink at `agent.log` pointing to an arbitrary file. When the agent starts, launchd will write (or truncate) that symlink target. This enables arbitrary file overwrite by the target user.

Additionally, the `EnvironmentVariables` section sets `HOME` to `/Users/Shared` (line 67), which means the agent's Application Support directory and IPC socket would also be created in the world-writable location if the postinstall does not actually rewrite this value.

**Risk**: Symlink attack enabling arbitrary file overwrite. Log data (potentially containing sensitive process intelligence) written to a world-readable location. Another user could read the monitoring agent's captured data. The IPC Unix domain socket created under `/Users/Shared/` would be accessible to all users, enabling potential event injection or interception.

**Recommendation**: 
1. **Immediately add plist rewriting to the postinstall script** using `plutil` or `/usr/libexec/PlistBuddy`:
```bash
/usr/libexec/PlistBuddy -c "Set :StandardOutPath ${USER_HOME}/Library/Logs/KMFlowAgent/agent.log" "$PLIST_DEST"
/usr/libexec/PlistBuddy -c "Set :StandardErrorPath ${USER_HOME}/Library/Logs/KMFlowAgent/agent-error.log" "$PLIST_DEST"
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:HOME ${USER_HOME}" "$PLIST_DEST"
```
2. Change the template defaults to use safe placeholders that will fail obviously if not rewritten (e.g., `/UNCONFIGURED/`) rather than a writable fallback.
3. Ensure the log and Application Support directories are created with `0700` permissions (the postinstall already does this, but only for `$USER_HOME` paths, not `/Users/Shared/`).

---

## HIGH Findings

### [HIGH] CWE-494 SUPPLY CHAIN: No integrity verification for downloaded Python framework

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/embed-python.sh:128-150`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```bash
download_tarball() {
    local arch="$1"
    local url
    url=$(resolve_download_url "$arch")
    local filename
    filename=$(basename "$url")
    local cached="${CACHE_DIR}/${filename}"

    mkdir -p "$CACHE_DIR"

    if [[ -f "$cached" ]]; then
        log "Cache hit: ${cached}"
    else
        log "Downloading: ${url}"
        curl -fL --progress-bar --output "$cached" "$url" \
            || { rm -f "$cached"; die "Download failed for ${url}"; }
```
**Description**: The `embed-python.sh` script downloads the Python 3.12 framework from GitHub (python-build-standalone releases) and embeds it into the app bundle. There is no SHA-256 checksum verification of the downloaded tarball. The download uses HTTPS (good), but there is no pinned hash to verify the downloaded content matches the expected artifact. A compromised mirror, CDN cache poisoning, or MITM attack on the download could inject a malicious Python interpreter that would then be bundled into every built agent.

Additionally, once a tarball is cached in `~/.cache/kmflow-python/`, subsequent builds reuse it without reverification. A local attacker who modifies the cached tarball would compromise all subsequent builds.

**Risk**: Supply chain compromise. A tampered Python interpreter embedded in the agent would execute with the user's full privileges including Accessibility API access, enabling keystroke logging, screen capture, and data exfiltration.

**Recommendation**: Add SHA-256 verification to `embed-python.sh`:
```bash
EXPECTED_SHA256_ARM64="<pin the hash here>"
EXPECTED_SHA256_X86_64="<pin the hash here>"
actual_hash=$(shasum -a 256 "$cached" | awk '{print $1}')
if [[ "$actual_hash" != "$expected_hash" ]]; then
    rm -f "$cached"
    die "SHA-256 mismatch for ${cached}"
fi
```

---

### [HIGH] CWE-426 PYTHONPATH INHERITANCE: Launcher appends to existing PYTHONPATH

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/python-launcher.sh:87`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```bash
export PYTHONPATH="${RESOURCES_DIR}/python:${RESOURCES_DIR}/python/site-packages${PYTHONPATH:+:${PYTHONPATH}}"
```
**Description**: The Python launcher shim prepends the bundle's directories to `PYTHONPATH` but also appends any existing `PYTHONPATH` from the environment via `${PYTHONPATH:+:${PYTHONPATH}}`. While the script does set `PYTHONNOUSERSITE=1` (line 91) and `PYTHONHOME` (line 80) to prevent user site-packages, the `PYTHONPATH` append means that if the parent process (the Swift binary or launchd) has a `PYTHONPATH` set in the environment, those paths will be included. An attacker who can influence the environment (e.g., through the LaunchAgent's `EnvironmentVariables`, or via a compromised `.zshrc` / `.bash_profile` if the agent is launched interactively) could inject a malicious Python module path.

**Risk**: Code injection via malicious Python module in an attacker-controlled path on `PYTHONPATH`. The agent runs with Accessibility API access, so compromised Python code gains keylogger and screen capture capabilities.

**Recommendation**: Do not inherit the existing `PYTHONPATH`. Replace with:
```bash
export PYTHONPATH="${RESOURCES_DIR}/python:${RESOURCES_DIR}/python/site-packages"
```
The embedded Python should be fully self-contained and never load modules from external paths.

---

### [HIGH] CWE-250 NO APP SANDBOX: Agent runs unsandboxed with Accessibility entitlements

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/KMFlowAgent.entitlements:24-25`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```xml
<key>com.apple.security.app-sandbox</key>
<false/>
```
**Description**: The agent runs without App Sandbox, which is explicitly disabled in the entitlements. Combined with the Accessibility API access (`com.apple.security.automation.apple-events`) and unrestricted file access (`com.apple.security.files.user-selected.read-write`), the agent has broad system access. While the App Sandbox may be intentionally disabled because Accessibility APIs require it (macOS does not allow sandboxed apps to use AXUIElement), this should be explicitly documented and the remaining entitlements should be minimized.

The `com.apple.security.files.user-selected.read-write` entitlement grants broad file access that is unnecessary for an unsandboxed app (this entitlement is only meaningful within a sandbox). Its presence suggests the entitlements file may have been cargo-culted rather than deliberately minimized.

**Risk**: Without sandboxing, any code execution vulnerability in the agent (or its Python layer) grants the attacker full access to the user's files, keychain, and all Accessibility-granted capabilities. The unnecessary `files.user-selected.read-write` entitlement is not a direct vulnerability but indicates incomplete entitlement hygiene.

**Recommendation**: 
1. Document why App Sandbox is disabled (Accessibility API requirement).
2. Remove `com.apple.security.files.user-selected.read-write` -- it has no effect outside the sandbox and its presence is misleading.
3. Consider implementing a manual sandboxing approach (restricted `PATH`, `chroot`-like containment for the Python process, or macOS Endpoint Security).

---

### [HIGH] CWE-367 TOCTOU: Postinstall plist ownership race condition

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/pkg/scripts/postinstall:52-59`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```bash
mkdir -p "$LAUNCH_AGENTS_DIR"
cp "$PLIST_SRC" "$PLIST_DEST"

# Ensure the plist is owned by the console user (installer runs as root)
if [[ -n "$CONSOLE_USER" ]]; then
    chown "${CONSOLE_USER}" "$PLIST_DEST"
fi
chmod 644 "$PLIST_DEST"
```
**Description**: The postinstall script creates the `~/Library/LaunchAgents/` directory (if it does not exist) as root, copies the plist, then changes ownership to the console user. There is a TOCTOU window between `cp` and `chown` where the file is owned by root with mode 644, meaning any user can read it. More importantly, the `mkdir -p` of the LaunchAgents directory is done as root. If the directory did not previously exist, it is created with root ownership, and the script never `chown`s the directory itself -- only the plist file. This could leave `~/Library/LaunchAgents/` owned by root, preventing the user from managing their own LaunchAgents afterward.

**Risk**: The user's `~/Library/LaunchAgents/` directory could be left with root ownership, breaking the ability to install/remove other LaunchAgents. In a contrived scenario, an attacker who can write to the directory between `cp` and `chown` could replace the plist with a malicious one that will be owned by the console user after `chown`.

**Recommendation**: 
1. Add `chown "${CONSOLE_USER}" "$LAUNCH_AGENTS_DIR"` after the `mkdir -p`.
2. Use `install -o "$CONSOLE_USER" -m 644` to atomically set ownership and permissions.
3. Consider writing to a temporary file and using `mv` for an atomic rename.

---

### [HIGH] CWE-665 INCOMPLETE UNINSTALL: Socket file and /Users/Shared residue not cleaned

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/uninstall.sh`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```bash
# Step 4: Remove Application Support data (line 95-101)
APP_SUPPORT="${HOME}/Library/Application Support/KMFlowAgent"
if [[ -d "$APP_SUPPORT" ]]; then
    rm -rf "$APP_SUPPORT"
    echo "  Removed: $APP_SUPPORT"
else
    echo "  Not found (already removed): $APP_SUPPORT"
fi
```
**Description**: The uninstall script has several omissions:

1. **Unix domain socket**: The IPC socket at `~/Library/Application Support/KMFlowAgent/agent.sock` should be cleaned up, but it is covered by the `rm -rf` of the Application Support directory. However, if the socket is in `/Users/Shared/` (as the un-rewritten plist would configure), it is NOT cleaned.

2. **`/Users/Shared/KMFlowAgent/` residue**: Due to the CRITICAL finding about un-rewritten plist paths, logs and data may exist under `/Users/Shared/KMFlowAgent/`. The uninstall script does not clean this location.

3. **`~/Library/Caches/` residue**: No cleanup of any cache directories the agent may create.

4. **`~/.cache/kmflow-python/` build cache**: Not relevant for end users, but developers/CI machines would retain cached Python tarballs.

5. **MDM configuration profile**: The uninstall script does not attempt to remove installed `.mobileconfig` profiles (though this is typically managed by MDM).

6. **UserDefaults**: Preferences written to `com.kmflow.agent` domain via `defaults write` or managed preferences are not cleared.

**Risk**: Monitoring data residue left on the machine after uninstall. For a privacy-sensitive tool (task mining agent), incomplete cleanup means screenshots, keystroke metadata, and process intelligence data could persist on the device after the user believes the agent has been removed.

**Recommendation**: Add cleanup for all residual locations:
```bash
# Clean /Users/Shared fallback location
rm -rf "/Users/Shared/KMFlowAgent" 2>/dev/null || true

# Clear UserDefaults
defaults delete com.kmflow.agent 2>/dev/null || true

# Note about MDM profiles in output
echo "  Note: MDM configuration profiles must be removed via your MDM console."
```

---

## MEDIUM Findings

### [MEDIUM] CWE-920 CRASH LOOP: ThrottleInterval of 10s allows sustained high CPU

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/launchagent/com.kmflow.agent.plist:43-44`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```xml
<key>ThrottleInterval</key>
<integer>10</integer>
```
**Description**: The `ThrottleInterval` is set to 10 seconds, and `KeepAlive.SuccessfulExit` is `false`, meaning launchd will restart the agent every 10 seconds even after a clean exit. If the agent has a startup crash (e.g., corrupted Python framework, missing dependency), launchd will restart it every 10 seconds indefinitely. Combined with the Python subprocess circuit breaker (5 restarts in 60 seconds at the Swift level), a crashing agent would cycle through: launchd starts Swift binary -> Swift starts Python -> Python crashes 5 times in 60s -> circuit breaker trips -> Swift exits -> launchd waits 10s -> repeat.

There is no maximum restart count at the launchd level, so this loop continues indefinitely.

**Risk**: Sustained CPU and battery drain from a crash-looping agent. On a laptop, this could significantly impact battery life and performance. The 10-second interval is better than no throttle, but a progressively increasing backoff or a maximum retry limit would be safer.

**Recommendation**: 
1. Increase `ThrottleInterval` to 30 or 60 seconds.
2. Consider implementing the `KeepAlive.PathState` pattern to only restart when the Application Support directory exists, giving users a manual kill switch.
3. Document the crash loop behavior and how administrators can disable the agent permanently by removing the plist.

---

### [MEDIUM] CWE-532 LOG EXPOSURE: Agent stdout/stderr sent directly to log files

**File**: `/Users/proth/repos/kmflow/agent/macos/Sources/KMFlowAgent/PythonProcessManager.swift:93-94`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```swift
proc.standardOutput = FileHandle.standardOutput
proc.standardError = FileHandle.standardError
```
**Description**: The Python subprocess's stdout and stderr are connected directly to the Swift process's stdout/stderr, which launchd routes to the log files specified in the plist (`StandardOutPath` and `StandardErrorPath`). There is no sanitization or filtering of the Python process's output before it reaches the log files. If the Python intelligence layer logs sensitive data (API keys, bearer tokens, user-entered text captured by the Accessibility API), this data ends up in plain-text log files on disk.

Given that the plist's log paths currently point to `/Users/Shared/` (world-readable), this becomes a data exposure vector.

**Risk**: Sensitive data (API tokens, captured text, backend credentials) may be logged to disk in plaintext. If log files are in a world-readable location (per the CRITICAL finding), any local user can read this data.

**Recommendation**: 
1. Implement log redaction in the Python layer for sensitive fields.
2. Create a Pipe-based log handler in Swift that filters sensitive patterns before writing to the file handle.
3. Ensure log files are created with `0600` permissions.
4. Implement log rotation to limit the window of exposure.

---

### [MEDIUM] CWE-426 DYLD_LIBRARY_PATH: Dynamic linker path manipulation

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/python-launcher.sh:114-115`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```bash
DYLD_LIBRARY_PATH="${PYTHON_HOME}/lib${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
export DYLD_LIBRARY_PATH
```
**Description**: Similar to the `PYTHONPATH` issue, the script appends any existing `DYLD_LIBRARY_PATH` to its own. While the comment on line 111 correctly notes that SIP strips `DYLD_LIBRARY_PATH` for protected binaries, the embedded Python interpreter is not a protected binary. An attacker who can set `DYLD_LIBRARY_PATH` in the agent's environment could cause the Python interpreter to load malicious dynamic libraries instead of the bundled ones.

In practice, launchd does not pass `DYLD_LIBRARY_PATH` through to LaunchAgents (it is stripped), but if the shim is invoked manually or from another context, this becomes exploitable.

**Risk**: Dynamic library injection if the attacker can influence the launch environment. Lower risk than PYTHONPATH because launchd strips DYLD_ variables, but the defensive coding should not rely on that.

**Recommendation**: Do not inherit existing `DYLD_LIBRARY_PATH`:
```bash
export DYLD_LIBRARY_PATH="${PYTHON_HOME}/lib"
```

---

### [MEDIUM] CWE-1188 PLIST INCONSISTENCY: Comments claim rewriting that does not occur

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/launchagent/com.kmflow.agent.plist:48-55`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```xml
<!-- NOTE: This path is a default fallback. The postinstall script creates
     ~/Library/Logs/KMFlowAgent/ owned by the console user.  For a per-user
     LaunchAgent the correct runtime path is expanded by launchd using the
     HOME environment variable.  Use the path below when deploying through
     MDM with launchd's environment substitution support:
       $(HOME)/Library/Logs/KMFlowAgent/agent.log
     For the PKG installer the postinstall script rewrites this plist with
     the actual home directory before installing it. -->
```
**Description**: The plist comments explicitly state that "the postinstall script rewrites this plist with the actual home directory before installing it." However, the postinstall script (`/Users/proth/repos/kmflow/agent/macos/installer/pkg/scripts/postinstall`) performs a simple `cp` on line 53 with no plist manipulation. This is not just a documentation error -- it represents a functional gap where the intended security behavior was documented but never implemented. This is the root cause of the CRITICAL `/Users/Shared/` finding above.

**Risk**: This documentation-implementation mismatch could lead developers to believe the plist paths are safely rewritten, preventing them from investigating the actual vulnerability. It indicates the security-critical postinstall logic was designed but not completed.

**Recommendation**: Either implement the plist rewriting as documented, or update the comments to match reality and change the default paths to safe values.

---

### [MEDIUM] CWE-1104 TCC PROFILE: Placeholder CodeRequirement allows any ad-hoc signed binary

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/profiles/com.kmflow.agent.tcc.mobileconfig:104-107`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```xml
<!-- PLACEHOLDER — replace before MDM deployment: -->
<key>CodeRequirement</key>
<string>identifier "com.kmflow.agent" and anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] and certificate leaf[field.1.2.840.113635.100.6.1.13] and certificate leaf[subject.OU] = "REPLACE_TEAM_ID"</string>
```
**Description**: The TCC/PPPC configuration profile contains a placeholder `REPLACE_TEAM_ID` in the CodeRequirement string. If this profile is deployed to MDM without replacing this value, the CodeRequirement will not match any real binary (since "REPLACE_TEAM_ID" is not a valid team ID), which means TCC pre-approval would silently fail. Users would be prompted for Accessibility access, which is the secure fallback. However, if someone "fixes" this by setting it to an overly broad requirement (e.g., removing the team ID check), it could pre-approve unintended binaries.

The comment warns to replace this, but there is no build-time validation to prevent deployment with the placeholder.

**Risk**: If deployed with placeholder, TCC pre-approval silently fails (low risk). If replaced with an overly broad CodeRequirement, arbitrary apps could gain pre-approved Accessibility access (high risk in that scenario).

**Recommendation**: Add a deployment validation script that checks for `REPLACE_TEAM_ID` in the profile and fails with a clear error message if found. Consider using a `.template` extension for the file to make it obvious it requires customization.

---

### [MEDIUM] CWE-295 INLINE PYTHON: Shell variable interpolation in heredoc Python script

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/build-app-bundle.sh:288-303`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```bash
python3 - <<PYEOF
import hashlib, json, os, pathlib, sys

python_dir = pathlib.Path("${PYTHON_RESOURCES}")
manifest = {}

for path in sorted(python_dir.rglob("*")):
    if path.is_file() and path.name != "integrity.json":
        rel = str(path.relative_to(python_dir))
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest[rel] = sha256

output = pathlib.Path("${INTEGRITY_FILE}")
output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
```
**Description**: The integrity manifest generation uses an unquoted heredoc (`<<PYEOF` not `<<'PYEOF'`), which means shell variables `${PYTHON_RESOURCES}` and `${INTEGRITY_FILE}` are interpolated before the Python script executes. If these paths contain characters that are significant in Python string literals (e.g., backslashes on other platforms, or quotes), the interpolation could break the Python script or cause unintended behavior. On macOS with standard paths this is low risk, but it is a code injection anti-pattern.

**Risk**: If build paths contain special characters (quotes, backslashes), the integrity manifest generation could fail or produce incorrect results, potentially allowing tampered files to pass integrity checks.

**Recommendation**: Use a quoted heredoc (`<<'PYEOF'`) and pass the paths as command-line arguments to the Python script:
```bash
python3 - "$PYTHON_RESOURCES" "$INTEGRITY_FILE" <<'PYEOF'
import hashlib, json, pathlib, sys
python_dir = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])
...
PYEOF
```

---

## LOW Findings

### [LOW] LAUNCHD CONFIG: Missing LowPriorityIO for background monitoring agent

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/launchagent/com.kmflow.agent.plist`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```xml
<key>ProcessType</key>
<string>Background</string>
```
**Description**: The plist sets `ProcessType` to `Background` (good), but does not include `LowPriorityIO` set to `true`. For a background monitoring agent that writes to a local SQLite database and log files, setting `LowPriorityIO` would reduce the agent's I/O priority, minimizing impact on the user's foreground applications. The `Nice` key is also absent, which could be set to a positive value (e.g., 10) to lower CPU scheduling priority.

**Risk**: The agent may compete with user applications for I/O bandwidth, particularly during high-activity periods when many events are captured.

**Recommendation**: Add to the plist:
```xml
<key>LowPriorityIO</key>
<true/>
<key>Nice</key>
<integer>10</integer>
```

---

### [LOW] ENTITLEMENT: LSUIElement in plist is not a standard launchd key

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/launchagent/com.kmflow.agent.plist:76-77`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```xml
<!-- Do NOT display a dock icon or UI for this background agent -->
<key>LSUIElement</key>
<true/>
```
**Description**: `LSUIElement` is an `Info.plist` key (part of the Launch Services framework), not a `launchd.plist` key. Including it in the LaunchAgent plist has no effect -- launchd ignores unknown keys. The actual `LSUIElement` setting should be in the app bundle's `Info.plist` (at `Contents/Resources/Info.plist`). This is a configuration error that does not cause harm but indicates the plist may not have been thoroughly reviewed.

**Risk**: No direct security risk. The dock icon suppression is not effective if it is only in the LaunchAgent plist. If `Info.plist` does not also set `LSUIElement`, the agent would show a dock icon, which is a usability issue for a background agent.

**Recommendation**: Remove `LSUIElement` from the LaunchAgent plist. Verify that `Info.plist` in the app bundle contains `<key>LSUIElement</key><true/>` (or the modern `<key>LSBackgroundOnly</key><true/>`).

---

### [LOW] DMG SIGNING: DMG not notarized, only codesigned

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/dmg/build-dmg.sh:112`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```bash
codesign --sign "$IDENTITY" "$DMG_PATH"
```
**Description**: The DMG build script signs the DMG image but does not submit it for Apple notarization (`xcrun notarytool submit`). A separate `notarize.sh` script exists for the app bundle itself, but the DMG is the actual distribution artifact that users download and open. Without notarization, macOS Gatekeeper will display a warning when users attempt to open the DMG (on macOS 10.15+), and on stricter enterprise configurations, it may be blocked entirely.

**Risk**: Users may be unable to open the DMG on managed macOS devices with Gatekeeper set to "App Store and identified developers" or stricter. Users who override the Gatekeeper warning are trained to ignore security prompts, which is a broader risk.

**Recommendation**: Add a notarization step to `build-dmg.sh` or document that notarization must be run separately after the DMG is built. Consider integrating with the existing `notarize.sh` workflow.

---

### [LOW] PREINSTALL: User identity resolution inconsistency

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/pkg/scripts/preinstall:59`
**Agent**: F2 (Installer & LaunchAgent Auditor)
**Evidence**:
```bash
CURRENT_USER_UID="$(id -u "${USER:-$(stat -f '%Su' /dev/console)}")"
```
**Description**: The preinstall script uses `${USER}` environment variable with a fallback to `stat -f '%Su' /dev/console` for determining the current user. In a PKG postinstall context running as root, `$USER` is typically "root", not the console user. The postinstall script correctly uses `stat -f '%Su' /dev/console` directly, but the preinstall uses `$USER` first. This inconsistency means the preinstall may attempt to `launchctl bootout` for the root user's GUI domain (which likely does not exist), causing the bootout to silently fail. The `|| echo "LaunchAgent not loaded (OK for fresh install)."` fallback handles this gracefully, but the inconsistency indicates a potential logic error.

**Risk**: Minimal -- the running agent may not be properly stopped before installation begins, leading to file-in-use issues. In practice, the `pkill` fallback on lines 66-74 mitigates this.

**Recommendation**: Use the same user resolution method as the postinstall script:
```bash
CONSOLE_USER="$(stat -f '%Su' /dev/console 2>/dev/null || echo "")"
CURRENT_USER_UID="$(id -u "$CONSOLE_USER" 2>/dev/null || echo "")"
```

---

## Security Posture Assessment

### Positive Security Practices Observed

1. **`set -euo pipefail`** used consistently across all shell scripts -- prevents silent failures and unset variable expansion.
2. **`mktemp -d` with trap cleanup** in `build-pkg.sh` (line 51-52) -- proper temporary directory handling.
3. **Integrity manifest generation** (`integrity.json` with SHA-256 hashes) in `build-app-bundle.sh` -- defense-in-depth for Python layer tampering detection.
4. **Circuit breaker pattern** in `PythonProcessManager.swift` -- limits crash-loop restarts to 5 within 60 seconds.
5. **`PYTHONNOUSERSITE=1`** in the launcher -- prevents loading user-level Python packages.
6. **Keychain cleanup** in the uninstall script -- removes stored credentials.
7. **Hardened Runtime entitlements** -- JIT, unsigned executable memory, and library validation are all explicitly disabled.
8. **Proper use of `launchctl bootstrap/bootout`** -- modern launchd API instead of deprecated `load/unload`.
9. **Process kill with graceful escalation** -- SIGTERM with 5-second timeout before SIGKILL in both uninstall.sh and PythonProcessManager.swift.
10. **`StaticCode` set to `false`** in TCC profile -- forces runtime signature re-validation.
11. **Application Support directories created with 0700** -- user-private by default.

### Areas of Concern

1. **The plist rewriting gap is the most operationally dangerous finding** -- the code and comments describe different behaviors, and the actual behavior results in a world-writable data path.
2. **No download integrity verification** for the embedded Python framework is a significant supply chain risk.
3. **Environment variable inheritance** (`PYTHONPATH`, `DYLD_LIBRARY_PATH`) breaks the isolation model that the launcher otherwise tries to establish.

### Overall Security Score: 5.5 / 10

The installer infrastructure demonstrates security awareness (hardened runtime, circuit breaker, integrity manifest) but has critical implementation gaps (plist rewriting never implemented, world-writable fallback paths, no download verification). The CRITICAL and HIGH findings must be addressed before any enterprise deployment.

### Checkbox Verification Results

- [ ] **NO HARDCODED SECRETS** -- No credentials, API keys, or sensitive data hardcoded: **PASS** -- No secrets found in any audited file.
- [ ] **INPUT VALIDATION** -- All user inputs properly validated: **PARTIAL** -- Shell scripts validate file existence and required arguments, but `eval` usage in postinstall is unsafe.
- [ ] **AUTHENTICATION SECURITY** -- Proper authentication mechanisms: **N/A** -- Installer scripts do not handle authentication directly.
- [ ] **PRIVILEGE MANAGEMENT** -- Minimal privilege principle followed: **FAIL** -- App Sandbox disabled without compensating controls; world-writable paths used.
- [ ] **SUPPLY CHAIN INTEGRITY** -- Downloaded dependencies verified: **FAIL** -- No SHA-256 verification for Python framework downloads.
- [ ] **DATA PROTECTION** -- Sensitive data protected at rest: **FAIL** -- Log files in world-readable `/Users/Shared/`; no log redaction.
- [ ] **COMPLETE UNINSTALL** -- All artifacts removed: **FAIL** -- `/Users/Shared/KMFlowAgent/`, UserDefaults, and potential cache directories not cleaned.
- [ ] **CRASH RESILIENCE** -- Proper crash loop protection: **PARTIAL** -- Circuit breaker in Swift (good), but no launchd-level retry limit.
