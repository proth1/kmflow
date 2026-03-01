# Active Context

**Last Updated**: 2026-02-28

## Project Status

**MVP COMPLETE + WGI ALIGNED** — Platform MVP done. Windows Task Mining Agent fully implemented. WGI Platform Alignment complete.

- **Current version**: 2026.02.202
- **Open issues**: 0
- **Presentation**: deployed to kmflow.agentic-innovations.com via Cloudflare Pages

## Current Focus

No active work. Clean backlog.

## Recently Completed

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

- **Evidence-first**: 15+ parsers → quality scoring → knowledge graph → LCD consensus
- **3D confidence**: Numeric score + brightness (BRIGHT/DIM/DARK) + evidence grade (A-U)
- **9 universal knowledge forms**: Coverage computation drives gap detection
- **Multi-store**: PostgreSQL (OLTP) + Neo4j (graph) + Redis (cache/queue/streams)
- **RLS**: Row-level security on 36 engagement-scoped tables
- **IDOR protection**: Every endpoint checks engagement membership
- **CDD workflow**: Evidence posted as GitHub Issue comments for traceability
- **ABAC PDP**: 8 attributes, obligation enforcement (masking/suppression/watermarking)
- **VCE pipeline**: Memory-only image lifecycle, on-device classification, PII redaction

---
