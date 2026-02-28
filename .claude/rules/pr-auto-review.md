# Mandatory PR Review

Every pull request MUST be reviewed by the `pr-orchestrator` agent before merge.

## Trigger
When a PR is created via `gh pr create`, the `pr-created-hook.sh` hook
automatically launches the pr-orchestrator in the background.

## Manual Invocation
If the hook doesn't fire, manually invoke:
```
Task(subagent_type="pr-orchestrator", model="opus", prompt="Review PR #NNN in proth1/kmflow")
```

## Review Agents (9 total)
1. **code-quality-reviewer** — Standards compliance, best practices
2. **security-reviewer** — Vulnerability analysis, OWASP checks
3. **architecture-reviewer** — Design patterns, structural integrity
4. **performance-analyzer** — Performance implications, bottlenecks
5. **dependency-checker** — Version compatibility, supply chain
6. **test-coverage-analyzer** — Test quality, coverage gaps
7. **design-review** — UI/UX for frontend changes
8. **bundle-analyzer** — Bundle size for frontend changes
9. **critical-thinking** — Systematic analysis of approach

## Policy
- Critical/High findings MUST be addressed before merge
- Medium findings SHOULD be addressed (document rationale if skipping)
- Low findings are informational
- Never merge without at least running the review

## Pre-Merge Gates (Blocking)
Before `gh pr merge` is allowed, two PreToolUse hooks enforce:
1. **Pipeline check** (`detect-merge-to-main.sh`): `.pipeline-passed` marker must exist and be <4h old
2. **Evidence check** (`validate-cdd-evidence.sh`): CDD evidence comments must exist on the linked issue

Both hooks will **block** the merge command if their conditions are not met.
