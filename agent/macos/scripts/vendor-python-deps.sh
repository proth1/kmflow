#!/bin/bash
# vendor-python-deps.sh — Install and vendor Python dependencies for the .app bundle.
#
# Installs each package from requirements.txt (and its transitive deps) into
# a self-contained site-packages/ directory using pip's --target mode.
# Uses --only-binary=:all: so that only pre-built wheels are accepted — no
# compilation toolchain is required on the build machine.
#
# After installation, cleans up artifacts that are not needed at runtime:
#   - __pycache__/ directories
#   - *.pyc / *.pyo compiled bytecode files
#   - *.dist-info/ directories  (pip metadata, not needed at runtime)
#   - tests/ and test/ subdirectories within installed packages
#
# Usage:
#   vendor-python-deps.sh --output <dir> [--requirements <file>]
#
# The <dir> argument is the parent of site-packages/, i.e.:
#   --output Contents/Resources/python
# produces:
#   Contents/Resources/python/site-packages/<packages>

set -euo pipefail

# ---------------------------------------------------------------------------
# Default transitive deps that pip may not automatically fetch when using
# --no-deps.  Listed here so we can install them explicitly in dependency order.
# ---------------------------------------------------------------------------
# NOTE: We do NOT use --no-deps in the main install pass (that would require
# manually tracking every transitive dep). Instead we use a single pip install
# invocation per top-level package and let pip resolve transitively, but we
# still restrict to --only-binary=:all: to avoid native compilation.
#
# The list below is kept for documentation / fallback purposes and is also
# used if STRICT_NODEPS=1 is set in the environment.
TRANSITIVE_DEPS=(
    anyio
    certifi
    h11
    httpcore
    idna
    sniffio
    cffi
    pycparser
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "[vendor-deps] $*" >&2; }
die()  { echo "[vendor-deps] ERROR: $*" >&2; exit 1; }

usage() {
    echo "Usage: $0 --output <dir> [--requirements <file>] [--platform <tag>]"
    echo ""
    echo "Options:"
    echo "  --output <dir>         Parent directory for site-packages/"
    echo "                         (e.g. Contents/Resources/python)"
    echo "  --requirements <file>  Path to requirements.txt"
    echo "                         (default: ../../python/requirements.txt"
    echo "                          relative to this script)"
    echo "  --platform <tag>       pip platform tag"
    echo "                         (default: macosx_14_0_arm64)"
    exit 1
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Default requirements.txt is in agent/python/ (two levels up from agent/macos/scripts/)
DEFAULT_REQUIREMENTS="${SCRIPT_DIR}/../../python/requirements.txt"

OUTPUT_DIR=""
REQUIREMENTS_FILE="$DEFAULT_REQUIREMENTS"
PIP_PLATFORM="macosx_14_0_arm64"
PYTHON_VERSION_TAG="3.12"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)       OUTPUT_DIR="${2:?'--output requires a value'}"; shift 2 ;;
        --requirements) REQUIREMENTS_FILE="${2:?'--requirements requires a value'}"; shift 2 ;;
        --platform)     PIP_PLATFORM="${2:?'--platform requires a value'}"; shift 2 ;;
        -h|--help) usage ;;
        *) die "Unknown argument: $1" ;;
    esac
done

[[ -z "$OUTPUT_DIR" ]] && usage

# Resolve to absolute path
OUTPUT_DIR="$(cd "$(dirname "$OUTPUT_DIR")"; pwd)/$(basename "$OUTPUT_DIR")"
SITE_PACKAGES="${OUTPUT_DIR}/site-packages"

# Validate requirements file
[[ -f "$REQUIREMENTS_FILE" ]] \
    || die "Requirements file not found: ${REQUIREMENTS_FILE}"
REQUIREMENTS_FILE="$(cd "$(dirname "$REQUIREMENTS_FILE")"; pwd)/$(basename "$REQUIREMENTS_FILE")"

# ---------------------------------------------------------------------------
# Locate a suitable pip / python3 on the host
# We use the host pip only as a downloader; the installed packages are
# targeted at the embedded Python version via --python-version.
# ---------------------------------------------------------------------------
find_pip() {
    local pip_cmd
    for candidate in pip3 pip python3 python; do
        if command -v "$candidate" &>/dev/null; then
            # Verify it can actually run pip
            if "$candidate" -m pip --version &>/dev/null 2>&1; then
                echo "$candidate -m pip"
                return
            fi
        fi
    done
    die "Cannot locate pip. Install Python 3 and pip, or activate a virtualenv."
}

PIP_CMD=$(find_pip)
log "Using pip: ${PIP_CMD}"

# ---------------------------------------------------------------------------
# Parse top-level requirements from file, stripping comments and blank lines
# ---------------------------------------------------------------------------
parse_requirements() {
    local req_file="$1"
    grep -v '^\s*#' "$req_file" \
        | grep -v '^\s*$' \
        | sed 's/#.*//' \
        | tr -d ' '
}

# ---------------------------------------------------------------------------
# Install packages
# ---------------------------------------------------------------------------
install_packages() {
    local site_dir="$1"
    shift
    local packages=("$@")

    log "Installing into: ${site_dir}"
    log "Packages: ${packages[*]}"

    # pip install arguments:
    #   --target           write packages into our site-packages dir
    #   --python-version   cross-version: target the embedded Python
    #   --platform         cross-platform: only fetch wheels for target OS/arch
    #   --only-binary=:all: forbid sdist / compilation
    #   --no-compile       skip .pyc compilation (we strip it anyway, saves time)
    #   --upgrade          ensure we always get a fresh install (idempotent behavior)
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
}

# ---------------------------------------------------------------------------
# Cleanup: remove runtime-unnecessary artifacts
# ---------------------------------------------------------------------------
cleanup_site_packages() {
    local site_dir="$1"

    log "Cleaning up site-packages..."

    # Remove compiled bytecode
    find "$site_dir" -name "*.pyc" -delete 2>/dev/null || true
    find "$site_dir" -name "*.pyo" -delete 2>/dev/null || true

    # Remove __pycache__ directories
    find "$site_dir" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

    # Remove pip/setuptools dist-info (not needed at runtime)
    find "$site_dir" -maxdepth 2 -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true

    # Remove test directories embedded in packages
    find "$site_dir" -maxdepth 3 \( -name "tests" -o -name "test" \) -type d \
        -exec rm -rf {} + 2>/dev/null || true

    # Remove .pth files that reference absolute host paths (not portable)
    find "$site_dir" -maxdepth 1 -name "*.pth" -delete 2>/dev/null || true

    # Remove bin/ scripts (we use the embedded Python directly, not entry points)
    rm -rf "${site_dir:?}/bin" 2>/dev/null || true

    log "Cleanup complete."
}

# ---------------------------------------------------------------------------
# Print a manifest of installed packages for audit/provenance
# ---------------------------------------------------------------------------
print_manifest() {
    local site_dir="$1"
    log "Installed packages:"
    # List top-level package directories (depth 1)
    find "$site_dir" -maxdepth 1 -mindepth 1 -type d \
        | sort \
        | while read -r pkg; do
            echo "  $(basename "$pkg")"
        done
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    mkdir -p "$SITE_PACKAGES"

    # Read top-level requirements
    mapfile -t TOP_LEVEL_PKGS < <(parse_requirements "$REQUIREMENTS_FILE")

    if [[ ${#TOP_LEVEL_PKGS[@]} -eq 0 ]]; then
        die "No packages found in requirements file: ${REQUIREMENTS_FILE}"
    fi

    log "Requirements file: ${REQUIREMENTS_FILE}"
    log "Top-level packages: ${TOP_LEVEL_PKGS[*]}"
    log "Target platform: ${PIP_PLATFORM}"
    log "Target Python: ${PYTHON_VERSION_TAG}"

    # Install all top-level packages in one pip invocation.
    # pip resolves the full transitive dependency graph, so we don't need to
    # manually enumerate transitives — but they are documented in TRANSITIVE_DEPS
    # at the top of this script for reference.
    install_packages "$SITE_PACKAGES" "${TOP_LEVEL_PKGS[@]}"

    cleanup_site_packages "$SITE_PACKAGES"
    print_manifest "$SITE_PACKAGES"

    # Emit a summary of what was installed and approximate size
    local size_kb
    size_kb=$(du -sk "$SITE_PACKAGES" | awk '{print $1}')
    log "site-packages size: ${size_kb} KB"
    log "Done. Vendored dependencies written to: ${SITE_PACKAGES}"
}

main
