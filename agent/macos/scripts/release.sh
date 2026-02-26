#!/bin/bash
# KMFlow Agent — Master release script (M9)
#
# Orchestrates the full build → sign → notarize → package → checksum pipeline.
# Usage: ./scripts/release.sh [--skip-notarize] [--skip-dmg] [--skip-pkg]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$AGENT_DIR/build}"
VERSION="${VERSION:-$(date +%Y.%m.%j)}"
IDENTITY="${KMFLOW_CODESIGN_IDENTITY:--}"
APP_NAME="KMFlow Agent"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"

SKIP_NOTARIZE=0
SKIP_DMG=0
SKIP_PKG=0

for arg in "$@"; do
    case "$arg" in
        --skip-notarize) SKIP_NOTARIZE=1 ;;
        --skip-dmg) SKIP_DMG=1 ;;
        --skip-pkg) SKIP_PKG=1 ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Guard: refuse ad-hoc signing for release builds
# Ad-hoc signed binaries cannot be notarized and will be rejected by
# Gatekeeper on other machines. This is defense-in-depth; sign-all.sh
# also enforces this check.
# ---------------------------------------------------------------------------
if [[ "$IDENTITY" == "-" ]]; then
    echo "ERROR: Ad-hoc signing identity ('-') is not permitted for release builds." >&2
    echo "       Set KMFLOW_CODESIGN_IDENTITY to a valid Developer ID Application certificate." >&2
    echo "       Example: export KMFLOW_CODESIGN_IDENTITY='Developer ID Application: YourOrg (TEAMID)'" >&2
    exit 1
fi

echo "=============================================="
echo "KMFlow Agent Release — v${VERSION}"
echo "=============================================="
echo "Identity: $IDENTITY"
echo "Build dir: $BUILD_DIR"
echo ""

cd "$AGENT_DIR"

# ── Step 1: Clean build ──────────────────────────────
echo "──── Step 1/7: Clean build ────"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# ── Step 2: App bundle (Swift + Python) ──────────────
echo "──── Step 2/7: App bundle ────"
KMFLOW_CODESIGN_IDENTITY="$IDENTITY" \
    bash "$SCRIPT_DIR/build-app-bundle.sh" --output "$BUILD_DIR"

# ── Step 3: Code signing ─────────────────────────────
echo "──── Step 3/7: Code signing ────"
KMFLOW_CODESIGN_IDENTITY="$IDENTITY" \
    bash "$SCRIPT_DIR/sign-all.sh" "$APP_BUNDLE"

# ── Step 4: Verification ─────────────────────────────
echo "──── Step 4/7: Verify signing ────"
bash "$SCRIPT_DIR/verify-signing.sh" "$APP_BUNDLE"

# ── Step 5: Notarization ─────────────────────────────
if [ "$SKIP_NOTARIZE" -eq 0 ]; then
    echo "──── Step 5/7: Notarization ────"
    bash "$SCRIPT_DIR/notarize.sh" "$APP_BUNDLE"
else
    echo "──── Step 5/7: Notarization (SKIPPED) ────"
fi

# ── Step 6: Packaging ────────────────────────────────
echo "──── Step 6/7: Packaging ────"

if [ "$SKIP_DMG" -eq 0 ]; then
    echo "  Building DMG..."
    KMFLOW_CODESIGN_IDENTITY="$IDENTITY" VERSION="$VERSION" \
        bash "$AGENT_DIR/installer/dmg/build-dmg.sh" "$APP_BUNDLE" "$BUILD_DIR" || \
        echo "  DMG build failed (create-dmg may not be installed)"
fi

if [ "$SKIP_PKG" -eq 0 ]; then
    echo "  Building PKG..."
    KMFLOW_CODESIGN_IDENTITY="$IDENTITY" VERSION="$VERSION" \
        bash "$AGENT_DIR/installer/pkg/build-pkg.sh" "$APP_BUNDLE" "$BUILD_DIR" || \
        echo "  PKG build failed"
fi

# ── Step 7: Checksums ────────────────────────────────
echo "──── Step 7/7: Checksums ────"
bash "$SCRIPT_DIR/checksums.sh" "$BUILD_DIR"

# ── Summary ──────────────────────────────────────────
echo ""
echo "=============================================="
echo "Release v${VERSION} complete"
echo "=============================================="
echo ""
echo "Artifacts:"
ls -lh "$BUILD_DIR"/*.{app,dmg,pkg} 2>/dev/null | awk '{print "  " $NF " (" $5 ")"}'
echo ""
echo "Checksums:"
if [ -f "$BUILD_DIR/SHA256SUMS" ]; then
    cat "$BUILD_DIR/SHA256SUMS" | sed 's/^/  /'
fi
echo ""

# Git tag suggestion
echo "To create a git tag:"
echo "  git tag -s agent/v${VERSION} -m 'KMFlow Agent v${VERSION}'"
echo "  git push origin agent/v${VERSION}"
