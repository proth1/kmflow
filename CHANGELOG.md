# Changelog

All notable changes to KMFlow are documented here.
Format: [CalVer](https://calver.org/) — `YYYY.MM.MICRO` (year.month.sequential-build)

## [2026.02.192] - 2026-02-28
### Changed
- Presentation: update stats to final MVP metrics (101K LOC, 5,797 tests, 65 routers, 92 models), add Project Stats Dashboard and Presentation Changelog appendix slides (#508)

## [2026.02.191] - 2026-02-28
### Security
- Bump cryptography to 46.0.5 (CVE fixes) (#253)

### Changed
- Frontend quality: strict dependency ranges, unused dep removal, page component hardening (#265)
- Agent capture layer privacy: consent version tracking, HMAC re-consent, strict CSPRNG (no UUID fallback), MDM onboarding pre-population, legacy record migration, BufferEncryptionManager extraction, strict decryption error handling (#268)

## [2026.02.190] - 2026-02-28
### Added
- Confidence heatmap overlay: Bright/Dim/Dark toggle on BPMN viewer, hover tooltip (score, brightness, grade), JSON/CSV summary export, UUID validation, memoized rendering, 20 tests (#341)

## [2026.02.189] - 2026-02-28
### Added
- Financial Impact Dashboard: side-by-side scenario cost comparison with CostRangeDisplay, AssumptionTable (inline edit), ScenarioDeltaHighlight (delta with color coding), parallel scenario loading, SSR-safe routing, 16 tests (#369)

## [2026.02.188] - 2026-02-28
### Added
- Persona-specific dashboard APIs: Engagement Lead (7 KPIs), Process Analyst (processing status, conflict queue), SME (review stats, decision history), Client Stakeholder (read-only findings), role-based access control, 23 tests (#362)

## [2026.02.187] - 2026-02-28
### Added
- Gap analysis dashboard API: gap counts by type/severity, TOM dimension alignment scores (1.0 - avg_severity), prioritized recommendations, maturity heatmap, 16 tests (#347)

## [2026.02.186] - 2026-02-28
### Added
- Evidence mapping overlay API: reverse evidence-to-element lookup, dark elements with type-specific acquisition suggestions, 19 tests (#343)

## [2026.02.185] - 2026-02-28
### Added
- Confidence heatmap API: per-element confidence map, brightness distribution summary with CSV export, enum-based comparison, 14 tests (Part of #341)

## [2026.02.184] - 2026-02-28
### Added
- BPMN viewer API: latest model with BPMN XML, element evidence detail, engagement dashboard KPIs, engagement access control, 19 tests (#338)

## [2026.02.183] - 2026-02-28
### Added
- Async executive report generation: 5-section assembly with evidence appendix and in-text citations, Redis job tracking, HTML/PDF download, engagement access control, 32 tests (#356)

## [2026.02.182] - 2026-02-28
### Added
- POV orchestrator API endpoints: progress tracking, version history with diff, engagement access control, TOTAL_STEPS constant, 23 tests (#318)

## [2026.02.181] - 2026-02-28
### Added
- Desktop task mining pipeline: SourceType/Brightness StrEnums, canonical event dict with source_system/engagement_id, PII documentation, error path tests, 44 tests (#355)

## [2026.02.180] - 2026-02-28
### Added
- Alerting engine: severity-based routing, configurable channels, escalation rules, engagement-scoped, 24 tests (#366)

## [2026.02.179] - 2026-02-28
### Added
- Variant comparison replay: LCS alignment algorithm, divergence detection (activity/performer/one-sided), per-step cycle time deltas, divergence evidence linking, 39 tests (#342)

## [2026.02.178] - 2026-02-28
### Added
- Aggregate volume replay: per-interval flow metrics (hourly/daily/weekly), bottleneck detection with configurable threshold, gateway variant distribution, heat map traceability, 36 tests (#339)

## [2026.02.177] - 2026-02-28
### Added
- Single-case timeline replay: brightness classification (bright/dim/dark), paginated frame retrieval, evidence ref linking, 48 tests (#337)

## [2026.02.176] - 2026-02-27
### Added
- POV generation orchestrator: PovGenerationWorker with 8-step LCD pipeline tracking, PovGenerationState with step progression/completion %, FAILED_PARTIAL preservation, compute_version_diff, 38 tests (Part of #318)

## [2026.02.175] - 2026-02-27
### Added
- Async task architecture: Redis Streams-backed TaskQueue with TaskWorker ABC, consumer groups (XREADGROUP/XACK), retry logic, concurrency control via asyncio.Semaphore, TaskProgress tracking, 33 tests (#320)

## [2026.02.174] - 2026-02-27
### Added
- Celonis EMS integration: event log, process model, and conformance deviation mappers with idempotent dedup, severity scoring, MismatchType mapping, checkpoint tracking, 45 tests (#325)

## [2026.02.173] - 2026-02-27
### Added
- Soroco Scout Work Graph integration: ScoutActivity parser, Activity node mapping with telemetric epistemic frames, SUPPORTED_BY evidence edges, ProcessElementMapping, WorkGraphImportResult, 30 tests (#326)

## [2026.02.172] - 2026-02-27
### Added
- ARIS AML and Visio VSDX process model importers: ModelImporter ABC with ImportedModel pre-graph-commit data structure, ARIS ObjDef/CxnDef/Lane parsing, Visio master shape mapping and connector resolution, defusedxml XXE protection, 28 tests (#328)

## [2026.02.171] - 2026-02-27
### Added
- SaaS connector incremental sync: SyncCheckpointStore with Redis key pattern, SyncLog with new/updated/skipped counts, async coordinator with checkpoint lifecycle, SAP DATS/TIMS/OData timestamp conversion, 34 tests (#330)

## [2026.02.170] - 2026-02-27
### Added
- XES event log importer: streaming IEEE XES parser with defusedxml XXE protection, standard extension mapping, batch processing, .xes.gz support, malformed XML handling, 25 tests (#332)

## [2026.02.169] - 2026-02-27
### Added
- Connector framework: CredentialProvider (env var + secrets manager), @with_retry decorator with exponential backoff and jitter, TransformPipeline with FieldMappingStep, rate limit header parsing, Credential repr masking, 34 tests (#323)

## [2026.02.168] - 2026-02-27
### Added
- Replay API endpoints: 5 async task endpoints (single-case, aggregate, variant-comparison, status, paginated frames), date-typed time ranges, Literal granularity, 1000-task eviction cap, schemas in src/api/schemas/, 30 tests (#345)

## [2026.02.167] - 2026-02-27
### Added
- Schema intelligence library: YAML-based templates for ServiceNow, SAP, Salesforce, case-insensitive table lookup, manual fallback mode, 4 API endpoints, 34 tests (#335)

## [2026.02.166] - 2026-02-27
### Added
- Transformation templates library: 4 analysis templates (consolidate tasks, automate gateway, shift decision, remove control), Literal action validation, max 500 elements, IDOR-safe, 35 tests (#376)

## [2026.02.165] - 2026-02-27
### Added
- LLM suggestion feedback loop: RejectionFeedback model/migration, traceability chain (modification→suggestion→audit log), exclusion prompt generation, IDOR-safe endpoints, LIMIT 50 on pattern queries, 25 tests (#390)

## [2026.02.164] - 2026-02-27
### Added
- Per-scenario simulation engine: ScenarioSimulationAdapter for all 7 modification types, confidence overlay (Bright/Dim/Dark), async trigger with status polling, IDOR-safe engagement membership check, background task lifecycle management, 31 tests (#380)

## [2026.02.163] - 2026-02-27
### Added
- Sensitivity analysis engine: OAT sensitivity ranking, tornado chart data, confidence-weighted P10/P50/P90 percentiles, custom cost functions, negative value support, 24 tests (#364)

## [2026.02.162] - 2026-02-27
### Added
- Governance flag detection for LLM suggestions: SoD checks for incompatible role mergers, regulatory compliance flagging for regulated elements, authorization change detection, knowledge boundary templates, engagement-scoped IDOR-safe query, engagement:update permission, 19 tests (#381)

## [2026.02.161] - 2026-02-27
### Added
- Cost-per-role and volume forecast modeling: RoleRateAssumption and VolumeForecast models, engagement-scoped CRUD, staffing/volume/quarterly/FTE-savings computation with interval arithmetic, typed TaskAssignment payloads, seasonal factor validation, unique constraint on (engagement_id, role_name), migration 078, 25 tests (#359)

## [2026.02.160] - 2026-02-27
### Added
- Financial assumption management: engagement-scoped CRUD, version history audit trail, confidence explanation/range fields, CHECK constraint for source-or-explanation invariant, engagement-scoped PATCH/history (IDOR fix), efficient count query, 16 tests (#354)

## [2026.02.159] - 2026-02-27
### Added
- Suggestion review workflow: ACCEPT/MODIFY/REJECT disposition for LLM suggestions, ScenarioModification creation with template_source and suggestion linkage, modified_content storage, rejection reason tracking, row-level locking for concurrent disposition safety, 409 Conflict for already-disposed, migration 076, 20 tests (#379)

## [2026.02.158] - 2026-02-27
### Added
- Seed list coverage report and dark room backlog: coverage computation with term-to-element name matching, dark segments ranked by uplift, evidence acquisition actions, SQL-filtered threshold, related seed terms cross-reference, thin route handlers delegating to service layer, 26 tests (#367)

## [2026.02.157] - 2026-02-27
### Added
- Best practices library and industry benchmarking: BestPractice model extension (title, maturity_level 1-5), migration 074-075, percentile ranking with linear interpolation, gap-to-practice matching by domain/dimension/keyword, domain filter on best-practices search, engagement metadata_json, 36 tests (#363)

## [2026.02.156] - 2026-02-27
### Added
- Republish cycle and version diff with BPMN color-coding: apply validation decisions (CONFIRM/CORRECT/REJECT/DEFER) to produce new POV versions, structured diff with green/red/yellow color hints, dark-room shrink rate, rename collision detection, corrected fields persistence fix, 31 tests (#361)

## [2026.02.155] - 2026-02-27
### Added
- Validation APIs: pack detail retrieval with engagement-scoped IDOR protection, filtered decision listing with action/reviewer/pack filters and pagination, role-based reviewer routing via RoleActivityMapping with unique constraint, migration 073, 14 tests (#365)

## [2026.02.154] - 2026-02-27
### Added
- Evidence grading progression tracking: per-version grade distributions (U/D/C/B/A), aggregate and per-element improvement rate computation with 100% cap, multi-cycle trend data for stacked bar charts, GradingSnapshot model, migration 072, 19 tests (#357)

## [2026.02.153] - 2026-02-27
### Added
- Structured reviewer actions with graph write-back: CONFIRM (grade promotion C→B→A, +0.1 confidence), CORRECT (SUPERSEDES edge + retraction), REJECT (ConflictObject creation, severity 0.8), DEFER (Dark Room backlog), ValidationDecision model, :Assertion-labeled Cypher, element_id pack validation, property allowlist injection defense, 30 tests (#353)

## [2026.02.152] - 2026-02-27
### Added
- Claim write-back service with Neo4j graph integration: SurveyClaim ingestion with SUPPORTS/CONTRADICTS edges, certainty tier weights (KNOWN=1.0 to CONTRADICTED=-0.5), EpistemicFrame nodes with HAS_FRAME linkage, auto-created ConflictObjects, activity confidence recomputation, engagement-scoped IDOR-safe Cypher queries, 27 tests (#324)

## [2026.02.151] - 2026-02-27
### Added
- Survey bot with 8 probe types: SurveySession lifecycle, fatigue-optimized probe generation from seed terms (EXISTENCE → UNCERTAINTY ordering), claim creation with conflict flagging, session summaries with certainty tier distribution, engagement-scoped IDOR-safe endpoints, migration 070, 23 tests (#319)

## [2026.02.150] - 2026-02-27
### Added
- Seed list pipeline with 4-stage workflow: consultant vocabulary upload with deduplication, NLP refinement with source tracking, probe generation (4 templates per term), extraction targeting for active terms, engagement-scoped endpoints with IDOR-safe DELETE, 25 tests (#321)

## [2026.02.149] - 2026-02-27
### Added
- Certainty tier tracking and survey claim management: SurveyClaimHistory audit trail, tier promotion with history recording, paginated filtered claim queries, shelf data request auto-generation from SUSPECTED claims, engagement-scoped IDOR-safe endpoints with require_engagement_access, migration 069, 24 tests (#322)

## [2026.02.148] - 2026-02-27
### Added
- Data classification and GDPR compliance framework: four-tier classification (public/internal/confidential/restricted) with access control, per-engagement retention policies with ARCHIVE/DELETE enforcement, ROPA tracking with all six Article 6 lawful bases, compliance reporting, RBAC-protected API routes, migration 068, 31 tests (#317)

## [2026.02.147] - 2026-02-27
### Added
- Scenario comparison dashboard API: side-by-side comparison of 2-5 scenarios across 5 metrics (cycle time, FTE, confidence, governance coverage, compliance flags), best/worst flagging with min_is_best for deltas, governance heuristic documentation, deterministic result ordering, 13 tests (#383)

## [2026.02.146] - 2026-02-27
### Added
- Consent architecture for endpoint capture: OPT_IN/ORG_AUTHORIZED/HYBRID consent modes, policy bundle versioning, 7-year retention floor, DB-level immutability trigger on core fields, DELETE prevention trigger, RESTRICT FK policy, withdraw+create pattern for scope updates, consent validation for pipeline gating, migration 067, 23 tests (#382)

## [2026.02.145] - 2026-02-27
### Added
- Export watermarking with recipient tracking: HMAC-SHA256 invisible watermarks, visible watermark text, HTML meta embedding, append-only export log with RESTRICT FK policy, WatermarkExtractor forensic recovery, dedicated watermark_signing_key, export:read RBAC permission, migration 066, 20 tests (#387)

## [2026.02.144] - 2026-02-27
### Added
- Evidence confidence overlay per scenario: per-element brightness lookup from ProcessElement, Dark-area modification warnings, risk score computation (bright/(bright+dark)), multi-scenario comparison with max-10 cap, engagement access control, 19 tests (#385)

## [2026.02.143] - 2026-02-27
### Added
- LLM audit trail with hallucination flagging: engagement-level querying with date range, hallucination flagging with re-flag guard, suggestion disposition stats (acceptance/modification/rejection rates), SQLAlchemy before_flush immutability enforcement, partial index on hallucination_flagged, migration 065, 21 tests (#386)

## [2026.02.142] - 2026-02-27
### Added
- Cohort suppression for analytics privacy: minimum cohort size enforcement (configurable per engagement, platform default in Settings), export blocking with HTTP 422, EXPORT_BLOCKED audit logging, engagement existence validation, session commit fix, 21 tests (#391)

## [2026.02.141] - 2026-02-27
### Added
- Policy Decision Point (PDP) service: ABAC policy evaluation with PERMIT/DENY decisions, in-memory cache (5s TTL with asyncio.Lock), obligation framework (watermark, enhanced audit, MFA, redaction), append-only audit trail, conditions validation, default policy seeding, role hierarchy comparison, 4 API endpoints, 25 tests (#377)

## [2026.02.140] - 2026-02-27
### Added
- Cross-border data transfer controls: GDPR-compliant transfer evaluation chain (residency → jurisdiction → TIA → SCC), jurisdiction registry, Transfer Impact Assessment lifecycle, Standard Contractual Clauses recording, append-only transfer log, role permissions for transfer:read/write and incident:read/write, migration 062, 20 tests (#395)

## [2026.02.139] - 2026-02-27
### Added
- Incident response automation: P1-P4 classification with GDPR 72-hour deadline, containment with access restriction and audit freeze events, 48-hour DPO escalation, timeline generation on close with 7-year retention, actor derived from authenticated user, 404/409 error differentiation, migration 061, 16 BDD tests (#397)

## [2026.02.138] - 2026-02-27
### Added
- Telemetry-triggered micro-survey generation: MicroSurvey model with GENERATED/SENT/RESPONDED status, deviation-to-probe mapping (5 categories), anomaly threshold gate (>2.0 std devs), SurveyClaim linkage, API endpoints (generate/respond/list), migration 060, ORM relationships, 16 tests (#398)

## [2026.02.137] - 2026-02-27
### Added
- Shelf-epistemic integration: auto-create shelf data request items from epistemic actions, follow-through rate endpoint (target >50%), source filter (PLANNER/MANUAL), ShelfRequestItemSource enum, migration 059, 11 BDD tests (#399)

## [2026.02.136] - 2026-02-27
### Added
- Epistemic Action Planner: GET endpoint for cached plans, shelf request linkage fix, engagement-level IDOR guard, pagination, shelf_request_id in response, 10 BDD tests (#389)

## [2026.02.135] - 2026-02-27
### Added
- Illumination Planner: targeted evidence acquisition with FORM_ACTION_TYPE_MAP (9 forms → 3 action types), idempotency guard (409 on duplicate), progress tracking, segment completion with recalculation trigger, 11 BDD tests (#396)

## [2026.02.134] - 2026-02-27
### Added
- Dark Room backlog management: prioritized Dark segments ranked by uplift, missing knowledge forms with probe types, Neo4j form coverage (outbound + inbound edges), engagement authz check, configurable dark_threshold query param, 12 BDD tests (#394)

## [2026.02.133] - 2026-02-27
### Added
- Evidence gap ranking with confidence uplift projection: per-gap uplift computation, cross-scenario shared gap detection with correlated subquery, Pearson correlation accuracy tracking, UpliftProjection model + migration 057, audit logging, 12 BDD tests (#393)

## [2026.02.132] - 2026-02-27
### Added
- Governance overlay API for process model activities: per-activity governance status classification (governed/partially_governed/ungoverned), ontology-aligned Cypher traversal (GOVERNED_BY→Policy/Regulation, IMPLEMENTS reverse join for Controls), IDOR-safe engagement access check, 10 BDD tests (#331)

## [2026.02.131] - 2026-02-27
### Added
- Gap-targeted probe generation from knowledge form gaps: GapProbeGenerator with brightness-based uplift scoring, form-to-probe-type mapping consolidated as single source of truth, POST/GET endpoints with pagination, 12 BDD tests (#327)

## [2026.02.130] - 2026-02-27
### Added
- CanonicalActivityEvent schema and Event Spine Builder: multi-source canonicalization, dedup with tolerance window, FK-constrained engagement_id, timezone-safe comparison, pagination with true count, 17 BDD tests (#334)

## [2026.02.129] - 2026-02-27
### Added
- Nine Universal Process Knowledge Forms: coverage computation and gap detection per engagement, ontology-validated edge type mappings, parameterized Cypher queries, 12 BDD tests (#316)

## [2026.02.128] - 2026-02-27
### Added
- Governance CRUD APIs: policy/control/regulation CRUD with soft-delete, Neo4j graph sync (write transactions), GET single regulation endpoint, governance chain traversal, 10 BDD tests (#329)

## [2026.02.127] - 2026-02-27
### Added
- Process maturity scoring: CMMI-aligned maturity levels (1-5), MaturityScore model + migration 051, evidence coverage/governance/metric dimensions, maturity heatmap with latest-per-area subquery, MaturityScoringService, 15 BDD tests (#358)

## [2026.02.126] - 2026-02-27
### Added
- Governance gap detection: GapFinding model + migration 055, regulation-aware gap resolution, ungoverned activity Cypher queries, severity scoring by activity criticality, idempotent gap persistence, 17 BDD tests (#340)

## [2026.02.125] - 2026-02-27
### Added
- Control effectiveness scoring: ControlEffectivenessScore model + migration 054, execution rate thresholds (90/70/50%), evidence-linked scoring, trend analysis with period comparison, 17 BDD tests (#336)

## [2026.02.124] - 2026-02-27
### Added
- Compliance state machine: ComplianceAssessment model + migration 053, control coverage percentage, state transitions (NOT_ASSESSED → FULLY/PARTIALLY/NON_COMPLIANT), compliance dashboard summary, 20 BDD tests (#333)

## [2026.02.123] - 2026-02-27
### Added
- Per-activity TOM alignment scoring: TOMAlignmentRun/TOMAlignmentResult models + migration 051, async background scoring, cosine similarity classification (NO_GAP/PARTIAL/FULL), gap rationale generation with LLM fallback, paginated results, 30 BDD tests (#348, #352)

## [2026.02.122] - 2026-02-27
### Added
- TOM definition management APIs with structured dimensions: TOMDimensionRecord and TOMVersion models, migration 050, structured DimensionInput with maturity 1-5 validation, version snapshotting on PATCH with atomic SQL-level increment and SELECT FOR UPDATE, duplicate dimension_type validation, version history endpoint, import/export endpoints, 18 BDD tests (#344)

## [2026.02.121] - 2026-02-27
### Added
- Cross-source consistency reporting: disagreement report with summary header and per-type breakdown, consistency metrics with agreement rate formula, POV version trend with conflict reduction rate, Pydantic response schemas, require_permission auth, HTML-escaped PDF template, paginated disagreement query, 13 BDD tests (#392)

## [2026.02.120] - 2026-02-27
### Added
- Disagreement resolution workflow: conflict resolution API with 5 endpoints (list/resolve/assign/escalate/escalation-check), filterable disagreement report (mismatch type, severity range, status, escalation flag, assigned SME), pagination, immutable audit trail (CONFLICT_ASSIGNED/RESOLVED/ESCALATED), 48h auto-escalation threshold, resolver_id/assigned_to columns on ConflictObject (migration 049), ConflictResolveRequest/AssignRequest/EscalateRequest schemas, 21 BDD tests (#388)

## [2026.02.119] - 2026-02-27
### Added
- I/O mismatch and control gap detection with shelf data requests: IOMismatchDetector (unmatched CONSUMES via NOT EXISTS Cypher), ControlGapDetector (ControlRequirement vs GOVERNED_BY absence), auto-generated ShelfDataRequest for control gaps, ControlRequirement node and REQUIRES_CONTROL relationship in ontology, _activity_criticality with max() multi-keyword scoring, idempotent shelf request dedup, pipeline extended to 6 detectors, 28 BDD tests (#378)

## [2026.02.118] - 2026-02-27
### Added
- Three-way distinction classifier for conflict resolution: ThreeWayDistinctionClassifier with NAMING_VARIANT (seed list alias + graph VARIANT_OF merge), TEMPORAL_SHIFT (non-overlapping effective dates + bitemporal validity), GENUINE_DISAGREEMENT (epistemic frame tagging + SME review flag), public run_write_query() on KnowledgeGraphService, MERGED_EDGE relationship in ontology, resolution_details/classified_at/classifier_version columns on ConflictObject (migration 048), batch classification, idempotent re-classification, 20 BDD tests (#384)

## [2026.02.117] - 2026-02-27
### Added
- Rule and existence conflict detection with temporal resolution: RuleConflictDetector (BusinessRule/HAS_RULE Cypher), ExistenceConflictDetector (EVIDENCED_BY absence), configurable authority weights per evidence category, check_temporal_resolution() for non-overlapping effective dates, conflict_detail (JSON) and resolution_hint columns on ConflictObject (migration 047), BusinessRule node and HAS_RULE relationship in ontology, pipeline extended to 4 detectors, 31 BDD tests (#375)

## [2026.02.116] - 2026-02-27
### Added
- LLM suggestion engine with audit logging: generate_audited_suggestions() wrapping AlternativeSuggesterService, LLMAuditLog model + migration (046), governance flag enrichment via GOVERNED_BY graph relationships, consideration framing enforcement, audit log in try/except finally block, public method delegators on suggester service, GET /scenarios/{id}/llm-audit route, 14 BDD tests (#374)

## [2026.02.115] - 2026-02-27
### Added
- Scenario Comparison Workbench CRUD: dedicated /api/v1/scenarios routes with max-5-per-engagement enforcement (SELECT FOR UPDATE), ScenarioStatus enum (DRAFT/SIMULATED/ARCHIVED), modification CRUD with DRAFT-only restriction, engagement membership authorization (IDOR protection), modification_count via SQL subquery, router registered in main app, 20 BDD tests (#373)

## [2026.02.114] - 2026-02-27
### Added
- Sequence and role conflict detection engine: SequenceConflictDetector (contradictory PRECEDES edges), RoleConflictDetector (different PERFORMED_BY assignments), severity scoring with weight differential and recency factor, idempotent ConflictObject persistence, public run_query() on KnowledgeGraphService, LIMIT 500 on Cypher queries, 26 BDD tests (#372)

## [2026.02.113] - 2026-02-27
### Added
- Gap-prioritized transformation roadmap generator: topological sort (Kahn's algorithm) for dependency resolution, threshold-based phase bucketing into 3-4 implementation phases (Quick Wins→Foundation→Transformation→Optimization), composite scoring from priority_score + effort estimate, HTML export with XSS-safe rendering, TransformationRoadmapModel with JSONB phases, remediation_cost and depends_on_ids columns on GapAnalysisResult, effort_weeks property (1-5 scale → 0.5-8 weeks), IDOR-protected roadmap endpoints with engagement membership checks, Alembic migration 045, 31 BDD tests (#368)

## [2026.02.112] - 2026-02-27
### Added
- Monitoring agent framework: BaseMonitoringAgent ABC with lifecycle management (start→connect→poll→stop), health state machine (STARTING→CONNECTED→POLLING→DEGRADED→UNHEALTHY→STOPPED), exponential backoff retry with circuit breaker after max failures, bounded event history (deque maxlen=1000), AgentRegistry for multi-agent lifecycle and health aggregation, Pydantic config models (AgentConfig, RetryConfig), GET /api/v1/monitoring/agents/health endpoint, connection_params repr=False for credential safety, 42 BDD tests (#346)

## [2026.02.111] - 2026-02-27
### Added
- Monitoring dashboard aggregation endpoint: GET /api/v1/monitoring/dashboard/{engagement_id} with date range filtering (default 7 days), agent status aggregation from TaskMiningAgent, deviation counts by severity, evidence flow rate (items/min last 5 min), alert summary, compliance score trend from MetricReading+SuccessMetric, trend direction computation (half-average comparison), 29 BDD tests (#371)

## [2026.02.110] - 2026-02-27
### Added
- Dark-Room Shrink Rate tracking dashboard: DarkRoomSnapshot model with unique constraint on (engagement_id, version_number), per-version shrink rate computation, below-target alert generation with dark segment names, illumination timeline tracking dark→dim/bright transitions, GET /api/v1/validation/dark-room-shrink with engagement access control, Alembic migration 044, 42 BDD tests including endpoint integration tests (#370)

## [2026.02.109] - 2026-02-27
### Added
- Continuous evidence collection pipeline: async Redis stream consumer with quality scoring, contradiction detection hook, incremental knowledge graph updates, time-based per-engagement quality threshold monitoring, rolling-window MetricsCollector (processing rate, p99 latency, queue depth, errors, avg quality), GET /api/v1/monitoring/pipeline/metrics endpoint with auth, submit_evidence_to_pipeline helper, 33 BDD tests (#360)

## [2026.02.108] - 2026-02-27
### Added
- Review pack generation engine: segments POV activities into 3-8 activity packs, aggregates evidence/confidence/conflicts/seed terms, SME routing by primary role, async POST with task_id (HTTP 202), paginated GET, failure sentinel on error, engagement validation, Alembic migration 043, 36 BDD tests (#349)

## [2026.02.107] - 2026-02-27
### Added
- RACI matrix derivation from knowledge graph edges: PERFORMED_BY→R, GOVERNED_BY→A, CONSULTED_BY/REVIEWS→C, NOTIFIED_BY→I, dedup on (activity, role, assignment), SME validation with audit trail, CSV export, GET/POST/PATCH/GET endpoints, Alembic migration 042, 41 BDD tests (#351)

## [2026.02.106] - 2026-02-27
### Added
- Process deviation detection engine with severity scoring: skipped activity, timing anomaly, and undocumented activity detection, importance-weighted severity formula, DeviationSeverity enum, GET /api/v1/deviations with filters/pagination, Alembic migration 041, 45 BDD tests (#350)

## [2026.02.105] - 2026-02-27
### Added
- BPMN model assembly with evidence citations and 3D confidence: three-dimensional confidence (score + brightness + evidence grade), gap markers on DARK elements, variant annotations for multi-path evidence, B/C grade distinction, 67 tests (#315)

## [2026.02.104] - 2026-02-27
### Added
- Audit logging middleware with before/after values, query API, and append-only trigger: fire-and-forget async persistence, IP extraction, user agent capture, resource type inference, admin-only query endpoint with filters/pagination, JSONB before/after change tracking, PostgreSQL append-only trigger, Alembic migration 040, 77 BDD tests (#314)

## [2026.02.103] - 2026-02-27
### Added
- OAuth2/OIDC authentication and RBAC authorization BDD tests: 47 tests covering JWT validation, token rejection, role boundaries for all 5 roles, engagement access control, permission matrix completeness (#313)

## [2026.02.102] - 2026-02-27
### Added
- PostgreSQL Row-Level Security for engagement data isolation: RLS policies on 32 engagement-scoped tables, table name validation, WITH CHECK on UPDATE, session context management, admin bypass mechanism, Alembic migration 039, 50 BDD tests (#311)

## [2026.02.101] - 2026-02-27
### Added
- Client evidence submission portal with token-based intake: time-limited UUID tokens, Levenshtein auto-matching, bulk upload progress tracking, intake API routes, 41 BDD tests (#308)

## [2026.02.100] - 2026-02-27
### Added
- Cross-source triangulation engine: evidence plane classification (4 planes), evidence_coverage and evidence_agreement factors with cross-plane bonus, single-source flagging, conflict detection, 33 BDD tests (#306)

## [2026.02.099] - 2026-02-27
### Added
- Evidence aggregation and entity extraction for LCD Steps 1-2: seed term guided extraction with confidence boost, duplicate candidate detection (containment, acronym, word overlap), DuplicateCandidate dataclass, ExtractionSummary with provenance maps, 62 BDD tests (#303)

## [2026.02.098] - 2026-02-27
### Added
- Contradiction resolution with three-way distinction classifier: naming variant (edit distance ≤2 to seed terms), temporal shift (≥2-year doc gap), genuine disagreement with epistemic frames; severity scoring, persistence bridge, 58 BDD tests (#312)

## [2026.02.097] - 2026-02-27
### Added
- Weighted consensus building with LCD algorithm: per-engagement weight overrides, exponential decay recency bias, variant detection, ConflictStub forwarding, brightness hints, 45 BDD tests (#310)

## [2026.02.096] - 2026-02-27
### Added
- Evidence cataloging with automated metadata extraction: PDF/Excel extractors, language detection, catalog API with LIKE-safe search, JSONB metadata, 38 BDD tests (#304)

## [2026.02.095] - 2026-02-27
### Added
- Database infrastructure BDD tests: Docker Compose services, pgvector, Neo4j APOC, Alembic migrations, SQLAlchemy async session — 35 tests (#309)

## [2026.02.094] - 2026-02-27
### Added
- API gateway BDD tests: health endpoint enhancements (timestamp, API_VERSION), OpenAPI, request tracing, CORS, DI validation with 33 tests (#307)

## [2026.02.093] - 2026-02-27
### Added
- Evidence lifecycle state machine: PENDING→VALIDATED→ACTIVE→EXPIRED→ARCHIVED with audit trail, SHA-256 hashing, auto-classification, retention expiry, 52 BDD tests (#301)

## [2026.02.092] - 2026-02-27
### Added
- Evidence quality scoring engine: Hill function freshness, configurable weights, validate_weights, composite scoring with 57 BDD tests (#300)

## [2026.02.091] - 2026-02-27
### Added
- Shelf data request workflow: BDD-aligned status enums, FollowUpReminder model, Pydantic schemas, migration 036 with 53 tests (#298)

## [2026.02.090] - 2026-02-27
### Added
- Evidence parsers: document (PDF/HTML/TXT), structured data (Excel/CSV/JSON), BPMN with factory dispatch and 74 BDD tests (#296)

## [2026.02.089] - 2026-02-27
### Added
- SemanticRelationship model with bitemporal validity: transaction + valid time, partial active index, check constraint (#305)

## [2026.02.088] - 2026-02-27
### Added
- SeedTerm entity schema: domain vocabulary store with 5 categories, 3 sources, self-referential merge, GIN FTS index (#302)

## [2026.02.087] - 2026-02-27
### Added
- ConflictObject model and disagreement taxonomy: 6 mismatch types, 3 resolution types, escalation lifecycle (#299)

## [2026.02.086] - 2026-02-27
### Added
- EpistemicFrame and SurveyClaim entity schemas: structured knowledge elicitation models with controlled vocabulary enforcement (#297)
- 8 probe types, 4 certainty tiers, 6 frame kinds, 12 authority_scope roles

## [2026.02.085] - 2026-02-27
### Added
- Controlled edge vocabulary: 12 typed edges with source/target constraints, atomic bidirectional creation, acyclicity enforcement (#295)
- Ontology v2.0.0: 5 new node types (DataObject, Assertion, Event, Gateway, SurveyClaim), 10+ new relationship types

## [2026.02.084] - 2026-02-27
### Added
- Three-dimensional confidence model: two-stage scoring formula, evidence grades (A-U), brightness classification with coherence constraint (#294)

## [2026.02.083] - 2026-02-27
### Security
- Fix Neo4j Cypher injection in get_relationships/traverse via VALID_RELATIONSHIP_TYPES allowlist (#271)
- Remove localStorage XSS-vulnerable token fallback in EvidenceUploader (#271)
- Add escapeHtml() to CF Worker, escape all user-controlled values in HTML templates (#271)
- Replace hardcoded DB passwords in init script with env vars (#271)
- Extend production secret validator to check postgres/neo4j passwords and debug flag (#271)
- Wrap sync run_simulation with asyncio.to_thread to prevent event loop blocking (#271)
- Filter list_engagements by membership for non-admin users (#271)
- Clear plaintext config_json when encrypted_config is written (#274)
- Encrypt integration credentials at rest with Fernet (#274)
- Mask PII in MCP auth logs (#274)

### Added
- Neo4j delete_node() and delete_engagement_subgraph() with engagement scoping (#272)
- ComponentErrorBoundary for BPMNViewer, GraphExplorer, MonitoringDashboard (#275)
- GDPR erasure job with _anonymize_user helper (#274)
- 33 new tests: audit logging, evidence dedup, auth cookie/blacklist, GDPR erasure (#274)
- AbortControllers in RegulatoryOverlay and AnnotationPanel useEffect (#275)
- Batch embedding writes via store_embeddings_batch() (#273)
- Redis-backed sliding window LLM rate limiter replacing in-process dict (#273)

### Changed
- Batch Neo4j node creation in evidence pipeline (N+1 fix) (#273)
- Add FK indexes on conformance.pov_model_id and taskmining.evidence_item_id (#272)
- Simplify Alembic env.py model imports to auto-register (#272)
- Add global rate limiting default (100/min) via SlowAPI (#272)
- Add pagination to get_fragments, POV gaps/contradictions/evidence-map endpoints (#272)
- Rename _assess_dimension_maturity to public API (#272)
- Add 12 Pydantic response schemas and response_model to 8 TOM endpoints (#272)
- Add audit logging to integration, governance, copilot, POV mutation endpoints (#274)
- Add user_consents and copilot_messages to GDPR data export (#274)
- Fix CI workflow to reference requirements.lock (#274)
- Upgrade agent cryptography>=43.0.0 (CVE-2024-26130) and PyJWT>=2.10.1 (CVE-2024-53861) (#274)
- Add AsyncGenerator return type to copilot event_generator (#275)

## [2026.02.078] - 2026-02-27
### Fixed
- Fix macOS agent build scripts for bash 3.2 compatibility (no `declare -A`, `mapfile`) (#270)
- Fix ad-hoc codesigning: strip pre-existing signatures, sign outside `.app` context (#270)
- Switch dylib references from `@rpath` to `@loader_path` for python-build-standalone (#270)
- Replace CommonCrypto GCM with CryptoKit AES.GCM (Command Line Tools SDK compat) (#270)
- Fix `InMemoryConsentStore` actor→class for protocol conformance (#270)
- Fix optional chaining on `pythonManager?.start()` (#270)

## [2026.02.077] - 2026-02-27
### Changed
- Convert IntegrityChecker from `@unchecked Sendable` + NSLock to Swift actor (#263)
- Replace `fputs`/`NSLog` with structured `os.Logger`/`AgentLogger` across 4 Swift files (#263)
- Convert 5 implicitly-unwrapped optionals to regular optionals in AppDelegate (#263)
- Fix PermissionsView timer closure to capture `state` reference instead of `self` struct (#263)
- Add 128-char length validation on MDM-supplied engagementId (#263)
- Move MockPermissionsProvider from production code to test target (#263)
- Add `@MainActor` annotation to AppSwitchMonitor (#263)
- Fix import ordering in 5 semantic bridge files (stdlib before third-party)

## [2026.02.076] - 2026-02-26
### Fixed
- Replace ~58 broad `except Exception` with specific exception types across 57 Python files (#267)
- Annotate ~55 intentionally broad handlers with `# Intentionally broad: <reason>` comments (#267)
- Widen health check handlers for TCP-level connectivity errors (OSError, ConnectionRefusedError) (#267)
- Add httpx.HTTPError to Camunda route handlers (#267)
- Replace os.path with pathlib.Path in evidence pipeline and Visio parser (#267)

## [2026.02.075] - 2026-02-26
### Fixed
- Fix N+1 query in governance SLA health dashboard and alerting — batch-fetch evidence items once per engagement (#261)
### Security
- Export KMFLOW_RELEASE_BUILD=1 in release.sh so downstream scripts enforce strict checks (#261)
- Populate real SHA-256 checksums for pinned python-build-standalone tarballs (#261)
- Update python-build-standalone URLs from indygreg to astral-sh after repo transfer (#261)

## [2026.02.074] - 2026-02-26
### Security
- Promote consentManager to AppDelegate property (prevents deallocation) (#259)
- Wire ConsentManager.onRevocation handler for runtime consent enforcement (#259)
- Add "Withdraw Consent…" menu item for GDPR Art. 7(3) compliance (#259)
- Reject legacy unsigned consent records (closes HMAC tamper bypass) (#259)
- Remove NSScreenCaptureUsageDescription from Info.plist (#259)
### Fixed
- Fix inverted BlocklistManager test assertion (nil bundleId returns false) (#259)
- Add async/await to BlocklistManager tests for actor compliance (#259)
- Remove stale ScreenCapture reference from TCC profile header (#259)

## [2026.02.073] - 2026-02-26
### Security
- Periodic integrity re-verification with configurable timer and violation callback (#257)
- HMAC-SHA256 signed integrity manifest with per-build random key (#257)
- Per-event consent guard via CaptureStateManager.isCapturePermitted (#257)
- Expanded L2 PII patterns: IBAN, file paths, UK National Insurance Number (#257)
- Replaced try! with lazy try? closures in regex compilation (#257)
### Added
- IntegrityChecker tests: 8 cases (verify, SHA-256, HMAC valid/tampered, periodic) (#257)
- L2PIIFilter tests: 12 cases covering all 8 patterns plus negatives (#257)
- ADR 001: sandbox-disabled rationale documentation (#257)
- Profile customization script for Team ID and org name replacement (#257)
- /Users/Shared cleanup in uninstall script (#257)

## [2026.02.072] - 2026-02-26
### Security
- AES-256-GCM buffer encryption with Keychain key provisioning and backward-compatible decryption (#254)
- IPC socket symlink detection and JSONSerialization-based auth handshake (#254)
- HMAC-SHA256 consent record signing with per-install Keychain key (#254)
- Consent revocation handler pattern for wiring buffer/IPC/Keychain cleanup (#254)
- kSecAttrSynchronizable on all Keychain stores to prevent iCloud sync (#254)
- CaptureStateManager.onStateChange() callback for monitor lifecycle management (#254)
- Disable content-level capture UI option until L2+ PII filtering validated (#254)
- Remove --deep from codesign, expose codesign errors, isolate PYTHONPATH (#254)

## [2026.02.071] - 2026-02-26
### Security
- Harden AgentLogger to use `privacy: .private` for all os_log interpolations (#255)
- Add `kSecAttrAccessibleAfterFirstUnlock` and `kSecAttrSynchronizable: false` to Keychain writes (#255)
- Clamp MDM integer config values to safe bounds in AgentConfig (screenshotInterval, batchSize, batchInterval, idleTimeout) (#255)
- Enforce HTTPS-only scheme validation for KMFLOW_BACKEND_URL in PythonProcessManager (#255)
- Remove unused `files.user-selected.read-write` entitlement (no effect outside sandbox) (#255)

## [2026.02.070] - 2026-02-26
### Fixed
- Add B-tree indexes on 13 unindexed ForeignKey columns for join/query performance (#252)

## [2026.02.069] - 2026-02-26
### Security
- Add --options runtime (Hardened Runtime) to all codesign invocations across build pipeline (#250)
- Refuse ad-hoc signing in release.sh (defense-in-depth) (#250)
- Pin all Python dependencies with exact versions and SHA-256 hashes for supply chain integrity (#250)
- Add SHA-256 verification for python-build-standalone tarball downloads (#250)

## [2026.02.068] - 2026-02-26
### Security
- Add WebSocket engagement membership verification for monitoring and alerts endpoints (#239)
- Wire engagement membership checks into all TOM CRUD routes (#239)
- Add pagination bounds (ge/le) to 22 limit/offset params across 10 route files (#239)

### Changed
- Replace duplicate _log_audit in engagements.py with centralized log_audit from core (#239)

### Added
- 2 new WebSocket auth tests for engagement membership (2308 total backend)

## [2026.02.067] - 2026-02-26
### Security
- Remove unused Apple Events entitlement from macOS agent (least privilege) (#244)
- Remove mouse x/y coordinates from InputEvent enum (GDPR data minimization) (#244)
- Block apps with nil bundleId by default (least privilege) (#244)
- Refuse ad-hoc signing for release builds (#244)
- Verify notarization result is "Accepted" before stapling; fail when credentials missing in release mode (#244)
- Add --require-hashes support for pip supply chain integrity (#244)
- Remove eval command injection in postinstall script (#244)
- Rewrite plist log paths from /Users/Shared to user home via PlistBuddy (#244)

### Changed
- Replace Thread.sleep with Task.sleep in SocketClient.reconnect() (#244)
- Convert 5 @unchecked Sendable classes to Swift actors for compiler-verified thread safety (#244)

## [2026.02.066] - 2026-02-26
### Security
- Harden RateLimitMiddleware: periodic pruning of expired entries to prevent memory exhaustion (#243)
- Stop trusting X-Forwarded-For header for client IP to prevent rate limit bypass (#243)

### Added
- 3 new tests for rate limiter pruning and X-Forwarded-For rejection (#243)

## [2026.02.065] - 2026-02-25
### Security
- Wire require_engagement_access into 11 route handlers for multi-tenancy enforcement (#242)
- Remove dead verify_api_key sync stub from MCP auth module (#242)
- Fix PIA R8 false encryption claim (#242)

## [2026.02.064] - 2026-02-25
### Security
- Audit Phase 0: Fix false security claims in whitepaper, DPA, PIA templates (#241)
- Correct encryption claims from "AES-256-GCM" to "planned — not yet implemented"
- Correct PII layer claims from "four-layer" to "two-layer on-device" (L3/L4 planned)
- Remove ScreenCapture from default TCC profile (principle of least privilege)
- Rename L1Filter to CaptureContextFilter for architectural clarity
- Fix incorrect socket and uninstall paths in whitepaper
- Fix false "All data is encrypted" UI string in WelcomeView

## [2026.02.063] - 2026-02-25
### Added
- CISO-ready macOS Task Mining Agent installer: app bundle with embedded Python.framework, code signing, notarization, privacy manifest
- Security hardening: buffer key and JWT token moved to macOS Keychain, mTLS client cert support, SHA-256 Python integrity manifest
- KeychainConsentStore replacing InMemoryConsentStore for persistent consent across restarts
- 5-step SwiftUI onboarding wizard (welcome, consent, permissions, connection, summary)
- Transparency log UI for real-time capture event visibility from menu bar
- DMG installer (create-dmg) and signed PKG installer with LaunchAgent for enterprise deployment
- MDM configuration profiles (managed preferences + TCC/PPPC) for Jamf/Intune/Mosyle
- Complete uninstall script removing all artifacts including Keychain items
- GitHub Actions release pipeline triggered by agent/v* tags
- CISO security whitepaper, DPA template, and PIA template for deployment approval

## [2026.02.062] - 2026-02-25
### Added
- ML task segmentation pipeline: feature extraction, gradient boosting classifier, hybrid classification, sequence mining (#231)
- Feature extraction: 30-dim vectors from AggregatedSession with interaction counts/ratios, temporal, app category one-hot (#232)
- Training data infrastructure: dataset builder, stratified splits, JSON export/import, versioned schemas (#233)
- Gradient boosting classifier: scikit-learn with calibrated probabilities, joblib model persistence (#234)
- Hybrid classifier: ML-first with configurable threshold fallback to rule-based classification (#235)
- Sequence pattern mining: n-gram extraction from classified action sequences (#235)
- Shared app category module: deduplicated detect_app_category() for graph ingestion and ML features
- 63 new tests across 4 test files (2306 total backend)

## [2026.02.061] - 2026-02-25
### Added
- Knowledge graph integration for task mining: graph ingestion, semantic bridge, LCD weight, variant detection (#225)
- Graph ingestion service: creates Application/UserAction nodes with PERFORMED_IN and PRECEDED_BY relationships (#226)
- Semantic bridge: links UserAction→Activity (SUPPORTS) and Application→System (MAPS_TO) via embedding cosine similarity (#227)
- LCD evidence weight: `task_mining: 0.90` in EVIDENCE_TYPE_WEIGHTS, above BPM models and documents (#228)
- Process variant detection: detects extra/missing/reordered steps, creates DEVIATES_FROM relationships (#229)
- Ontology extensions: SUPPORTS, MAPS_TO relationship types; DEVIATES_FROM extended for UserAction
- 71 new tests across 4 test files (2243 total backend)

### Fixed
- Chain traversal bug in variant detection: correctly identifies temporal chain starts (nodes with no predecessor)
- App category heuristic: "Calculator" no longer falsely categorized as spreadsheet

## [2026.02.060] - 2026-02-25
### Added
- Task mining admin dashboard: 4 frontend pages for agent management, capture policy, activity monitoring, quarantine review (#215)
- Agent management page: approve/revoke with confirmation, status badges, 30s auto-refresh (#216)
- Capture policy editor: app allowlist/blocklist with bundle ID validation, keystroke mode toggle with DPA confirmation (#217)
- Real-time activity dashboard: stats cards, WebSocket with exponential backoff, app usage bar chart, agent health (#218)
- PII quarantine review: TTL countdown, delete/release with reason, urgency filter (#219)
- Task mining API client module (taskmining.ts) with typed functions for all endpoints
- 38 Jest tests for API client and page utilities
- 400ms debounced engagement ID filter on all admin pages

### Fixed
- AppShell test: disambiguate multiple Dashboard link matches after adding TM Dashboard nav item

## [2026.02.059] - 2026-02-25
### Added
- Privacy and compliance suite: PII detection tests, quarantine cleanup, consent management, audit logging (#210)
- PII detection test suite: 217+ parametrized tests covering all 7 PII types with ≥99% recall validation
- Quarantine auto-cleanup job: atomic DELETE of expired PIIQuarantine records with summary reporting
- Consent management: ConsentRecord model, ConsentManager service, HMAC-SHA256 IP hashing, re-grant state machine
- Task mining audit logger: 11 new AuditAction enum values, insert-only TaskMiningAuditLogger with 9 convenience methods
- Alembic migration 028 for consent_records table

### Fixed
- PII pattern gaps: international phone (word boundary before +), US address (Broadway/Parkway suffixes), financial account (number/routing keywords)
- Quarantine cleanup TOCTOU: replaced count-then-delete with single atomic DELETE using rowcount
- Consent re-grant: REVOKED agents can now re-consent (REVOKED → APPROVED transition)
- IP address hashing: upgraded from bare SHA-256 to HMAC-SHA256 keyed by server secret

## [2026.02.058] - 2026-02-25
### Added
- Action aggregation engine: session grouping, rule-based classification, evidence materialization (#206)
- SessionAggregator: groups raw desktop events into bounded app sessions by app switches and idle periods
- ActionClassifier: first-match-wins rule engine with 6 default rules (communication, file_operation, review, data_entry, navigation_url, navigation_scroll)
- EvidenceMaterializer: converts classified sessions to EvidenceItem records (KM4WORK, reliability=0.90)
- YAML-configurable classification rules with documented ordering constraints
- 44 unit tests across 3 test files (session, classifier, materializer)

### Fixed
- YAML rule ordering aligned with hardcoded defaults (communication first, review before navigation_scroll)
- Unknown YAML conditions logged at ERROR level instead of WARNING
- PII upstream filtering contract documented for window_title_sample in materializer

## [2026.02.057] - 2026-02-25
### Added
- macOS desktop agent: Swift capture layer (21 source files) + Python intelligence layer (17 source files) (#195)
- Swift: CGEventTap input monitoring, NSWorkspace app switch, L1+L2 PII filtering, consent state machine, menu bar UI
- Python: Unix socket server, encrypted SQLite buffer, batch uploader, config manager, health reporter
- JWT auth module for agent-to-backend HTTP requests
- AmEx and JCB credit card PII patterns in both Swift and Python L2 filters

### Security
- Socket moved from /tmp to user-private ~/Library/Application Support/ with 0600 permissions
- Auto-generated random encryption key replaces hardcoded fallback
- Shared authenticated httpx.AsyncClient with JWT bearer tokens
- Socket reconnection with exponential backoff

### Fixed
- Async SQLite: all DB ops run via asyncio.to_thread() to avoid event loop blocking
- AnyCodable now handles arrays and nested dictionaries
- Menu bar items wired to action handlers via MenuActionDelegate
- Non-blocking cpu_percent() reads in health reporter

## [2026.02.056] - 2026-02-25
### Added
- Task Mining backend infrastructure: models, PII engine, API routes, processor, worker (#184)
- 37 GitHub Issues for Task Mining initiative (Epics 1-6, 37 stories) (#183)
- Full SDLC workflow infrastructure: commands, hooks, memory bank, coding standards

### Infrastructure
- SDLC hooks: session start, PR creation, post-merge, session end, decision log
- Memory bank: platformState, activeContext, decisionLog
- CalVer versioning initialized

## [2026.02.055] - 2026-02-24
### Fixed
- Fix 2 pre-existing frontend API client test failures

## [2026.02.054] - 2026-02-23
### Added
- 10 KMFlow logo concepts for brand identity review (#181)

## [2026.02.053] - 2026-02-22
### Added
- Frontend component tests for BPMNViewer, GraphExplorer, EvidenceUploader

## [2026.02.052] - 2026-02-21
### Fixed
- Audit remediation batch 2: remaining backlog (waves A/B/C) (#180)

## [2026.02.051] - 2026-02-20
### Changed
- Extract schemas and service layer from simulations.py (1334 to 1037 lines) (#179)

## [2026.02.050] - 2026-02-19
### Changed
- Refactor models.py into domain-specific package (77 classes, 11 modules) (#178)

## [2026.02.049] - 2026-02-18
### Added
- Implement HttpOnly JWT cookies (#156) and GDPR data subject rights (#165) (#177)

### Security
- Remove arbitrary Cypher query endpoint (security hardening) (#176)

## [2026.02.048] - 2026-02-17
### Fixed
- Audit remediation batch 1: resolve CRITICAL/HIGH findings (#175)

## [2026.02.047] - 2026-02-16
### Added
- Phase 3.2 + Phase 4: Complete Operating Model Scenario Engine (#127)
