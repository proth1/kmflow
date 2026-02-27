#!/bin/bash
# build-dmg.sh — Build a branded DMG installer for the KMFlow Agent.
# Usage: build-dmg.sh <APP_PATH> [OUTPUT_DIR]
#
# Dependencies:
#   brew install create-dmg
#
# Env:
#   KMFLOW_CODESIGN_IDENTITY  (default: "-" for ad-hoc signing)
#   VERSION                   (default: read from ../../.current-version)

set -euo pipefail

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
APP_PATH="${1:?Usage: build-dmg.sh <APP_PATH> [OUTPUT_DIR]}"
OUTPUT_DIR="${2:-./build}"
IDENTITY="${KMFLOW_CODESIGN_IDENTITY:--}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Determine version
if [[ -z "${VERSION:-}" ]]; then
    VERSION_FILE="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)/.current-version"
    if [[ -f "$VERSION_FILE" ]]; then
        VERSION="$(<"$VERSION_FILE")"
    else
        VERSION="0.0.0"
        echo "WARNING: VERSION not set and .current-version not found; using $VERSION" >&2
    fi
fi

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if [[ ! -d "$APP_PATH" ]]; then
    echo "ERROR: APP_PATH does not exist or is not a directory: $APP_PATH" >&2
    exit 1
fi

if ! command -v create-dmg &>/dev/null; then
    echo "ERROR: create-dmg not found. Install with: brew install create-dmg" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

DMG_NAME="KMFlowAgent-${VERSION}.dmg"
DMG_PATH="${OUTPUT_DIR}/${DMG_NAME}"

# Optional asset paths (create-dmg skips missing assets gracefully via our args)
VOLICON="${SCRIPT_DIR}/volume-icon.icns"
BACKGROUND="${SCRIPT_DIR}/background.png"
BACKGROUND_2X="${SCRIPT_DIR}/background@2x.png"

echo "=== KMFlow Agent DMG Build ==="
echo "  App:        $APP_PATH"
echo "  Version:    $VERSION"
echo "  Output:     $DMG_PATH"
echo "  Identity:   $IDENTITY"
echo ""

# ---------------------------------------------------------------------------
# Build the DMG (remove any stale copy first — create-dmg won't overwrite)
# ---------------------------------------------------------------------------
echo "--- Step 1: Building DMG with create-dmg ---"
rm -f "$DMG_PATH"

# Assemble optional asset flags conditionally
CREATE_DMG_ARGS=()

if [[ -f "$VOLICON" ]]; then
    CREATE_DMG_ARGS+=( --volicon "$VOLICON" )
    echo "  Volume icon: $VOLICON"
else
    echo "  Volume icon: not found (skipping)"
fi

if [[ -f "$BACKGROUND" ]]; then
    CREATE_DMG_ARGS+=( --background "$BACKGROUND" )
    echo "  Background:  $BACKGROUND"
else
    echo "  Background:  not found (skipping)"
fi

if [[ -f "$BACKGROUND_2X" ]]; then
    CREATE_DMG_ARGS+=( --background "$BACKGROUND_2X" )
    echo "  Background@2x: $BACKGROUND_2X"
fi

create-dmg \
    --volname "KMFlow Agent" \
    "${CREATE_DMG_ARGS[@]}" \
    --window-pos  200 120 \
    --window-size 600 400 \
    --icon-size   100 \
    --icon "KMFlow Agent.app" 150 190 \
    --app-drop-link            450 190 \
    --hide-extension "KMFlow Agent.app" \
    "$DMG_PATH" \
    "$APP_PATH"

echo ""
echo "  DMG created: $DMG_PATH"

# ---------------------------------------------------------------------------
# Step 2: Sign the DMG
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 2: Signing DMG ---"
codesign --sign "$IDENTITY" --timestamp "$DMG_PATH"
echo "  DMG signed."

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
DMG_SIZE="$(du -sh "$DMG_PATH" | cut -f1)"
echo ""
echo "=== DMG Build Complete ==="
echo "  Path: $DMG_PATH"
echo "  Size: $DMG_SIZE"
