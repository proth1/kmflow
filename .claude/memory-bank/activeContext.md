# Active Context

**Last Updated**: 2026-02-28

## Project Status

**MVP COMPLETE** — Platform MVP done. Now building Windows Task Mining Agent (PRD: `docs/prd/PRD_KMFlow_TaskMining_Windows.md`).

- **Current version**: 2026.02.196
- **Open issues**: ~37 Windows Agent stories (#519-#555) across 8 epics (#511-#518)
- **Presentation**: deployed to kmflow.agentic-innovations.com via Cloudflare Pages

## Current Focus

**Windows Task Mining Agent** — C# .NET 8 NativeAOT capture layer + shared Python platform abstraction.

### Completed Epics
- **Epic #511** (Capture Layer): InputMonitor, AppSwitchMonitor, WindowTitleCapture, IdleDetector, CaptureStateManager, HookDll
- **Epic #512** (PII L1): CaptureContextFilter, PrivateBrowsingDetector
- **Epic #513** (IPC & Platform): EventProtocol, NamedPipeClient (dual transport), Python platform abstraction (_windows.py, _macos.py)
- **Epic #514** (Consent/Config — partial): DPAPIConsentStore, ConsentManager, IntegrityChecker, AgentConfig
- **Epic #516** (Security — partial): IntegrityChecker (Authenticode verification)
- **Epic #518** (MDM — partial): AgentConfig (Registry-based, GPO/Intune compatible)

### Remaining Stories
- **Epic #514**: #537 (SystemTrayApp WPF), #538 (OnboardingWindow), #539 (TransparencyLogWindow)
- **Epic #515**: #540 (WiX MSI), #541 (MSIX), #542 (Task Scheduler), #543 (Windows Service), #544 (GPO ADMX)
- **Epic #516**: #545 (Authenticode pipeline), #547 (WDAC policy), #548 (AV pre-submission)
- **Epic #517**: #550 (Integration tests), #552 (Win 10/11 test matrix)
- **Epic #518**: #554 (Intune profile), #555 (SCCM docs)

## Recently Completed

- **PR #556**: Windows Agent Epics #511-#513 + partial #514/#516/#518 (merged 2026-02-28)
- **PR #510**: Windows Task Mining Agent PRD (merged 2026-02-28)
- **PR #509**: Alembic hardening + docs refresh (merged 2026-02-28)

## Post-MVP Pending Work

These are known follow-up items identified during development:

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

## Key Architectural Patterns

- **Evidence-first**: 15+ parsers → quality scoring → knowledge graph → LCD consensus
- **3D confidence**: Numeric score + brightness (BRIGHT/DIM/DARK) + evidence grade (A-U)
- **9 universal knowledge forms**: Coverage computation drives gap detection
- **Multi-store**: PostgreSQL (OLTP) + Neo4j (graph) + Redis (cache/queue/streams)
- **RLS**: Row-level security on 32 engagement-scoped tables
- **IDOR protection**: Every endpoint checks engagement membership
- **CDD workflow**: Evidence posted as GitHub Issue comments for traceability
