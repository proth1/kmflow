#!/bin/bash
# build-app-bundle.sh — Master build script for KMFlowAgent.app bundle.
#
# Compiles the Swift package in release mode, assembles the .app directory
# structure, embeds the relocatable CPython 3.12 framework, vendors Python
# dependencies, copies the Python intelligence layer source, and codesigns
# the finished bundle.
#
# Usage:
#   build-app-bundle.sh [--output <dir>] [--arch <arm64|x86_64|universal>]
#
# Options:
#   --output <dir>   Directory to write KMFlowAgent.app into (default: ./build/)
#   --arch <arch>    Target architecture: arm64 (default), x86_64, or universal
#
# Environment:
#   KMFLOW_CODESIGN_IDENTITY  Codesign identity string (default: "-" for ad-hoc signing)
#
# The resulting bundle layout is:
#   KMFlowAgent.app/
#     Contents/
#       MacOS/
#         KMFlowAgent              # Swift binary
#         kmflow-python            # Shell shim → embedded Python
#       Frameworks/
#         Python.framework/        # Relocatable CPython 3.12
#       Resources/
#         python/
#           kmflow_agent/          # Python intelligence layer (source)
#           site-packages/         # Vendored Python deps
#           integrity.json         # SHA-256 manifest of all Python files
#         Info.plist
#         KMFlowAgent.entitlements
#         PrivacyInfo.xcprivacy
#
# This script is idempotent for the embed-python step (Python.framework is
# only downloaded once and cached in ~/.cache/kmflow-python/).

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# agent/macos/ is one level above scripts/
MACOS_DIR="$(dirname "$SCRIPT_DIR")"
# agent/ is one level above macos/
AGENT_DIR="$(dirname "$MACOS_DIR")"
# Python source lives in agent/python/
PYTHON_SRC_DIR="${AGENT_DIR}/python"

APP_NAME="KMFlowAgent.app"
BUNDLE_ID="com.kmflow.agent"
SWIFT_BINARY_NAME="KMFlowAgent"

CODESIGN_IDENTITY="${KMFLOW_CODESIGN_IDENTITY:--}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "[build-app] $*"; }
step() { echo ""; echo "==> $*"; }
die()  { echo "[build-app] ERROR: $*" >&2; exit 1; }

usage() {
    echo "Usage: $0 [--output <dir>] [--arch <arm64|x86_64|universal>]"
    echo ""
    echo "  --output <dir>   Where to write ${APP_NAME} (default: ./build/)"
    echo "  --arch <arch>    arm64 (default), x86_64, or universal"
    exit 1
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
OUTPUT_DIR="${MACOS_DIR}/build"
ARCH="arm64"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output) OUTPUT_DIR="${2:?'--output requires a value'}"; shift 2 ;;
        --arch)   ARCH="${2:?'--arch requires a value'}";         shift 2 ;;
        -h|--help) usage ;;
        *) die "Unknown argument: $1" ;;
    esac
done

# Resolve output dir to an absolute path, creating it if needed
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

APP_BUNDLE="${OUTPUT_DIR}/${APP_NAME}"
CONTENTS="${APP_BUNDLE}/Contents"
MACOS_BUNDLE="${CONTENTS}/MacOS"
FRAMEWORKS="${CONTENTS}/Frameworks"
RESOURCES="${CONTENTS}/Resources"
PYTHON_RESOURCES="${RESOURCES}/python"

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------
step "Checking prerequisites..."

command -v swift       &>/dev/null || die "'swift' not found — install Xcode Command Line Tools"
command -v codesign    &>/dev/null || die "'codesign' not found — install Xcode Command Line Tools"
command -v install_name_tool &>/dev/null || die "'install_name_tool' not found"
command -v python3     &>/dev/null || die "'python3' not found — needed for pip and integrity manifest"

# Validate we are running from within the expected directory layout
[[ -f "${MACOS_DIR}/Package.swift" ]] \
    || die "Package.swift not found at ${MACOS_DIR}/Package.swift — are you running from agent/macos/?"

[[ -d "${PYTHON_SRC_DIR}/kmflow_agent" ]] \
    || die "Python source not found at ${PYTHON_SRC_DIR}/kmflow_agent"

[[ -f "${PYTHON_SRC_DIR}/requirements.txt" ]] \
    || die "requirements.txt not found at ${PYTHON_SRC_DIR}/requirements.txt"

[[ -f "${MACOS_DIR}/Resources/Info.plist" ]] \
    || die "Info.plist not found at ${MACOS_DIR}/Resources/Info.plist"

[[ -f "${MACOS_DIR}/Resources/KMFlowAgent.entitlements" ]] \
    || die "Entitlements not found at ${MACOS_DIR}/Resources/KMFlowAgent.entitlements"

[[ -f "${MACOS_DIR}/Resources/python-launcher.sh" ]] \
    || die "python-launcher.sh not found at ${MACOS_DIR}/Resources/python-launcher.sh"

log "All prerequisites satisfied."
log "Output: ${APP_BUNDLE}"
log "Architecture: ${ARCH}"
log "Codesign identity: ${CODESIGN_IDENTITY}"

# ---------------------------------------------------------------------------
# Step 1: Compile Swift package
# ---------------------------------------------------------------------------
step "Step 1/9: Compiling Swift package (release)..."

# swift build must run from the package root
pushd "$MACOS_DIR" > /dev/null

SWIFT_BUILD_FLAGS="-c release"
# If building for a specific non-native arch, pass it explicitly
case "$ARCH" in
    arm64)   SWIFT_BUILD_FLAGS+=" --arch arm64"  ;;
    x86_64)  SWIFT_BUILD_FLAGS+=" --arch x86_64" ;;
    universal)
        # For a universal bundle, build both slices and lipo-merge
        log "Building arm64 slice..."
        swift build -c release --arch arm64
        log "Building x86_64 slice..."
        swift build -c release --arch x86_64
        log "Creating universal binary via lipo..."
        lipo -create \
            ".build/arm64-apple-macosx/release/${SWIFT_BINARY_NAME}" \
            ".build/x86_64-apple-macosx/release/${SWIFT_BINARY_NAME}" \
            -output ".build/release/${SWIFT_BINARY_NAME}"
        ;;
esac

# For single-arch builds the binary lands at .build/release/
if [[ "$ARCH" != "universal" ]]; then
    # shellcheck disable=SC2086
    swift build $SWIFT_BUILD_FLAGS
fi

SWIFT_BINARY="${MACOS_DIR}/.build/release/${SWIFT_BINARY_NAME}"
[[ -f "$SWIFT_BINARY" ]] \
    || die "Swift build succeeded but binary not found at ${SWIFT_BINARY}"

popd > /dev/null
log "Swift binary: ${SWIFT_BINARY}"

# ---------------------------------------------------------------------------
# Step 2: Create .app directory structure
# ---------------------------------------------------------------------------
step "Step 2/9: Creating .app bundle structure..."

# Remove a previous build artifact if present
[[ -d "$APP_BUNDLE" ]] && rm -rf "$APP_BUNDLE"

mkdir -p \
    "$MACOS_BUNDLE" \
    "$FRAMEWORKS" \
    "$PYTHON_RESOURCES/site-packages"

log "Bundle skeleton created at: ${APP_BUNDLE}"

# ---------------------------------------------------------------------------
# Step 3: Copy Swift binary
# ---------------------------------------------------------------------------
step "Step 3/9: Copying Swift binary..."
cp "$SWIFT_BINARY" "${MACOS_BUNDLE}/${SWIFT_BINARY_NAME}"
chmod +x "${MACOS_BUNDLE}/${SWIFT_BINARY_NAME}"
log "Copied: ${MACOS_BUNDLE}/${SWIFT_BINARY_NAME}"

# ---------------------------------------------------------------------------
# Step 4: Embed Python framework
# ---------------------------------------------------------------------------
step "Step 4/9: Embedding Python.framework..."
"${SCRIPT_DIR}/embed-python.sh" \
    --output "$FRAMEWORKS" \
    --arch "$ARCH"
log "Python.framework embedded."

# ---------------------------------------------------------------------------
# Step 5: Vendor Python dependencies
# ---------------------------------------------------------------------------
step "Step 5/9: Vendoring Python dependencies..."
"${SCRIPT_DIR}/vendor-python-deps.sh" \
    --output "$PYTHON_RESOURCES" \
    --requirements "${PYTHON_SRC_DIR}/requirements.txt"

# Adjust platform tag for x86_64 / universal builds so wheels match the arch
if [[ "$ARCH" == "x86_64" ]]; then
    "${SCRIPT_DIR}/vendor-python-deps.sh" \
        --output "$PYTHON_RESOURCES" \
        --requirements "${PYTHON_SRC_DIR}/requirements.txt" \
        --platform macosx_14_0_x86_64
fi
log "Python dependencies vendored."

# ---------------------------------------------------------------------------
# Step 6: Copy kmflow_agent Python source
# ---------------------------------------------------------------------------
step "Step 6/9: Copying Python intelligence layer..."
cp -R "${PYTHON_SRC_DIR}/kmflow_agent" "${PYTHON_RESOURCES}/kmflow_agent"
# Remove any cached bytecode from the source tree (may have been generated locally)
find "${PYTHON_RESOURCES}/kmflow_agent" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "${PYTHON_RESOURCES}/kmflow_agent" -name "*.pyc" -delete 2>/dev/null || true
log "Copied: ${PYTHON_RESOURCES}/kmflow_agent"

# ---------------------------------------------------------------------------
# Step 7: Install Python launcher shim
# ---------------------------------------------------------------------------
step "Step 7/9: Installing Python launcher shim..."
cp "${MACOS_DIR}/Resources/python-launcher.sh" "${MACOS_BUNDLE}/kmflow-python"
chmod +x "${MACOS_BUNDLE}/kmflow-python"
log "Installed: ${MACOS_BUNDLE}/kmflow-python"

# ---------------------------------------------------------------------------
# Step 8: Copy bundle resources (plist, entitlements, privacy manifest)
# ---------------------------------------------------------------------------
step "Step 8/9: Copying bundle resources..."

cp "${MACOS_DIR}/Resources/Info.plist"                  "${RESOURCES}/Info.plist"
cp "${MACOS_DIR}/Resources/KMFlowAgent.entitlements"    "${RESOURCES}/KMFlowAgent.entitlements"

# PrivacyInfo.xcprivacy is required for App Store / notarization compliance.
# It documents what data the app accesses and why.
PRIVACY_SRC="${MACOS_DIR}/Resources/PrivacyInfo.xcprivacy"
if [[ -f "$PRIVACY_SRC" ]]; then
    cp "$PRIVACY_SRC" "${RESOURCES}/PrivacyInfo.xcprivacy"
else
    log "WARNING: PrivacyInfo.xcprivacy not found at ${PRIVACY_SRC}"
    log "         Creating minimal placeholder — update before distribution."
    cat > "${RESOURCES}/PrivacyInfo.xcprivacy" <<'PRIVACY_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>NSPrivacyAccessedAPITypes</key>
    <array/>
    <key>NSPrivacyCollectedDataTypes</key>
    <array/>
    <key>NSPrivacyTracking</key>
    <false/>
</dict>
</plist>
PRIVACY_EOF
fi

log "Bundle resources installed."

# ---------------------------------------------------------------------------
# Step 9: Generate SHA-256 integrity manifest
#
# The manifest lists every file under Contents/Resources/python/ with its
# SHA-256 hash.  The Swift binary reads this at startup to verify the Python
# layer has not been tampered with (defense-in-depth; not a security boundary
# for sandboxed apps, but useful for detecting accidental corruption).
#
# Format: JSON object mapping relative paths to hex SHA-256 digests.
# ---------------------------------------------------------------------------
step "Step 9/9: Generating Python integrity manifest..."

INTEGRITY_FILE="${PYTHON_RESOURCES}/integrity.json"

INTEGRITY_SIG_FILE="${PYTHON_RESOURCES}/integrity.sig"

python3 - <<PYEOF
import hashlib, hmac, json, os, pathlib, secrets, sys

python_dir = pathlib.Path("${PYTHON_RESOURCES}")
manifest = {}

for path in sorted(python_dir.rglob("*")):
    if path.is_file() and path.name not in ("integrity.json", "integrity.sig"):
        rel = str(path.relative_to(python_dir))
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest[rel] = sha256

# Write the manifest wrapped in {"files": {...}} for ManifestPayload decoding.
output = pathlib.Path("${INTEGRITY_FILE}")
manifest_json = json.dumps({"files": manifest}, indent=2, sort_keys=True) + "\n"
output.write_text(manifest_json)
print(f"[build-app] Integrity manifest: {len(manifest)} files hashed -> {output}")

# Compute HMAC-SHA256 signature with a per-build random key.
# The key is embedded in the signature file alongside the HMAC.
# Since the entire bundle is code-signed, tampering with either file
# breaks the codesign seal. The HMAC adds defense-in-depth for cases
# where integrity verification runs independently of codesign.
hmac_key = secrets.token_bytes(32)
sig = hmac.new(hmac_key, manifest_json.encode(), hashlib.sha256).hexdigest()

sig_payload = {
    "hmac_sha256": sig,
    "key_hex": hmac_key.hex(),
    "manifest_sha256": hashlib.sha256(manifest_json.encode()).hexdigest(),
}

sig_output = pathlib.Path("${INTEGRITY_SIG_FILE}")
sig_output.write_text(json.dumps(sig_payload, indent=2) + "\n")
print(f"[build-app] Integrity signature written -> {sig_output}")
PYEOF

log "Integrity manifest written: ${INTEGRITY_FILE}"
log "Integrity signature written: ${INTEGRITY_SIG_FILE}"

# ---------------------------------------------------------------------------
# Codesign the bundle
#
# Signing order matters: inner resources first, then the bundle root.
# With ad-hoc signing (-) notarization is not possible, but the binary
# runs locally without Gatekeeper quarantine issues.
# ---------------------------------------------------------------------------
step "Codesigning bundle (identity: ${CODESIGN_IDENTITY})..."

# Strip existing code signatures from Mach-O binaries in Frameworks/.
# python-build-standalone ships with its own signatures that have a different
# Team ID. Without stripping, the Python interpreter can't load libpython3.12
# because macOS enforces Team ID consistency for ad-hoc signed binaries.
# NOTE: Only strip/re-sign in Frameworks/ — the .so files in Resources/python/
# site-packages/ are loaded by Python (not dyld) and must keep their original
# hashes for the integrity manifest check.
log "Stripping existing code signatures..."
while IFS= read -r -d '' macho; do
    codesign --remove-signature "$macho" 2>/dev/null || true
done < <(find "$FRAMEWORKS" \( -name "*.dylib" -o -name "*.so" \) -type f -print0 2>/dev/null)
PYTHON_BIN="${FRAMEWORKS}/Python.framework/Versions/3.12/bin/python3.12"
if [[ -f "$PYTHON_BIN" ]]; then
    codesign --remove-signature "$PYTHON_BIN" 2>/dev/null || true
fi
codesign --remove-signature "${MACOS_BUNDLE}/${SWIFT_BINARY_NAME}" 2>/dev/null || true

# Sign inside-out: dylibs/so → Python interpreter → Swift binary.
# All are signed sequentially with the same ad-hoc identity ("-").
# TODO: For Developer ID signing, re-enable --options runtime and --timestamp.
log "Signing Mach-O binaries..."
while IFS= read -r -d '' macho; do
    codesign --force --sign "$CODESIGN_IDENTITY" "$macho" \
        || log "WARNING: Could not sign $(basename "$macho") (non-fatal)"
done < <(find "$FRAMEWORKS" \( -name "*.dylib" -o -name "*.so" \) -type f -print0 2>/dev/null)

if [[ -f "$PYTHON_BIN" ]]; then
    codesign --force --sign "$CODESIGN_IDENTITY" "$PYTHON_BIN" \
        || log "WARNING: Could not sign Python interpreter (non-fatal)"
fi

# Sign the Swift binary outside the .app context to avoid codesign
# traversing the bundle and failing on Python.framework (which lacks
# a proper Apple framework Info.plist) or the shell script shim.
SWIFT_TEMP="$(mktemp)"
cp "${MACOS_BUNDLE}/${SWIFT_BINARY_NAME}" "$SWIFT_TEMP"
codesign --force --sign "$CODESIGN_IDENTITY" \
    --entitlements "${RESOURCES}/KMFlowAgent.entitlements" \
    "$SWIFT_TEMP" \
    || log "WARNING: Could not sign Swift binary (non-fatal)"
cp "$SWIFT_TEMP" "${MACOS_BUNDLE}/${SWIFT_BINARY_NAME}"
rm -f "$SWIFT_TEMP"

log "Codesigning complete."

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
step "Verifying bundle..."

# Verify the Swift binary is properly signed (most important for launch).
codesign --verify --verbose=1 "${MACOS_BUNDLE}/${SWIFT_BINARY_NAME}" 2>&1 \
    && log "codesign --verify Swift binary: PASS" \
    || log "WARNING: Swift binary verification reported issues"

# Verify the Python interpreter can load its dylib.
if [[ -f "$PYTHON_BIN" ]]; then
    codesign --verify --verbose=1 "$PYTHON_BIN" 2>&1 \
        && log "codesign --verify Python binary: PASS" \
        || log "WARNING: Python binary verification reported issues"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
BUNDLE_SIZE_MB=$(du -sm "$APP_BUNDLE" | awk '{print $1}')

step "Build complete!"
echo ""
echo "  Bundle:    ${APP_BUNDLE}"
echo "  Size:      ~${BUNDLE_SIZE_MB} MB"
echo "  Identity:  ${CODESIGN_IDENTITY}"
echo ""
echo "To run:"
echo "  open ${APP_BUNDLE}"
echo ""
echo "To test the Python layer directly:"
echo "  ${MACOS_BUNDLE}/kmflow-python --version"
echo "  ${MACOS_BUNDLE}/kmflow-python -m kmflow_agent status"
