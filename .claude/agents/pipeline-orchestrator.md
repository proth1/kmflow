---
name: pipeline-orchestrator
description: Local CI/CD pipeline that replaces GitHub Actions. Runs lint, format, mypy, tests, security scan, and frontend tests. Invoked manually via `/pipeline` or `claude -a pipeline-orchestrator`.
tools:
  - Bash
  - Read
  - Write
  - Grep
  - Glob
model: sonnet
---

# Pipeline Orchestrator SubAgent

## SubAgent Metadata
**Type**: CI/CD Orchestrator
**Scope**: Lint, Format, Type Check, Test, Security Scan
**Manual**: `claude -a pipeline-orchestrator` or `/pipeline`
**Version**: 1.0.0

## Purpose
Execute the full CI/CD pipeline locally using Claude Code as the execution engine.
This is the sole CI/CD mechanism for KMFlow — there is no GitHub Actions CI workflow.

Pipeline steps run sequentially (fail-fast):
1. Backend lint (ruff check)
2. Backend format check (ruff format --check)
3. Backend type check (mypy)
4. Backend tests with coverage
5. Frontend tests
6. Security scan (pip-audit + npm audit)

## Execution

Run all steps from the project root `/Users/proth/repos/kmflow`.

### Step 1: Backend Lint
```bash
python -m ruff check /Users/proth/repos/kmflow/src/ /Users/proth/repos/kmflow/tests/
```
If this fails, report the errors and stop.

### Step 2: Backend Format Check
```bash
python -m ruff format --check /Users/proth/repos/kmflow/src/ /Users/proth/repos/kmflow/tests/
```
If this fails, offer to auto-fix with `ruff format /Users/proth/repos/kmflow/src/ /Users/proth/repos/kmflow/tests/`.

### Step 3: Backend Type Check
```bash
python -m mypy /Users/proth/repos/kmflow/src/ --ignore-missing-imports
```
If this fails, report the errors and stop.

### Step 4: Backend Tests
```bash
python -m pytest tests/ -v --cov=src --cov-report=term-missing --cov-fail-under=80
```
Report pass/fail count and coverage percentage.

### Step 5: Frontend Tests
```bash
cd /Users/proth/repos/kmflow/frontend && npx jest --passWithNoTests
```
Report pass/fail count.

### Step 6: Security Scan
```bash
cd /Users/proth/repos/kmflow
pip freeze | grep -v '^\-e' | grep -iv '^kmflow' > /tmp/audit-reqs.txt && pip-audit --strict --desc -r /tmp/audit-reqs.txt 2>&1 || echo "pip-audit found issues"
cd frontend && npm audit --audit-level=high 2>&1 || echo "npm audit found issues"
```

### Step 7: Report Summary
Output a consolidated status table:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PIPELINE RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step                    Status
──────────────────────  ──────
Backend Lint            PASS/FAIL
Backend Format          PASS/FAIL
Backend Type Check      PASS/FAIL
Backend Tests           PASS (N passed)
Frontend Tests          PASS (N passed)
Security Scan           PASS/WARN

Overall: PASS / FAIL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Error Recovery

### Format Failures
Auto-fix with `ruff format src/ tests/` and re-check.

### Mypy Failures
Report exact errors with file:line references.

### Test Failures
Show failing test names and first failure traceback.

### Security Scan Warnings
Distinguish between HIGH (blocking) and lower severity (informational).
