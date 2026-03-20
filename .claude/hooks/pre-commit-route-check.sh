#!/usr/bin/env bash
# Pre-commit hook: Check FastAPI route decorators for missing response_model
# This is a warning-only check — it does not block commits.
#
# Usage: Called automatically by Claude Code hooks on file save/commit
# Manual: bash .claude/hooks/pre-commit-route-check.sh

set -euo pipefail

ROUTES_DIR="src/api/routes"

if [ ! -d "$ROUTES_DIR" ]; then
    exit 0
fi

# Find route decorators without response_model
VIOLATIONS=$(grep -rn '@router\.\(get\|post\|put\|patch\|delete\)(' "$ROUTES_DIR" \
    | grep -v 'response_model' \
    | grep -v '# noqa' \
    | grep -v '__pycache__' \
    || true)

if [ -n "$VIOLATIONS" ]; then
    COUNT=$(echo "$VIOLATIONS" | wc -l | tr -d ' ')
    echo "⚠️  Route compliance: $COUNT route decorator(s) missing response_model="
    echo "$VIOLATIONS" | head -10
    if [ "$COUNT" -gt 10 ]; then
        echo "  ... and $((COUNT - 10)) more"
    fi
    echo ""
    echo "See .claude/rules/fastapi-routes.md for the response_model requirement."
fi

# Check for bare except Exception without justification
BARE_EXCEPT=$(grep -rn 'except Exception' src/ \
    --include="*.py" \
    | grep -v '# Intentionally broad' \
    | grep -v '__pycache__' \
    | grep -v 'tests/' \
    || true)

if [ -n "$BARE_EXCEPT" ]; then
    COUNT=$(echo "$BARE_EXCEPT" | wc -l | tr -d ' ')
    echo "⚠️  Error handling: $COUNT broad except Exception without justification comment"
    echo "$BARE_EXCEPT" | head -5
    if [ "$COUNT" -gt 5 ]; then
        echo "  ... and $((COUNT - 5)) more"
    fi
    echo ""
    echo "See .claude/rules/error-handling.md for exception handling standards."
fi
