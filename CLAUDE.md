# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KMFlow is an AI-powered Process Intelligence platform for consulting engagements. Evidence-first approach: ingests diverse client evidence, builds semantic knowledge graph, generates confidence-scored process views, and automates TOM gap analysis.

**PRD**: `docs/prd/PRD_KMFlow_Platform.md`

## Architecture

```
Frontend (Next.js 15+, Port 3000)
  -> API Gateway (FastAPI, Port 8000)
    -> Processing Services (Evidence, Semantic, Consensus, TOM, Gap, RAG)
      -> Data Layer (PostgreSQL+pgvector, Neo4j, Redis, MinIO)
```

**Tech Stack**: Python 3.12+ (FastAPI), Next.js 15+ (React 18), Neo4j 5.x, PostgreSQL 15 (pgvector), Redis 7, CIB7 (Camunda BPMN engine), MinIO (object storage)

## Development Commands

```bash
# ── Infrastructure ──
docker compose up -d postgres neo4j redis          # Core data services
docker compose up -d                                # All services (includes cib7, minio, backend, frontend)
docker compose --profile dev up frontend-dev        # Frontend with hot reload (local dev only)

# ── Backend ──
pip install -e ".[dev]"                             # Install with dev deps
uvicorn src.api.main:app --reload --port 8000       # Run API server

# ── Frontend ──
cd frontend && npm install && npm run dev           # Dev server (port 3000)
cd frontend && npm run build                        # Production build

# ── Backend Tests ──
pytest tests/                                       # All backend tests
pytest tests/ --cov --cov-report=term-missing       # With coverage
pytest tests/evidence/test_pipeline.py              # Single test file
pytest tests/evidence/test_pipeline.py::test_ingest # Single test function
pytest tests/ -k "keyword"                          # Filter by keyword

# ── Frontend Tests ──
cd frontend && npm test                             # All Jest tests
cd frontend && npm test -- --testPathPattern=MyComp # Single component
cd frontend && npm run test:coverage                # With coverage

# ── E2E Tests ──
cd frontend && npm run test:e2e                     # Playwright (headless)
cd frontend && npm run test:e2e:ui                  # Playwright (interactive UI)

# ── Lint & Type Check ──
ruff check src/ tests/                              # Lint Python
ruff format src/ tests/                             # Format Python
mypy src/ --ignore-missing-imports                  # Type check Python
cd frontend && npm run lint                         # Lint frontend (Next.js)

# ── Database Migrations ──
alembic upgrade head                                # Apply all migrations
alembic revision --autogenerate -m "description"    # Create new migration
alembic downgrade -1                                # Rollback one migration
```

## Docker Port Mappings

Host ports differ from container-internal ports:

| Service | Host Port | Container Port | URL |
|---------|-----------|----------------|-----|
| PostgreSQL | 5433 | 5432 | `localhost:5433` |
| Neo4j Browser | 7475 | 7474 | `http://localhost:7475` |
| Neo4j Bolt | 7688 | 7687 | `bolt://localhost:7688` |
| Redis | 6380 | 6379 | `localhost:6380` |
| Backend (Docker) | 8002 | 8000 | `http://localhost:8002` |
| CIB7 (Camunda) | 8081 | 8080 | `http://localhost:8081` |
| MinIO API | 9002 | 9000 | `http://localhost:9002` |
| MinIO Console | 9003 | 9001 | `http://localhost:9003` |
| Frontend | 3002 | 3000 | `http://localhost:3002` |
| Mailpit UI | 8026 | 8025 | `http://localhost:8026` |

When running backend/frontend locally (not in Docker), they use standard ports (8000, 3000).

## Key Directories

```
src/
  api/              # FastAPI routes, schemas, middleware
  core/             # Domain models, config, database, auth, RLS, encryption
  evidence/         # Evidence ingestion: 15+ parsers, pipeline, quality scoring
  semantic/         # Knowledge graph engine, entity extraction, confidence scoring
  pov/              # Consensus algorithm, POV generator, triangulation
  tom/              # TOM alignment, gap analysis, maturity scoring
  integrations/     # External connectors (Celonis, Soroco, SAP, ARIS, Visio, XES)
  rag/              # Retrieval-augmented generation, copilot
  security/         # PDP/ABAC, incident response, consent, watermarking
  taskmining/       # Desktop task mining (PII, processor, worker, ML)
frontend/
  src/app/          # Next.js app router pages
  src/components/   # React components
  e2e/              # Playwright E2E tests
platform/           # BPMN orchestration workflows (L3/L4 models)
alembic/            # Database migrations (80+ versions)
infrastructure/     # Cloudflare Workers (presentation auth)
agent/              # Desktop agent: macOS (Swift) + Windows (C#) + shared Python
evidence/           # CDD evidence artifacts (loan-origination case study)
docs/presentations/ # Stakeholder presentations (deployed to Cloudflare Pages)
```

## Project Management

- **Primary tool**: Jira (`https://agentic-sdlc.atlassian.net`, project: KMFLOW)
- **Legacy**: GitHub Issues (#1-#590, `proth1/kmflow`)
- **Branch format**: `feature/{issue-number}-{description}`
- **PR body**: Always include `Closes #{issue-number}` to auto-close

### Git Worktree Conventions

- **Main worktree** (`/repos/kmflow`): PRD, documentation, infrastructure
- **Feature worktrees**: `git worktree add ../kmflow-{issue} feature/{issue}-{description}`
- **Cleanup**: `git worktree remove ../kmflow-{issue}` after PR merge

## SDLC & CDD

The project follows a 4-phase SDLC with Compliance-Driven Development (CDD) evidence collection:

1. **Strategic Intelligence**: PRD analysis, work item decomposition
2. **Automated Development**: TDD/BDD, >80% coverage, security scans
3. **Orchestrated Deployment**: PR creation, `pr-orchestrator` review (9 agents), merge
4. **Lifecycle Management**: Memory Bank persistence, pattern learning

CDD config: `.claude/config/cdd-config.yaml`. Evidence posted as GitHub Issue comments.

## API Conventions

- Base path: `/api/v1/`
- Response format: JSON with Pydantic models
- Error format: `{"detail": "message", "status_code": int}`
- Authentication: OAuth2/OIDC bearer tokens
- Pagination: `?limit=N&offset=M`
- Interactive docs: `http://localhost:8000/docs`

## Versioning

CalVer format: `YYYY.MM.MICRO` (e.g., `2026.03.211`). MICRO is monotonically incrementing and never resets. Current version stored in `.current-version`.

## Important Conventions

- The "LCD" algorithm was renamed to **"Consensus algorithm"** — never use "LCD" in any content
- Heavy frontend visualization libs (cytoscape, bpmn-js, recharts) must use `next/dynamic` with `ssr: false`
- Coding standards are in `.claude/rules/coding-standards.md`
- Post-merge update process is in `.claude/rules/post-merge-updates.md`
- Presentation deployment rules are in `.claude/rules/presentation-deployment.md`
- PR review requirements are in `.claude/rules/pr-auto-review.md`
- Frontend Docker build rules are in `.claude/rules/frontend-docker-build.md`
