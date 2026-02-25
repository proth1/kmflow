#!/usr/bin/env bash
# PostToolUse hook: Secondary PR creation notification
# Provides colored terminal output and work item reminders

set -euo pipefail

TOOL_OUTPUT="${CLAUDE_TOOL_OUTPUT:-}"

# ANSI colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Extract PR info
PR_URL=$(echo "${TOOL_OUTPUT}" | grep -oE 'https://github.com/[^ ]+/pull/[0-9]+' | head -1)
PR_NUMBER=$(echo "${PR_URL}" | grep -oE '[0-9]+$')

# Extract issue from branch
BRANCH=$(git -C /Users/proth/repos/kmflow rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
ISSUE_NUMBER=""
if [[ "${BRANCH}" =~ ^feature/([0-9]+)- ]]; then
    ISSUE_NUMBER="${BASH_REMATCH[1]}"
fi

if [[ -n "${PR_URL}" ]]; then
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  PR #${PR_NUMBER} Created Successfully${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  URL: ${PR_URL}${NC}"
    if [[ -n "${ISSUE_NUMBER}" ]]; then
        echo -e "${CYAN}  Issue: #${ISSUE_NUMBER}${NC}"
    fi
    echo -e "${YELLOW}  REMINDER: PR requires human approval before merge${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
fi
