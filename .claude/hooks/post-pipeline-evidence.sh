#!/usr/bin/env bash
# PostToolUse hook: After pipeline-orchestrator completes, post results as CDD evidence
# Triggered after the pipeline-orchestrator agent finishes (manual invocation)
# Posts pipeline results as a GitHub Issue comment for traceability

set -euo pipefail

PROJECT_DIR="/Users/proth/repos/kmflow"
REPO="proth1/kmflow"
PIPELINE_MARKER="${PROJECT_DIR}/.pipeline-passed"
PIPELINE_REPORT="${PROJECT_DIR}/.pipeline-report.md"

# Extract issue number from branch name
BRANCH=$(git -C "${PROJECT_DIR}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
ISSUE_NUMBER=""
if [[ "${BRANCH}" =~ ^feature/([0-9]+)- ]]; then
    ISSUE_NUMBER="${BASH_REMATCH[1]}"
fi

# If no issue number, nothing to post to
if [[ -z "${ISSUE_NUMBER}" ]]; then
    exit 0
fi

# Check if pipeline report exists (created by pipeline-orchestrator)
if [[ ! -f "${PIPELINE_REPORT}" ]]; then
    exit 0
fi

# Read pipeline results
PIPELINE_RESULTS=$(cat "${PIPELINE_REPORT}")
if [[ -f "${PIPELINE_MARKER}" ]]; then
    PIPELINE_STATUS="PASSED"
else
    PIPELINE_STATUS="FAILED"
fi

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Build CDD evidence comment
EVIDENCE_BODY=$(cat <<EVIDENCE
## CDD Evidence: Pipeline Results

**Type**: \`test_results\`, \`code_coverage\`, \`security_scan\`
**Status**: ${PIPELINE_STATUS}
**Branch**: \`${BRANCH}\`
**Timestamp**: ${TIMESTAMP}

### Pipeline Output

${PIPELINE_RESULTS}

---
*Auto-posted by CDD enforcement hook*
EVIDENCE
)

# Post to GitHub Issue
gh issue comment "${ISSUE_NUMBER}" --repo "${REPO}" --body "${EVIDENCE_BODY}" 2>/dev/null || true

cat <<EOF
{
  "hookSpecificOutput": {
    "additionalContext": "CDD EVIDENCE POSTED: Pipeline results (${PIPELINE_STATUS}) posted as evidence comment on issue #${ISSUE_NUMBER}."
  }
}
EOF
