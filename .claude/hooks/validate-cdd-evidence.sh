#!/usr/bin/env bash
# PreToolUse hook: Triggered before `gh pr merge`
# Validates that CDD evidence comments exist on the linked GitHub Issue
# Checks for a "CDD Evidence" marker string in issue comments

set -euo pipefail

PROJECT_DIR="/Users/proth/repos/kmflow"
REPO="proth1/kmflow"

# Extract issue number from branch name
BRANCH=$(git -C "${PROJECT_DIR}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
ISSUE_NUMBER=""
if [[ "${BRANCH}" =~ ^feature/([0-9]+)- ]]; then
    ISSUE_NUMBER="${BASH_REMATCH[1]}"
fi

# If no issue number found, skip validation (might be a hotfix branch)
if [[ -z "${ISSUE_NUMBER}" ]]; then
    exit 0
fi

# Check if gh CLI is available
if ! command -v gh &>/dev/null; then
    exit 0
fi

# Fetch issue comments and look for CDD evidence markers
COMMENTS=$(gh api "repos/${REPO}/issues/${ISSUE_NUMBER}/comments" --jq '.[].body' 2>/dev/null || echo "")

if [[ -z "${COMMENTS}" ]]; then
    cat <<EOF
{
  "decision": "block",
  "reason": "MERGE BLOCKED: No comments found on issue #${ISSUE_NUMBER}. CDD requires evidence (pipeline results, test coverage, security scan) posted as issue comments before merge.\n\nRun the pipeline-orchestrator to generate and post evidence:\n  claude -a pipeline-orchestrator\n\nThen post CDD evidence to issue #${ISSUE_NUMBER}."
}
EOF
    exit 0
fi

# Check for CDD evidence markers in comments
MISSING_EVIDENCE=()

if ! echo "${COMMENTS}" | grep -qi "CDD Evidence"; then
    MISSING_EVIDENCE+=("CDD Evidence comment (containing pipeline results)")
fi

# If evidence is missing, block with specifics
if [[ ${#MISSING_EVIDENCE[@]} -gt 0 ]]; then
    MISSING_LIST=""
    for item in "${MISSING_EVIDENCE[@]}"; do
        MISSING_LIST="${MISSING_LIST}\n  - ${item}"
    done

    cat <<EOF
{
  "decision": "block",
  "reason": "MERGE BLOCKED: Missing CDD evidence on issue #${ISSUE_NUMBER}:${MISSING_LIST}\n\nPost pipeline results as a CDD Evidence comment on the issue before merging. The post-pipeline-evidence.sh hook does this automatically after pipeline-orchestrator completes."
}
EOF
    exit 0
fi

# Evidence found — allow merge
cat <<EOF
{
  "hookSpecificOutput": {
    "additionalContext": "CDD evidence validation PASSED for issue #${ISSUE_NUMBER}. Evidence comments found on the issue."
  }
}
EOF
