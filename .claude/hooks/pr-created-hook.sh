#!/usr/bin/env bash
# PostToolUse hook: Triggered after `gh pr create`
# Extracts PR URL/number and instructs Claude to run pr-orchestrator review

set -euo pipefail

TOOL_OUTPUT="${CLAUDE_TOOL_OUTPUT:-}"

# Extract PR URL and number from gh pr create output
PR_URL=""
PR_NUMBER=""

if [[ -n "${TOOL_OUTPUT}" ]]; then
    PR_URL=$(echo "${TOOL_OUTPUT}" | grep -oE 'https://github.com/[^ ]+/pull/[0-9]+' | head -1)
    PR_NUMBER=$(echo "${PR_URL}" | grep -oE '[0-9]+$')
fi

# Extract issue number from branch name
BRANCH=$(git -C /Users/proth/repos/kmflow rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
ISSUE_NUMBER=""
if [[ "${BRANCH}" =~ ^feature/([0-9]+)- ]]; then
    ISSUE_NUMBER="${BASH_REMATCH[1]}"
fi

cat <<EOF
{
  "hookSpecificOutput": {
    "additionalContext": "PR CREATED HOOK TRIGGERED. PR #${PR_NUMBER:-unknown} created at ${PR_URL:-unknown}. Related issue: #${ISSUE_NUMBER:-unknown}.\n\nMANDATORY: You MUST now launch the pr-orchestrator agent (opus, background) for comprehensive PR review. Use:\n\nTask(subagent_type='pr-orchestrator', model='opus', run_in_background=true, prompt='Comprehensive review of PR #${PR_NUMBER:-unknown} in proth1/kmflow. PR URL: ${PR_URL:-unknown}')\n\nAlso update the issue #${ISSUE_NUMBER:-unknown} status label from status:in-progress to status:in-review.\n\nREMINDER: PR requires human approval before merge. Do not merge without explicit user confirmation."
  }
}
EOF
