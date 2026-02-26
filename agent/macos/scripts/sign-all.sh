#!/bin/bash
# sign-all.sh — Code-sign all dylibs/.so files in a .app bundle, then sign the bundle itself.
# Usage: sign-all.sh <APP_PATH>
# Env:   KMFLOW_CODESIGN_IDENTITY  (default: "-" for ad-hoc signing)

set -euo pipefail

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
APP_PATH="${1:?Usage: sign-all.sh <APP_PATH>}"
IDENTITY="${KMFLOW_CODESIGN_IDENTITY:--}"

# Resolve the entitlements file relative to this script's location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTITLEMENTS_PATH="${SCRIPT_DIR}/../Resources/KMFlowAgent.entitlements"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if [[ ! -d "$APP_PATH" ]]; then
    echo "ERROR: APP_PATH does not exist or is not a directory: $APP_PATH" >&2
    exit 1
fi

if [[ ! -f "$ENTITLEMENTS_PATH" ]]; then
    echo "ERROR: Entitlements file not found: $ENTITLEMENTS_PATH" >&2
    exit 1
fi

# Refuse ad-hoc signing ("-") for release builds. Ad-hoc signed binaries
# cannot be notarized and will be rejected by Gatekeeper on other machines.
if [[ "$IDENTITY" == "-" ]]; then
    if [[ "${KMFLOW_RELEASE_BUILD:-0}" == "1" ]]; then
        echo "ERROR: Ad-hoc signing identity ('-') is not permitted for release builds." >&2
        echo "       Set KMFLOW_CODESIGN_IDENTITY to a valid Developer ID Application certificate." >&2
        exit 1
    else
        echo "WARNING: Using ad-hoc signing identity ('-'). This is acceptable for local development only."
    fi
fi

echo "=== KMFlow Agent Code Signing ==="
echo "  App:          $APP_PATH"
echo "  Identity:     $IDENTITY"
echo "  Entitlements: $ENTITLEMENTS_PATH"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Sign all .dylib and .so files individually (inside-out order)
# ---------------------------------------------------------------------------
echo "--- Step 1: Signing nested binaries ---"

# Build a list of .so and .dylib files, sorted deepest-first so we sign
# dependencies before their consumers (codesign requirement on macOS 13+).
mapfile -t NESTED_BINARIES < <(
    find "$APP_PATH" \
        \( -name "*.dylib" -o -name "*.so" \) \
        -type f \
        | sort --reverse
)

if [[ ${#NESTED_BINARIES[@]} -eq 0 ]]; then
    echo "  No .dylib or .so files found — skipping nested binary signing."
else
    for BINARY in "${NESTED_BINARIES[@]}"; do
        echo "  Signing: $BINARY"
        codesign \
            --force \
            --sign "$IDENTITY" \
            --options runtime \
            --timestamp \
            "$BINARY"
    done
    echo "  Signed ${#NESTED_BINARIES[@]} nested binary/libraries."
fi

echo ""

# ---------------------------------------------------------------------------
# Step 2: Sign the overall .app bundle
# ---------------------------------------------------------------------------
echo "--- Step 2: Signing .app bundle ---"
echo "  Signing: $APP_PATH"

codesign \
    --deep \
    --force \
    --sign "$IDENTITY" \
    --options runtime \
    --entitlements "$ENTITLEMENTS_PATH" \
    --timestamp \
    "$APP_PATH"

echo "  Bundle signed."
echo ""

# ---------------------------------------------------------------------------
# Step 3: Verification
# ---------------------------------------------------------------------------
echo "--- Step 3: Verifying signature ---"
codesign -vvv --deep --strict "$APP_PATH"

echo ""
echo "=== Signing complete ==="
