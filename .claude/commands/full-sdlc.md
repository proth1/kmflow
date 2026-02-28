# Full SDLC Workflow

Execute the complete Software Development Lifecycle for a work item.

## Prerequisites
- GitHub Issues configured (proth1/kmflow)
- Git worktrees for isolated development
- Memory bank initialized at `.claude/memory-bank/`

## Workflow Phases

### Phase 1: Work Item Management
1. **Identify the work item**: Get the GitHub Issue number (e.g., #123)
2. **Read the issue**: `gh issue view 123 --repo proth1/kmflow`
3. **Verify acceptance criteria**: Ensure the issue has Gherkin BDD scenarios
4. **Update issue status**: Add `status:in-progress` label, remove `status:ready`
5. **Update activeContext.md**: Record the work item being started

### Phase 2: CDD Compliance Setup
1. **Review CDD config**: Read `.claude/config/cdd-config.yaml`
2. **Identify required evidence**: Based on issue type (story, task, bug)
3. **Create evidence tracking**: Note required deliverables (tests, coverage, security scan)

### Phase 3: Implementation
1. **Create feature branch**: `git checkout -b feature/{issue}-{description}`
   - Auto-applies `cdd:evidence-required` label to the issue (label-taxonomy automation)
2. **Create worktree** (if needed): `git worktree add ../kmflow-{issue} feature/{issue}-{description}`
3. **Implement the changes**: Write code following coding standards (`.claude/rules/coding-standards.md`)
4. **Write tests**: pytest unit tests, >80% coverage target
5. **Run pipeline**: Use pipeline-orchestrator (`claude -a pipeline-orchestrator`) to validate:
   - Backend lint (ruff check)
   - Backend format (ruff format --check)
   - Backend type check (mypy)
   - Backend tests with coverage
   - WGI subsystem test suites (when applicable):
     - Correlation Engine — correlation quality and diagnostic checks
     - VCE Pipeline — VCE privacy compliance and output validation
     - Switching Sequences — sequence correctness and state transition tests
     - ABAC PDP — policy decision point authorization tests
   - Frontend tests (if applicable)
   - Security scan (pip-audit + npm audit)
   - **Creates `.pipeline-passed` marker** on success (required for merge)
   - **Generates `.pipeline-report.md`** (posted as CDD evidence on issue)

### Phase 4: Commit, Push, and Pull Request
1. **Stage changes**: `git add` specific files (never `git add -A`)
2. **Commit**: Descriptive message referencing the issue
3. **Push**: `git push -u origin feature/{issue}-{description}`
4. **Post CDD evidence**: Pipeline results are auto-posted to the issue by `post-pipeline-evidence.sh`
5. **Create PR**: Use `gh pr create` with:
   - Title: Short, descriptive (<70 chars)
   - Body: `Closes #{issue}` + summary + test plan
   - Labels matching issue labels

### Phase 5: PR Review
1. **Mandatory**: Run `pr-orchestrator` (opus, background) for comprehensive review
2. **9 review agents** analyze: code quality, security, architecture, performance, dependencies, test coverage, design review, bundle analysis
3. **Wait for results**: Review findings before proceeding

### Phase 6: Address Review Findings
1. **Fix critical/high findings**: Must be resolved before merge
2. **Acknowledge medium/low**: Document rationale if not fixing
3. **Re-run pipeline**: Verify fixes don't break anything
4. **Push fixes**: Additional commits on the same branch

### Phase 7: Post-Merge Updates
After PR is merged (triggered by post-merge hook):
1. **Update CHANGELOG.md**: CalVer entry (YYYY.MM.MICRO format)
2. **Update .current-version**: Increment version
3. **Update platformState.md**: Recent releases table, quick stats
4. **Update activeContext.md**: Clear current work, note completion
5. **Remove worktree**: `git worktree remove ../kmflow-{issue}`
6. **Delete feature branch**: `git branch -d feature/{issue}-{description}`
7. **Pull main**: `git checkout main && git pull`
8. **Close issue**: Update labels to `status:done` (auto-closed by `Closes #` if PR linked)

## Rules
- **Every change needs a work item**: No commits without a GitHub Issue
- **Always use worktrees**: Isolate feature work from main
- **PR review is mandatory**: Never merge without pr-orchestrator review
- **Post-merge updates are mandatory**: CHANGELOG, version, memory bank
- **Evidence collection**: Tests, coverage, security scan results attached to issue

## Quick Reference
```bash
# Start work on issue #123
gh issue view 123 --repo proth1/kmflow
git checkout -b feature/123-add-feature
git worktree add ../kmflow-123 feature/123-add-feature

# After implementation
git push -u origin feature/123-add-feature
gh pr create --title "Add feature X" --body "Closes #123\n\n## Summary\n..."

# After merge
git checkout main && git pull
git worktree remove ../kmflow-123
git branch -d feature/123-add-feature
```
