#!/bin/bash
# verify-signing.sh — Post-build verification of code signing and entitlements.
# Usage: verify-signing.sh <APP_PATH>
# Exits 1 if any check fails.

set -euo pipefail

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
APP_PATH="${1:?Usage: verify-signing.sh <APP_PATH>}"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if [[ ! -d "$APP_PATH" ]]; then
    echo "ERROR: APP_PATH does not exist or is not a directory: $APP_PATH" >&2
    exit 1
fi

echo "=== KMFlow Agent Signing Verification ==="
echo "  App: $APP_PATH"
echo ""

# Track overall pass/fail
PASS=0
FAIL=0

# Helper: record result and print it
check_result() {
    local label="$1"
    local status="$2"   # "PASS" or "FAIL"
    local detail="${3:-}"

    if [[ "$status" == "PASS" ]]; then
        echo "  [PASS] $label"
        (( PASS++ )) || true
    else
        echo "  [FAIL] $label${detail:+: $detail}"
        (( FAIL++ )) || true
    fi
}

# ---------------------------------------------------------------------------
# Check 1: Bundle deep signature is valid
# ---------------------------------------------------------------------------
echo "--- Check 1: Bundle deep signature ---"
if codesign -vvv --deep --strict "$APP_PATH" 2>&1; then
    check_result "Bundle signature (deep + strict)" "PASS"
else
    check_result "Bundle signature (deep + strict)" "FAIL" "codesign returned non-zero"
fi
echo ""

# ---------------------------------------------------------------------------
# Check 2: Gatekeeper assessment (only meaningful if notarized; may warn for ad-hoc)
# ---------------------------------------------------------------------------
echo "--- Check 2: Gatekeeper assessment ---"
if spctl --assess --type exec -vvv "$APP_PATH" 2>&1; then
    check_result "Gatekeeper assessment" "PASS"
else
    # spctl exits non-zero for ad-hoc signed apps — report as warning, not failure
    echo "  [WARN] Gatekeeper rejected the bundle (expected for ad-hoc / unsigned identity)."
    echo "         Run notarize.sh before shipping to end-users."
    check_result "Gatekeeper assessment (notarized)" "FAIL" "spctl returned non-zero (ad-hoc signing?)"
fi
echo ""

# ---------------------------------------------------------------------------
# Check 3: All .dylib and .so files are individually signed
# ---------------------------------------------------------------------------
echo "--- Check 3: Nested binary signatures ---"
UNSIGNED_COUNT=0
mapfile -t NESTED_BINARIES < <(
    find "$APP_PATH" \( -name "*.dylib" -o -name "*.so" \) -type f | sort
)

if [[ ${#NESTED_BINARIES[@]} -eq 0 ]]; then
    echo "  No .dylib or .so files found — skipping nested binary check."
    check_result "Nested binaries (none present)" "PASS"
else
    for BINARY in "${NESTED_BINARIES[@]}"; do
        if codesign -v "$BINARY" 2>/dev/null; then
            echo "  [signed] $BINARY"
        else
            echo "  [UNSIGNED] $BINARY"
            (( UNSIGNED_COUNT++ )) || true
        fi
    done

    if [[ $UNSIGNED_COUNT -eq 0 ]]; then
        check_result "All ${#NESTED_BINARIES[@]} nested binaries signed" "PASS"
    else
        check_result "Nested binaries signed" "FAIL" "$UNSIGNED_COUNT unsigned file(s) found"
    fi
fi
echo ""

# ---------------------------------------------------------------------------
# Check 4: Dangerous entitlement flags are false
# ---------------------------------------------------------------------------
echo "--- Check 4: Entitlement safety checks ---"

# Extract entitlements as XML plist
ENTITLEMENTS_XML="$(codesign -d --entitlements :- "$APP_PATH" 2>/dev/null || true)"

# Check cs-allow-unsigned-executable-memory
if echo "$ENTITLEMENTS_XML" | grep -A1 'cs-allow-unsigned-executable-memory' | grep -q '<true/>'; then
    check_result "cs-allow-unsigned-executable-memory is false" "FAIL" \
        "Entitlement is set to true — weakens memory security"
else
    check_result "cs-allow-unsigned-executable-memory is false" "PASS"
fi

# Check cs-disable-library-validation
if echo "$ENTITLEMENTS_XML" | grep -A1 'cs-disable-library-validation' | grep -q '<true/>'; then
    check_result "cs-disable-library-validation is false" "FAIL" \
        "Entitlement is set to true — allows loading unsigned libraries"
else
    check_result "cs-disable-library-validation is false" "PASS"
fi

echo ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "=== Verification Summary ==="
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
echo ""

if [[ $FAIL -gt 0 ]]; then
    echo "RESULT: FAILED — $FAIL check(s) did not pass."
    exit 1
else
    echo "RESULT: PASSED — all checks passed."
    exit 0
fi
