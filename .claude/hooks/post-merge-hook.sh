#!/usr/bin/env bash
# PostToolUse hook: Triggered after `gh pr merge`
# Extracts PR info and instructs Claude to perform post-merge updates

set -euo pipefail

# Extract PR number from the command or stdout
TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"
TOOL_OUTPUT="${CLAUDE_TOOL_OUTPUT:-}"

# Try to extract PR number from command args (gh pr merge 123)
PR_NUMBER=""
if echo "${TOOL_INPUT}" | grep -qoE 'pr merge [0-9]+'; then
    PR_NUMBER=$(echo "${TOOL_INPUT}" | grep -oE 'pr merge ([0-9]+)' | grep -oE '[0-9]+')
fi

# Fallback: extract from stdout
if [[ -z "${PR_NUMBER}" ]] && [[ -n "${TOOL_OUTPUT}" ]]; then
    PR_NUMBER=$(echo "${TOOL_OUTPUT}" | grep -oE '#[0-9]+' | head -1 | tr -d '#')
fi

# Extract issue number from branch name (feature/123-description)
BRANCH=$(git -C /Users/proth/repos/kmflow rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
ISSUE_NUMBER=""
if [[ "${BRANCH}" =~ ^feature/([0-9]+)- ]]; then
    ISSUE_NUMBER="${BASH_REMATCH[1]}"
fi

# Build the hook directive
cat <<EOF
{
  "hookSpecificOutput": {
    "additionalContext": "POST-MERGE HOOK TRIGGERED. PR #${PR_NUMBER:-unknown} merged. Issue #${ISSUE_NUMBER:-unknown}. You MUST now perform ALL post-merge updates as defined in .claude/rules/post-merge-updates.md:\n\n1. Update CHANGELOG.md with CalVer entry\n2. Update .current-version\n3. Update .claude/memory-bank/platformState.md (recent releases table)\n4. Update .claude/memory-bank/activeContext.md (clear current work)\n5. Remove worktree: git worktree remove ../kmflow-${ISSUE_NUMBER:-unknown}\n6. Delete branch: git branch -d feature/${ISSUE_NUMBER:-unknown}-*\n7. Pull main: git checkout main && git pull\n8. Verify issue #${ISSUE_NUMBER:-unknown} is closed (should be auto-closed by Closes # in PR)\n\nDo NOT skip any of these steps."
  }
}
EOF
