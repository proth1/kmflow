# KMFlow Platform State

**Version**: 2026.02.179
**Last Updated**: 2026-02-28

## Quick Stats

| Metric | Value |
|--------|-------|
| SQLAlchemy Models | 82+ classes across 12 modules |
| API Routes | 26+ routers |
| Test Count | 3230 backend + 206 frontend passing |
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
| 2026.02.179 | 2026-02-28 | Variant comparison replay: LCS alignment, divergence detection, cycle time deltas, evidence linking, 39 tests (#342) |
| 2026.02.178 | 2026-02-28 | Aggregate volume replay: per-interval flow metrics, bottleneck detection, gateway distribution, heat map, 36 tests (#339) |
| 2026.02.177 | 2026-02-28 | Single-case timeline replay: brightness classification, paginated frames, evidence linking, 48 tests (#337) |
| 2026.02.176 | 2026-02-27 | POV generation orchestrator: 8-step LCD pipeline tracking, FAILED_PARTIAL preservation, version diff, 38 tests (Part of #318) |
| 2026.02.175 | 2026-02-27 | Async task architecture: Redis Streams TaskQueue, TaskWorker ABC, consumer groups, retry logic, concurrency control, 33 tests (#320) |
| 2026.02.174 | 2026-02-27 | Celonis EMS integration: event log, process model, conformance mappers, idempotent dedup, severity scoring, 45 tests (#325) |
| 2026.02.173 | 2026-02-27 | Soroco Scout Work Graph integration: ScoutActivity parser, Activity node mapping with telemetric epistemic frames, SUPPORTED_BY evidence edges, 30 tests (#326) |
| 2026.02.172 | 2026-02-27 | ARIS AML and Visio VSDX process model importers: ModelImporter ABC, ImportedModel, defusedxml XXE protection, 28 tests (#328) |
| 2026.02.171 | 2026-02-27 | SaaS connector incremental sync: SyncCheckpointStore, SyncLog, async coordinator, SAP timestamp conversion, 34 tests (#330) |
| 2026.02.170 | 2026-02-27 | XES event log importer: streaming parser, defusedxml XXE protection, batch processing, .xes.gz, 25 tests (#332) |
| 2026.02.169 | 2026-02-27 | Connector framework: CredentialProvider, @with_retry, TransformPipeline, rate limit parsing, Credential masking, 34 tests (#323) |
| 2026.02.168 | 2026-02-27 | Replay API endpoints: 5 async task endpoints, date-typed ranges, Literal granularity, eviction cap, schemas, 30 tests (#345) |
| 2026.02.167 | 2026-02-27 | Schema intelligence library: YAML templates for ServiceNow/SAP/Salesforce, case-insensitive lookup, manual fallback, 34 tests (#335) |
| 2026.02.166 | 2026-02-27 | Transformation templates library: 4 analysis templates, Literal validation, max 500 elements, IDOR-safe, 35 tests (#376) |
| 2026.02.165 | 2026-02-27 | LLM suggestion feedback loop: RejectionFeedback, traceability chain, exclusion prompt, IDOR-safe, 25 tests (#390) |
| 2026.02.164 | 2026-02-27 | Per-scenario simulation: 7 mod types, confidence overlay, async trigger, IDOR-safe, task lifecycle, 31 tests (#380) |
| 2026.02.163 | 2026-02-27 | Sensitivity analysis engine: OAT ranking, tornado chart, P10/P50/P90 percentiles, custom cost functions, 24 tests (#364) |
| 2026.02.162 | 2026-02-27 | Governance flag detection: SoD checks, regulatory compliance flagging, authorization change detection, knowledge boundaries, IDOR-safe, 19 tests (#381) |
| 2026.02.161 | 2026-02-27 | Cost-per-role and volume forecast modeling: RoleRateAssumption/VolumeForecast, staffing/volume/quarterly/FTE computation, typed payloads, seasonal validation, 25 tests (#359) |
| 2026.02.160 | 2026-02-27 | Financial assumption management: engagement-scoped CRUD, version history, CHECK constraint, IDOR fix, 16 tests (#354) |
| 2026.02.159 | 2026-02-27 | Suggestion review workflow: ACCEPT/MODIFY/REJECT, ScenarioModification linkage, row-level lock, 409 Conflict, 20 tests (#379) |
| 2026.02.158 | 2026-02-27 | Seed list coverage and dark room backlog: coverage report, uplift-ranked dark segments, evidence actions, SQL-filtered threshold, related seed terms, 26 tests (#367) |
| 2026.02.157 | 2026-02-27 | Best practices library: percentile ranking, gap-to-practice matching, domain filter, maturity validation, engagement metadata_json, 36 tests (#363) |
| 2026.02.156 | 2026-02-27 | Republish cycle and version diff: CONFIRM/CORRECT/REJECT/DEFER decisions, BPMN color-coding, dark-room shrink rate, rename collision guard, 31 tests (#361) |
| 2026.02.155 | 2026-02-27 | Validation APIs: pack detail, decision listing, reviewer routing via RoleActivityMapping, IDOR fix, unique constraint, 14 tests (#365) |
| 2026.02.154 | 2026-02-27 | Evidence grading progression: per-version grade distributions, improvement rate with 100% cap, multi-cycle trend data, GradingSnapshot model, 19 tests (#357) |
| 2026.02.153 | 2026-02-27 | Structured reviewer actions: CONFIRM/CORRECT/REJECT/DEFER with graph write-back, ValidationDecision model, :Assertion labels, element pack validation, 30 tests (#353) |
| 2026.02.152 | 2026-02-27 | Claim write-back: Neo4j graph integration, SUPPORTS/CONTRADICTS edges, EpistemicFrame, ConflictObject auto-creation, confidence recomputation, 27 tests (#324) |
| 2026.02.151 | 2026-02-27 | Survey bot with 8 probe types: session lifecycle, fatigue-optimized probes, claim creation, conflict flagging, certainty summaries, 23 tests (#319) |
| 2026.02.150 | 2026-02-27 | Seed list pipeline: 4-stage workflow, consultant upload, NLP refinement, probe generation, extraction targeting, IDOR-safe DELETE, 25 tests (#321) |
| 2026.02.149 | 2026-02-27 | Certainty tier tracking: SurveyClaimHistory audit trail, tier promotion, shelf data auto-generation, IDOR-safe engagement-scoped endpoints, 24 tests (#322) |
| 2026.02.148 | 2026-02-27 | Data classification + GDPR compliance: 4-tier classification, retention enforcement, ROPA tracking, compliance reporting, 31 tests (#317) |
| 2026.02.147 | 2026-02-27 | Scenario comparison dashboard: 5-metric comparison, best/worst flagging, governance heuristic, 13 tests (#383) |
| 2026.02.146 | 2026-02-27 | Consent architecture: 3 consent modes, policy bundles, immutability triggers, RESTRICT FK, 23 tests (#382) |
| 2026.02.145 | 2026-02-27 | Export watermarking: HMAC-SHA256 invisible watermarks, append-only log, forensic extractor, RESTRICT FK policy, 20 tests (#387) |
| 2026.02.144 | 2026-02-27 | Evidence confidence overlay: per-element brightness, Dark-area warnings, risk score, multi-scenario comparison, 19 tests (#385) |
| 2026.02.143 | 2026-02-27 | LLM audit trail: hallucination flagging, immutability enforcement, disposition stats, 21 tests (#386) |
| 2026.02.142 | 2026-02-27 | Cohort suppression: privacy enforcement, export blocking, audit logging, 21 tests (#391) |
| 2026.02.141 | 2026-02-27 | PDP service: ABAC policy evaluation, obligation framework, audit trail, conditions validation, default policy seeding, 25 tests (#377) |
| 2026.02.140 | 2026-02-27 | Cross-border transfer controls: GDPR transfer evaluation, TIA/SCC workflow, jurisdiction registry, role permissions, 20 tests (#395) |
| 2026.02.139 | 2026-02-27 | Incident response automation: P1-P4 classification, GDPR 72h deadline, containment, escalation, timeline, 16 tests (#397) |
| 2026.02.138 | 2026-02-27 | Telemetry micro-surveys: deviation-to-probe mapping, anomaly threshold, SurveyClaim linkage, API endpoints, 16 tests (#398) |
| 2026.02.137 | 2026-02-27 | Shelf-epistemic integration: auto-create shelf items, follow-through rate, source filter, 11 tests (#399) |
| 2026.02.136 | 2026-02-27 | Epistemic Action Planner: GET endpoint, shelf linkage, IDOR guard, pagination, 10 tests (#389) |
| 2026.02.135 | 2026-02-27 | Illumination Planner: targeted evidence acquisition, 9-form action mapping, idempotency guard, progress tracking, 11 tests (#396) |
| 2026.02.134 | 2026-02-27 | Dark Room backlog: prioritized Dark segments, missing forms, Neo4j coverage, authz, configurable threshold, 12 tests (#394) |
| 2026.02.133 | 2026-02-27 | Evidence gap ranking: uplift projection, cross-scenario gaps, Pearson correlation tracking, 12 tests (#393) |
| 2026.02.132 | 2026-02-27 | Governance overlay API: per-activity status classification, ontology-aligned Cypher, IDOR-safe access, 10 tests (#331) |
| 2026.02.131 | 2026-02-27 | Gap-targeted probe generation: brightness uplift scoring, consolidated mapping, pagination, 12 tests (#327) |
| 2026.02.130 | 2026-02-27 | CanonicalActivityEvent + Event Spine Builder: multi-source canonicalization, dedup, FK constraint, timezone safety, 17 tests (#334) |
| 2026.02.129 | 2026-02-27 | Nine Universal Knowledge Forms: coverage computation, gap detection, ontology-validated edge types, 12 tests (#316) |
| 2026.02.128 | 2026-02-27 | Governance CRUD APIs: soft-delete, Neo4j graph sync, governance chain traversal, 10 tests (#329) |
| 2026.02.127 | 2026-02-27 | Process maturity scoring: CMMI levels 1-5, evidence/governance/metric dimensions, heatmap, 15 tests (#358) |
| 2026.02.126 | 2026-02-27 | Governance gap detection: GapFinding model, regulation-aware resolution, severity scoring, 17 tests (#340) |
| 2026.02.125 | 2026-02-27 | Control effectiveness scoring: execution rate thresholds, evidence-linked, trend analysis, 17 tests (#336) |
| 2026.02.124 | 2026-02-27 | Compliance state machine: coverage percentage, state transitions, dashboard summary, 20 tests (#333) |
| 2026.02.123 | 2026-02-27 | Per-activity TOM alignment scoring: async background scoring, cosine similarity, gap rationale, 30 tests (#348, #352) |
| 2026.02.122 | 2026-02-27 | TOM definition management APIs: structured dimensions, version history, import/export, 18 tests (#344) |
| 2026.02.121 | 2026-02-27 | Cross-source consistency reporting: disagreement report, agreement rate, POV trend, 13 tests (#392) |
| 2026.02.120 | 2026-02-27 | Disagreement resolution workflow: 5-endpoint conflict API, filterable report, audit trail, 48h auto-escalation, 21 tests (#388) |
| 2026.02.119 | 2026-02-27 | I/O mismatch + control gap detection: IOMismatchDetector, ControlGapDetector, auto shelf requests, ControlRequirement ontology node, 28 tests (#378) |
| 2026.02.118 | 2026-02-27 | Three-way distinction classifier: NAMING_VARIANT/TEMPORAL_SHIFT/GENUINE_DISAGREEMENT classification, run_write_query(), MERGED_EDGE ontology, bitemporal validity, 20 tests (#384) |
| 2026.02.117 | 2026-02-27 | Rule/existence conflict detection: RuleConflictDetector, ExistenceConflictDetector, temporal resolution, authority weights, ontology updates, 31 tests (#375) |
| 2026.02.116 | 2026-02-27 | LLM suggestion engine: audited suggestions, governance flags, LLMAuditLog model, 14 tests (#374) |
| 2026.02.115 | 2026-02-27 | Scenario Workbench CRUD: /api/v1/scenarios with max-5 enforcement, IDOR protection, DRAFT-only modifications, 20 tests (#373) |
| 2026.02.114 | 2026-02-27 | Sequence/role conflict detection: contradictory PRECEDES/PERFORMED_BY edges, severity scoring, idempotent persistence, 26 tests (#372) |
| 2026.02.113 | 2026-02-27 | Gap-prioritized transformation roadmap generator: topo sort, phase bucketing, HTML export, IDOR-protected endpoints, 31 tests (#368) |
| 2026.02.112 | 2026-02-27 | Monitoring agent framework: BaseMonitoringAgent ABC, lifecycle, circuit breaker, AgentRegistry, health endpoint, 42 tests (#346) |
| 2026.02.111 | 2026-02-27 | Monitoring dashboard: aggregated endpoint with date range filtering, agent statuses, deviation counts, evidence flow rate, alert summary, compliance trend, 29 tests (#371) |
| 2026.02.110 | 2026-02-27 | Dark-Room Shrink Rate dashboard: DarkRoomSnapshot model, per-version shrink rate computation, below-target alerts, illumination timeline, 42 tests (#370) |
| 2026.02.109 | 2026-02-27 | Continuous evidence pipeline: async Redis stream consumer, quality scoring, per-engagement quality monitoring, MetricsCollector, pipeline metrics API, 33 tests (#360) |
| 2026.02.108 | 2026-02-27 | Review pack generation: 3-8 activity segments, SME routing, async gen, failure sentinel, 36 tests (#349) |
| 2026.02.107 | 2026-02-27 | RACI matrix derivation from knowledge graph edges, SME validation, CSV export, 41 tests (#351) |
| 2026.02.106 | 2026-02-27 | Deviation detection engine: severity scoring, timing/skipped/undocumented detection, 45 tests (#350) |
| 2026.02.105 | 2026-02-27 | BPMN assembly with 3D confidence, gap markers, variant annotations, 67 tests (#315) |
| 2026.02.104 | 2026-02-27 | Audit logging middleware: fire-and-forget persistence, query API, append-only trigger, 77 BDD tests (#314) |
| 2026.02.103 | 2026-02-27 | OAuth2/OIDC auth and RBAC BDD tests: JWT validation, role boundaries, engagement access (#313) |
| 2026.02.102 | 2026-02-27 | PostgreSQL RLS: 32 engagement-scoped tables, table name validation, WITH CHECK, Alembic 039 (#311) |
| 2026.02.101 | 2026-02-27 | Client evidence submission portal: token-based intake, Levenshtein auto-matching, bulk upload progress (#308) |
| 2026.02.100 | 2026-02-27 | Cross-source triangulation: evidence planes, coverage/agreement factors, cross-plane bonus, conflict detection (#306) |
| 2026.02.099 | 2026-02-27 | Evidence aggregation and entity extraction: seed term guided, duplicate candidate detection, provenance maps (#303) |
| 2026.02.098 | 2026-02-27 | Contradiction resolution: three-way distinction classifier, severity scoring, epistemic frames, persistence bridge (#312) |
| 2026.02.097 | 2026-02-27 | Weighted consensus building with LCD algorithm, recency bias, variant detection (#310) |
| 2026.02.096 | 2026-02-27 | Evidence cataloging, metadata extraction, catalog API (#304) |
| 2026.02.095 | 2026-02-27 | Database infrastructure BDD tests (#309) |
| 2026.02.094 | 2026-02-27 | API gateway BDD tests, health endpoint enhancements (#307) |
| 2026.02.093 | 2026-02-27 | Evidence lifecycle state machine with audit trail (#301) |
| 2026.02.092 | 2026-02-27 | Evidence quality scoring engine with Hill function, configurable weights (#300) |
| 2026.02.091 | 2026-02-27 | Shelf data request workflow with BDD-aligned status enums (#298) |
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

- All 2510 backend + 206 frontend tests passing
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
