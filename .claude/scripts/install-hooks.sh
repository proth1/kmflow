#!/usr/bin/env bash
# Install git hooks from .githooks/ into .git/hooks/
# Also installs pre-commit framework hooks for ruff/mypy.
#
# Usage: .claude/scripts/install-hooks.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
HOOKS_SRC="${PROJECT_DIR}/.githooks"
HOOKS_DST="${PROJECT_DIR}/.git/hooks"

echo "Installing git hooks..."

# Copy tracked hooks to .git/hooks/
for hook in "${HOOKS_SRC}"/*; do
    hook_name=$(basename "${hook}")
    cp "${hook}" "${HOOKS_DST}/${hook_name}"
    chmod +x "${HOOKS_DST}/${hook_name}"
    echo "  Installed: ${hook_name}"
done

# Install pre-commit framework hooks (ruff, mypy)
if command -v pre-commit &>/dev/null; then
    echo "  pre-commit framework already integrated via pre-commit hook"
else
    echo "  WARNING: pre-commit not installed. Run: pip install pre-commit && pre-commit install"
fi

echo "Done. Git hooks are active."
