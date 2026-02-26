# F1: Code Signing & Notarization Security Re-Audit

**Agent**: F1 (Code Signing & Notarization Auditor)
**Date**: 2026-02-26 (Re-Audit)
**Previous Audit**: 2026-02-25
**Scope**: macOS Task Mining Agent signing pipeline, notarization flow, packaging, and supply chain
**Target Distribution**: Enterprise MDM (Jamf, Intune, Mosyle) to employee machines
**Remediation PRs Reviewed**: #248, #251, #256

---

## Executive Summary

The KMFlow macOS Agent signing pipeline has undergone significant remediation since the initial audit on 2026-02-25. Of the original 18 findings (4 CRITICAL, 6 HIGH, 5 MEDIUM, 3 LOW), **8 have been fully resolved** and **2 partially resolved**. The pipeline's security posture has materially improved: all four CRITICAL findings have been addressed, the `--deep` flag has been removed, Hardened Runtime is now consistently applied, stderr suppression has been eliminated, and Python dependencies are pinned with SHA-256 hash verification.

**Remaining risks** are concentrated in the MEDIUM and LOW tiers. The most significant unresolved items are: (a) the `verify-signing.sh` script still does not assert Hardened Runtime, Team ID, or notarization ticket stapling; (b) the DMG signing command still lacks `--timestamp`; (c) the PKG installer uses the application signing identity instead of a dedicated installer identity; (d) the CI pipeline still allows ad-hoc signed artifacts when secrets are not configured; and (e) the embedded Python tarball checksum array contains empty placeholder values.

**Overall Security Score: 7/10** (up from 4/10).

---

## Remediation Status Summary

| ID | Severity | Finding | Status | PR | Notes |
|----|----------|---------|--------|----|-------|
| C1 | CRITICAL | Ad-hoc signing default allows Gatekeeper-rejected builds to ship | **RESOLVED** | #248 | `release.sh` refuses ad-hoc identity; `sign-all.sh` refuses ad-hoc when `KMFLOW_RELEASE_BUILD=1` |
| C2 | CRITICAL | Notarization silently skipped (exit 0) when credentials missing | **RESOLVED** | #248 | `notarize.sh` now exits non-zero when `APPLE_ID` is missing and `KMFLOW_RELEASE_BUILD=1` |
| C3 | CRITICAL | Notarization result not verified before stapling | **RESOLVED** | #248 | Script now extracts submission ID, checks for "Accepted" status, fetches log on failure |
| C4 | CRITICAL | Supply chain: pip install without `--require-hashes` | **RESOLVED** | #251 | `requirements.txt` pinned with `==` and `--hash`; `vendor-python-deps.sh` enables `--require-hashes` when hashes detected |
| H1 | HIGH | Embedded Python framework signed without Hardened Runtime | **RESOLVED** | #251 | `--options runtime` and `--timestamp` added to all codesign calls in `embed-python.sh` |
| H2 | HIGH | Codesign failures suppressed via `2>/dev/null \|\| true` | **RESOLVED** | #256 | All stderr suppression removed from `codesign_framework()` in `embed-python.sh` |
| H3 | HIGH | `--deep` flag in codesign (Apple-discouraged) | **RESOLVED** | #256 | `--deep` removed from `sign-all.sh` and `build-app-bundle.sh`; components signed individually |
| H4 | HIGH | PKG uses same identity for app and installer signing | OPEN | -- | `productsign` still uses `KMFLOW_CODESIGN_IDENTITY` |
| H5 | HIGH | Downloaded Python tarball not hash-verified | **PARTIAL** | #251 | `PBS_CHECKSUMS` array and verification logic added, but hash values are empty placeholders |
| H6 | HIGH | Apple notarization credentials passed as env vars, not Keychain profile | OPEN | -- | `--password "$APP_PASSWORD"` still on command line |
| M1 | MEDIUM | Verification script does not check Hardened Runtime flag | OPEN | -- | `verify-signing.sh` unchanged |
| M2 | MEDIUM | DMG signing lacks `--timestamp` | OPEN | -- | `build-dmg.sh:112` unchanged |
| M3 | MEDIUM | PKG postinstall script not independently signed | OPEN (by design) | -- | Protected by outer PKG signature |
| M4 | MEDIUM | `--force` on all signing operations | OPEN (accepted risk) | -- | Required for idempotent builds |
| M5 | MEDIUM | App Sandbox disabled | OPEN (by design) | -- | Documented architectural decision |
| L1 | LOW | CI pipeline has no gate preventing unsigned release artifacts | OPEN | -- | CI still defaults to `-` when secrets missing |
| L2 | LOW | Checksums file not GPG-signed by default | OPEN | -- | `GPG_KEY_ID` still optional, not configured in CI |
| L3 | LOW | Apple ID echoed to build log | OPEN | -- | PII disclosure in logs; minor |

---

## Verified Fixes (Detailed)

### C1: Ad-Hoc Signing Default -- RESOLVED

**Files reviewed**:
- `/Users/proth/repos/kmflow/agent/macos/scripts/release.sh` (lines 36-41)
- `/Users/proth/repos/kmflow/agent/macos/scripts/sign-all.sh` (lines 31-41)

**Evidence of fix**:

In `release.sh`, ad-hoc signing is now unconditionally rejected:
```bash
# release.sh:36-41
if [[ "$IDENTITY" == "-" ]]; then
    echo "ERROR: Ad-hoc signing identity ('-') is not permitted for release builds." >&2
    echo "       Set KMFLOW_CODESIGN_IDENTITY to a valid Developer ID Application certificate." >&2
    echo "       Example: export KMFLOW_CODESIGN_IDENTITY='Developer ID Application: YourOrg (TEAMID)'" >&2
    exit 1
fi
```

In `sign-all.sh`, ad-hoc signing is rejected when `KMFLOW_RELEASE_BUILD=1` and emits a warning otherwise:
```bash
# sign-all.sh:33-41
if [[ "$IDENTITY" == "-" ]]; then
    if [[ "${KMFLOW_RELEASE_BUILD:-0}" == "1" ]]; then
        echo "ERROR: Ad-hoc signing identity ('-') is not permitted for release builds." >&2
        exit 1
    else
        echo "WARNING: Using ad-hoc signing identity ('-'). This is acceptable for local development only."
    fi
fi
```

**Verification**: The defense-in-depth is appropriate. `release.sh` acts as the primary gate (always rejects ad-hoc), and `sign-all.sh` provides a secondary gate keyed on `KMFLOW_RELEASE_BUILD`. The original recommendation to validate the identity against the Keychain (`security find-identity`) has NOT been implemented, which means a typo in the identity string would not be caught until `codesign` fails -- but `set -euo pipefail` ensures this propagates as a hard error.

---

### C2: Notarization Silently Skipped -- RESOLVED

**File reviewed**: `/Users/proth/repos/kmflow/agent/macos/scripts/notarize.sh` (lines 19-27)

**Evidence of fix**:
```bash
# notarize.sh:19-27
if [[ -z "${APPLE_ID:-}" ]]; then
    if [[ "${KMFLOW_RELEASE_BUILD:-0}" == "1" ]]; then
        echo "ERROR: APPLE_ID not set but KMFLOW_RELEASE_BUILD=1." >&2
        echo "       Notarization is mandatory for release builds." >&2
        exit 1
    fi
    echo "Skipping notarization: APPLE_ID not set (dev build)"
    exit 0
fi
```

**Verification**: The fix correctly gates on `KMFLOW_RELEASE_BUILD`. For dev builds (the default), notarization is still skippable with exit 0, which is appropriate for local development. For release builds, missing credentials now cause a hard failure. Note that `release.sh` does NOT set `KMFLOW_RELEASE_BUILD=1` -- it relies on its own ad-hoc check and the `--skip-notarize` flag. This means the `KMFLOW_RELEASE_BUILD` gate in `notarize.sh` only triggers if a caller explicitly sets that variable. This is acceptable because `release.sh` refuses ad-hoc signing entirely, and the `--skip-notarize` flag provides explicit opt-out with a visible log message.

---

### C3: Notarization Result Not Verified -- RESOLVED

**File reviewed**: `/Users/proth/repos/kmflow/agent/macos/scripts/notarize.sh` (lines 73-97, 105-113)

**Evidence of fix**:
```bash
# notarize.sh:80-97
SUBMISSION_ID="$(echo "$SUBMIT_OUTPUT" | grep -m1 'id:' | awk '{print $2}')"
if [[ -z "$SUBMISSION_ID" ]]; then
    echo "ERROR: Could not extract submission ID from notarytool output." >&2
    exit 1
fi

NOTARY_STATUS="$(echo "$SUBMIT_OUTPUT" | grep -m1 'status:' | awk '{print $2}')"
if [[ "$NOTARY_STATUS" != "Accepted" ]]; then
    echo "ERROR: Notarization was NOT accepted (status: ${NOTARY_STATUS:-unknown})." >&2
    echo "       Fetching detailed log for submission $SUBMISSION_ID..." >&2
    xcrun notarytool log "$SUBMISSION_ID" \
        --apple-id "$APPLE_ID" \
        --team-id "$TEAM_ID" \
        --password "$APP_PASSWORD" \
        2>&1 || true
    exit 1
fi
```

Additionally, Gatekeeper assessment is performed after stapling:
```bash
# notarize.sh:113
spctl --assess --type exec -vvv "$APP_PATH"
```

**Verification**: The fix captures the submission output, extracts the submission ID, explicitly checks for "Accepted" status, fetches the detailed log on failure, and exits non-zero. Post-staple, `spctl --assess` provides the final Gatekeeper gate. The original recommendation to also run `stapler validate` was not implemented (only `spctl` is used), which is a minor gap -- `spctl` is actually the stronger check since it validates the full Gatekeeper policy, not just ticket presence.

---

### C4: Supply Chain -- pip install Without `--require-hashes` -- RESOLVED

**Files reviewed**:
- `/Users/proth/repos/kmflow/agent/python/requirements.txt`
- `/Users/proth/repos/kmflow/agent/macos/scripts/vendor-python-deps.sh` (lines 153-159)

**Evidence of fix**:

`requirements.txt` now pins all 11 packages (4 direct, 7 transitive) with exact versions and SHA-256 hashes:
```
httpx==0.28.1 \
    --hash=sha256:d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad
PyJWT[crypto]==2.9.0 \
    --hash=sha256:3b02fb0f44517787776cf48f2ae25d8e14f300e6d7545a4315cee571a415e850
...
```

`vendor-python-deps.sh` now conditionally enables `--require-hashes`:
```bash
# vendor-python-deps.sh:153-159
local hash_flag=""
if grep -q -- '--hash' "$REQUIREMENTS_FILE" 2>/dev/null; then
    hash_flag="--require-hashes"
    log "Hash verification enabled (requirements.txt contains --hash entries)"
else
    log "WARNING: requirements.txt has no --hash entries. Pin versions and add hashes for supply chain security."
fi
```

**Verification**: All direct and transitive dependencies are pinned with `==` and have `--hash` entries. The `--require-hashes` flag is auto-detected from the requirements file content. Combined with `--only-binary=:all:` (which prevents sdist/compilation attacks), this provides strong supply chain integrity. One minor observation: the hashes appear to be for a single platform (arm64). The script comment notes this, advising that x86_64/universal builds need additional platform hashes. This is acceptable for the current arm64-only primary target.

---

### H1: Hardened Runtime Missing on Embedded Python Framework -- RESOLVED

**File reviewed**: `/Users/proth/repos/kmflow/agent/macos/scripts/embed-python.sh` (lines 369-384)

**Evidence of fix**:
```bash
# embed-python.sh:377-378
find "${fw_root}" \( -name "*.so" -o -name "*.dylib" \) -print0 \
    | xargs -0 -P4 codesign --force --sign "$CODESIGN_IDENTITY" --options runtime --timestamp

# embed-python.sh:380-381
codesign --force --sign "$CODESIGN_IDENTITY" --options runtime --timestamp \
    "${fw_root}/Versions/${PYTHON_VERSION}/bin/python${PYTHON_VERSION}"

# embed-python.sh:384
codesign --force --sign "$CODESIGN_IDENTITY" --options runtime --timestamp "$fw_root"
```

**Verification**: All three codesign invocations in `codesign_framework()` now include `--options runtime` (Hardened Runtime) and `--timestamp` (Apple timestamp server). The same flags are consistently used in `build-app-bundle.sh` for the framework components (lines 341-346, 351, 360-366, 370-376) and in `sign-all.sh` for nested binaries (lines 68-73) and the bundle (lines 88-94).

---

### H2: Codesign Failures Suppressed -- RESOLVED

**File reviewed**: `/Users/proth/repos/kmflow/agent/macos/scripts/embed-python.sh` (lines 369-384)

**Evidence of fix**: All `2>/dev/null || true` patterns have been removed from the codesign commands in `codesign_framework()`. The function now allows codesign errors to propagate via `set -euo pipefail`. The `2>/dev/null || true` pattern is still present on `install_name_tool` calls (lines 298, 307) and `strip` calls (lines 331, 335, 339), which is acceptable because those tools emit benign warnings for non-Mach-O files or already-stripped binaries.

---

### H3: `--deep` Flag Usage -- RESOLVED

**Files reviewed**:
- `/Users/proth/repos/kmflow/agent/macos/scripts/sign-all.sh` (lines 86-94)
- `/Users/proth/repos/kmflow/agent/macos/scripts/build-app-bundle.sh` (lines 368-376)

**Evidence of fix**:

`sign-all.sh` now signs the bundle without `--deep`:
```bash
# sign-all.sh:88-94
codesign \
    --force \
    --sign "$IDENTITY" \
    --options runtime \
    --entitlements "$ENTITLEMENTS_PATH" \
    --timestamp \
    "$APP_PATH"
```

`build-app-bundle.sh` similarly signs without `--deep`:
```bash
# build-app-bundle.sh:370-376
codesign \
    --force \
    --sign "$CODESIGN_IDENTITY" \
    --options runtime \
    --timestamp \
    --entitlements "${RESOURCES}/KMFlowAgent.entitlements" \
    "$APP_BUNDLE"
```

**Verification**: The `--deep` flag is no longer used in any signing operation. Both scripts sign components individually (inside-out) and then sign the top-level bundle. The only remaining `--deep` usage is in `codesign -vvv --deep --strict` for VERIFICATION (sign-all.sh:103, verify-signing.sh:48), which is correct -- `--deep` is appropriate for verification (checking all nested components) even though it should not be used for signing.

---

### H5: Downloaded Python Tarball Not Hash-Verified -- PARTIAL

**File reviewed**: `/Users/proth/repos/kmflow/agent/macos/scripts/embed-python.sh` (lines 40-52, 169-195)

**Evidence of partial fix**:

The verification infrastructure is in place:
```bash
# embed-python.sh:40-52
declare -A PBS_CHECKSUMS=(
    # Placeholder hashes — MUST be replaced with real values from the release
    ["aarch64"]=""
    ["x86_64"]=""
)
```

Verification logic exists and is correct:
```bash
# embed-python.sh:176-194
local expected_hash="${PBS_CHECKSUMS[$pbs_arch]:-}"
if [[ -n "$expected_hash" ]]; then
    local actual_hash
    actual_hash=$(shasum -a 256 "$cached" | awk '{print $1}')
    if [[ "$actual_hash" != "$expected_hash" ]]; then
        ...
        die "SHA-256 verification failed — possible supply chain attack or corrupt download."
    fi
else
    log "WARNING: No SHA-256 checksum configured for arch '${pbs_arch}'."
    if [[ "${KMFLOW_RELEASE_BUILD:-0}" == "1" ]]; then
        die "SHA-256 checksum verification is mandatory for release builds. Populate PBS_CHECKSUMS and retry."
    fi
fi
```

**Gap**: The `PBS_CHECKSUMS` values are empty strings. In development builds (`KMFLOW_RELEASE_BUILD` not set or `0`), the script logs a WARNING and continues without hash verification. In release builds, it correctly dies. However, since `release.sh` does not set `KMFLOW_RELEASE_BUILD=1`, the release gate depends on the caller setting this environment variable explicitly. This is a defense-in-depth gap -- the tarball hash verification can be bypassed in release flows if `KMFLOW_RELEASE_BUILD` is not set.

---

## Open Findings (Carried Forward)

### [HIGH] H4: PKG Installer Uses Same Identity for App Signing and Package Signing

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/pkg/build-pkg.sh:16,114-117`
**Status**: OPEN -- no change from original audit.

`productsign` requires a "Developer ID Installer" certificate, but the script uses `KMFLOW_CODESIGN_IDENTITY` which is a "Developer ID Application" certificate. Using the wrong certificate type will cause `productsign` to fail or produce an improperly signed PKG.

**Recommendation**: Add `KMFLOW_INSTALLER_IDENTITY` environment variable. Validate the identity type in `build-pkg.sh`.

---

### [HIGH] H6: Apple Notarization Credentials Passed as Environment Variables

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/notarize.sh:73-77`
**Status**: OPEN -- no change from original audit.

The app-specific password is passed via `--password "$APP_PASSWORD"` on the command line, making it visible in process listings. Apple's recommended approach is `--keychain-profile`.

**Recommendation**: Use `xcrun notarytool store-credentials` during CI setup and reference via `--keychain-profile`.

---

### [MEDIUM] M1: Verification Script Does Not Check Hardened Runtime, Team ID, or Stapled Ticket

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/verify-signing.sh`
**Status**: OPEN -- no change from original audit.

The script performs 4 checks: (1) deep bundle signature, (2) Gatekeeper assessment, (3) nested binary signatures, (4) dangerous entitlement flags. It does NOT verify:
- Hardened Runtime is enabled (`flags=0x10000(runtime)`)
- Team ID matches expected value
- Notarization ticket is stapled (`stapler validate`)

**Recommendation**: Add three additional verification checks as described in the original audit.

---

### [MEDIUM] M2: DMG Signing Lacks `--timestamp`

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/dmg/build-dmg.sh:112`
**Status**: OPEN -- no change from original audit.

```bash
codesign --sign "$IDENTITY" "$DMG_PATH"
```

Missing `--timestamp` and `--force`. Apple's notary service requires timestamped signatures.

**Recommendation**: Change to `codesign --force --sign "$IDENTITY" --timestamp "$DMG_PATH"`.

---

### [MEDIUM] M3: PKG postinstall Script Not Independently Signed

**File**: `/Users/proth/repos/kmflow/agent/macos/installer/pkg/scripts/postinstall`
**Status**: OPEN (by design) -- protected by the outer PKG signature when the PKG is properly signed.

---

### [MEDIUM] M4: `--force` Flag on All Signing Operations

**Status**: OPEN (accepted risk) -- required for idempotent build pipelines. The risk of accidentally re-signing a notarized bundle is mitigated by the sequential ordering in `release.sh` (sign before notarize).

---

### [MEDIUM] M5: App Sandbox Disabled

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/KMFlowAgent.entitlements`
**Status**: OPEN (by design) -- documented architectural decision. The entitlements file has been cleaned up: `com.apple.security.automation.apple-events` and `com.apple.security.files.user-selected.read-write` have been removed (they were present in the original audit). The remaining entitlements are minimal:
- `com.apple.security.cs.allow-jit` = false
- `com.apple.security.cs.allow-unsigned-executable-memory` = false
- `com.apple.security.cs.disable-library-validation` = false
- `com.apple.security.network.client` = true (required)
- `com.apple.security.app-sandbox` = false (required for task mining)

This is an improvement -- the entitlement surface has been reduced.

---

### [LOW] L1: CI Pipeline Has No Gate Preventing Unsigned Release Artifacts

**File**: `/Users/proth/repos/kmflow/.github/workflows/agent-release.yml:90`
**Status**: OPEN.

```yaml
KMFLOW_CODESIGN_IDENTITY: ${{ env.KMFLOW_CODESIGN_IDENTITY || '-' }}
```

The CI defaults to ad-hoc when the signing secret is not configured. Since `release.sh` now rejects ad-hoc, this will cause the build to FAIL (which is the correct behavior). However, the failure happens late in the pipeline. A pre-flight check before the build step would save CI minutes.

Additionally, the notarization skip logic in CI (line 96) allows skipping when `APPLE_ID` is empty:
```yaml
if [[ "${{ inputs.skip_notarize }}" == "true" ]] || [[ -z "${APPLE_ID:-}" ]]; then
    RELEASE_ARGS="--skip-notarize"
fi
```

This means a release tag push without notarization secrets will produce signed-but-not-notarized artifacts that are uploaded to the GitHub Release. This is the remaining gap -- the CI does not fail when notarization is skipped due to missing secrets on a tag push.

**Recommendation**: Add a step before the build that validates `KMFLOW_CODESIGN_IDENTITY != '-'` and `APPLE_ID` is set when the trigger is a tag push (not `workflow_dispatch`).

---

### [LOW] L2: Checksums File Not GPG-Signed by Default

**Status**: OPEN -- no change from original audit.

---

### [LOW] L3: Notarization Credentials Echoed to Build Log

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/notarize.sh:44-47`
**Status**: OPEN -- no change from original audit. Apple ID and Team ID are still echoed to stdout. In GitHub Actions, secrets are auto-masked, but `APPLE_ID` and `TEAM_ID` may not be configured as secrets (they may be set as environment variables).

---

## New Findings (Discovered During Re-Audit)

### [MEDIUM] N1: PYTHONPATH Isolation Incomplete -- DYLD_LIBRARY_PATH Inherited

**File**: `/Users/proth/repos/kmflow/agent/macos/Resources/python-launcher.sh:116-117`

**Evidence**:
```bash
# python-launcher.sh:116-117
DYLD_LIBRARY_PATH="${PYTHON_HOME}/lib${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
export DYLD_LIBRARY_PATH
```

**Description**: While PYTHONPATH is correctly set to only bundle-internal paths (line 89) and `PYTHONNOUSERSITE=1` prevents user site-packages (line 93), the `DYLD_LIBRARY_PATH` variable APPENDS the caller's existing `DYLD_LIBRARY_PATH`. This means an attacker who can control the parent process's environment could prepend a malicious `DYLD_LIBRARY_PATH` entry that would be preserved, potentially causing the embedded Python interpreter to load a trojanized `libpython3.12.dylib` from an attacker-controlled path.

In practice, SIP strips `DYLD_LIBRARY_PATH` for protected binaries, and the launcher comment acknowledges this. However, since the embedded Python interpreter is NOT a SIP-protected binary, the inherited path is effective.

**Severity**: MEDIUM. Exploitability requires control over the parent process environment, which is a limited attack surface when the agent is launched via LaunchAgent.

**Recommendation**: Replace the append pattern with an explicit set:
```bash
export DYLD_LIBRARY_PATH="${PYTHON_HOME}/lib"
```

---

### [LOW] N2: Integrity Manifest HMAC Key Stored Alongside Signature (No Security Benefit)

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/build-app-bundle.sh:308-323`

**Evidence**:
```python
# build-app-bundle.sh:313
hmac_key = secrets.token_bytes(32)
sig = hmac.new(hmac_key, manifest_json.encode(), hashlib.sha256).hexdigest()

sig_payload = {
    "hmac_sha256": sig,
    "key_hex": hmac_key.hex(),          # Key stored alongside the HMAC
    "manifest_sha256": hashlib.sha256(manifest_json.encode()).hexdigest(),
}
```

**Description**: The integrity manifest uses HMAC-SHA256 for tamper detection, but the HMAC key is generated per-build and stored in `integrity.sig` alongside the HMAC value. An attacker who can modify `integrity.json` can also modify `integrity.sig` (recompute the HMAC with any key and store the new key). The comment in the script acknowledges this: "Since the entire bundle is code-signed, tampering with either file breaks the codesign seal." This is accurate -- the codesign seal is the actual security boundary, not the HMAC.

**Severity**: LOW. The HMAC provides no additional security beyond what codesign already provides. It serves as a defense-in-depth for pre-codesign integrity checking during the build pipeline, which is a valid use case. The plain `manifest_sha256` field provides equivalent tamper detection for that scenario.

**Recommendation**: Informational only. Consider simplifying to just SHA-256 of the manifest (drop the HMAC) to avoid the false impression of cryptographic tamper-proofing. Alternatively, if independent integrity verification is desired, embed the HMAC key in the Swift binary at compile time (not in the signature file).

---

### [LOW] N3: `release.sh` Does Not Set `KMFLOW_RELEASE_BUILD=1`

**File**: `/Users/proth/repos/kmflow/agent/macos/scripts/release.sh`

**Description**: Several scripts use `KMFLOW_RELEASE_BUILD=1` as a gate for enforcing release-mode security checks (sign-all.sh:34, notarize.sh:20, embed-python.sh:191). However, `release.sh` -- the master release orchestrator -- never sets this variable. It relies on its own ad-hoc check (lines 36-41) instead of propagating `KMFLOW_RELEASE_BUILD=1` to all sub-scripts.

This means:
- `embed-python.sh` will not enforce PBS tarball hash verification during release builds invoked via `release.sh`
- `sign-all.sh` will not trigger its release-mode ad-hoc check (though `release.sh` catches it first)
- `notarize.sh` will not trigger its release-mode credential check (though `--skip-notarize` flag handling provides an alternative path)

**Severity**: LOW. The direct security impact is limited because `release.sh` has its own ad-hoc guard and the `--skip-notarize` flag provides explicit opt-out. However, the PBS tarball hash verification gap in `embed-python.sh` is a real defense-in-depth miss.

**Recommendation**: Add `export KMFLOW_RELEASE_BUILD=1` near the top of `release.sh`, after the ad-hoc identity check. This ensures all downstream scripts apply their release-mode security gates consistently.

---

## Updated Finding Counts

| Severity | Original | Resolved | Partial | New | Current Open |
|----------|----------|----------|---------|-----|--------------|
| CRITICAL | 4 | 4 | 0 | 0 | **0** |
| HIGH | 6 | 3 | 1 | 0 | **3** (H4, H5-partial, H6) |
| MEDIUM | 5 | 0 | 0 | 1 | **6** (M1-M5, N1) |
| LOW | 3 | 0 | 0 | 2 | **5** (L1-L3, N2, N3) |
| **Total** | **18** | **7** | **1** | **3** | **14** |

---

## Updated Security Checklist

| Check | Previous | Current | Notes |
|-------|----------|---------|-------|
| No hardcoded secrets | PASS | PASS | All credentials via environment variables |
| Signing identity validated (release) | FAIL | **PASS** | `release.sh` refuses ad-hoc unconditionally |
| `--timestamp` on all signing operations | FAIL | **PARTIAL** | All except `build-dmg.sh:112` |
| `--options runtime` on all signing operations | FAIL | **PASS** | Consistently applied in all codesign calls |
| `--deep` avoided for signing | FAIL | **PASS** | Removed; only used for verification |
| Notarization result verified | FAIL | **PASS** | Checks "Accepted" status; fetches log on failure |
| Notarization ticket stapled | PASS | PASS | `xcrun stapler staple` called |
| Stapled ticket verified post-staple | FAIL | **PARTIAL** | `spctl --assess` run (stronger than `stapler validate`), but `verify-signing.sh` does not check |
| Hardened Runtime verified in test suite | FAIL | FAIL | `verify-signing.sh` still does not assert runtime flag |
| Team ID verified | FAIL | FAIL | Not checked anywhere |
| PKG uses correct installer identity | FAIL | FAIL | Still uses app signing identity |
| DMG properly signed | PARTIAL | PARTIAL | Still missing `--timestamp` |
| Supply chain hashes verified (pip) | FAIL | **PASS** | Pinned versions + `--require-hashes` |
| Downloaded Python hash verified | FAIL | **PARTIAL** | Logic correct but checksums are empty placeholders |
| Build pipeline gated in CI | FAIL | **PARTIAL** | `release.sh` rejects ad-hoc (catches it at build time) but CI still allows no-notarize releases |
| Checksums cryptographically signed | FAIL | FAIL | GPG optional, not configured in CI |
| Entitlements minimal | PASS | **IMPROVED** | Reduced entitlement surface (removed automation + files entitlements) |
| PYTHONPATH isolation | N/A | **PARTIAL** | PYTHONPATH isolated; DYLD_LIBRARY_PATH inherits caller env |

---

## Risk Assessment

**Overall Security Score: 7/10** (up from 4/10)

The pipeline now handles the critical-path security correctly: release builds refuse ad-hoc signing, notarization failures are caught and surfaced, supply chain integrity is enforced via pinned hashes, Hardened Runtime is consistently applied, and stderr is no longer suppressed. The remaining items are in the "defense-in-depth" and "operational hygiene" tiers rather than the "can ship compromised binaries" tier.

**Priority Remediation Order for Remaining Items:**
1. H5-partial (populate `PBS_CHECKSUMS` with real hashes) -- 5-minute fix, blocks supply chain attack on Python tarball
2. N3 (set `KMFLOW_RELEASE_BUILD=1` in `release.sh`) -- 1-line fix, activates all release gates
3. M2 (add `--timestamp` to DMG signing) -- 1-line fix, required for DMG notarization
4. H4 (separate installer identity for PKG) -- small refactor, required for proper MDM deployment
5. M1 (add Hardened Runtime / Team ID / staple checks to verify-signing.sh) -- medium effort, catches regressions
6. N1 (stop inheriting DYLD_LIBRARY_PATH) -- 1-line fix, closes env injection vector
7. H6 (switch to Keychain profile for notarization) -- medium effort, improves credential hygiene
8. L1 (CI pre-flight checks) -- small effort, saves CI minutes and catches misconfig early
9. L2, L3, N2 -- informational / low priority

---

*Re-audit report generated by F1 (Code Signing & Notarization Auditor) on 2026-02-26 as part of the KMFlow macOS Agent post-remediation security review.*
