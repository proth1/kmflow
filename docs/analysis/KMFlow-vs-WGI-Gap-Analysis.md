# KMFlow vs WorkGraphIQ (WGI): Gap Analysis & Recommendations

**Version**: 2.0
**Date**: 2026-02-26
**Status**: Final
**Authors**: Paul Roth, David Johnson

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-25 | Initial gap analysis against 5 WGI documents |
| 2.0 | 2026-02-26 | Added KM4ProcessBot v1 + David Johnson architectural vision; reduced true gaps from 12 to 9; expanded differentiators from 6 to 13; added unified capability model, merged knowledge graph schema, 3D confidence model, cross-source consistency checks, and updated phased delivery |

---

## Context

This analysis compares the KMFlow PRD (`docs/prd/PRD_KMFlow_Platform.md`) against **seven** source documents from the WorkGraphIQ (WGI) / KM4ProcessBot ecosystem:

1. **WGI PRD** — Full engineering-grade requirements (4 segments covering capture, graph, publishing, governance, NFRs, deployment)
2. **WGI Blueprint Generation** — 6-phase engagement lifecycle with BPM orchestration and handoff logic
3. **WGI Functional Requirements** — Detailed subsystem-by-subsystem functional specs with acceptance criteria
4. **WGI Solution Description** — End-to-end client-facing description of capabilities and outputs
5. **Why WGI** — Internal/external positioning and messaging (internal brief + client one-pager)
6. **KM4ProcessBot v1** — Structured process knowledge capture: nine universal process knowledge forms, seed list pipeline, survey bot with domain-seeded probes, controlled edge vocabulary, epistemic frames
7. **David Johnson Architectural Vision** — Original requirements and extended vision for knowledge factory, three context layers, SDLC transformation platform

Both systems occupy the same domain: evidence-driven process intelligence for consulting/transformation engagements. They share the same intellectual DNA — evidence-first, confidence-scored, knowledge-graph-backed, TOM gap analysis. WGI extends the vision significantly in several directions. KM4ProcessBot v1 provides structured process knowledge capture that KMFlow's v1 PRD had not yet formalized. David Johnson's architectural vision establishes guiding principles (domain lens via seed list, plural truth preservation, active inferencing) that inform both systems.

**v2 Key Findings**: Three v1 gaps (Survey Bot, Narrative Generation, RACI) are substantially addressed by KM4ProcessBot v1 concepts already in David Johnson's vision. They become FORMALIZE items (schema + integration work) rather than net-new capabilities. True gaps reduce from 12 to 9. KMFlow differentiators expand from 6 to 13 when KM4ProcessBot's unique contributions are included.

---

## 1. Shared DNA (What Both Get Right)

| # | Concept | KMFlow | WGI / KM4ProcessBot |
|---|---------|--------|---------------------|
| 1 | Evidence-first philosophy | Core principle | Core principle |
| 2 | Knowledge graph (Neo4j) | Semantic relationship engine | Work Reality Graph |
| 3 | Confidence scoring | 5-factor weighted model (0-1) | Bright/Dim/Dark + numeric 0-1 |
| 4 | BPMN 2.0 output | Generated with evidence citations | Generated with extension metadata |
| 5 | TOM alignment & gap analysis | Full gap engine with maturity scoring | Benchmarking + gap map + roadmap |
| 6 | Evidence quality scoring | 4 dimensions (completeness, reliability, freshness, consistency) | Multi-factor per evidence type |
| 7 | Consulting engagement scoping | Engagement-level isolation | Engagement Workspace container |
| 8 | Phased delivery | 4 phases (Foundation through Reimagination) | 6-phase lifecycle + Zero Phase |
| 9 | Scenario/future-state design | Scenario Comparison Workbench (Phase 3-4) | Scenario Studio + Assessment Overlay |
| 10 | Epistemic/uncertainty planning | Epistemic Action Planner with confidence uplift | Dark Room Operations + Illumination Planner |
| 11 | Multi-tenant isolation | Row-level security per engagement | Strict tenant boundary (physical + logical) |
| 12 | Structured knowledge capture | Evidence taxonomy (12 categories) | Nine universal process knowledge forms |
| 13 | Domain vocabulary awareness | Evidence categories with format-specific parsing | Seed list pipeline with NLP refinement |
| 14 | Cross-source validation | Contradiction resolution with severity scoring | Cross-source consistency checks (6 rules) |

---

## 2. True Gaps: What WGI Has That KMFlow Lacks (9 Gaps)

> **Note**: v1 identified 12 gaps. Three (Survey Bot GAP-3, Narrative Generation GAP-6, RACI GAP-7) are reclassified as FORMALIZE items because KM4ProcessBot v1 already defines the conceptual framework. They move to the KMFlow differentiators section as items that need schema formalization and integration, not net-new capability design.

### GAP-1: Desktop Endpoint Agent + Work-Surface Reality Capture (CRITICAL)

**WGI**: Full desktop agent (Windows + macOS) capturing focus sessions, interaction counts, system switching patterns, and Visual Context Events (VCEs — targeted screenshots converted to structured metadata on-device). This is the primary evidence plane that reveals "in-between" work invisible to system logs.

**KMFlow**: No endpoint agent for work-surface capture. Relies on evidence uploaded by consultants (documents, system exports, interviews). Has Soroco Scout integration planned (Phase 3) but as a connector, not a native capability. The macOS agent (`agent/macos/`) exists but serves consent/transparency, not work-surface capture.

**Impact**: WGI can capture work reality that KMFlow cannot — the 30-50% of operational time spent searching, navigating, waiting, verifying, and handling exceptions that never touches a system-of-record.

**Recommendation**: Three options:
- **Option A (Lean)**: Elevate Soroco Scout / desktop task mining integration from Phase 3 to Phase 2 as a first-class evidence plane. Add KM4Work (Category 7) processing as the "endpoint evidence" bridge.
- **Option B (Strategic)**: Extend the existing macOS agent codebase from consent/transparency into focus-session + VCE capture.
- **Option C (Partnership)**: Deep integration with an existing task mining vendor with a structured VCE metadata schema feeding directly into the knowledge graph.

### GAP-2: Cross-System Telemetry Connectors + Event Spine (CRITICAL)

**WGI**: Connector framework with 5 categories (SaaS/Enterprise Apps, Database/Data Platforms, Integration Telemetry, Observability/OpenTelemetry, Agent Runtime). Builds a canonical event spine (`case_id + activity + timestamp + provenance + confidence`) from raw logs through normalization and mapping.

**KMFlow**: SaaS connectors listed for Phase 3 (Salesforce, SAP, ServiceNow). Has XES format import and Celonis integration. But no canonical event spine construction, no mapping rule engine, no incremental extraction with watermarks, no schema drift detection.

**Impact**: Without an event spine, KMFlow cannot reconstruct case-centric longitudinal timelines from system data. It processes evidence that arrives but doesn't actively pull and stitch system telemetry.

**Recommendation**: Add a Canonicalization + Event Spine subsystem:
- Define `CanonicalActivityEvent` schema: `case_id, activity_name, timestamp_utc, source_system, performer_role_ref, evidence_refs, confidence_score, brightness`
- Add a mapping rule engine (configuration-driven, versioned) to transform raw system data into canonical events
- Prioritize Connector Category A (SaaS lifecycle extracts) for Phase 2
- Add schema drift detection and incremental extraction with watermarks

### GAP-3: Replay and Simulation Visualization Engine (HIGH)

**WGI**: Three replay modes — single-case replay (step-by-step with evidence pointers), aggregate volume replay (animated flow showing accumulation/throughput), variant comparison replay. Heat maps directly traceable to replay metrics.

**KMFlow**: Interactive HTML process flow visualizations (BPMN.js), confidence heatmaps, evidence mapping overlays. Process simulation and what-if analysis listed for Phase 3. No replay capability.

**Impact**: Replay is WGI's primary trust-building mechanism with stakeholders. KMFlow delivers static views; WGI lets executives "watch the work move."

**Recommendation**: Add replay visualization to Phase 3:
- Single-case timeline view (sequential event display with evidence pointers) — achievable with existing knowledge graph data
- Aggregate volume animation over process model — requires the event spine (GAP-2)
- Variant comparison replay with divergence highlighting
- Replay-to-heatmap traceability (click a hotspot, drill to contributing cases/variants)

### GAP-4: Validation Hub + Republish Cycle (HIGH)

**WGI**: Structured validation workflow — segment-level review packs routed to specific SMEs, structured reviewer actions (confirm/correct/reject/defer), validation writes back to graph, republish cycle produces v2/v3 with diffs and reduced dark-room coverage. Dark-room coverage is measurable and trendable across versions.

**KMFlow**: SME review via annotation (Flow 2, steps 8-10). Evidence validation workflow exists (auto-classify → human review → approve/reject). But no structured segment-level validation packs, no version-diffing, no dark-room shrink rate tracking.

**Recommendation**: Enhance the SME review workflow:
- Generate segment-level review packs from process model + evidence + confidence
- Implement structured validation actions (confirm/correct/reject/defer) that write directly to the knowledge graph
- Track dark-room shrink rate across POV versions as a KPI
- Add BPMN diff visualization between versions
- Integrate with evidence grading ladder (progression from unvalidated → proposed → confirmed)

### GAP-5: Policy Decision Point (OPA-style RBAC/ABAC) (MEDIUM)

**WGI**: Central Policy Decision Point + Policy Enforcement Points throughout the stack. Machine-enforceable policy bundles controlling capture posture, data access, export redaction/watermarking, cohort suppression, identity visibility. Versioned policy bundles.

**KMFlow**: RBAC per persona type, engagement-level data isolation, audit logging, data classification. But no central PDP, no ABAC, no policy enforcement points, no export watermarking, no cohort suppression.

**Recommendation**: Phase 3 enhancement:
- Implement a lightweight PDP service for access decisions + data handling obligations
- Add export watermarking for PDF/narrative artifacts
- Add cohort suppression (don't display analytics below minimum cohort size)
- Version policy configurations per engagement

### GAP-6: Deployment Flexibility (Cloud / Hybrid / On-Prem) (MEDIUM)

**WGI**: Explicitly supports 3 deployment modes — Cloud, Hybrid (hosted control plane + on-prem data plane), On-Prem (air-gapped, full Kubernetes deployment within client perimeter).

**KMFlow**: Docker Compose for dev, containerized deployment for prod. No explicit on-prem or hybrid deployment model.

**Recommendation**: Phase 3+. Add deployment mode configuration:
- Define `tenant.deployment_mode` attribute
- Document Kubernetes-based on-prem deployment pattern
- Design connector framework for "bring the extractor to the data" pattern

### GAP-7: Schema Intelligence Library (MEDIUM)

**WGI**: Versioned library of extraction templates for major enterprise platforms (SAP, ServiceNow, Salesforce, Snowflake, Databricks). Includes recommended source objects, lifecycle reconstruction patterns, correlation keys, known pitfalls. Guided configuration during onboarding.

**KMFlow**: No equivalent. SaaS connectors with native connector + semantic alignment, but no pre-built schema knowledge.

**Recommendation**: Phase 2-3. Build a schema intelligence library:
- Start with the 3 most common systems (ServiceNow, SAP, Salesforce)
- Document extraction templates, lifecycle tables, correlation keys
- Use as onboarding accelerator for new engagements

### GAP-8: BPM-Orchestrated Engagement Lifecycle (LOW-MEDIUM)

**WGI Blueprint**: Full 6-phase lifecycle orchestrated by BPM engine with hard logic gates, quality gates, data inheritance between phases, automated handoffs, and "truth velocity" tracking.

**KMFlow**: Engagement management with status tracking. BPMN workflows exist as documentation (`platform/*.bpmn`) but no BPM engine orchestrating the engagement lifecycle.

**Recommendation**: Phase 4. KMFlow already has Camunda-compatible BPMN models. Could activate them as executable workflows to orchestrate engagement phases with quality gates.

### GAP-9: Consent Architecture (LOW-MEDIUM)

**WGI**: Formal consent model (Opt-in, Org-Authorized, Hybrid) with immutable ConsentRecord per participant, linked to `policy_bundle_version`. Desktop widget with transparency controls.

**KMFlow**: The macOS agent has ConsentManager (`agent/macos/Sources/Consent/ConsentManager.swift`). But no platform-level consent model.

**Recommendation**: Extend the existing agent consent framework to the platform level if endpoint capture is added (GAP-1). Otherwise, lower priority.

---

## 3. KMFlow Differentiators (13 Items)

### What KMFlow Has That WGI Lacks

#### KMF-1: Evidence Taxonomy Breadth

**KMFlow**: 12 evidence categories including Audio, Video, Images, BPM Process Models, Regulatory/Policy documents, Controls/Evidence, Domain Communications, Job Aids/Edge Cases. Explicit format support per category with format-specific parsers.

**WGI**: Focused on three evidence planes (endpoint, system telemetry, survey). No explicit handling of pre-existing documents, audio, video, images, or regulatory frameworks as evidence inputs.

**Takeaway**: KMFlow's evidence taxonomy is a significant differentiator. Preserve and enhance it. WGI's three-plane model complements but does not replace it.

#### KMF-2: Regulatory-Policy-Control Overlay Engine

**KMFlow**: Explicit governance modeling — `Process --governed_by--> Policy --enforced_by--> Control --satisfies--> Regulation`. Compliance state tracking per process element. Control effectiveness scoring. Gap detection for ungoverned processes.

**WGI**: Mentions controls and compliance in passing but has no dedicated regulatory overlay engine.

**Takeaway**: Major KMFlow advantage for regulated industries (FS, Healthcare, Energy). Preserve and emphasize.

#### KMF-3: Shelf Data Request Workflow

**KMFlow**: Full shelf data request lifecycle — compose requests, deliver to clients, track responses, match received evidence to requested items, follow-up automation. Integrated with Epistemic Action Planner.

**WGI**: No explicit shelf data request management.

**Takeaway**: Consulting-native workflow that WGI doesn't address.

#### KMF-4: Semantic Bridge Architecture

**KMFlow**: Named semantic bridges — ProcessEvidenceBridge, EvidencePolicyBridge, ProcessTOMBridge, CommunicationDeviationBridge. Each with typed relationships and confidence weighting.

**WGI**: Work Reality Graph with typed edges, but focused on case/event/activity relationships rather than policy/TOM alignment.

**Takeaway**: KMFlow's bridge architecture is well-suited for the consulting use case. Keep and extend with WGI's case-event-activity edge types.

#### KMF-5: LCD Consensus Algorithm

**KMFlow**: Specific consensus algorithm with weighted voting across evidence types (system data > documentation > communications > interviews > job aids), contradiction resolution with severity scoring, recency bias.

**WGI**: Multi-plane reconciliation but no explicit weighted voting algorithm. Reconciliation is described at a conceptual level.

**Takeaway**: KMFlow's consensus algorithm is more implementable. Preserve it and extend to incorporate WGI's three evidence planes.

#### KMF-6: Celonis / Process Mining Tool Integration

**KMFlow**: Explicit Celonis EMS API integration for event log import, process model import, conformance results. XES format support. ARIS and Visio import.

**WGI**: Positions as replacing traditional process mining, not integrating with it.

**Takeaway**: KMFlow's integration approach is pragmatic for consulting firms that already use these tools.

#### KMF-7: Nine Universal Process Knowledge Forms (from KM4ProcessBot)

**KM4ProcessBot**: Defines nine fundamental forms of process knowledge that any process capture system must address — Activities, Sequences, Dependencies, Inputs/Outputs, Rules, Personas, Controls, Evidence, Uncertainty. Each form maps to specific graph structures and probe types.

**WGI**: Captures process knowledge but doesn't formalize the taxonomy of knowledge forms themselves.

**Takeaway**: The nine forms provide a completeness checklist for process capture. Formalize as a first-class schema in KMFlow.

#### KMF-8: Seed List Pipeline

**KM4ProcessBot**: Domain vocabulary extraction pipeline — domain seed list → NLP refinement → probe generation → extraction targeting. The seed list acts as a domain lens that focuses all capture and extraction on terms relevant to the specific business area.

**WGI**: No equivalent domain vocabulary pipeline. Relies on generic extraction patterns.

**Takeaway**: The seed list is KMFlow's mechanism for domain specialization without domain-specific model training. Formalize and integrate.

#### KMF-9: Structured Survey Bot with Domain-Seeded Probes

**KM4ProcessBot**: Eight probe types (existence, sequence, dependency, I/O, rule, persona, control, uncertainty), certainty tiers (known/suspected/unknown/contradicted), claim objects with proof expectations. Probes are generated from the seed list, not generic.

**WGI**: Process Assessment Bot (PAB) conducts structured interviews, but probe generation is not seed-list-driven and doesn't formalize the nine knowledge forms as probe categories.

**Takeaway**: KM4ProcessBot's survey bot is more structured than WGI's PAB. Formalize the claim schema and integrate probe generation with the seed list pipeline. This is a FORMALIZE item, not net-new.

#### KMF-10: Epistemic Frames

**KM4ProcessBot**: Typed epistemic frames (`frame_kind`: procedural/regulatory/experiential/telemetric) with `authority_scope` and `access_policy`. Frames partition knowledge by how it was obtained and who can assert it.

**WGI**: No equivalent. All assertions treated uniformly regardless of epistemic source.

**Takeaway**: Epistemic frames enable plural truth preservation — the system can hold conflicting assertions from different authority scopes without forcing premature resolution. Add to KMFlow's knowledge graph schema.

#### KMF-11: Bitemporal Validity Model

**KM4ProcessBot**: Every assertion carries `asserted_at`, `retracted_at`, `valid_from`, `valid_to`, `superseded_by`. Enables temporal queries ("what was believed true at time T?") and tracks how process knowledge evolves.

**WGI**: Temporal properties on some entities but no formal bitemporal model.

**Takeaway**: Bitemporal validity is essential for consulting engagements where process knowledge evolves across phases. Add to relationship properties in Neo4j.

#### KMF-12: Controlled Edge Vocabulary (12 Typed Edges)

**KM4ProcessBot**: Formalizes 12 typed edge kinds for the knowledge graph: `PRECEDES`, `TRIGGERS`, `DEPENDS_ON`, `CONSUMES`, `PRODUCES`, `GOVERNED_BY`, `PERFORMED_BY`, `EVIDENCED_BY`, `CONTRADICTS`, `SUPERSEDES`, `DECOMPOSES_INTO`, `VARIANT_OF`. Each with defined semantics and constraint rules.

**WGI**: Typed edges but not formalized into a controlled vocabulary with constraint rules.

**Takeaway**: The controlled edge vocabulary provides schema discipline for the knowledge graph. Formalize and enforce.

#### KMF-13: Cross-Source Consistency Checks (6 Rules)

**KM4ProcessBot**: Six automated detection rules for cross-source consistency: (1) Sequence conflict — two sources assert contradictory orderings, (2) Role conflict — different sources assign same activity to different performers, (3) Rule conflict — contradictory business rules, (4) Existence conflict — one source asserts activity exists while another denies it, (5) I/O mismatch — upstream output doesn't match downstream input, (6) Control gap — activity lacks governance while policy requires it.

**WGI**: Cross-plane reconciliation but doesn't formalize specific consistency check rules.

**Takeaway**: These six rules provide concrete, implementable consistency validation. Integrate into the consensus algorithm alongside KMFlow's existing contradiction resolution.

---

## 4. Cross-Source Consistency Checks (Detail)

The six rules from KM4ProcessBot v1, formalized for implementation:

| # | Check | Detection Logic | Resolution |
|---|-------|----------------|------------|
| 1 | **Sequence Conflict** | Source A asserts X→Y, Source B asserts Y→X | Flag as `SEQUENCE_MISMATCH`; resolve by evidence weight + recency |
| 2 | **Role Conflict** | Source A assigns Activity Z to Role R1, Source B assigns to R2 | Flag as `ROLE_MISMATCH`; present both with confidence; mark for SME validation |
| 3 | **Rule Conflict** | Business rule R from source A contradicts rule R' from source B | Flag as `RULE_MISMATCH`; check effective dates (bitemporal); escalate if unresolvable |
| 4 | **Existence Conflict** | Source A asserts activity exists, Source B denies or omits it | Flag as `EXISTENCE_MISMATCH`; weight by source authority + recency |
| 5 | **I/O Mismatch** | Upstream activity produces output O, downstream expects input I, O ≠ I | Flag as `IO_MISMATCH`; check for naming variants via seed list; escalate if true gap |
| 6 | **Control Gap** | Activity A has no governance edge, but policy P requires governance for A's category | Flag as `CONTROL_GAP`; generate shelf data request for evidence of control |

**Three-Way Distinction** for each mismatch:
- **Genuine Disagreement**: Sources truly conflict → preserve both views with epistemic frames, mark for validation
- **Naming Variant**: Same concept, different terminology → resolve via seed list / entity resolution
- **Temporal Shift**: Both true at different times → resolve via bitemporal validity model

---

## 5. Synthesis: Unified Capability Model

The best path forward takes KMFlow's existing architecture and evidence taxonomy as the foundation, then layers in WGI's evidence plane model, replay engine, validation hub, and engagement lifecycle rigor. KM4ProcessBot's structured knowledge capture fills the gap between passive evidence ingestion and active knowledge elicitation.

### 5.1 Updated Evidence Model (4 Planes)

The 4-plane model is an **organizing layer above** KMFlow's 12 evidence categories, not a replacement:

```
Plane 1: Document Evidence (KMFlow Categories 1-6, 8-12)
  - Pre-existing artifacts uploaded by consultants
  - Processed through KMFlow's evidence ingestion engine
  - Quality scored across 4 dimensions
  - Includes regulatory/policy docs, BPM models, job aids, communications

Plane 2: System Telemetry (WGI's System-Recorded Reality)
  - Cross-system connectors with canonical event spine
  - Schema Intelligence Library for accelerated onboarding
  - Incremental extraction, idempotent processing, drift detection
  - Maps to KMFlow Category 6 (SaaS Exports) + new connector framework

Plane 3: Work-Surface Reality (WGI's Desktop Agent)
  - Focus sessions, interaction counts, VCE metadata
  - Privacy-first: counts not content, on-device processing
  - Soroco Scout integration as bridge (Phase 2), native agent (Phase 3+)
  - Maps to KMFlow Category 7 (KM4Work)

Plane 4: Human Interpretation (KM4ProcessBot's Survey Bot)
  - Structured survey claims with certainty tiers
  - Domain-seeded probes targeting the nine process knowledge forms
  - Reconciliation against other planes
  - Telemetry-triggered micro-surveys (Phase 3)
```

### 5.2 Updated Knowledge Graph (Merged Schema)

Merge KMFlow's semantic bridge model with WGI's temporal case-event model and KM4ProcessBot's controlled edge vocabulary:

```
KMFlow existing (preserve):
  (Process)-[:SUPPORTED_BY]->(Evidence)
  (Process)-[:GOVERNED_BY]->(Policy)
  (Policy)-[:ENFORCED_BY]->(Control)
  (Control)-[:SATISFIES]->(Regulation)
  (Process)-[:DEVIATES_FROM]->(TOM)
  (Evidence)-[:CONTRADICTS]->(Evidence)
  (Activity)-[:FOLLOWED_BY]->(Activity)

KM4ProcessBot additions (formalize):
  Controlled Edge Vocabulary (12 types):
    PRECEDES, TRIGGERS, DEPENDS_ON, CONSUMES, PRODUCES,
    GOVERNED_BY, PERFORMED_BY, EVIDENCED_BY, CONTRADICTS,
    SUPERSEDES, DECOMPOSES_INTO, VARIANT_OF

  Epistemic Frame properties on assertions:
    frame_kind: procedural | regulatory | experiential | telemetric
    authority_scope: string (who can assert this)
    access_policy: string (visibility rules)

  Bitemporal properties on relationships:
    asserted_at, retracted_at, valid_from, valid_to, superseded_by

  New node types:
    (SurveyClaim) — structured claim from survey bot
    (EpistemicFrame) — partitioned knowledge context
    (ConflictObject) — detected cross-source inconsistency
    (SeedTerm) — domain vocabulary term

WGI additions (new):
  (Case)-[:HAS_EVENT]->(CanonicalActivityEvent)     [Phase 3]
  (CanonicalActivityEvent)-[:MAPS_TO]->(Activity)    [Phase 3]
  (Activity)-[:PRECEDES]->(Activity) {variant_id, frequency}
  (Activity)-[:PERFORMED_BY]->(Role) {confidence}
  (Activity)-[:OCCURS_IN]->(System) {confidence}
  (SurveyClaim)-[:SUPPORTS / :CONTRADICTS]->(Segment)
  (UncertaintyItem)-[:AFFECTS]->(Segment)
  (ValidationDecision)-[:CONFIRMS / :CORRECTS]->(Segment) [Phase 3]
```

### 5.3 Updated Confidence Model (3D)

Merge KMFlow's numeric scoring with WGI's Bright/Dim/Dark overlay and KM4ProcessBot's evidence grading:

```
Dimension 1 — Confidence Score (0-1):
  KMFlow's existing 5-factor weighted formula:
  confidence = (evidence_coverage * 0.30 +
                evidence_agreement * 0.25 +
                evidence_quality * 0.20 +
                source_reliability * 0.15 +
                evidence_recency * 0.10)

Dimension 2 — Brightness Classification:
  Bright (>= 0.75): Evidence from 3+ sources, validated
  Dim (0.40-0.74): 1-2 sources or unvalidated
  Dark (< 0.40): Missing, contradictory, or under-observed

Dimension 3 — Evidence Grading Ladder:
  Grade A: Validated by SME + corroborated by 2+ planes
  Grade B: Corroborated by 2+ planes, not yet validated
  Grade C: Single-plane evidence, reasonable confidence
  Grade D: Single-source, unvalidated claim
  Grade U: No evidence (dark room)

MVC (Minimum Viable Confidence):
  The threshold below which a process element MUST be flagged
  for additional evidence acquisition before publication.
  Default: 0.40 (boundary between Dim and Dark)
```

### 5.4 Updated Output Suite

```
Existing KMFlow outputs (preserve):
  - BPMN 2.0 with evidence citations
  - Confidence heatmaps
  - Evidence mapping overlays
  - Gap analysis dashboards
  - Regulatory-policy-control overlay
  - Executive PDF/HTML reports

New outputs from WGI + KM4ProcessBot (add):
  - Derived RACI (Proposed vs Validated) — from role/activity graph
  - Cross-frame comparison views — epistemic frame lens selector
  - Disagreement report — all ConflictObjects with resolution status
  - Evidence grading progression dashboard — Grade U→D→C→B→A over time
  - Seed list coverage report — % of seed terms with evidence
  - Dark Room backlog — prioritized list of Dark segments
  - Process narratives with embedded validation prompts
  - Replay: single-case timeline, aggregate volume, variant comparison [Phase 3]
  - Variant report (volume share, cycle time, rework, uncertainty) [Phase 3]
  - Uncertainty backlog (operational Dark Room) [Phase 3]
```

### 5.5 Disagreement Taxonomy

Eight mismatch types detected by cross-source consistency checks:

| # | Mismatch Type | Description |
|---|---------------|-------------|
| 1 | `SEQUENCE_MISMATCH` | Contradictory activity orderings |
| 2 | `ROLE_MISMATCH` | Different role assignments for same activity |
| 3 | `RULE_MISMATCH` | Contradictory business rules |
| 4 | `EXISTENCE_MISMATCH` | Disputed activity existence |
| 5 | `IO_MISMATCH` | Input/output schema disagreement |
| 6 | `CONTROL_GAP` | Missing governance where policy requires it |
| 7 | `TEMPORAL_MISMATCH` | Same assertion, different effective periods |
| 8 | `AUTHORITY_MISMATCH` | Conflicting assertions from different authority scopes |

Three-way distinction for each: Genuine Disagreement | Naming Variant | Temporal Shift.

---

## 6. Updated Phased Delivery

### Phase 1 — Foundation (MVP)

**EXISTING** (preserve):
- Engagement management (create, scope, team)
- Evidence ingestion pipeline (documents, structured data, BPM models)
- Shelf data request workflow (compose, track, intake)
- Evidence quality scoring and validation
- Basic semantic relationship engine (Neo4j graph construction)
- Process POV generation with consensus algorithm and evidence linking
- Confidence scoring engine
- Simple HTML process flow visualization
- Evidence provenance tracking
- Engagement Lead and Process Analyst dashboards
- Security: engagement-level isolation, auth, audit logging

**NEW — FORMALIZE** (schema + data model, no new UI):
- 3D confidence model schema (numeric score + brightness + evidence grade)
- Controlled edge vocabulary (12 typed edges) in Neo4j schema
- `SurveyClaim` entity schema with certainty tiers
- `EpistemicFrame` entity schema with frame_kind, authority_scope, access_policy
- Disagreement taxonomy (8 mismatch types + ConflictObject entity)
- Seed list entity schema (`SeedTerm` with domain, source, status)

### Phase 2 — Intelligence

**EXISTING** (preserve):
- Full evidence taxonomy support (all 12 categories including audio/video)
- Advanced semantic bridges across all domain pairs
- Regulatory-policy-control overlay engine
- TOM alignment and automated gap analysis
- Best practices library and benchmarking
- Celonis and Soroco Scout integration
- Conformance checking against reference models
- SME and Client Stakeholder portals
- Executive report generation
- Gap-prioritized transformation roadmap generator

**NEW** (from gap analysis):
- Seed list pipeline (domain vocabulary → NLP refinement → probe generation → extraction targeting)
- Survey bot with domain-seeded probes (8 probe types, claim objects, certainty tiers)
- Process narratives with embedded validation prompts (Claude API)
- Derived RACI generation (Proposed vs Validated)
- Evidence grading ladder (Grade U through Grade A progression)
- Cross-source consistency checks (6 automated detection rules)
- SaaS connector framework (ServiceNow, SAP, Salesforce) — accelerated from Phase 3
- Schema Intelligence Library (top 3 platforms)

### Phase 3 — Scale and Insight

**EXISTING** (preserve):
- Monitoring agent integration (log analysis, task mining)
- Continuous evidence collection
- Real-time process deviation detection
- Agentic capabilities (proactive evidence gap identification)
- Cross-engagement pattern library (with strict data isolation)
- Process simulation and what-if analysis
- Client portal with interactive exploration
- API/MCP server for consulting platform integration
- Evidence coverage classification (Bright / Dim / Dark per process element)
- Scenario Comparison Workbench
- Epistemic Action Planner

**NEW** (from gap analysis):
- Event spine builder (canonicalization + mapping rules + CanonicalActivityEvent)
- Replay visualization (single-case timeline, aggregate volume, variant comparison)
- Validation Hub (segment-level review packs, structured feedback, republish cycle)
- Active inferencing engine (gap identification → targeted probes/extraction)
- Telemetry-triggered micro-surveys
- Dark Room operations (uncertainty backlog, illumination planner, shrink-rate tracking)
- Desktop task mining integration (deep Soroco/KM4Work)
- Schema Intelligence Library expansion

### Phase 4 — Reimagination

**EXISTING** (preserve):
- Financial data model (cost per role, volume forecasts, technology cost assumptions)
- Financial impact estimation with ranges, assumptions, sensitivity analysis
- Assisted Alternative Suggestion (LLM-suggested modifications)
- BPMN diff visualization
- Scenario ranking with composite scoring
- Engagement-level scenario history and audit trail
- Reimagination dashboard

**NEW** (from gap analysis):
- Assessment Overlay Matrix (Value x Ability-to-Execute)
- Policy Decision Point (OPA-style PDP for RBAC/ABAC decisions)
- Export watermarking + redaction controls
- BPM-orchestrated engagement lifecycle (activate existing BPMN models)
- Ontology derivation (from seed list + knowledge graph → domain ontology)
- Deployment flexibility (hybrid/on-prem patterns)

---

## 7. Top 7 Highest-Impact Recommendations (Priority Order)

1. **Formalize 3D confidence model as platform-wide standard** — KMFlow already has the confidence scoring model in PRD Section 6.3. Add brightness classification and evidence grading ladder. Make it pervasive: every graph node, every BPMN element, every API response carries all three dimensions. Low effort, high conceptual alignment.

2. **Formalize controlled edge vocabulary + epistemic frames** — These are schema-level changes that make the knowledge graph significantly more expressive. Define in Phase 1 so all Phase 2+ development builds on the right foundation. The 12 typed edges and epistemic frame properties cost nothing at the schema level but enable plural truth preservation.

3. **Add seed list pipeline + survey bot (Phase 2)** — KM4ProcessBot already defines the conceptual framework. Build the seed list pipeline (domain vocabulary → NLP refinement → probe generation) and a basic survey bot that produces `SurveyClaim` objects with certainty tiers. This fills the gap between passive evidence ingestion and active knowledge elicitation.

4. **Add canonical event spine + connector framework (Phase 2-3)** — This unlocks replay, variant analysis, cycle time analytics, and case-centric views. Start with the schema + 1 connector (ServiceNow) in Phase 2, expand in Phase 3.

5. **Add process narratives with validation prompts (Phase 2)** — Use Claude API to generate human-readable process stories from the knowledge graph. Embed validation questions at Dim/Dark segments. This is WGI's most practical validation mechanism and aligns with KMFlow's existing LLM stack.

6. **Add replay visualization (Phase 3)** — Single-case timeline first (achievable with existing graph data), then aggregate volume replay (requires event spine). This is the trust accelerator that makes stakeholders believe the model.

7. **Add validation hub with republish cycle (Phase 3)** — Structured segment-level review packs, confirm/correct/reject/defer actions, version diffs, dark-room shrink rate tracking. This closes the loop between POV generation and SME validation.

---

## 8. What NOT to Adopt from WGI

- **Native desktop agent build**: Too much investment for the current phase. Integrate with existing task mining tools instead. The macOS agent can be extended later if needed.
- **On-prem deployment mode**: Defer until there's a concrete client requirement. Cloud-first with hybrid as Phase 3+.
- **Full OPA policy engine**: Overkill for current maturity. Lightweight PDP pattern is sufficient for Phase 3.
- **WGI's dismissal of document evidence**: WGI focuses on live capture and downplays pre-existing documents. KMFlow's evidence taxonomy is a strength — keep it.
- **WGI's "replace process mining" positioning**: KMFlow's integration with Celonis/Signavio is pragmatic and valuable. Keep the integration strategy.
- **WGI's generic extraction patterns**: KM4ProcessBot's seed-list-driven approach is superior — domain-specific extraction without domain-specific model training. Use seed list, not generic.

---

## 9. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Schema formalization delays Phase 1 | Medium | High | Limit Phase 1 FORMALIZE to schema definitions only — no UI, no new APIs |
| Survey bot scope creep | High | Medium | Phase 2 MVP = structured claim objects + basic probes; full multi-turn bot in Phase 3 |
| Event spine complexity | Medium | High | Start with 1 connector (ServiceNow); mapping rule engine before full framework |
| Replay requires too much data | Medium | Medium | Single-case timeline works with existing graph data; aggregate replay deferred until event spine mature |
| Validation hub adoption by SMEs | Medium | High | Process narratives as the primary validation vehicle (lower friction than structured review packs) |
| Seed list quality | Low | Medium | NLP refinement step + manual curation by consultant; iterate per engagement |

---

## 10. Naming and Positioning

WGI uses compelling names that could be adopted or adapted:

| WGI Term | KMFlow Equivalent | Recommendation |
|----------|-------------------|----------------|
| Work Reality Graph | Knowledge Graph / Semantic Graph | Keep KMFlow's term; it's broader |
| Process Evidence Pack | Client Deliverable Package | Consider adopting; it's more specific |
| Bright / Dim / Dark | Evidence Coverage Classification | Adopt the metaphor; already partially present in PRD |
| Dark Room | Uncertainty Backlog | Adopt; it's vivid and actionable |
| Truth Velocity | Confidence Progression Rate | Consider adopting for engagement dashboards |
| Process Assessment Bot | Survey Bot | Keep "Survey Bot"; less anthropomorphic |
| Illumination Planner | Epistemic Action Planner | Keep KMFlow's term; more precise |

---

## Appendix: Scorecard Summary

| # | Dimension | KMFlow v1 | WGI | KM4ProcessBot | KMFlow v2 (Target) |
|---|-----------|-----------|-----|---------------|-------------------|
| 1 | Evidence taxonomy | 12 categories | 3 planes | 9 knowledge forms | 12 categories + 4 planes + 9 forms |
| 2 | Active capture | None | Desktop agent + connectors | Survey bot | Survey bot (Phase 2) + connectors (Phase 2-3) |
| 3 | Knowledge graph | Semantic bridges | Case-event-activity | Controlled edges + epistemic frames | Merged schema |
| 4 | Confidence model | 5-factor numeric | Bright/Dim/Dark | Evidence grading ladder | 3D model (numeric + brightness + grading) |
| 5 | Consensus algorithm | Weighted voting | Multi-plane reconciliation | Cross-source consistency checks | Extended algorithm with 6 consistency rules |
| 6 | Governance overlay | Full (Process→Policy→Control→Regulation) | Minimal | None | Full (preserved) |
| 7 | Validation | SME annotation | Validation Hub + republish | Claim confirmation | Validation Hub (Phase 3) |
| 8 | Replay | None | 3 replay modes | None | 3 replay modes (Phase 3) |
| 9 | Domain specialization | None | Schema Intelligence Library | Seed list pipeline | Seed list + Schema Intelligence Library |
| 10 | RACI | None | Derived RACI | Role-activity mapping | Derived RACI (Phase 2) |
| 11 | Narratives | PDF/HTML reports | Validation narratives | None | Validation narratives (Phase 2) |
| 12 | Deployment | Cloud only | Cloud/Hybrid/On-Prem | N/A | Cloud + Hybrid (Phase 3+) |
| 13 | Process mining integration | Celonis, XES, ARIS, Visio | None (replace strategy) | None | Preserved (pragmatic) |
| 14 | Engagement lifecycle | Status tracking | BPM-orchestrated 6-phase | None | BPM-orchestrated (Phase 4) |

---

## Verification

- [x] All 7 source documents referenced and analyzed
- [x] 9 true gaps identified (3 reclassified from v1 as FORMALIZE items)
- [x] 13 KMFlow differentiators documented (7 new from KM4ProcessBot)
- [x] Unified capability model synthesizes all three sources
- [x] Phased delivery updated with EXISTING + NEW items per phase
- [x] Cross-source consistency checks formalized (6 rules + 3-way distinction)
- [x] 3D confidence model defined (numeric + brightness + evidence grading)
- [x] Risk assessment included
- [x] Naming and positioning guidance provided
- [x] 14-dimension scorecard comparison included
