# Mandatory PR Review Workflow

These rules apply to ALL code changes in the KMFlow repository.

## Hard Constraints

1. **NEVER commit directly to `main`**: All work MUST go through feature
   branches (`feature/{issue}-{description}`) and pull requests. The only
   exception is trivial documentation fixes (typos, formatting) with no
   code changes.

2. **NEVER merge without pr-orchestrator**: Every PR MUST be reviewed by
   the `pr-orchestrator` subagent before merge. No exceptions for code
   changes. The orchestrator dispatches the appropriate subset of review
   agents based on change type.

3. **Agent selection is change-driven**: pr-orchestrator modulates which
   agents fire based on the diff content:
   - UI changes (`.tsx`, `.css`) → design-review + code-quality + security
   - API changes (`.py`, routes) → security-reviewer + architecture-reviewer
   - Config/infra changes → dependency-checker + security-reviewer
   - All PRs → critical-thinking (bookends), test-coverage-analyzer, playwright-e2e-tester

4. **Critical-thinking bookends are mandatory**: Every review starts AND
   ends with a critical-thinking pass. First pass analyzes approach and
   risks. Final pass validates review completeness and flags gaps.

5. **Playwright E2E testing is mandatory**: The playwright-e2e-tester
   agent runs the full E2E suite on every PR. New UI pages require
   corresponding E2E test coverage.

6. **CRITICAL and HIGH issues block merge**: Any finding rated CRITICAL
   or HIGH by any review agent MUST be resolved before merge. MEDIUM
   findings should be addressed but do not block. LOW findings are
   advisory.

## Branch Naming

```
feature/{issue-number}-{description}
```

Example: `feature/67-phase6-fixes`

## PR Creation Checklist

Before creating a PR:
- [ ] Feature branch created from `main`
- [ ] All tests pass locally (`pytest src/` and `cd frontend && npm test`)
- [ ] E2E tests pass (`cd frontend && npx playwright test`)
- [ ] No secrets or credentials in diff
- [ ] PR body includes `Closes #{issue}` for auto-close

## PR Review Sequence

1. Create PR with description and test plan
2. Run pr-orchestrator against the PR
3. Review findings — fix CRITICAL/HIGH issues
4. Re-run pr-orchestrator if significant changes made
5. Merge when all CRITICAL/HIGH resolved

## Failure Mode Checklist

If code was committed directly to main without review:
- [ ] Do NOT rewrite history (no force-push, no rebase)
- [ ] Run pr-orchestrator retroactively against the diff range
- [ ] Create a fix branch for any CRITICAL/HIGH findings
- [ ] Fix issues via proper PR workflow
- [ ] Document the incident to prevent recurrence
