# KMFlow Platform State

**Version**: 2026.02.059
**Last Updated**: 2026-02-25

## Quick Stats

| Metric | Value |
|--------|-------|
| SQLAlchemy Models | 78+ classes across 12 modules |
| API Routes | 25+ routers |
| Test Count | 2172 passing |
| Coverage | >80% |
| Python Version | 3.12+ |
| FastAPI Version | 0.109+ |
| Frontend | Next.js 14+ |

## Runtime Requirements

| Service | Purpose |
|---------|---------|
| PostgreSQL 15 (pgvector) | Primary database |
| Neo4j 5.x | Knowledge graph |
| Redis 7 | Caching, streams, pub/sub |

## Recent Releases

| Version | Date | Summary |
|---------|------|---------|
| 2026.02.059 | 2026-02-25 | Privacy and compliance: PII tests, consent, audit, quarantine cleanup |
| 2026.02.058 | 2026-02-25 | Action aggregation engine: session grouping, classification, materialization |
| 2026.02.057 | 2026-02-25 | macOS desktop agent: Swift capture + Python intelligence layer |
| 2026.02.056 | 2026-02-25 | Task Mining backend + SDLC infrastructure |
| 2026.02.055 | 2026-02-24 | Fix frontend API client test failures |
| 2026.02.054 | 2026-02-23 | KMFlow logo concepts (#181) |
| 2026.02.053 | 2026-02-22 | Frontend component tests |
| 2026.02.052 | 2026-02-21 | Audit remediation batch 2 (#180) |
| 2026.02.051 | 2026-02-20 | Extract schemas from simulations.py (#179) |
| 2026.02.050 | 2026-02-19 | Refactor models into domain package (#178) |
| 2026.02.049 | 2026-02-18 | JWT cookies + GDPR rights (#177) |
| 2026.02.048 | 2026-02-17 | Audit remediation batch 1 (#175) |
| 2026.02.047 | 2026-02-16 | Operating Model Scenario Engine (#127) |

## Platform Health

- All 1858 tests passing
- No known critical vulnerabilities
- Backend lint/format/type checks clean

## Active Integrations

| Integration | Status |
|-------------|--------|
| Soroco Task Mining | Connector implemented |
| Celonis Process Mining | Connector implemented |
| SAP Signavio | Connector implemented |
| Camunda BPM | BPMN execution ready |

## Key Directories

```
src/                  # Backend (FastAPI)
  api/                # Routes, schemas, middleware
  core/               # Models, config, database, auth
  evidence/           # Evidence ingestion
  semantic/           # Knowledge graph engine
  pov/                # LCD algorithm, POV generator
  tom/                # TOM alignment, gap analysis
  taskmining/         # Task mining (NEW: PII engine, processor, worker)
  integrations/       # External connectors
frontend/             # Next.js 14+ frontend
docs/                 # PRD, presentations
  prd/                # Product requirements
evidence/             # CDD evidence artifacts
.claude/              # SDLC infrastructure
  commands/           # Slash commands (full-sdlc, code-audit)
  hooks/              # Lifecycle hooks
  rules/              # Development rules
  memory-bank/        # Persistent state
  config/             # PM and CDD config
  agents/             # SubAgent definitions
```

## Version Sources

| File | Purpose |
|------|---------|
| `.current-version` | CalVer version string |
| `CHANGELOG.md` | Release history |
| `.claude/memory-bank/platformState.md` | This file |
