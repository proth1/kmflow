# KMFlow Platform State

**Version**: 2026.02.090
**Last Updated**: 2026-02-27

## Quick Stats

| Metric | Value |
|--------|-------|
| SQLAlchemy Models | 78+ classes across 12 modules |
| API Routes | 25+ routers |
| Test Count | 2383 backend + 206 frontend passing |
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
| 2026.02.090 | 2026-02-27 | Evidence parsers: document, structured data, BPMN with factory dispatch (#296) |
| 2026.02.089 | 2026-02-27 | SemanticRelationship bitemporal validity model (#305) |
| 2026.02.088 | 2026-02-27 | SeedTerm entity schema and vocabulary store (#302) |
| 2026.02.087 | 2026-02-27 | ConflictObject model and disagreement taxonomy (#299) |
| 2026.02.086 | 2026-02-27 | EpistemicFrame and SurveyClaim entity schemas (#297) |
| 2026.02.085 | 2026-02-27 | Controlled edge vocabulary with constraint validation (#295) |
| 2026.02.084 | 2026-02-27 | Three-dimensional confidence model schema (#294) |
| 2026.02.083 | 2026-02-27 | Audit Phase 8: 10 CRITICALs + 28 HIGHs across 5 PRs (#271-#275) |
| 2026.02.078 | 2026-02-27 | Fix macOS agent build: bash 3.2 compat, codesign, @loader_path, CryptoKit (#270) |
| 2026.02.077 | 2026-02-27 | Agent Swift quality: actor conversion, structured logging, IUO removal, import ordering fix (#263) |
| 2026.02.076 | 2026-02-26 | Audit Phase 6: Replace ~58 broad except Exception with specific types, annotate ~55 intentional, widen health checks (#267) |
| 2026.02.075 | 2026-02-26 | Audit Phase 5: N+1 SLA query fix, release build flag export, real SHA-256 checksums, astral-sh URL migration (#261) |
| 2026.02.074 | 2026-02-26 | Audit Phase 4: consent lifecycle — property promotion, revocation handler, withdraw UI, reject unsigned records (#259) |
| 2026.02.073 | 2026-02-26 | Audit Phase 3: periodic integrity, HMAC manifest, expanded PII, per-event consent, tests, ADR, profile customization (#257) |
| 2026.02.072 | 2026-02-26 | Audit Phase 2 PR 4: AES-256-GCM encryption, IPC auth, HMAC consent, iCloud sync prevention, codesign cleanup (#254) |
| 2026.02.071 | 2026-02-26 | Audit Phase 2 PR 3: agent HIGH security hardening — logger privacy, Keychain ACL, MDM bounds, HTTPS-only URL (#255) |
| 2026.02.070 | 2026-02-26 | Audit Phase 2 PR 2: add 13 missing FK indexes (migration 029) (#252) |
| 2026.02.069 | 2026-02-26 | Audit Phase 1: macOS agent build pipeline hardening — Hardened Runtime, dep pinning, SHA-256 verification (#250) |
| 2026.02.068 | 2026-02-26 | Audit Phase 2 PR 1: platform auth/API hardening — pagination bounds, WS membership, TOM access (#239) |
| 2026.02.067 | 2026-02-26 | Audit Phase 1 PR 3: agent security — entitlements, signing, installer, Swift actors (#244) |
| 2026.02.066 | 2026-02-26 | Audit Phase 1 PR 2: rate limiter hardening — pruning, X-Forwarded-For rejection (#243) |
| 2026.02.065 | 2026-02-25 | Audit Phase 1 PR 1: engagement access control, MCP auth cleanup, PIA R8 fix (#242) |
| 2026.02.064 | 2026-02-25 | Audit Phase 0: fix false security claims in whitepaper, DPA, PIA, TCC profile, WelcomeView (#241) |
| 2026.02.063 | 2026-02-25 | CISO-ready agent installer: app bundle, code signing, Keychain hardening, onboarding wizard, DMG/PKG/MDM |
| 2026.02.062 | 2026-02-25 | ML task segmentation: feature extraction, gradient boosting, hybrid classification, sequence mining |
| 2026.02.061 | 2026-02-25 | Knowledge graph integration: ingestion, semantic bridge, LCD weight, variant detection |
| 2026.02.060 | 2026-02-25 | Admin dashboard: agents, policy, activity monitoring, quarantine review |
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

- All 2308 backend + 206 frontend tests passing
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
  taskmining/         # Task mining (PII, processor, worker, graph, ML classification)
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
