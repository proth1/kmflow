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

### Step 7: Report Summary and CDD Evidence
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

### Step 8: CDD Pipeline Marker
After generating the report, write the results for CDD evidence tracking:

1. **Write pipeline report** to `.pipeline-report.md` with the summary table above
2. **If ALL steps passed**: Create `.pipeline-passed` marker file with the timestamp
3. **If ANY step failed**: Remove `.pipeline-passed` if it exists (stale from prior run)

```bash
# On success:
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > /Users/proth/repos/kmflow/.pipeline-passed

# On failure:
rm -f /Users/proth/repos/kmflow/.pipeline-passed
```

The `.pipeline-passed` marker is checked by the pre-merge hook to enforce that the pipeline has been run before allowing merge.

3. **Post CDD evidence to GitHub Issue**: Run the evidence posting script to auto-post pipeline results as a CDD evidence comment on the linked issue:
```bash
bash /Users/proth/repos/kmflow/.claude/hooks/post-pipeline-evidence.sh
```
This script reads `.pipeline-report.md`, determines pass/fail from `.pipeline-passed`, and posts a structured CDD Evidence comment on the GitHub Issue linked via the branch name.

## Error Recovery

### Format Failures
Auto-fix with `ruff format src/ tests/` and re-check.

### Mypy Failures
Report exact errors with file:line references.

### Test Failures
Show failing test names and first failure traceback.

### Security Scan Warnings
Distinguish between HIGH (blocking) and lower severity (informational).
