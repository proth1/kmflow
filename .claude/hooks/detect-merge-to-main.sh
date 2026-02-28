#!/usr/bin/env bash
# PreToolUse hook: Triggered before `gh pr merge`
# Blocks merge if pipeline has not been run (no .pipeline-passed marker)
# Also validates that the marker is recent (within 4 hours of HEAD commit)

set -euo pipefail

PROJECT_DIR="/Users/proth/repos/kmflow"
PIPELINE_MARKER="${PROJECT_DIR}/.pipeline-passed"

# Check if pipeline marker exists
if [[ ! -f "${PIPELINE_MARKER}" ]]; then
    cat <<'EOF'
{
  "decision": "block",
  "reason": "MERGE BLOCKED: Pipeline has not been run for this branch. You MUST run the pipeline-orchestrator before merging:\n\n  claude -a pipeline-orchestrator\n\nThe pipeline creates a .pipeline-passed marker on success, which is required before merge."
}
EOF
    exit 0
fi

# Check if marker is stale (older than 4 hours)
MARKER_TIME=$(stat -f "%m" "${PIPELINE_MARKER}" 2>/dev/null || echo "0")
NOW=$(date +%s)
DIFF=$(( NOW - MARKER_TIME ))
MAX_AGE=14400  # 4 hours in seconds

if [[ "${DIFF}" -gt "${MAX_AGE}" ]]; then
    cat <<EOF
{
  "decision": "block",
  "reason": "MERGE BLOCKED: Pipeline marker is stale ($(( DIFF / 3600 ))h $(( (DIFF % 3600) / 60 ))m old, max 4h). Re-run the pipeline to verify current code:\n\n  claude -a pipeline-orchestrator"
}
EOF
    exit 0
fi

# Pipeline passed and marker is fresh — allow merge
cat <<'EOF'
{
  "hookSpecificOutput": {
    "additionalContext": "Pipeline check PASSED. Marker is fresh. Merge is allowed.\n\nREMINDER: CI/CD runs locally via the pipeline-orchestrator agent, NOT GitHub Actions."
  }
}
EOF
