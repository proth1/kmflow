# Active Context

**Last Updated**: 2026-03-09

## Project Status

**MVP COMPLETE + WGI ALIGNED** — Platform MVP done. Windows Task Mining Agent fully implemented. WGI Platform Alignment complete.

- **Current version**: 2026.03.213
- **Open issues**: 0
- **PM tool**: Jira (KMFLOW project at agentic-sdlc.atlassian.net)
- **Presentations**: kmflow.agentic-innovations.com + state-street-apex.agentic-innovations.com

## Current Focus

PRD v3.0 decomposition into Jira Epics/Stories for Phase 5 (Production Hardening) and remaining Phase 4 work.

## Recently Completed

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
- **CDD workflow**: Evidence posted as GitHub Issue comments for traceability
- **ABAC PDP**: 8 attributes, obligation enforcement (masking/suppression/watermarking)
- **VCE pipeline**: Memory-only image lifecycle, on-device classification, PII redaction

---

---
