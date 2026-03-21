# Active Context

**Last Updated**: 2026-03-21

## Project Status

**MVP COMPLETE + WGI ALIGNED** — Platform MVP done. Windows Task Mining Agent fully implemented. WGI Platform Alignment complete.

- **Current version**: 2026.03.249
- **Open issues**: 0
- **PM tool**: Jira (KMFLOW project at agentic-sdlc.atlassian.net)
- **Presentations**: kmflow.agentic-innovations.com + state-street-apex.agentic-innovations.com

## Current Focus

Audit remediation rounds 2-5 complete. All response_model on ALL routes. All except Exception justified. All POST endpoints have status_code. MCP rate limiting on Redis. LLM endpoints rate-limited. Remaining: ~7 accepted-risk MEDIUMs (consent enforcement needs product decision, deterministic PBKDF2 salt, dev DB URIs), god-file decomposition, MagicMock spec bulk migration.

## Recently Completed

- **PR #660**: Audit R5 — Final sweep: MCP Redis rate limiting, LLM rate limits, POST status_code (~85 endpoints), response_model on ALL routes (0 missing), POV .limit(1000), ~20 :Any fixed, 5 function splits, dual-write compensator, frontend cancellation guards + error states + error.tsx + index keys, ~1,500 lines new tests (#659, merged 2026-03-21)
- **PR #658**: Audit R4 — 1 CRITICAL + 10 HIGH + 7 MEDIUM fixes: WS env guard, graph engagement access, erasure job tables, RLS consent tables, 17 response_model endpoints, all except justified, RBAC N+1 cache, dashboard parallel queries, retention async, MIME fallback, core layering fix, 8 new tests (#657, merged 2026-03-21)
- **PR #656**: Audit R3 — 2 CRITICAL + 13 HIGH fixes: dev-mode auth guard, CSRF session binding (HMAC), CIB7 auth, frontend non-root, RLS tables, GDPR export/anonymize, 66 response_model endpoints, 29 exception justifications, 10 type narrowings, GDPR stub → NotImplementedError, 19 new tests (#655, merged 2026-03-21)
- **PR #652**: Audit R2 — 8 batches, 60+ findings: slowapi Redis, coverage 90%, CSRF middleware, refresh token rotation, Neo4j constraints, pagination, response_model (30 endpoints), exception handling, test coverage, frontend quality, TLS, network segmentation, coding guardrails (merged 2026-03-20)
- **PRs #637-#651**: Comprehensive audit remediation — 6 batches, 92 findings (2 CRIT + 27 HIGH + 47 MED + 26 LOW): tasks router prefix fix, engagement IDOR (13 routes), refresh token blacklisting, CSRF cookies, async parallelism, Neo4j LIMIT, SurveyClaim rename, Camunda pagination, API compliance, main.py SRP, LLM user attribution, supply chain hardening (merged 2026-03-20)
- **PR #635**: GDPR Article 28 DPA tracking — DataProcessingAgreement model, 5 endpoints, engagement compliance summary, evidence upload warning, field allowlist, RLS, migration 091, 13 tests (merged 2026-03-20)
- **PR #634**: Audit remediation #4 — response_model (27 endpoints), GDPR agent tests (23), flaky tests hardened, seeds YAML, HNSW index, exception comments, dependency pinning (#633, merged 2026-03-19)
- **PR #632**: Audit remediation #3 — schema extraction (104 schemas → 6 files), 106 new tests, classification enforcement, BPMNViewer cast fix, rate limit alignment (#631, merged 2026-03-19)
- **PR #630**: Audit remediation #2 — 20 CRITICAL/HIGH findings: 2 IDOR fixes (10 routes), RLS 34 tables, N+1 elimination (search_similar, governance, pipeline), LLM audit logging, supply chain hashes, per-email auth lockout (#629, merged 2026-03-19)
- **PR #628**: Audit followup — 13 remaining findings: shared auth, domain exceptions, schema extraction, Lua rate limiter, classification enforcement, 6 new tests (#627, merged 2026-03-19)
- **PR #625**: Audit remediation — 107 findings (6 CRITICAL, 34 HIGH, 37 MEDIUM, 30 LOW) across security, architecture, quality, performance, compliance, and dependency domains. 108 files changed. (#624, merged 2026-03-19)
- **PR #623**: Fix BPMN viewer top clipping — add 30px viewbox padding after fit-viewport so pool headers and confidence badges aren't cut off (merged 2026-03-19)
- **PR #622**: Ingestion pipeline optimization — token-aware chunking, nomic-embed-text-v1.5 upgrade, graph expansion fix, cross-encoder reranking, MMR diversity, DataObject/Event/Gateway entity extraction, layout-aware PDF parser, domain config bundles, 49 new tests (merged 2026-03-19)
- **PR #621**: ADR: Dependency version pinning strategy — patch-only policy, 7 revisit triggers (#620, merged 2026-03-18)
- **PR #619**: Upgrade Next.js 15.5.10 → 15.5.13 — CVE-2026-29057 HTTP request smuggling fix (#618, merged 2026-03-18)
- **PR #617**: Remove unused deps, eliminate all Python CVEs (#614) — python-jose/ecdsa/passlib removed, pypdf floor pin removed; pip-audit 0 CVEs (merged 2026-03-18)
- **PR #613**: Remediate 6 Python CVEs (#612) — PyJWT 2.12.1, pyopenssl ≥26.0.0, pyasn1 ≥0.6.3, pypdf ≥6.9.1; ecdsa + npm accepted risks (merged 2026-03-18)
- **PR #610**: Improve Knowledge Graph Explorer readability (#611) — hide edge labels (hover-to-reveal), larger nodes (40→50px), hover highlighting for connected nodes/edges, force-directed layout tuning, faded search class (merged 2026-03-18)
- **PR #608**: Decision Intelligence presentation slides + fix all 79 mypy errors (#607) — 3 new slides (KM4ProcessBot, KM4DecisionBot, Decision UI), updated What's New/Stats/Changelog to v7.0, 79→0 mypy errors across 38 files, types-PyYAML added to pre-commit (merged 2026-03-12)
- **PR #606**: Extract task mining utilities for Next.js 15 compliance (KMFLOW-114) — 6 functions to shared modules, fix ontology hook args, fix semantic API client (merged 2026-03-12)
- **PR #605**: Remediate 25/26 CVEs across 14 Python packages (KMFLOW-113) — cryptography 46.0.5, pypdf 6.8.0, pillow, urllib3, werkzeug, flask, pdfminer.six, filelock, pyasn1, pynacl, azure-core, wheel, black, pip; accepted risks documented (merged 2026-03-12)
- **PR #604**: Fix 64 pre-existing test failures across 19 test files (#603) — RLS side-effect exhaustion, lazy import patch targets, mock API drift, exception type specificity, WebSocket auth dual-module patching (merged 2026-03-12)
- **PR #602**: REST endpoints for graph/semantic/ML services (KMFLOW-67) — 3 route files (semantic, confidence, graph_analytics), 10 endpoints, frontend TypeScript API client, 12 tests (merged 2026-03-12)
- **PR #601**: Hybrid/on-prem deployment (KMFLOW-7) — LLM provider abstraction (Anthropic/Ollama/Stub with auto-detection), data residency enforcement middleware, deployment capabilities API, on-prem Docker overlay with Ollama, air-gapped build script with SHA-256 manifest, 28 new tests (merged 2026-03-11)
- **PR #600**: Ontology derivation from knowledge graph — seed term clustering, Neo4j pattern extraction, property mapping with domain/range, axiom generation, completeness scoring, OWL 2 XML + YAML export, validation (orphan/subgraph), RLS on all 4 tables, Cytoscape graph viz, 30 tests (KMFLOW-6, merged 2026-03-11)
- **PR #599**: Activate BPMN workflows in Camunda — external task worker (fetch-and-lock), orchestration API (deploy/instances/retry/cancel), CamundaClient extended with 8 methods, variable type inference, 39 tests (KMFLOW-5, merged 2026-03-11)
- **PR #598**: Assessment Overlay Matrix — Value x Ability-to-Execute scatter chart with quadrant analysis, composite scoring, 3 API endpoints, recharts frontend, 33 tests (KMFLOW-4, merged 2026-03-11)
- **PR #597**: Decision Knowledge Module for KM4ProcessBot — DMN 1.3 parser/generator, 5 decision API routes, deep rule probes (5 sub-types), decision seed list, job aids rule extraction, gateway condition expressions, frontend decision dashboard, 69 new tests (KMFLOW-103, merged 2026-03-11)
- **PR #596**: Fix two LOW security findings in git hooks — backup before overwrite, simple output replacing box art (#595 follow-up, merged 2026-03-10)
- **PR #595**: Git hooks to enforce SDLC branch protection — pre-commit/pre-push block main, install-hooks.sh, GitHub branch protection enabled (merged 2026-03-10)
- **PR #594**: Redis worker wiring (KMFLOW-58) — unified task runner, POST/GET task endpoints, WebSocket progress, EvidenceBatchWorker, GdprErasureWorker, per-type auth, fresh-instance concurrency fix, 26 BDD tests (merged 2026-03-09)
- **PR #593**: Fix GitHub Issues → Jira references in CLAUDE.md, activeContext.md, MEMORY.md (merged 2026-03-09)
- **PR #592**: Align PRD v3.0 with implemented platform state — version 3.0.0, remove Phase labels, add Desktop Agent/Process Orchestration/Analytics sections, update data model + API + security + phased delivery (KMFLOW-1, merged 2026-03-09)
- **PR #591**: Upgrade jira-manager to v3.0 with world-class PRD-driven templates — BDD/Gherkin AC, 10-section Epic template, mandatory 6-8 sub-task breakdown, ADF formatting (merged 2026-03-09)
- **PR #590**: Zero-config Docker startup + PR review fixes — ApiRequestError class, status-based 404 detection, inline RLS in migrations, seed_demo import fix, backend entrypoint with auto-migrate/seed (#589, merged 2026-03-09)
- **PR #588**: Populate presentation screenshots with seeded demo data — RLS bypass for admin, dashboard filter fix, conformance seeding, Playwright capture script (merged 2026-03-02)
- **PR #587**: State Street APEX presentation auth fix + slide redesign — custom domain, CF Access, 3 slide redesigns, deployment rules (#586, merged 2026-03-01)
- **PR #585**: Frontend production build + graph loading optimization (#585, merged 2026-03-01)
- **PR #584**: Fix WebSocket dev mode auth and /ws/taskmining/events endpoint — shared `get_websocket_user()`, Redis Pub/Sub channel constant (#583, merged 2026-03-01)
- **PR #582**: Rename LCD → Consensus Algorithm across entire codebase — 47 files, POV_STEPS, test renames, BPMN, docs, presentation redeployed (#581, merged 2026-03-01)
- **PR #580**: Fix tunnel-auth Worker session persistence — Descope refresh retry, tunnel 502/503 handling, Set-Cookie RFC fix (merged 2026-03-01)
- **PR #577**: Fix frontend "Failed to fetch" via Next.js rewrites proxy, centralize API base URL (merged 2026-03-01)
- **Commit 91510ce**: Add tunnel-auth Cloudflare Worker, optimize Neo4j Docker, fix Descope JWT issuer validation (pushed 2026-02-28)
- **PR #576**: WGI remaining codebase changes — formatting, TYPE_CHECKING, pre-merge gates, RLS TOM context (merged 2026-02-28)
- **PR #575**: WGI Platform Alignment — switching sequences, VCE pipeline, correlation engine, ABAC PDP, PRD refactoring, 4 migrations (merged 2026-02-28)
- **PR #562**: Fix Knowledge Graph empty edge IDs crashing Cytoscape rendering (#560) — merged 2026-02-28
- **PR #561**: Disable Next.js dev indicator overlay (#561) — merged 2026-02-28

### WGI Platform Alignment (Epics #563-#574)
- **Part A**: PRDs renamed to WGI terminology, 5 DOCX sources archived, VCE/Switching sections added
- **Part B**: Switching Sequences backend, VCE full pipeline (macOS/Windows capture, classifier, OCR, redactor, trigger engine)
- **Part C**: Correlation Engine (deterministic + assisted linkage), PDP ABAC (8 attributes, obligation enforcer, PEP middleware)
- **Part D**: Agent runtime connector, schema drift, BPMN auto-gen, evidence quality scorecards, survey consensus, uncertainty queue

### Windows Agent (Epics #511-#518)
- All 8 epics complete: Capture, PII, IPC, Consent/UI, Installer, Security, Testing, MDM

## Post-MVP Pending Work

- **Worker.py wiring**: Connect aggregation engine to Redis stream consumer (TODO in worker.py)
- **API endpoints**: Expose graph ingestion, semantic bridge, variant detection, ML classification via REST
- **Client-side role guard layout**: Follow-up from PR #224 (admin dashboard)
- **WebSocket auth verification**: Follow-up from PR #224
- **Survey bot NLP integration**: Framework present, full NLP integration TBD
- **Epistemic frames UI visualization**: Schema present, visualization TBD
- **Cross-store consistency enforcement rules**: Schema present, enforcement TBD
- **Schema library pre-built schemas**: Structure present, pre-built schemas TBD
- **Multi-tenant governance**: Currently single-tenant only
- **Mobile/offline modes**: Not implemented
- **Real-time streaming from Celonis/Soroco**: Connectors are batch-mode only

## Development History Summary

The project was built over February 2026 in a rapid sprint:

- **v2026.02.025–v2026.02.056** (Feb 16-25): Foundation — Task Mining backend (Epics 1-8), macOS desktop agent, SDLC infrastructure
- **v2026.02.057–v2026.02.063** (Feb 25): macOS agent hardening — CISO-ready installer, code signing, Keychain, DMG/PKG
- **v2026.02.064–v2026.02.083** (Feb 25-27): Security audit — 8 phases, 10 CRITICALs + 28 HIGHs remediated across platform + agent
- **v2026.02.084–v2026.02.100** (Feb 27): Core domain models — Confidence model, controlled edges, epistemic frames, conflict objects, seed terms, evidence parsers, lifecycle, quality scoring, cataloging, triangulation
- **v2026.02.101–v2026.02.130** (Feb 27): Process intelligence — Client portal, RLS, auth/RBAC, audit logging, BPMN assembly, deviation detection, RACI matrix, review packs, monitoring pipeline, event spine
- **v2026.02.131–v2026.02.170** (Feb 27): Advanced features — Governance, compliance, TOM alignment, scenarios, financial modeling, conflict detection/resolution, privacy (GDPR, consent, watermarking, PDP), task mining integrations, connectors (Celonis, Soroco, SAP, XES, ARIS, Visio)
- **v2026.02.171–v2026.02.192** (Feb 27-28): Platform completion — Async task queue, POV orchestrator, replay engines, dashboards (executive, gap, persona, financial, confidence), alerting, presentation deployment, security cleanup, inaugural release
- **v2026.02.193–v2026.02.197** (Feb 28): Windows Agent — PRD, C# capture layer, PII, IPC, consent, UI, installer, security, testing, MDM
- **v2026.02.198–v2026.02.201** (Feb 28): WGI Platform Alignment — Switching sequences, VCE pipeline, correlation engine, ABAC PDP, codebase-wide cleanup

## Key Architectural Patterns

- **Evidence-first**: 15+ parsers → quality scoring → knowledge graph → consensus algorithm
- **3D confidence**: Numeric score + brightness (BRIGHT/DIM/DARK) + evidence grade (A-U)
- **9 universal knowledge forms**: Coverage computation drives gap detection
- **Multi-store**: PostgreSQL (OLTP) + Neo4j (graph) + Redis (cache/queue/streams)
- **RLS**: Row-level security on 36 engagement-scoped tables
- **IDOR protection**: Every endpoint checks engagement membership
- **CDD workflow**: Evidence posted as Jira issue comments for traceability
- **ABAC PDP**: 8 attributes, obligation enforcement (masking/suppression/watermarking)
- **VCE pipeline**: Memory-only image lifecycle, on-device classification, PII redaction

---

---

---
> SESSION END WARNING (2026-03-11T21:22:54Z): activeContext.md was NOT updated during this session.
> Branch: main, Uncommitted: 23

---
> SESSION END WARNING (2026-03-12T17:35:42Z): activeContext.md was NOT updated during this session.
> Branch: main, Uncommitted: 23

---
> SESSION END WARNING (2026-03-17T19:16:48Z): activeContext.md was NOT updated during this session.
> Branch: main, Uncommitted: 24

---
> SESSION END WARNING (2026-03-18T21:06:40Z): activeContext.md was NOT updated during this session.
> Branch: main, Uncommitted: 24

---
> SESSION END WARNING (2026-03-19T12:50:08Z): activeContext.md was NOT updated during this session.
> Branch: main, Uncommitted: 41
