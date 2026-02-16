# KMFlow Platform - Development Guide

## Project Overview

KMFlow is an AI-powered Process Intelligence platform for consulting engagements. Evidence-first approach: ingests diverse client evidence, builds semantic knowledge graph, generates confidence-scored process views, and automates TOM gap analysis.

**PRD**: `docs/prd/PRD_KMFlow_Platform.md`

## Architecture

```
Frontend (Next.js 14+, Port 3000)
  -> API Gateway (FastAPI, Port 8000)
    -> Processing Services (Evidence, Semantic, LCD, TOM, Gap, RAG)
      -> Data Layer (PostgreSQL+pgvector, Neo4j, Redis)
```

**Tech Stack**: Python 3.12+ (FastAPI), Next.js 14+ (React 18), Neo4j 5.x, PostgreSQL 15 (pgvector), Redis 7

## Key Directories

```
src/
  api/           # FastAPI routes and endpoints
  core/          # Business logic and domain models
  evidence/      # Evidence ingestion and processing
  semantic/      # Knowledge graph and relationship engine
  pov/           # LCD algorithm and POV generator
  tom/           # TOM alignment and gap analysis
  integrations/  # External system connectors
frontend/
  src/
    components/  # React components
    pages/       # Next.js pages
    lib/         # Client utilities
docs/
  prd/           # Product requirements
  presentations/ # Stakeholder presentations
evidence/        # CDD evidence artifacts
```

## Project Management

- **Tool**: GitHub Issues (configured in `.claude/config/project-management.yaml`)
- **Repository**: `proth1/kmflow`
- **Agent**: Use `github-issues-manager` subagent for issue operations
- **Label Taxonomy**: `.claude/config/label-taxonomy.yaml`
- **Label Sync**: `.claude/scripts/gh-sync-labels.sh proth1/kmflow`

### Issue Hierarchy (Label-Based)
```
Epic (label: epic)
  -> Story (body: "Part of epic #XXX") (label: story)
    -> Task (body: "Related to story #XXX") (label: task)
```

### Branch Format
```
feature/{issue-number}-{description}
```

### PR Linking
Always include `Closes #{issue-number}` in PR body to auto-close issues on merge.

## Git Worktree Conventions

- **Main worktree** (`/repos/kmflow`): PRD, documentation, infrastructure changes
- **Feature worktrees**: Created per-epic for isolated development
- **Naming**: `kmflow-{issue-number}` (e.g., `kmflow-12` for issue #12)
- **Creation**: `git worktree add ../kmflow-{issue} feature/{issue}-{description}`
- **Cleanup**: `git worktree remove ../kmflow-{issue}` after PR merge
- Each worktree has independent dependency installs

## SDLC Phases

### Phase 1 - Strategic Intelligence
- PRD analysis and work item decomposition
- Memory Bank initialization
- Quality gates: `prd_exists`, `work_items_created`

### Phase 2 - Automated Development
- Code generation with TDD/BDD test writing
- CDD evidence collection
- Quality gates: `tests_pass`, `coverage_above_80`, `no_critical_vulnerabilities`

### Phase 3 - Orchestrated Deployment
- PR creation with `Closes #` linking
- Code review via `pr-orchestrator`
- Quality gates: `pr_approved`, `ci_green`, `evidence_attached`

### Phase 4 - Lifecycle Management
- Memory Bank persistence
- Pattern learning and session handoff
- Quality gates: `memory_bank_updated`, `patterns_documented`

## CDD Evidence Requirements

Configuration: `.claude/config/cdd-config.yaml`

Evidence is posted as GitHub Issue comments for traceability. Each phase requires specific evidence types:
- **Phase 1**: PRD traceability matrix, work item mapping, architectural decision records
- **Phase 2**: Unit test results, code coverage reports, security scan outputs, BDD scenario results
- **Phase 3**: PR review evidence, CI/CD pipeline logs, deployment verification
- **Phase 4**: Memory Bank snapshots, pattern documentation, session handoff records

## PR Workflow

1. Create feature branch: `feature/{issue}-{description}`
2. Develop with tests (>80% coverage)
3. Create PR with `Closes #{issue}` and BDD test plan
4. PR review via `pr-orchestrator` (9 review agents)
5. Collect CDD evidence and attach to PR/issue
6. Merge to main
7. Cleanup: delete branch, remove worktree, update issue labels, close issue

Template: `.github/pull_request_template.md`

## Testing Requirements

- **Backend**: pytest with >80% coverage
- **Frontend**: Jest for unit tests
- **E2E**: Playwright for critical flows
- **BDD**: Gherkin scenarios in every Story issue

## API Conventions

- Base path: `/api/v1/`
- Response format: JSON with Pydantic models
- Error format: `{"detail": "message", "status_code": int}`
- Authentication: OAuth2/OIDC bearer tokens
- Pagination: `?limit=N&offset=M`

## Evidence Taxonomy Reference

12 categories: Documents, Images, Audio, Video, Structured Data, SaaS Exports, KM4Work, BPM Process Models, Regulatory/Policy, Controls/Evidence, Domain Communications, Job Aids/Edge Cases

See PRD Section 5 for full details.

## Development Commands

```bash
# Backend
cd src && uvicorn api.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
pytest src/ --cov --cov-report=html
cd frontend && npm test

# Database
docker compose up -d postgres neo4j redis

# Label sync
.claude/scripts/gh-sync-labels.sh proth1/kmflow
```
