#!/usr/bin/env bash
# PostToolUse hook: Triggered after Write|Edit on source files
# Reminds to document architectural decisions in decisionLog.md

set -euo pipefail

TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"

# Extract the file path being written/edited
FILE_PATH=""
if [[ -n "${TOOL_INPUT}" ]]; then
    FILE_PATH=$(echo "${TOOL_INPUT}" | grep -oE '"file_path"\s*:\s*"[^"]+"' | head -1 | sed 's/.*"file_path"\s*:\s*"//;s/"//')
fi

# Only check for architecture-significant files
ARCH_PATTERNS=(
    "src/core/config"
    "src/core/database"
    "src/core/models"
    "src/api/main"
    "src/api/middleware"
    "src/semantic/ontology"
    "alembic/versions"
    "docker-compose"
    "infrastructure/"
    "CLAUDE.md"
)

IS_ARCHITECTURAL=false
for pattern in "${ARCH_PATTERNS[@]}"; do
    if echo "${FILE_PATH}" | grep -q "${pattern}"; then
        IS_ARCHITECTURAL=true
        break
    fi
done

# Also check file contents for architecture keywords
if [[ "${IS_ARCHITECTURAL}" == "false" ]] && [[ -n "${FILE_PATH}" ]] && [[ -f "${FILE_PATH}" ]]; then
    if grep -qiE '(breaking change|migration|new table|new model|new endpoint|security|authentication|authorization|encryption)' "${FILE_PATH}" 2>/dev/null; then
        IS_ARCHITECTURAL=true
    fi
fi

if [[ "${IS_ARCHITECTURAL}" == "true" ]]; then
    DECISION_LOG="/Users/proth/repos/kmflow/.claude/memory-bank/decisionLog.md"
    LAST_MODIFIED=0
    if [[ -f "${DECISION_LOG}" ]]; then
        LAST_MODIFIED=$(stat -f "%m" "${DECISION_LOG}" 2>/dev/null || echo "0")
    fi
    NOW=$(date +%s)
    DIFF=$(( NOW - LAST_MODIFIED ))

    # Only remind if decision log hasn't been updated in the last 30 minutes
    if [[ "${DIFF}" -gt 1800 ]]; then
        cat <<EOF
{
  "hookSpecificOutput": {
    "additionalContext": "ARCHITECTURE REMINDER: You modified an architecture-significant file (${FILE_PATH}). Consider documenting this decision in .claude/memory-bank/decisionLog.md if it involves: new patterns, breaking changes, security decisions, schema changes, or infrastructure modifications."
  }
}
EOF
    fi
fi
