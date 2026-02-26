#!/bin/bash
# embed-python.sh — Download and embed relocatable CPython 3.12 into the .app bundle.
#
# Downloads a python-build-standalone release from Gregory Szorc's GitHub releases,
# extracts the interpreter and standard library, patches dylib references so they
# use @rpath/@loader_path (making the bundle relocatable), strips debug symbols,
# and lays out a Python.framework/ directory tree inside the specified output dir.
#
# Usage:
#   embed-python.sh --output <dir> [--arch <arm64|x86_64|universal>]
#
# Environment:
#   KMFLOW_CODESIGN_IDENTITY  Codesign identity (default: "-" for ad-hoc)
#
# Idempotent: skips download if a matching tarball is already cached.
# Cache location: ~/.cache/kmflow-python/

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PYTHON_VERSION="3.12"
# Pin to a specific python-build-standalone release tag so builds are reproducible.
# Update this date when you want to pick up a newer CPython patch release.
PBS_RELEASE="20241016"

CACHE_DIR="${HOME}/.cache/kmflow-python"
CODESIGN_IDENTITY="${KMFLOW_CODESIGN_IDENTITY:--}"

# python-build-standalone download base URL
PBS_BASE_URL="https://github.com/indygreg/python-build-standalone/releases/download/${PBS_RELEASE}"

# ---------------------------------------------------------------------------
# Known SHA-256 checksums for python-build-standalone tarballs.
# Update these when changing PBS_RELEASE or PYTHON_VERSION.
# Obtain checksums from the SHA256SUMS file published with each release:
#   https://github.com/indygreg/python-build-standalone/releases/download/${PBS_RELEASE}/SHA256SUMS
# ---------------------------------------------------------------------------
declare -A PBS_CHECKSUMS=(
    # Placeholder hashes — MUST be replaced with real values from the release
    # SHA256SUMS file before any production build. The build will fail if these
    # do not match the downloaded tarball.
    #
    # To populate:
    #   1. Download the tarball manually or via this script (first run will fail verification)
    #   2. Run: shasum -a 256 ~/.cache/kmflow-python/<tarball>
    #   3. Paste the hash below for the matching architecture
    #   4. Re-run the build to verify
    ["aarch64"]=""
    ["x86_64"]=""
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "[embed-python] $*" >&2; }
die()  { echo "[embed-python] ERROR: $*" >&2; exit 1; }

usage() {
    echo "Usage: $0 --output <dir> [--arch <arm64|x86_64|universal>]"
    echo ""
    echo "Options:"
    echo "  --output <dir>   Directory in which Python.framework/ will be created"
    echo "  --arch <arch>    Target architecture: arm64 (default), x86_64, or universal"
    exit 1
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
OUTPUT_DIR=""
ARCH="arm64"
UNIVERSAL=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)  OUTPUT_DIR="${2:?'--output requires a value'}"; shift 2 ;;
        --arch)
            ARCH="${2:?'--arch requires a value'}"
            shift 2
            [[ "$ARCH" == "universal" ]] && UNIVERSAL=1
            ;;
        -h|--help) usage ;;
        *) die "Unknown argument: $1" ;;
    esac
done

[[ -z "$OUTPUT_DIR" ]] && usage

# ---------------------------------------------------------------------------
# Resolve tarball names for each architecture
# ---------------------------------------------------------------------------
# python-build-standalone naming convention:
#   cpython-3.12.<patch>+<date>-<arch>-apple-darwin-install_only.tar.gz
# The "install_only" variant ships just the interpreter + stdlib, no dev headers.
pbs_tarball_name() {
    local arch="$1"
    local pbs_arch
    case "$arch" in
        arm64)   pbs_arch="aarch64" ;;
        x86_64)  pbs_arch="x86_64"  ;;
        *) die "Unsupported arch for tarball mapping: $arch" ;;
    esac
    # The release tag encodes the CPython patch version; we use a glob-compatible
    # pattern and rely on the cached file to avoid re-downloading.
    echo "cpython-${PYTHON_VERSION}.*+${PBS_RELEASE}-${pbs_arch}-apple-darwin-install_only.tar.gz"
}

# Resolve the actual download URL — we query the GitHub releases API to find the
# exact filename for the pinned release tag rather than hard-coding the patch ver.
resolve_download_url() {
    local arch="$1"
    local pbs_arch
    case "$arch" in
        arm64)   pbs_arch="aarch64" ;;
        x86_64)  pbs_arch="x86_64"  ;;
        *) die "Unsupported arch: $arch" ;;
    esac

    local pattern="cpython-${PYTHON_VERSION}.*${PBS_RELEASE}-${pbs_arch}-apple-darwin-install_only.tar.gz"

    log "Querying GitHub release ${PBS_RELEASE} for pattern: ${pattern}"
    local api_url="https://api.github.com/repos/indygreg/python-build-standalone/releases/tags/${PBS_RELEASE}"
    local asset_url
    asset_url=$(curl -fsSL "$api_url" \
        | python3 -c "
import sys, json, re
data = json.load(sys.stdin)
pattern = r'${pattern}'
for asset in data.get('assets', []):
    if re.search(pattern, asset['name']):
        print(asset['browser_download_url'])
        break
" 2>/dev/null) || true

    if [[ -z "$asset_url" ]]; then
        # Fallback: construct URL directly with a known patch version format.
        # This may need updating if the patch number changes.
        asset_url="${PBS_BASE_URL}/cpython-${PYTHON_VERSION}.9+${PBS_RELEASE}-${pbs_arch}-apple-darwin-install_only.tar.gz"
        log "GitHub API query failed or returned no match; falling back to: ${asset_url}"
    fi

    echo "$asset_url"
}

# ---------------------------------------------------------------------------
# Download function (idempotent via cache)
# ---------------------------------------------------------------------------
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
        log "Saved to cache: ${cached}"
    fi

    # SHA-256 verification — ensure the tarball matches the expected checksum.
    local pbs_arch
    case "$arch" in
        arm64)   pbs_arch="aarch64" ;;
        x86_64)  pbs_arch="x86_64"  ;;
    esac
    local expected_hash="${PBS_CHECKSUMS[$pbs_arch]:-}"
    if [[ -n "$expected_hash" ]]; then
        local actual_hash
        actual_hash=$(shasum -a 256 "$cached" | awk '{print $1}')
        if [[ "$actual_hash" != "$expected_hash" ]]; then
            log "HASH MISMATCH for ${filename}!"
            log "  Expected: ${expected_hash}"
            log "  Actual:   ${actual_hash}"
            rm -f "$cached"
            die "SHA-256 verification failed — possible supply chain attack or corrupt download. Removed cached file."
        fi
        log "SHA-256 verified: ${actual_hash}"
    else
        log "WARNING: No SHA-256 checksum configured for arch '${pbs_arch}'."
        log "         Populate PBS_CHECKSUMS in this script before production builds."
        log "         Current file hash: $(shasum -a 256 "$cached" | awk '{print $1}')"
        if [[ "${KMFLOW_RELEASE_BUILD:-0}" == "1" ]]; then
            rm -f "$cached"
            die "SHA-256 checksum verification is mandatory for release builds. Populate PBS_CHECKSUMS and retry."
        fi
    fi

    echo "$cached"
}

# ---------------------------------------------------------------------------
# Extract and stage a single architecture
# ---------------------------------------------------------------------------
stage_arch() {
    local arch="$1"
    local tarball
    tarball=$(download_tarball "$arch")

    local stage_dir
    stage_dir=$(mktemp -d -t kmflow-python-stage-XXXXXX)
    # shellcheck disable=SC2064
    trap "rm -rf '${stage_dir}'" EXIT

    log "Extracting ${tarball} to ${stage_dir}..."
    tar -xzf "$tarball" -C "$stage_dir"

    # The install_only tarball unpacks to python/
    local src_root="${stage_dir}/python"
    [[ -d "$src_root" ]] || die "Expected python/ directory inside tarball; got: $(ls "$stage_dir")"

    echo "$stage_dir"
}

# ---------------------------------------------------------------------------
# Build the Python.framework/ tree
#
# Framework layout we produce:
#   Python.framework/
#     Versions/
#       3.12/
#         bin/
#           python3.12          (executable)
#         lib/
#           python3.12/         (stdlib)
#         lib/libpython3.12.dylib
#     Versions/Current -> 3.12  (symlink)
#     Python -> Versions/Current/lib/libpython3.12.dylib  (symlink)
# ---------------------------------------------------------------------------
build_framework() {
    local src_root="$1"   # path to python/ inside extracted tarball
    local fw_root="$2"    # destination Python.framework/

    local ver_dir="${fw_root}/Versions/${PYTHON_VERSION}"
    mkdir -p "${ver_dir}/bin" "${ver_dir}/lib"

    # ---- Copy stdlib ----
    log "Copying stdlib..."
    local stdlib_src="${src_root}/lib/python${PYTHON_VERSION}"
    [[ -d "$stdlib_src" ]] || die "Stdlib not found at ${stdlib_src}"
    cp -R "$stdlib_src" "${ver_dir}/lib/"

    # ---- Copy interpreter binary ----
    log "Copying interpreter binary..."
    local interp_src="${src_root}/bin/python${PYTHON_VERSION}"
    [[ -f "$interp_src" ]] || die "Interpreter not found at ${interp_src}"
    cp "$interp_src" "${ver_dir}/bin/python${PYTHON_VERSION}"
    chmod +x "${ver_dir}/bin/python${PYTHON_VERSION}"

    # ---- Copy shared library ----
    # install_only builds ship the dylib inside lib/
    local dylib_src
    dylib_src=$(find "${src_root}/lib" -maxdepth 1 -name "libpython${PYTHON_VERSION}*.dylib" | head -1)
    if [[ -n "$dylib_src" ]]; then
        cp "$dylib_src" "${ver_dir}/lib/libpython${PYTHON_VERSION}.dylib"
    else
        log "WARNING: shared dylib not found in ${src_root}/lib — interpreter may be statically linked"
    fi

    # ---- Symlinks ----
    # Versions/Current -> 3.12
    ln -sf "${PYTHON_VERSION}" "${fw_root}/Versions/Current"
    # Top-level Python symlink (macOS framework convention)
    if [[ -f "${ver_dir}/lib/libpython${PYTHON_VERSION}.dylib" ]]; then
        ln -sf "Versions/Current/lib/libpython${PYTHON_VERSION}.dylib" "${fw_root}/Python"
    fi
}

# ---------------------------------------------------------------------------
# Patch dylib install names so the framework is relocatable
#
# We rewrite absolute /path/to/.../libpython3.12.dylib references to use
# @rpath so that the dynamic linker resolves them relative to the binary's
# rpath (which will point at .app/Contents/Frameworks/).
# ---------------------------------------------------------------------------
patch_install_names() {
    local fw_root="$1"
    local ver_dir="${fw_root}/Versions/${PYTHON_VERSION}"
    local dylib="${ver_dir}/lib/libpython${PYTHON_VERSION}.dylib"

    if [[ ! -f "$dylib" ]]; then
        log "No dylib to patch (statically linked build); skipping install_name_tool step."
        return
    fi

    log "Patching install names for relocatability..."

    # Rewrite the dylib's own install name to @rpath form
    local rpath_name="@rpath/Python.framework/Versions/${PYTHON_VERSION}/lib/libpython${PYTHON_VERSION}.dylib"
    install_name_tool -id "$rpath_name" "$dylib" 2>/dev/null || true

    # Rewrite references inside the interpreter binary
    local interp="${ver_dir}/bin/python${PYTHON_VERSION}"
    local old_name
    old_name=$(otool -L "$interp" 2>/dev/null \
        | awk '/libpython/{print $1}' | head -1) || true

    if [[ -n "$old_name" && "$old_name" != "$rpath_name" ]]; then
        install_name_tool -change "$old_name" "$rpath_name" "$interp" 2>/dev/null || true
    fi

    # Walk all .so extension modules in stdlib and patch any libpython references
    find "${ver_dir}/lib" -name "*.so" -print0 | while IFS= read -r -d '' so; do
        local ref
        ref=$(otool -L "$so" 2>/dev/null \
            | awk '/libpython/{print $1}' | head -1) || true
        if [[ -n "$ref" && "$ref" != "$rpath_name" ]]; then
            install_name_tool -change "$ref" "$rpath_name" "$so" 2>/dev/null || true
        fi
    done
}

# ---------------------------------------------------------------------------
# Strip debug symbols to reduce bundle size
# ---------------------------------------------------------------------------
strip_debug_symbols() {
    local fw_root="$1"
    local ver_dir="${fw_root}/Versions/${PYTHON_VERSION}"

    log "Stripping debug symbols..."

    # Strip the interpreter binary
    strip -S "${ver_dir}/bin/python${PYTHON_VERSION}" 2>/dev/null || true

    # Strip the shared library if present
    local dylib="${ver_dir}/lib/libpython${PYTHON_VERSION}.dylib"
    [[ -f "$dylib" ]] && strip -S "$dylib" 2>/dev/null || true

    # Strip extension modules
    find "${ver_dir}/lib" -name "*.so" -print0 \
        | xargs -0 -P4 strip -S 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Remove unnecessary stdlib content to reduce bundle size
# ---------------------------------------------------------------------------
prune_stdlib() {
    local fw_root="$1"
    local stdlib="${fw_root}/Versions/${PYTHON_VERSION}/lib/python${PYTHON_VERSION}"

    log "Pruning stdlib (test dirs, __pycache__, *.pyc)..."

    # Remove test packages — significant size savings
    rm -rf \
        "${stdlib}/test" \
        "${stdlib}/lib2to3/tests" \
        "${stdlib}/distutils/tests" \
        "${stdlib}/ctypes/test" \
        "${stdlib}/unittest/test" \
        2>/dev/null || true

    # Remove compiled bytecode — will be regenerated on first run if needed,
    # or can be pre-compiled at bundle time (out of scope for Milestone 1)
    find "${stdlib}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find "${stdlib}" -name "*.pyc" -delete 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Codesign the framework
# ---------------------------------------------------------------------------
codesign_framework() {
    local fw_root="$1"
    log "Codesigning Python.framework with identity: ${CODESIGN_IDENTITY}"

    # Sign all dylibs and .so files first, then the binary, then the framework.
    # --options runtime enables Hardened Runtime (required for notarization).
    # --timestamp is required for notarization (Apple rejects untimestamped signatures).
    find "${fw_root}" \( -name "*.so" -o -name "*.dylib" \) -print0 \
        | xargs -0 -P4 codesign --force --sign "$CODESIGN_IDENTITY" --options runtime --timestamp 2>/dev/null || true

    codesign --force --sign "$CODESIGN_IDENTITY" --options runtime --timestamp \
        "${fw_root}/Versions/${PYTHON_VERSION}/bin/python${PYTHON_VERSION}" \
        2>/dev/null || true

    # Sign the framework bundle itself
    codesign --force --sign "$CODESIGN_IDENTITY" --options runtime --timestamp "$fw_root" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# lipo: create a universal binary from arm64 + x86_64 slices
# ---------------------------------------------------------------------------
lipo_framework() {
    local arm_fw="$1"
    local x86_fw="$2"
    local out_fw="$3"

    log "Creating universal (fat) framework via lipo..."

    # We merge by copying the arm64 tree as base, then lipo-merging each binary
    cp -R "$arm_fw" "$out_fw"

    local ver_dir="${out_fw}/Versions/${PYTHON_VERSION}"
    local arm_ver="${arm_fw}/Versions/${PYTHON_VERSION}"
    local x86_ver="${x86_fw}/Versions/${PYTHON_VERSION}"

    # Merge interpreter binary
    lipo -create -output "${ver_dir}/bin/python${PYTHON_VERSION}" \
        "${arm_ver}/bin/python${PYTHON_VERSION}" \
        "${x86_ver}/bin/python${PYTHON_VERSION}"

    # Merge dylib if present
    if [[ -f "${arm_ver}/lib/libpython${PYTHON_VERSION}.dylib" \
       && -f "${x86_ver}/lib/libpython${PYTHON_VERSION}.dylib" ]]; then
        lipo -create -output "${ver_dir}/lib/libpython${PYTHON_VERSION}.dylib" \
            "${arm_ver}/lib/libpython${PYTHON_VERSION}.dylib" \
            "${x86_ver}/lib/libpython${PYTHON_VERSION}.dylib"
    fi

    # Merge extension modules (.so) that exist in both trees
    find "${arm_ver}/lib" -name "*.so" -print0 | while IFS= read -r -d '' arm_so; do
        local rel="${arm_so#${arm_ver}/lib/}"
        local x86_so="${x86_ver}/lib/${rel}"
        local out_so="${ver_dir}/lib/${rel}"
        if [[ -f "$x86_so" ]]; then
            lipo -create -output "$out_so" "$arm_so" "$x86_so" 2>/dev/null || true
        fi
    done
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    OUTPUT_DIR="$(cd "$(dirname "$OUTPUT_DIR")"; pwd)/$(basename "$OUTPUT_DIR")"
    local fw_out="${OUTPUT_DIR}/Python.framework"

    # Idempotency check: if framework directory already exists and contains the
    # interpreter binary, assume this step has already run successfully.
    if [[ -f "${fw_out}/Versions/${PYTHON_VERSION}/bin/python${PYTHON_VERSION}" ]]; then
        log "Python.framework already present at ${fw_out}; skipping."
        exit 0
    fi

    mkdir -p "$OUTPUT_DIR"

    if [[ $UNIVERSAL -eq 1 ]]; then
        # Download and stage both architectures, then lipo-merge
        local arm_stage x86_stage
        arm_stage=$(stage_arch "arm64")
        x86_stage=$(stage_arch "x86_64")

        local arm_fw="${arm_stage}/Python.framework"
        local x86_fw="${x86_stage}/Python.framework"

        mkdir -p "$arm_fw" "$x86_fw"
        build_framework "${arm_stage}/python" "$arm_fw"
        build_framework "${x86_stage}/python" "$x86_fw"

        patch_install_names "$arm_fw"
        patch_install_names "$x86_fw"
        strip_debug_symbols "$arm_fw"
        strip_debug_symbols "$x86_fw"
        prune_stdlib "$arm_fw"

        lipo_framework "$arm_fw" "$x86_fw" "$fw_out"
        # Re-patch install names on the merged output
        patch_install_names "$fw_out"
    else
        local stage_dir
        stage_dir=$(stage_arch "$ARCH")
        local src_root="${stage_dir}/python"

        build_framework "$src_root" "$fw_out"
        patch_install_names "$fw_out"
        strip_debug_symbols "$fw_out"
        prune_stdlib "$fw_out"
    fi

    codesign_framework "$fw_out"

    log "Done. Python.framework written to: ${fw_out}"
    log "Interpreter: ${fw_out}/Versions/${PYTHON_VERSION}/bin/python${PYTHON_VERSION}"
}

main
