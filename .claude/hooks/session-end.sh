#!/usr/bin/env bash
# SessionEnd hook: Capture session state for continuity
# Saves branch, last commit, uncommitted changes to .session-state.json
# Appends warning to activeContext.md if not updated during session

set -euo pipefail

PROJECT_DIR="/Users/proth/repos/kmflow"
MEMORY_BANK_DIR="${PROJECT_DIR}/.claude/memory-bank"
STATE_FILE="${PROJECT_DIR}/.session-state.json"

# Capture current state
BRANCH=$(git -C "${PROJECT_DIR}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
LAST_COMMIT=$(git -C "${PROJECT_DIR}" log -1 --format="%H %s" 2>/dev/null || echo "unknown")
UNCOMMITTED=$(git -C "${PROJECT_DIR}" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Write session state
cat > "${STATE_FILE}" <<STATEJSON
{
  "branch": "${BRANCH}",
  "lastCommit": "${LAST_COMMIT}",
  "uncommittedChanges": ${UNCOMMITTED},
  "endedAt": "${TIMESTAMP}"
}
STATEJSON

# Check if activeContext.md was updated during this session
if [[ -f "${MEMORY_BANK_DIR}/activeContext.md" ]]; then
    LAST_MODIFIED=$(stat -f "%m" "${MEMORY_BANK_DIR}/activeContext.md" 2>/dev/null || echo "0")
    # If not modified in the last 2 hours, append warning
    CUTOFF=$(( $(date +%s) - 7200 ))
    if [[ "${LAST_MODIFIED}" -lt "${CUTOFF}" ]]; then
        echo "" >> "${MEMORY_BANK_DIR}/activeContext.md"
        echo "---" >> "${MEMORY_BANK_DIR}/activeContext.md"
        echo "> SESSION END WARNING (${TIMESTAMP}): activeContext.md was NOT updated during this session." >> "${MEMORY_BANK_DIR}/activeContext.md"
        echo "> Branch: ${BRANCH}, Uncommitted: ${UNCOMMITTED}" >> "${MEMORY_BANK_DIR}/activeContext.md"
    fi
fi

# Auto-archive old evidence files (>30 days)
EVIDENCE_DIR="${PROJECT_DIR}/evidence"
ARCHIVE_DIR="${EVIDENCE_DIR}/archive"
if [[ -d "${EVIDENCE_DIR}" ]]; then
    mkdir -p "${ARCHIVE_DIR}"
    find "${EVIDENCE_DIR}" -maxdepth 1 -name "*.md" -mtime +30 -exec mv {} "${ARCHIVE_DIR}/" \; 2>/dev/null || true
fi

echo "Session state saved to ${STATE_FILE}"
