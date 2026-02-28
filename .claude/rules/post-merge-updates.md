# Post-Merge Updates (MANDATORY)

After every PR merge to main, the following updates MUST be performed.
This is enforced by the post-merge hook (`.claude/hooks/post-merge-hook.sh`).

## Required Steps

### 1. Update CHANGELOG.md
Add an entry at the top of the changelog:
```markdown
## [YYYY.MM.MICRO] - YYYY-MM-DD
### {Type}
- {Description} (#{issue_number})
```
Where:
- `YYYY.MM.MICRO` is CalVer (year.month.sequential-build)
- Type is one of: Added, Changed, Fixed, Removed, Security, Infrastructure
- Description is a concise summary of the change
- Issue number links to the GitHub Issue

### 2. Update .current-version
Write the new CalVer version string to `.current-version`.

### 3. Update platformState.md
Update the memory bank platform state file (`.claude/memory-bank/platformState.md`):
- Increment the version at the top
- Add the release to the Recent Releases table
- Update Quick Stats if relevant (test count, model count, etc.)

### 4. Update activeContext.md
Update `.claude/memory-bank/activeContext.md`:
- Move current work item to "Recently Completed"
- Clear the "Current Focus" section
- Note any follow-up work items

### 5. Clean Up Worktree
```bash
git worktree remove ../kmflow-{issue}
git branch -d feature/{issue}-{description}
```

### 6. Pull Main
```bash
git checkout main
git pull
```

### 7. Close Issue (if not auto-closed)
If the PR body had `Closes #{issue}`, GitHub auto-closes it.
Otherwise, manually add `status:done` label and close.

## CalVer Format
KMFlow uses Calendar Versioning:
- Format: `YYYY.MM.MICRO` (e.g., `2026.02.192`)
- YYYY = 4-digit year
- MM = 2-digit month (zero-padded)
- MICRO = monotonically incrementing build number (does NOT reset across months)

## Skipping
These updates cannot be skipped. If you encounter issues:
1. Fix the issue
2. Complete all steps
3. Document any anomalies in activeContext.md
