#!/usr/bin/env bash
# PreToolUse hook: Prevents creation/editing of traditional CI/CD pipeline files.
# Wraps prevent-traditional-pipelines.js, extracting the file path from CLAUDE_TOOL_INPUT.

set -euo pipefail

TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"

# Extract file_path from the JSON tool input
FILE_PATH=$(echo "${TOOL_INPUT}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('file_path',''))" 2>/dev/null || echo "")

if [[ -z "${FILE_PATH}" ]]; then
    exit 0
fi

# Check against pipeline patterns
if echo "${FILE_PATH}" | grep -qE '\.github/workflows/.*\.yml$|azure-pipelines.*\.yml$|Jenkinsfile$|\.gitlab-ci\.yml$|\.circleci/config\.yml$'; then
    cat <<EOF
{
  "decision": "block",
  "reason": "ARCHITECTURAL VIOLATION: Traditional CI/CD pipeline detected (${FILE_PATH}). Claude Code IS the CI/CD engine. Use the pipeline-orchestrator agent instead: claude -a pipeline-orchestrator"
}
EOF
    exit 0
fi

exit 0
