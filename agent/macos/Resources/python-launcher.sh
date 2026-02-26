#!/bin/bash
# python-launcher.sh — Shell shim that launches the embedded Python interpreter.
#
# This file is installed as Contents/MacOS/kmflow-python inside the .app bundle.
# It is invoked by the Swift binary (KMFlowAgent) via NSTask or posix_spawn
# whenever it needs to delegate work to the Python intelligence layer.
#
# The shim resolves all paths relative to its own location inside the bundle,
# so the bundle is fully relocatable — it works regardless of where the user
# installs the .app.
#
# Path resolution:
#   $0                  → .../KMFlowAgent.app/Contents/MacOS/kmflow-python
#   MACOS_DIR           → .../KMFlowAgent.app/Contents/MacOS/
#   CONTENTS_DIR        → .../KMFlowAgent.app/Contents/
#   FRAMEWORKS_DIR      → .../KMFlowAgent.app/Contents/Frameworks/
#   RESOURCES_DIR       → .../KMFlowAgent.app/Contents/Resources/
#   PYTHON_HOME         → .../Contents/Frameworks/Python.framework/Versions/3.12/
#   PYTHON_BIN          → .../Contents/Frameworks/Python.framework/Versions/3.12/bin/python3.12
#   PYTHONPATH          → .../Contents/Resources/python
#
# Usage (from Swift):
#   exec $BUNDLE/Contents/MacOS/kmflow-python [args...]
#
# Usage (manual / testing):
#   /Applications/KMFlowAgent.app/Contents/MacOS/kmflow-python --version
#   /Applications/KMFlowAgent.app/Contents/MacOS/kmflow-python -m kmflow_agent status

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve bundle paths from this script's location
# ---------------------------------------------------------------------------

# Resolve the real path of this script, following symlinks if needed.
# We use a portable approach that works on macOS without GNU readlink -f.
_resolve_script_dir() {
    local source="${BASH_SOURCE[0]}"
    local dir
    # Follow symlinks until we reach the actual file
    while [[ -L "$source" ]]; do
        dir="$(cd -P "$(dirname "$source")" && pwd)"
        source="$(readlink "$source")"
        # If the symlink was relative, make it absolute
        [[ "$source" != /* ]] && source="${dir}/${source}"
    done
    cd -P "$(dirname "$source")" && pwd
}

MACOS_DIR="$(_resolve_script_dir)"
CONTENTS_DIR="$(dirname "$MACOS_DIR")"
FRAMEWORKS_DIR="${CONTENTS_DIR}/Frameworks"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"

# ---------------------------------------------------------------------------
# Embedded Python configuration
# ---------------------------------------------------------------------------
PYTHON_VERSION="3.12"
PYTHON_FRAMEWORK="${FRAMEWORKS_DIR}/Python.framework"
PYTHON_HOME="${PYTHON_FRAMEWORK}/Versions/${PYTHON_VERSION}"
PYTHON_BIN="${PYTHON_HOME}/bin/python${PYTHON_VERSION}"

# ---------------------------------------------------------------------------
# Validate the embedded interpreter exists
# ---------------------------------------------------------------------------
if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "ERROR [kmflow-python]: Embedded Python interpreter not found." >&2
    echo "  Expected: ${PYTHON_BIN}" >&2
    echo "  The .app bundle may be incomplete or corrupted." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

# PYTHONHOME tells the interpreter where to find its standard library and
# site-packages. We point it at the embedded framework so it never falls back
# to a system Python installation.
export PYTHONHOME="${PYTHON_HOME}"

# PYTHONPATH prepends our Resources/python directory so that:
#   - kmflow_agent/ (the intelligence layer package) is importable
#   - site-packages/ (vendored deps) is importable
# The site-packages path is included explicitly because PYTHONHOME alone
# configures the stdlib path, not our vendored extras directory.
# Do NOT inherit the caller's PYTHONPATH — it may contain incompatible packages
# or inject untrusted code into the embedded interpreter.
export PYTHONPATH="${RESOURCES_DIR}/python:${RESOURCES_DIR}/python/site-packages"

# Prevent the embedded interpreter from picking up user-level site-packages
# from ~/.local or system locations (avoids version conflicts on developer machines).
export PYTHONNOUSERSITE=1

# Disable .pth file processing in site-packages to avoid unintended path additions.
# Our vendored deps are on PYTHONPATH directly so this is safe.
export PYTHONPATH_ISOLATE=1

# Set a deterministic locale to avoid encoding issues when the agent is
# launched as a background process without a full login session.
export PYTHONIOENCODING="utf-8"
export PYTHONUTF8=1

# Propagate the bundle's Contents dir so Python code can locate bundle
# resources without re-deriving the path.
export KMFLOW_BUNDLE_CONTENTS="${CONTENTS_DIR}"
export KMFLOW_BUNDLE_RESOURCES="${RESOURCES_DIR}"

# ---------------------------------------------------------------------------
# Add the embedded framework's dylib to the dynamic linker search path.
# This ensures extension modules (.so) can dlopen libpython3.12.dylib
# even if the system DYLD_LIBRARY_PATH doesn't include our Frameworks dir.
# Note: DYLD_LIBRARY_PATH is stripped by SIP for protected binaries, but
# our unprotected Python interpreter is not affected.
# ---------------------------------------------------------------------------
DYLD_LIBRARY_PATH="${PYTHON_HOME}/lib${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
export DYLD_LIBRARY_PATH

# ---------------------------------------------------------------------------
# Exec the embedded interpreter
#
# If no arguments are supplied, default to running the kmflow_agent module
# so that `kmflow-python` alone is equivalent to `python -m kmflow_agent`.
# Explicit arguments (e.g., -m some.module, -c "code", a script path) are
# passed through unchanged.
# ---------------------------------------------------------------------------
if [[ $# -eq 0 ]]; then
    exec "$PYTHON_BIN" -m kmflow_agent
else
    exec "$PYTHON_BIN" "$@"
fi
