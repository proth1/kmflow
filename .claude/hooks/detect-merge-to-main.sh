#!/usr/bin/env bash
# PostToolUse hook: Triggered after `gh pr merge`
# Reminds the agent to run the pipeline-orchestrator before merging
# and to verify pipeline passed.

set -euo pipefail

cat <<'EOF'
{
  "hookSpecificOutput": {
    "additionalContext": "MERGE DETECTED: Remember that CI/CD runs locally via the pipeline-orchestrator agent, NOT GitHub Actions. If you haven't already run the pipeline for this branch, do so now with: claude -a pipeline-orchestrator\n\nThe pipeline-orchestrator replaces .github/workflows/ci.yml entirely."
  }
}
EOF
