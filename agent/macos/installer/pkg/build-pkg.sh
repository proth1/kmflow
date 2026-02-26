#!/bin/bash
# build-pkg.sh — Build a signed .pkg installer for MDM deployment of KMFlow Agent.
# Usage: build-pkg.sh <APP_PATH> [OUTPUT_DIR] [VERSION]
#
# Env:
#   KMFLOW_CODESIGN_IDENTITY  Identity for productsign (default: "-" for ad-hoc)
#   VERSION                   Override version string

set -euo pipefail

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
APP_PATH="${1:?Usage: build-pkg.sh <APP_PATH> [OUTPUT_DIR] [VERSION]}"
OUTPUT_DIR="${2:-./build}"
IDENTITY="${KMFLOW_CODESIGN_IDENTITY:--}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Determine version
if [[ -n "${3:-}" ]]; then
    VERSION="$3"
elif [[ -n "${VERSION:-}" ]]; then
    : # already set in env
else
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

DISTRIBUTION_XML="${SCRIPT_DIR}/distribution.xml"
if [[ ! -f "$DISTRIBUTION_XML" ]]; then
    echo "ERROR: distribution.xml not found at: $DISTRIBUTION_XML" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

echo "=== KMFlow Agent PKG Build ==="
echo "  App:        $APP_PATH"
echo "  Version:    $VERSION"
echo "  Output:     $OUTPUT_DIR"
echo "  Identity:   $IDENTITY"
echo "  Work dir:   $WORK_DIR"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Stage the payload root
# ---------------------------------------------------------------------------
echo "--- Step 1: Staging payload ---"
STAGED_ROOT="${WORK_DIR}/root"
APPS_DIR="${STAGED_ROOT}/Applications"
mkdir -p "$APPS_DIR"

# Copy the signed .app into the staged root at /Applications
cp -R "$APP_PATH" "$APPS_DIR/"
APP_NAME="$(basename "$APP_PATH")"
echo "  Staged: $APP_NAME -> $APPS_DIR/"

# ---------------------------------------------------------------------------
# Step 2: Build the component package
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 2: Building component package ---"
COMPONENT_PKG="${WORK_DIR}/KMFlowAgent-component.pkg"

pkgbuild \
    --root           "$STAGED_ROOT" \
    --identifier     "com.kmflow.agent" \
    --version        "$VERSION" \
    --install-location / \
    --scripts        "${SCRIPT_DIR}/scripts" \
    "$COMPONENT_PKG"

echo "  Component package: $COMPONENT_PKG"

# ---------------------------------------------------------------------------
# Step 3: Build the distribution package
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 3: Building distribution package ---"
UNSIGNED_PKG="${WORK_DIR}/KMFlowAgent-${VERSION}.pkg"

productbuild \
    --distribution  "$DISTRIBUTION_XML" \
    --resources     "${SCRIPT_DIR}/resources" \
    --package-path  "$WORK_DIR" \
    "$UNSIGNED_PKG"

echo "  Distribution package: $UNSIGNED_PKG"

# ---------------------------------------------------------------------------
# Step 4: Sign the distribution package
# ---------------------------------------------------------------------------
echo ""
echo "--- Step 4: Signing package ---"
SIGNED_PKG="${OUTPUT_DIR}/KMFlowAgent-${VERSION}-signed.pkg"

productsign \
    --sign "$IDENTITY" \
    "$UNSIGNED_PKG" \
    "$SIGNED_PKG"

echo "  Signed package: $SIGNED_PKG"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
PKG_SIZE="$(du -sh "$SIGNED_PKG" | cut -f1)"
echo ""
echo "=== PKG Build Complete ==="
echo "  Path: $SIGNED_PKG"
echo "  Size: $PKG_SIZE"
