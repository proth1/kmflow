#!/usr/bin/env bash
# SessionStart hook: Load lightweight context for KMFlow sessions
# Provides quick orientation: Docker status, branch, last session summary

set -uo pipefail

MEMORY_BANK_DIR="/Users/proth/repos/kmflow/.claude/memory-bank"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "KMFlow Session Context"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Current branch
BRANCH=$(git -C /Users/proth/repos/kmflow rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
echo "Branch: ${BRANCH}"

# Version
if [[ -f /Users/proth/repos/kmflow/.current-version ]]; then
    VERSION=$(cat /Users/proth/repos/kmflow/.current-version)
    echo "Version: ${VERSION}"
fi

# Docker services status
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    RUNNING=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -E 'postgres|neo4j|redis' | tr '\n' ', ' | sed 's/,$//')
    if [[ -n "${RUNNING}" ]]; then
        echo "Docker: ${RUNNING}"
    else
        echo "Docker: No KMFlow services running"
    fi
else
    echo "Docker: Not available"
fi

# Last session summary from activeContext.md
if [[ -f "${MEMORY_BANK_DIR}/activeContext.md" ]]; then
    echo ""
    echo "── Last Session ──"
    # Extract the Current Focus section (first 5 lines)
    awk '/^## Current Focus/{found=1; next} /^##/{found=0} found' "${MEMORY_BANK_DIR}/activeContext.md" | head -5
fi

# Uncommitted changes
CHANGES=$(git -C /Users/proth/repos/kmflow status --porcelain 2>/dev/null | wc -l | tr -d ' ')
if [[ "${CHANGES}" -gt 0 ]]; then
    echo ""
    echo "WARNING: ${CHANGES} uncommitted changes in working tree"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
