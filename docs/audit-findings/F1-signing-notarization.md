# F1: Code Signing & Notarization Security Audit

**Agent**: F1 (Code Signing & Notarization Auditor)
**Date**: 2026-02-25
**Scope**: macOS Task Mining Agent signing pipeline, notarization flow, packaging, and supply chain
**Target Distribution**: Enterprise MDM (Jamf, Intune, Mosyle) to employee machines

---

## Executive Summary

The KMFlow macOS Agent signing pipeline has a well-structured release flow (build -> sign -> notarize -> verify -> package -> checksum) but contains **several critical and high-severity issues** that must be resolved before enterprise distribution. The most dangerous finding is that the default signing identity is ad-hoc (`-`), and the pipeline silently proceeds with ad-hoc signing when credentials are absent -- meaning a release build distributed via MDM could be ad-hoc signed and rejected by Gatekeeper on every target machine. Additionally, the notarization script silently exits successfully when credentials are missing, the embedded Python framework is signed without Hardened Runtime, Python dependencies are fetched without hash verification, and the verification script does not check for Hardened Runtime or notarization ticket stapling.

---

## Finding Counts

| Severity | Count |
|----------|-------|
| CRITICAL | 4     |
| HIGH     | 6     |
| MEDIUM   | 5     |
| LOW      | 3     |
| **Total** | **18** |

---

## CRITICAL Findings

### [CRITICAL] C1: Ad-Hoc Signing Default Allows Gatekeeper-Rejected Builds to Ship

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/sign-all.sh:12`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# sign-all.sh:4
# Env:   KMFLOW_CODESIGN_IDENTITY  (default: "-" for ad-hoc signing)

# sign-all.sh:12
IDENTITY="${KMFLOW_CODESIGN_IDENTITY:--}"
```
**Description**: The signing identity defaults to `"-"` (ad-hoc signing) when `KMFLOW_CODESIGN_IDENTITY` is not set. Ad-hoc signed binaries have no Developer ID signature, meaning Gatekeeper will block them on any macOS machine that has not explicitly trusted the developer. This is also the default in `build-app-bundle.sh:56`, `release.sh:13`, `build-dmg.sh:19`, and `build-pkg.sh:16`. There is no validation that the identity is a real Developer ID certificate before proceeding with the release pipeline.
**Risk**: An enterprise MDM deployment with an ad-hoc signed binary will be rejected by Gatekeeper on every target machine. Users will see "This app cannot be opened because the developer cannot be verified." The entire deployment will fail silently -- the installer runs but the app is quarantined.
**Recommendation**: (1) Add a pre-signing check that validates the identity exists in the Keychain via `security find-identity -v -p codesigning | grep "$IDENTITY"`. (2) In `release.sh`, refuse to proceed if `IDENTITY` is `"-"` unless an explicit `--allow-adhoc` flag is passed. (3) In CI (`agent-release.yml`), fail the job if `KMFLOW_CODESIGN_IDENTITY` resolves to `"-"`.

---

### [CRITICAL] C2: Notarization Silently Skipped When Credentials Missing -- Exit 0

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/notarize.sh:19-22`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# notarize.sh:17-22
# Guard: skip if APPLE_ID not set (local / CI without notarization credentials)
if [[ -z "${APPLE_ID:-}" ]]; then
    echo "Skipping notarization: APPLE_ID not set"
    exit 0
fi
```
**Description**: When `APPLE_ID` is not set, the notarization script prints a message to stdout and exits with code 0 (success). The calling script (`release.sh`) does not check whether notarization actually occurred -- it just proceeds to packaging. This means a release build can complete the full pipeline and produce DMG/PKG artifacts that are signed but NOT notarized, and there is no error or failure signal anywhere in the pipeline.
**Risk**: Un-notarized artifacts can be distributed to enterprise machines via MDM. On macOS 10.15+ (Catalina), Gatekeeper requires notarization for apps distributed outside the App Store. The PKG installer will fail the Gatekeeper check at install time, or the app will be quarantined after install, causing deployment failures across the enterprise.
**Recommendation**: (1) In `release.sh`, after calling `notarize.sh`, check whether notarization actually ran (e.g., check for a stapled ticket via `stapler validate`). (2) If `--skip-notarize` was NOT requested but notarization was skipped due to missing credentials, fail the release. (3) Add a final gating step that runs `spctl --assess --type exec` and fails the pipeline if it does not pass.

---

### [CRITICAL] C3: Notarization Result Not Checked Before Stapling

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/notarize.sh:68-79`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# notarize.sh:68-79
xcrun notarytool submit "$ZIP_PATH" \
    --apple-id  "$APPLE_ID" \
    --team-id   "$TEAM_ID" \
    --password  "$APP_PASSWORD" \
    --wait
echo ""

# Step 3: Staple the notarization ticket to the .app
echo "--- Step 3: Stapling notarization ticket ---"
xcrun stapler staple "$APP_PATH"
```
**Description**: While `set -euo pipefail` is active and a non-zero exit from `notarytool` would halt the script, Apple's `notarytool submit --wait` can return exit code 0 even when the notarization status is "Invalid" in some edge cases (e.g., when the submission is accepted but the audit fails). The script does not capture the submission ID, does not call `notarytool info` to verify the status is "Accepted", and does not log the notarization audit URL. It proceeds directly to stapling, which may silently fail or succeed with a stale ticket.
**Risk**: A build that was rejected by Apple's notary service could proceed through stapling and packaging without any error. The resulting artifacts would appear to be complete but would fail Gatekeeper assessment on end-user machines.
**Recommendation**: (1) Capture the submission ID from `notarytool submit` output. (2) After `--wait` completes, run `xcrun notarytool info <submission-id>` and parse the status for "Accepted". (3) If status is not "Accepted", fetch and display the notarization log via `xcrun notarytool log <submission-id>` and exit 1. (4) After stapling, verify with `xcrun stapler validate "$APP_PATH"`.

---

### [CRITICAL] C4: Supply Chain Risk -- Python Dependencies Fetched Without Hash Verification

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/vendor-python-deps.sh:151-160`  
**Additional File**: `/Users/proth/repos/kmflow/agent/python/requirements.txt`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# vendor-python-deps.sh:151-160
$PIP_CMD install \
    --target "$site_dir" \
    --python-version "$PYTHON_VERSION_TAG" \
    --platform "$PIP_PLATFORM" \
    --only-binary=:all: \
    --no-compile \
    --upgrade \
    --quiet \
    "${packages[@]}" \
    || die "pip install failed for: ${packages[*]}"
```
```
# requirements.txt (entire file)
httpx>=0.28.0
PyJWT[crypto]>=2.9.0
psutil>=5.9.0
cryptography>=42.0.0
```
**Description**: Python dependencies are installed at build time from PyPI without `--require-hashes`. The requirements file uses `>=` version specifiers (not pinned), meaning pip will fetch the latest compatible version at build time. There is no lock file, no hash verification, and no SBOM generation. The `--only-binary=:all:` flag prevents source compilation but does not prevent a compromised wheel from being installed.
**Risk**: A PyPI supply chain attack (typosquatting, account takeover, dependency confusion) could inject malicious code into the signed and notarized application bundle. Because the dependencies are vendored inside the `.app` bundle and then code-signed, a compromised package would receive a valid Apple Developer ID signature, making the malware trusted by Gatekeeper and MDM policies. This is particularly dangerous because the agent runs with Accessibility API access and can observe all user activity.
**Recommendation**: (1) Pin exact versions in requirements.txt (e.g., `httpx==0.28.1`). (2) Generate a lock file with hashes using `pip-compile --generate-hashes` or `pip freeze --require-hashes`. (3) Pass `--require-hashes` to the pip install command. (4) Generate an SBOM (e.g., CycloneDX) and include it in the release artifacts. (5) Consider committing vendored wheels to the repository for full reproducibility.

---

## HIGH Findings

### [HIGH] H1: Embedded Python Framework Signed Without Hardened Runtime

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/embed-python.sh:326-334`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# embed-python.sh:326-334
find "${fw_root}" \( -name "*.so" -o -name "*.dylib" \) -print0 \
    | xargs -0 -P4 codesign --force --sign "$CODESIGN_IDENTITY" 2>/dev/null || true

codesign --force --sign "$CODESIGN_IDENTITY" \
    "${fw_root}/Versions/${PYTHON_VERSION}/bin/python${PYTHON_VERSION}" \
    2>/dev/null || true

# Sign the framework bundle itself
codesign --force --sign "$CODESIGN_IDENTITY" "$fw_root" 2>/dev/null || true
```
**Description**: The embedded Python.framework (interpreter binary, dylibs, and .so extension modules) is signed without `--options runtime` (Hardened Runtime) and without `--timestamp`. The `--options runtime` flag is only applied in `sign-all.sh:77` for the final `.app` bundle signing, not for the individual framework components signed during `embed-python.sh`. While the outer `.app` bundle does have Hardened Runtime, the individual components within the framework lack it.
**Risk**: Without Hardened Runtime on individual components, the Python interpreter and its native extensions can execute arbitrary code, load unsigned libraries, and use JIT compilation without restriction. While the outer app signature constrains the bundle, individually-signed components that lack `--options runtime` may behave differently when loaded as frameworks. Apple's notarization service may also reject bundles where nested components lack Hardened Runtime.
**Recommendation**: Add `--options runtime --timestamp` to all three codesign invocations in `codesign_framework()`. Also apply `--timestamp` to enable notarization compatibility.

---

### [HIGH] H2: Codesign Failures Silently Suppressed via `2>/dev/null || true`

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/embed-python.sh:327,331,334`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# embed-python.sh:327
    | xargs -0 -P4 codesign --force --sign "$CODESIGN_IDENTITY" 2>/dev/null || true

# embed-python.sh:329-331
codesign --force --sign "$CODESIGN_IDENTITY" \
    "${fw_root}/Versions/${PYTHON_VERSION}/bin/python${PYTHON_VERSION}" \
    2>/dev/null || true

# embed-python.sh:334
codesign --force --sign "$CODESIGN_IDENTITY" "$fw_root" 2>/dev/null || true
```
**Description**: All three codesign operations in `codesign_framework()` redirect stderr to `/dev/null` and use `|| true` to suppress any failure. This means if the signing identity is invalid, the keychain is locked, or the binary is malformed, the script will silently continue. The same pattern appears in `build-app-bundle.sh:322` and `build-app-bundle.sh:327`.
**Risk**: Signing failures go completely undetected. The build produces an unsigned or partially-signed Python.framework that is then embedded in the .app bundle. The outer `sign-all.sh` step uses `--deep` (see H3) which may paper over the issue, but Gatekeeper and notarization can still detect component-level signing problems.
**Recommendation**: Remove `2>/dev/null || true` from all codesign commands in the signing pipeline. Use `set -euo pipefail` (already set) and let failures propagate naturally. If specific failures are expected and acceptable (e.g., signing non-Mach-O files), check the file type before signing rather than suppressing errors.

---

### [HIGH] H3: Use of `--deep` for Code Signing (Apple Discouraged)

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/sign-all.sh:74`  
**Additional File**: `/Users/proth/repos/kmflow/agent/macos/scripts/build-app-bundle.sh:346`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# sign-all.sh:73-80
codesign \
    --deep \
    --force \
    --sign "$IDENTITY" \
    --options runtime \
    --entitlements "$ENTITLEMENTS_PATH" \
    --timestamp \
    "$APP_PATH"

# build-app-bundle.sh:345-350
codesign \
    --force \
    --deep \
    --sign "$CODESIGN_IDENTITY" \
    --timestamp \
    --entitlements "${RESOURCES}/KMFlowAgent.entitlements" \
    "$APP_BUNDLE"
```
**Description**: Both `sign-all.sh` and `build-app-bundle.sh` use the `--deep` flag when signing the `.app` bundle. Apple's official documentation (TN3127) explicitly discourages `--deep` for production signing because it applies the same signing options and entitlements to all nested code, which may not be appropriate (e.g., frameworks should not receive the app's full entitlements). The scripts do sign nested binaries individually first (which is correct), but then `--deep` re-signs them with the app's entitlements.
**Risk**: The `--deep` flag applies the main app's entitlements (including `com.apple.security.automation.apple-events` and `com.apple.security.network.client`) to the embedded Python interpreter and all .so/.dylib files. This over-grants entitlements to nested code. It can also mask signing problems in nested components because `--deep` will re-sign everything regardless of the individual component's state.
**Recommendation**: Remove `--deep` from both `sign-all.sh` and `build-app-bundle.sh`. The scripts already sign nested components individually (correct approach). After individual signing, sign only the top-level `.app` bundle without `--deep`. Nested frameworks should have minimal or no entitlements.

---

### [HIGH] H4: PKG Installer Uses Same Identity for App Signing and Package Signing

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/pkg/build-pkg.sh:16,114-117`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# build-pkg.sh:16
IDENTITY="${KMFLOW_CODESIGN_IDENTITY:--}"

# build-pkg.sh:114-117
productsign \
    --sign "$IDENTITY" \
    "$UNSIGNED_PKG" \
    "$SIGNED_PKG"
```
**Description**: The PKG installer is signed using `productsign` with the same `KMFLOW_CODESIGN_IDENTITY` environment variable used for app code signing. However, `productsign` requires a "Developer ID Installer" certificate, which is a different certificate type than the "Developer ID Application" certificate used by `codesign`. Using the wrong certificate type will cause `productsign` to fail, or worse, if ad-hoc identity (`-`) is used, the PKG will be unsigned.
**Risk**: If the same application signing identity is passed to `productsign`, the PKG will either fail to sign (error) or be signed with the wrong certificate type. MDM systems (Jamf, Intune) validate PKG signatures and will reject improperly signed packages. An unsigned PKG distributed via MDM could be tampered with in transit.
**Recommendation**: (1) Add a separate environment variable `KMFLOW_INSTALLER_IDENTITY` for the "Developer ID Installer" certificate. (2) Validate that the installer identity is of the correct type. (3) In `release.sh`, pass the installer identity separately to `build-pkg.sh`.

---

### [HIGH] H5: Downloaded Python Tarball Not Hash-Verified

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/embed-python.sh:130-150`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# embed-python.sh:140-147
if [[ -f "$cached" ]]; then
    log "Cache hit: ${cached}"
else
    log "Downloading: ${url}"
    curl -fL --progress-bar --output "$cached" "$url" \
        || { rm -f "$cached"; die "Download failed for ${url}"; }
    log "Saved to cache: ${cached}"
fi
```
**Description**: The python-build-standalone tarball is downloaded from GitHub Releases via HTTPS and cached locally, but its SHA-256 hash is never verified. The cache check only tests file existence, not integrity. python-build-standalone publishes SHA-256 checksums with every release, but they are not fetched or checked.
**Risk**: A man-in-the-middle attack (e.g., on a compromised CI runner network), a cache poisoning attack (replacing the cached tarball on disk), or a GitHub CDN compromise could substitute a trojanized Python interpreter. This interpreter would then be embedded in the signed `.app` bundle and receive a valid Developer ID signature.
**Recommendation**: (1) Hardcode the expected SHA-256 hash for each pinned release in the script (e.g., `EXPECTED_SHA256_ARM64="abc123..."`). (2) After download, compute `shasum -a 256 "$cached"` and compare to the expected hash. (3) On cache hit, also verify the hash to detect cache corruption/tampering.

---

### [HIGH] H6: Apple Notarization Credentials Passed as Environment Variables, Not Keychain Profile

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/notarize.sh:68-72`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# notarize.sh:24-25
TEAM_ID="${TEAM_ID:?TEAM_ID environment variable is required for notarization}"
APP_PASSWORD="${APP_PASSWORD:?APP_PASSWORD environment variable is required for notarization}"

# notarize.sh:68-72
xcrun notarytool submit "$ZIP_PATH" \
    --apple-id  "$APPLE_ID" \
    --team-id   "$TEAM_ID" \
    --password  "$APP_PASSWORD" \
    --wait
```
**Description**: The Apple ID app-specific password is passed via the `APP_PASSWORD` environment variable and then to `notarytool` via the `--password` flag on the command line. This means the password appears in process listings (`ps aux`), may be logged by shell history, and is visible in CI/CD build logs unless explicitly masked. Apple's recommended approach is to use `notarytool store-credentials` to save a Keychain profile and then reference it via `--keychain-profile`.
**Risk**: The app-specific password could leak via process listing, CI build logs, or shell history on the build machine. An attacker with this password could submit malicious binaries for notarization under the organization's Apple Developer account, obtaining legitimate Apple notarization tickets for malware.
**Recommendation**: (1) Use `xcrun notarytool store-credentials "KMFlow-Notarize" --apple-id ... --team-id ... --password ...` to store credentials in the Keychain during CI setup. (2) Replace `--password "$APP_PASSWORD"` with `--keychain-profile "KMFlow-Notarize"`. (3) In CI, use the GitHub Actions Keychain setup that already exists in `agent-release.yml` and store the notarization profile there.

---

## MEDIUM Findings

### [MEDIUM] M1: Verification Script Does Not Check Hardened Runtime Flag

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/verify-signing.sh`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# verify-signing.sh:47-52 (entire Check 1)
echo "--- Check 1: Bundle deep signature ---"
if codesign -vvv --deep --strict "$APP_PATH" 2>&1; then
    check_result "Bundle signature (deep + strict)" "PASS"
else
    check_result "Bundle signature (deep + strict)" "FAIL" "codesign returned non-zero"
fi
```
**Description**: The verification script checks that the bundle has a valid signature and verifies entitlement safety flags, but it does not explicitly verify that Hardened Runtime is enabled. The `codesign -vvv` output includes flags like `flags=0x10000(runtime)` when Hardened Runtime is active, but the script does not parse or assert this. It also does not verify the Team ID matches an expected value, and does not check that a notarization ticket is stapled (only relies on `spctl` which may pass for different reasons).
**Risk**: A build could pass all verification checks despite lacking Hardened Runtime (which would cause notarization rejection), having the wrong Team ID (which would fail MDM TCC profile matching), or missing the notarization ticket (which would fail offline Gatekeeper assessment).
**Recommendation**: Add three new checks: (1) Parse `codesign -d --verbose=4` output for `flags=0x10000(runtime)` to verify Hardened Runtime. (2) Parse `codesign -d --verbose=2` output for `TeamIdentifier=` and compare to an expected value. (3) Run `xcrun stapler validate "$APP_PATH"` to verify the notarization ticket is stapled.

---

### [MEDIUM] M2: DMG Signing Lacks `--timestamp` and Hardened Runtime Flags

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/dmg/build-dmg.sh:112`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# build-dmg.sh:112
codesign --sign "$IDENTITY" "$DMG_PATH"
```
**Description**: The DMG is signed with a bare `codesign --sign` without `--timestamp` or `--force`. The `--timestamp` flag is required for notarization (it contacts Apple's timestamping server to prove the signing time). Without it, the DMG signature will be rejected by the notary service. The `--force` flag is used elsewhere but not here, so re-signing a DMG would fail.
**Risk**: DMG files submitted for notarization will be rejected by Apple's notary service due to the missing timestamp. If distributed without notarization, the DMG will be quarantined by Gatekeeper on download.
**Recommendation**: Change to `codesign --force --sign "$IDENTITY" --timestamp "$DMG_PATH"`.

---

### [MEDIUM] M3: PKG Installer postinstall Script Not Signed

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/pkg/scripts/postinstall`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# postinstall:1-4
#!/bin/bash
# postinstall — KMFlow Agent PKG post-installation script.
# Runs as root after the payload has been installed to the target volume.

# postinstall:91-93
launchctl bootstrap "gui/${CONSOLE_UID}" "$PLIST_DEST" \
    && echo "  LaunchAgent loaded for uid ${CONSOLE_UID}." \
    || echo "  WARNING: launchctl bootstrap returned non-zero..."
```
**Description**: The `postinstall` script runs as root and performs sensitive operations (creating directories with specific permissions, loading a LaunchAgent into the user session). While the script itself is included in the signed PKG, the individual script file has no independent signature. More importantly, the script's content is not validated before execution -- if the PKG payload is tampered with before signing (or if the PKG is unsigned due to ad-hoc identity), the postinstall script could be modified to execute arbitrary code as root.
**Risk**: If the PKG is distributed unsigned (see C1, H4), the postinstall script could be modified in transit to install malware that runs as root. Even with a signed PKG, the postinstall script's execution as root with `launchctl bootstrap` provides a privilege escalation path if the script logic is exploitable.
**Recommendation**: (1) Ensure the PKG is always signed with a valid "Developer ID Installer" certificate (fixes the unsigned distribution risk). (2) Consider hardcoding expected paths and values in the postinstall script rather than computing them dynamically. (3) Add integrity verification of the installed .app bundle in the postinstall script before loading the LaunchAgent.

---

### [MEDIUM] M4: `--force` Flag Used in All Signing Operations

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/sign-all.sh:57,75`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# sign-all.sh:56-60 (nested binaries)
codesign \
    --force \
    --sign "$IDENTITY" \
    --timestamp \
    "$BINARY"

# sign-all.sh:73-80 (.app bundle)
codesign \
    --deep \
    --force \
    --sign "$IDENTITY" \
    --options runtime \
    --entitlements "$ENTITLEMENTS_PATH" \
    --timestamp \
    "$APP_PATH"
```
**Description**: The `--force` flag is used in every codesign invocation across all scripts (`sign-all.sh`, `build-app-bundle.sh`, `embed-python.sh`). This flag replaces any existing code signature without warning. In a normal build pipeline this is expected, but it means there is no safeguard against accidentally re-signing a previously notarized bundle, which would invalidate the notarization ticket.
**Risk**: If `sign-all.sh` is run after notarization (e.g., due to a script ordering error), `--force` will silently replace the notarized signature, invalidating the stapled ticket. The resulting binary would appear signed but fail Gatekeeper assessment. This is particularly risky because `release.sh` runs signing (Step 3) before notarization (Step 5), but nothing prevents running `sign-all.sh` again manually.
**Recommendation**: (1) Add a guard at the top of `sign-all.sh` that checks if the bundle is already notarized (via `stapler validate`) and refuses to re-sign unless `--force-resign` is explicitly passed. (2) In `release.sh`, add a comment or assertion that signing must not occur after notarization.

---

### [MEDIUM] M5: App Sandbox Disabled -- Entitlements Allow Full System Access

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/KMFlowAgent.entitlements:24-25`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```xml
<!-- KMFlowAgent.entitlements:24-25 -->
<key>com.apple.security.app-sandbox</key>
<false/>
```
**Description**: The App Sandbox is explicitly disabled. Combined with the Accessibility API entitlement (`com.apple.security.automation.apple-events`), network access (`com.apple.security.network.client`), and file read-write access (`com.apple.security.files.user-selected.read-write`), the agent has effectively unrestricted access to the system. While this may be architecturally necessary for a task mining agent that observes user activity, the lack of sandboxing means a vulnerability in the agent (e.g., in the Python layer) gives an attacker full user-level access.
**Risk**: Any code execution vulnerability in the agent's Python layer, HTTP client, or dependency chain provides full access to the user's session, file system, network, and all accessibility events. Without sandboxing, the blast radius of a compromise is the entire user environment.
**Recommendation**: This may be an intentional design decision given the agent's requirements. Document the security rationale. Consider implementing application-level sandboxing within the Python layer (e.g., restricting file access to specific directories, network access to specific endpoints). Ensure the integrity manifest (`integrity.json`) is cryptographically validated at startup to detect Python layer tampering.

---

## LOW Findings

### [LOW] L1: No CI/CD Gate Prevents Unsigned Release Artifacts from Being Published

**File**: `/Users/proth/repos/kmflow/.github/workflows/agent-release.yml:58,90`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```yaml
# agent-release.yml:58
- name: Import signing certificate
  if: env.MACOS_CERT_P12 != ''

# agent-release.yml:90
KMFLOW_CODESIGN_IDENTITY: ${{ env.KMFLOW_CODESIGN_IDENTITY || '-' }}
```
**Description**: The CI pipeline conditionally imports the signing certificate (`if: env.MACOS_CERT_P12 != ''`), and if the secret is not configured, `KMFLOW_CODESIGN_IDENTITY` defaults to `'-'` (ad-hoc). The build and release steps proceed regardless, and artifacts are uploaded and a GitHub Release is created even with ad-hoc signing. There is no gate that fails the pipeline if signing credentials are missing.
**Risk**: A GitHub Release could be created with ad-hoc signed artifacts. Users or automation downloading from the Release page would receive unsigned binaries.
**Recommendation**: Add a verification step after `Build release` that checks the signing identity is not `"-"` and that `spctl --assess` passes on the built artifacts. Fail the workflow if verification fails.

---

### [LOW] L2: Checksums File Not GPG-Signed by Default

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/checksums.sh:50-55`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# checksums.sh:50-55
# Optional GPG signature
if [ -n "${GPG_KEY_ID:-}" ]; then
    echo ""
    echo "Signing checksums with GPG key $GPG_KEY_ID..."
    gpg --default-key "$GPG_KEY_ID" --detach-sign --armor SHA256SUMS
    echo "GPG signature: $CHECKSUMS_FILE.asc"
fi
```
**Description**: GPG signing of the SHA256SUMS file is optional and requires `GPG_KEY_ID` to be set. In the CI pipeline, there is no step that sets `GPG_KEY_ID`, so checksums will never be GPG-signed in automated releases.
**Risk**: Without a GPG signature, the SHA256SUMS file can be modified by an attacker who compromises the GitHub Release page or CDN. An attacker could replace both the artifacts and the checksums file, and the `shasum -a 256 -c SHA256SUMS` verification recommended in the release notes would pass.
**Recommendation**: Configure GPG signing in CI by adding a GPG key secret and setting `GPG_KEY_ID`. Alternatively, consider using `cosign` (sigstore) for keyless signing of release artifacts.

---

### [LOW] L3: Notarization Credentials Echoed to Build Log

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/notarize.sh:40-41`
**Agent**: F1 (Code Signing & Notarization Auditor)
**Evidence**:
```bash
# notarize.sh:38-42
echo "=== KMFlow Agent Notarization ==="
echo "  App:     $APP_PATH"
echo "  Apple ID: $APPLE_ID"
echo "  Team ID:  $TEAM_ID"
echo "  Zip:      $ZIP_PATH"
```
**Description**: The Apple ID and Team ID are echoed to stdout at the start of the notarization script. While these are not secrets per se (Team ID is embedded in every signed binary), the Apple ID email address is PII and its exposure in CI logs could be used for phishing or social engineering attacks against the Apple Developer account.
**Risk**: Minor information disclosure. The Apple ID email could be harvested from public CI logs and used for targeted phishing.
**Recommendation**: Mask the Apple ID in log output (e.g., show only the domain: `p****@example.com`). In GitHub Actions, the secrets are automatically masked, but if logs are exported or the script is run locally, the full email is visible.

---

## Security Checklist Status

| Check | Status | Notes |
|-------|--------|-------|
| No hardcoded secrets | PASS | All credentials via environment variables |
| Signing identity validated | FAIL | No Keychain validation; defaults to ad-hoc |
| `--timestamp` on all signs | FAIL | Missing from DMG, embed-python.sh |
| `--options runtime` on all signs | FAIL | Missing from embed-python.sh framework signing |
| `--deep` avoided | FAIL | Used in sign-all.sh and build-app-bundle.sh |
| Notarization result verified | FAIL | No status parsing after notarytool submit |
| Notarization ticket stapled | PASS | `xcrun stapler staple` is called |
| Stapled ticket verified | FAIL | No `stapler validate` in verify-signing.sh |
| Hardened Runtime verified | FAIL | Not checked in verify-signing.sh |
| Team ID verified | FAIL | Not checked in verify-signing.sh |
| PKG uses installer identity | FAIL | Uses same app signing identity |
| DMG properly signed | PARTIAL | Signed but missing --timestamp |
| postinstall scripts integrity | PARTIAL | Protected by PKG signature, but PKG may be unsigned |
| Supply chain hashes verified | FAIL | No --require-hashes, no pinned versions |
| Downloaded Python hash verified | FAIL | No SHA-256 verification of tarball |
| Build pipeline gated | FAIL | Can produce unsigned release artifacts |
| Checksums cryptographically signed | FAIL | GPG signing optional and not configured in CI |
| Entitlements appropriate | PASS | Dangerous entitlements disabled; sandbox off (documented) |

---

## Risk Assessment

**Overall Security Score: 4/10**

The pipeline has good structural foundations (ordered build stages, integrity manifest, individual component signing, entitlements verification), but lacks critical validation gates that prevent unsigned, un-notarized, or supply-chain-compromised artifacts from being distributed. For an MDM-deployed enterprise agent with Accessibility API access, these gaps represent significant risk.

**Priority Remediation Order:**
1. C4 (supply chain hashes) -- highest blast radius
2. C1 (ad-hoc signing default) -- blocks enterprise deployment
3. C2 (silent notarization skip) -- blocks enterprise deployment
4. H5 (Python tarball hash verification) -- supply chain risk
5. C3 (notarization result verification) -- can produce false positive release
6. H1 (Hardened Runtime on framework) -- notarization requirement
7. H2 (suppressed codesign errors) -- masks all other issues
8. H6 (credentials in env vars) -- credential exposure
9. H3 (`--deep` usage) -- over-granted entitlements
10. Remaining MEDIUM and LOW findings

---

*Report generated by F1 (Code Signing & Notarization Auditor) as part of the KMFlow macOS Agent comprehensive security audit.*
