# KMFlow Platform - Product Requirements Document

**Version**: 3.0.0
**Status**: Implemented Platform
**Last Updated**: 2026-03-09
**Author**: David Johnson, Paul Roth
**Classification**: Internal - Confidential
**Revision Note v3.0**: Reflects implemented platform state as of v2026.03.211. All Phase 1-3 capabilities are built and operational. Phase 4 substantially complete. Adds Desktop Agent Platform (Section 6.13), Process Orchestration (Section 6.14), Analytics Data Layer (Section 6.15) sections. Updates data model to 96+ models, 67 routers, 508+ endpoints, 83 migrations. Platform scale: ~113K LOC, 6,035+ tests, 19 evidence parsers, 12+ integration connectors.
**Revision Note v2.1**: Incorporates 10-perspective expert review findings. Key changes: restructured confidence model, added process structure discovery step, security architecture section, async task architecture, GDPR/consent requirements moved to Phase 1, cross-store consistency model, acceptance criteria. See `docs/prd/PRD_v2_Expert_Review_Synthesis.md` for full review synthesis.
**Revision Note v2.0**: Incorporates KM4ProcessBot v1, WorkGraphIQ gap analysis, David Johnson architectural vision. See `docs/analysis/KMFlow-vs-WGI-Gap-Analysis.md` for full gap analysis.

---

## 1. Executive Summary

KMFlow is an AI-powered Process Intelligence platform designed for consulting engagements. It occupies genuine white space at the intersection of Process Mining (Celonis, Signavio), AI-powered consulting tools (McKinsey Lilli, KPMG Workbench), and qualitative evidence analysis.

**Core Innovation**: KMFlow is evidence-first, not event-log-first. It starts with the diverse evidence consultants actually collect (documents, interviews, system exports, policies) rather than requiring structured event log extracts that take months to configure.

**What KMFlow Does**:
- Ingests diverse client evidence per business area (not cross-enterprise)
- Builds semantic relationships across all evidence items using a controlled edge vocabulary
- Synthesizes a Consensus first-pass process point of view — the baseline consensus view from all available evidence, including elements mentioned by any source weighted by evidence type and confidence
- Scores every process element with a three-dimensional confidence model (numeric score + brightness classification + evidence grade)
- Captures structured process knowledge via survey bot with domain-seeded probes
- Aligns against Target Operating Models, best practices, and industry benchmarks
- Generates prioritized gap analysis with evidence-backed recommendations
- Models regulations, policies, and controls as connective tissue between process elements
- Detects and classifies cross-source disagreements with a formal disagreement taxonomy

**Strategic Positioning**: No existing product combines evidence ingestion from consulting engagements, structured process knowledge capture via domain-seeded survey bot, semantic relationship building across qualitative and quantitative data, confidence-scored process model generation with brightness classification, and automated TOM gap analysis. KMFlow's seed list pipeline provides domain specialization without domain-specific model training. Its universal process knowledge forms ensure completeness of capture. Its active inferencing capability means the system knows what it doesn't know and can target evidence acquisition accordingly.

**Platform Scale** (as of v2026.03.211):

| Metric | Value |
|--------|-------|
| Total Lines of Code | ~113,000 |
| Backend + Frontend Tests | 6,035+ |
| SQLAlchemy Models | 96 |
| API Route Files / Endpoints | 67 / 508+ |
| Evidence Parsers | 19 |
| Integration Connectors | 12+ |
| Alembic Migrations | 83 |
| BPMN Orchestration Workflows | 8 |
| Desktop Agent Platforms | 3 (macOS Swift, Windows C#, shared Python) |
| Test Coverage | >80% |

**Target Market**: Consulting firms serving regulated enterprises in Financial Services, Healthcare, and Energy.

**Time-to-Insight**: Days, not months.

---

## 2. Problem Statement

Organizations have fragmented process knowledge spread across BPM tools (ARIS, Visio, Camunda), regulations, policies, communications, and ad-hoc documentation. There is no consistent way to create a unified, evidence-based view of organizational processes.

**Key Problems**:

1. **Manual process discovery is slow and subjective**: Traditional process discovery takes weeks of workshops, interviews, and document reviews. Results vary by analyst and lack objective evidence backing.

2. **Gap analysis between current state and TOMs is manual**: Consultants manually compare observed processes against target operating models, a process that is time-consuming, inconsistent, and difficult to defend with evidence.

3. **Process mining tools require structured event logs**: Celonis, Signavio, and similar tools require structured event log extracts from IT systems. These take months to configure and miss processes that lack system event trails.

4. **No tool supports qualitative evidence alongside quantitative data**: Existing tools cannot ingest interview transcripts, workshop outputs, observation notes, policy documents, and system data into a unified analysis.

5. **37% of organizations report manual routing and process gaps** that log-based tools miss entirely. These gaps exist in the informal, human-driven parts of processes.

6. **Regulations, policies, and controls are disconnected from process models**: The governance tissue that connects processes, policies, and regulations is not modeled, making compliance analysis ad-hoc.

7. **Tacit process knowledge is lost**: Subject matter experts hold critical knowledge about exceptions, workarounds, and decision logic that is never formally captured. No tool provides structured elicitation of this knowledge with certainty tracking.

8. **Cross-source contradictions go undetected**: When multiple evidence sources describe the same process differently, traditional tools cannot detect, classify, or resolve the disagreement systematically.

---

## 3. Product Vision

KMFlow transforms consulting delivery by enabling data-driven process conversations from day one of client engagement.

**Vision Statement**: Ingest a focused body of evidence related to a specific business area. Actively elicit structured process knowledge through domain-seeded probes. Create consistent semantic relationships between all evidence items using a controlled edge vocabulary. Produce a Consensus first-pass point of view across the evidence corpus — the baseline consensus including all evidence-supported elements, weighted by source type and confidence. Score every process element with confidence based on evidence coverage, quality, and agreement. Preserve plural truths through epistemic frames when sources legitimately disagree. Align against TOMs, best practices, and industry benchmarks. Generate prioritized gap analysis with evidence-backed recommendations. Know what you don't know — and target evidence acquisition to fill the gaps.

**Guiding Principles**:
- Evidence-first: every assertion is traceable to source evidence
- Focused scope: one business area at a time, not cross-enterprise
- Confidence transparency: no black-box outputs; every score is explainable
- Consulting-native: designed for how consultants actually work
- Regulations, policies, and controls as connective tissue between items
- Domain lens via seed list: all capture and extraction focused through domain-specific vocabulary
- Plural truth preservation via epistemic frames: the system can hold conflicting assertions from different authority scopes without forcing premature resolution
- Active inferencing: the system knows what it doesn't know and can generate targeted probes and extraction tasks to fill evidence gaps

---

## 4. Market Context

**Market Size**: The process mining market was valued at $3.66B in 2025 and is projected to reach $42.69B by 2032 at a 42% CAGR.

**Competitive Landscape**:

| Player | Approach | Gap |
|--------|----------|-----|
| **Celonis** | Process Intelligence Graph from event logs | Requires structured event logs; months to deploy; no qualitative evidence |
| **Signavio** | Process modeling + mining | Similar event log dependency; limited evidence ingestion |
| **Soroco Scout** | Work Graph from desktop activity | Desktop-only; no document evidence; no consulting workflow |
| **McKinsey Lilli** | General-purpose AI assistant | Not process-specific; no evidence graph; no confidence scoring |
| **KPMG Workbench** | AI-assisted consulting | General-purpose; no semantic process graphs |
| **Deloitte Zora** | AI-assisted analysis | General-purpose; not process intelligence |
| **NVivo** | Qualitative data analysis | Academic focus; no process model generation; no TOM alignment |
| **ABBYY Timeline** | Process mining from document-centric evidence | Overlapping positioning but no consulting workflow; no TOM alignment; no knowledge capture |
| **UiPath Process Mining** | Task mining + process mining integration | Strong on structured data; weak on qualitative evidence; no confidence model |
| **Microsoft Process Advisor** | Integrated with Power Platform | Massive distribution advantage; limited evidence diversity; no epistemic frames |
| **IBM Process Mining** | Strong in regulated industries | Event-log-first; no qualitative evidence; limited consulting workflow |

**KMFlow's Unique Position**: Consulting-first process intelligence. The only platform that combines evidence ingestion from consulting engagements, structured process knowledge capture with domain-seeded probes, semantic relationship building, confidence-scored process models with brightness classification, and automated TOM gap analysis.

**Competitive Strategy**: KMFlow complements rather than replaces event-log-first tools. Its value is strongest in the pre-event-log phase (qualitative evidence, process discovery from diverse sources) and the post-event-log phase (TOM alignment, gap analysis, scenario planning). The Celonis connector (Section 6.6) bridges these complementary capabilities.

---

## 5. Evidence Taxonomy

KMFlow processes 12 categories of evidence, reflecting the diverse inputs consultants encounter.

| # | Category | Formats | Processing Approach |
|---|----------|---------|-------------------|
| 1 | **Documents** | PDF, Word, PowerPoint, HTML | Visual object parsing with layout preservation |
| 2 | **Images** | PNG, JPEG, TIFF, BMP | OCR with bounding box coordinates |
| 3 | **Audio** | MP3, WAV, M4A, FLAC | Spectrogram chunking + ASR transcription (Whisper) |
| 4 | **Video** | MP4, MOV, AVI, WebM | Frame extraction + audio track separation + scene segmentation |
| 5 | **Structured Data** | Excel, CSV, JSON, SQL exports | Schema discovery with relationship detection; normalized into One-Column JSON |
| 6 | **SaaS Exports** | Salesforce, SAP, ServiceNow | Native connector with semantic alignment |
| 7 | **KM4Work** | BPMN 2.0 XML, EPC, DMN, desktop captures | Native desktop agents (macOS Swift + Windows C#), VCE pipeline (video capture, OCR, ML classification), switching sequence analysis, task correlation engine |
| 8 | **BPM Process Models** | BPMN 2.0 XML, EPC, ARIS, Flowable/Camunda | Extraction pipeline for activities, sequences, gateways, swim lanes, decision points |
| 9 | **Regulatory and Policy** | Regulatory filings, policy docs, compliance frameworks, SOP libraries, SEC/FINRA/OCC filings | Clause-level extraction with requirement linkage and obligation mapping; financial regulatory parser for SEC/FINRA/OCC documents |
| 10 | **Controls and Evidence** | Control matrices, evidence logs, monitoring outputs, audit trails | Control-to-process linkage with compliance state tracking |
| 11 | **Domain Communications** | Email archives, chat transcripts, tickets, incident reports | Pattern extraction: actual process execution vs. documented procedures |
| 12 | **Job Aids and Edge Cases** | Decision trees, quick reference cards, exception guides, workarounds | Rule extraction for ambiguous edge cases and undocumented decision logic |

### 5.1 Evidence Planes

The 12 evidence categories are organized into four **evidence planes** — an organizing layer that groups evidence by how it is captured and what it reveals:

| Plane | Name | KMFlow Categories | Capture Mode | What It Reveals |
|-------|------|-------------------|--------------|-----------------|
| 1 | **Document Evidence** | 1-6, 8-12 | Passive (consultant uploads) | Documented intent, stated procedures, organizational definition |
| 2 | **System Telemetry** | 6 (SaaS Exports) + connector framework | Active (system extraction) | System-recorded reality, case timelines, transaction flows |
| 3 | **Work-Surface Reality** | 7 (KM4Work) | Active (endpoint capture) | In-between work, navigation patterns, workarounds invisible to systems |
| 4 | **Human Interpretation** | Survey claims (new) | Active (structured elicitation) | Tacit knowledge, exception logic, uncertainty, expert judgment |

The four planes ensure comprehensive evidence coverage. No single plane is sufficient — process intelligence requires triangulation across all four. The seed list (Section 6.10.3) acts as a cross-cutting domain lens that focuses capture and extraction across all planes.

### 5.2 Parser Inventory (19 Implemented)

All parsers reside in `src/evidence/parsers/` with a factory pattern (`factory.py`) for format detection and routing.

| Parser | Evidence Categories | Formats |
|--------|-------------------|---------|
| `document_parser` | 1 (Documents) | PDF, DOCX, XLS/XLSX via pdfplumber, python-docx, openpyxl |
| `image_parser` | 2 (Images) | PNG, JPEG, TIFF, BMP — OCR with bounding boxes |
| `audio_parser` | 3 (Audio) | MP3, WAV, M4A — spectrogram + ASR transcription |
| `video_parser` | 4 (Video) | MP4, MOV, MKV — frame extraction + audio separation |
| `structured_data_parser` | 5 (Structured Data) | CSV, JSON, SQL dumps |
| `saas_parser` | 6 (SaaS Exports) | Salesforce, ServiceNow, SAP exports |
| `km4work_parser` | 7 (KM4Work) | Desktop task mining artifacts |
| `bpmn_parser` | 8 (BPM Models) | BPMN 2.0 XML — activity/gateway/lane extraction |
| `aris_parser` | 8 (BPM Models) | ARIS AML/XML process models |
| `visio_parser` | 8 (BPM Models) | Visio VSDX files |
| `xes_parser` | 8 (BPM Models) | XES event log format |
| `regulatory_parser` | 9 (Regulatory) | Policy docs, compliance frameworks |
| `financial_regulatory_parser` | 9 (Regulatory) | SEC/FINRA/OCC filings |
| `controls_parser` | 10 (Controls) | Control matrices (CSV/XLS) |
| `communication_parser` | 11 (Communications) | Slack, email, Teams exports |
| `job_aids_parser` | 12 (Job Aids) | Decision trees, SOPs, exception guides |

---

## 6. Core Platform Capabilities

### 6.1 Evidence Ingestion Engine

Multi-format document processing pipeline with format-specific parsers for all 12 evidence categories.

**Key Features**:
- Shelf data request management with item-level tracking:
  - Compose requests with individual line items per evidence need
  - Deliver to clients (email/portal)
  - Track at item level: `SENT` → `ACKNOWLEDGED` → `PARTIAL_RESPONSE` → `RECEIVED` → `VALIDATED` (also: `WRONG_FORMAT_RECEIVED`, `ESCALATED`, `CLIENT_PUSH_BACK`, `SUBSTITUTION_OFFERED`, `CLOSED_INCOMPLETE`)
  - Follow-up automation: configurable escalation intervals with templated language
  - Evidence substitution: when client cannot provide requested item, analyst marks acceptable substitute and system adjusts confidence accordingly
  - Realistic fulfillment milestones: >40% within 2 weeks, >60% within 4 weeks, >80% stretch goal
- Evidence cataloging with automated metadata extraction
- Evidence quality scoring across four dimensions:
  - **Completeness** (0.0-1.0): How much of the requested evidence is present
  - **Reliability** (0.0-1.0): Source credibility and document integrity
  - **Freshness** (0.0-1.0): How current the evidence is
  - **Consistency** (0.0-1.0): Agreement with other evidence items
- Evidence validation workflow: automated classification → human review → approval/rejection
- Duplicate detection and conflicting evidence flagging
- Evidence lifecycle: `PENDING` → `VALIDATED` → `ACTIVE` → `EXPIRED` → `ARCHIVED`
- Content hashing (SHA-256) for integrity verification and content-addressable deduplication
- Complete audit trail for evidence provenance
- MinIO object storage backend for evidence file persistence
- Evidence lifecycle management with full state machine (10+ states including `PENDING`, `VALIDATED`, `ACTIVE`, `EXPIRED`, `ARCHIVED`, `WRONG_FORMAT_RECEIVED`, `ESCALATED`, `CLIENT_PUSH_BACK`, `SUBSTITUTION_OFFERED`, `CLOSED_INCOMPLETE`)

### 6.2 Semantic Relationship Engine

Knowledge graph construction using Neo4j with typed nodes and relationships. Uses a **controlled edge vocabulary** for schema discipline. The authoritative vocabulary is defined in `src/semantic/ontology/kmflow_ontology.yaml` — the PRD table below describes the target vocabulary; the ontology YAML must be reconciled to match.

**Semantic Bridges**:
- `ProcessEvidenceBridge`: Process ↔ Evidence (confidence-weighted)
- `EvidencePolicyBridge`: Evidence ↔ Policy/Regulation/Control
- `ProcessTOMBridge`: Process ↔ Target Operating Model (gap-scored)
- `CommunicationDeviationBridge`: Communications ↔ Documented procedures (deviation detection)

**Controlled Edge Vocabulary** (12 types):

| Edge Type | Semantics | Constraint |
|-----------|-----------|------------|
| `PRECEDES` | Activity A happens before Activity B | Acyclic within variant |
| `TRIGGERS` | Event E causes Activity A to start | Source must be event/gateway |
| `DEPENDS_ON` | Activity A requires Activity B to complete first | Acyclic |
| `CONSUMES` | Activity A uses Input I | Target must be data object |
| `PRODUCES` | Activity A generates Output O | Target must be data object |
| `GOVERNED_BY` | Element X is governed by Policy P | Target must be Policy node |
| `PERFORMED_BY` | Activity A is performed by Role R | Target must be Role node |
| `EVIDENCED_BY` | Assertion X is supported by Evidence E | Target must be Evidence node |
| `CONTRADICTS` | Assertion X conflicts with Assertion Y | Bidirectional |
| `SUPERSEDES` | Assertion X replaces Assertion Y | Requires bitemporal validity |
| `DECOMPOSES_INTO` | Process P breaks down into Subprocess S | Hierarchical |
| `VARIANT_OF` | Activity A is an alternative to Activity B | Bidirectional |

**Epistemic Frame Properties** on assertions:

| Property | Type | Description |
|----------|------|-------------|
| `frame_kind` | Enum | `procedural` \| `regulatory` \| `experiential` \| `telemetric` \| `elicited` \| `behavioral` |
| `authority_scope` | ControlledVocab | Who can assert this — controlled vocabulary tied to engagement roles, not freeform string (e.g., `operations_team`, `compliance_officer`, `system_telemetry`) |
| `access_policy` | String | Visibility rules for this assertion |

**Bitemporal Validity** on relationships:

| Property | Type | Description |
|----------|------|-------------|
| `asserted_at` | DateTime | When the assertion was made |
| `retracted_at` | DateTime | When the assertion was withdrawn (null if active) |
| `valid_from` | DateTime | When the asserted fact becomes true |
| `valid_to` | DateTime | When the asserted fact ceases to be true (null if ongoing) |
| `superseded_by` | UUID | Reference to the superseding assertion |

**Knowledge Graph Assumption Model**:
- **Open World Assumption (default)**: A missing edge means "no evidence yet," not "doesn't exist." Consistent with the brightness model — Dark segments are under-observed, not absent. Applied to all general graph traversals and confidence scoring.
- **Closed World Assumption (governance queries only)**: When running Control Gap detection (consistency check #6, Section 6.10.5) against a specific regulatory framework, a missing `GOVERNED_BY` edge is treated as a gap finding. CWA is scoped to the specific compliance domain under analysis.

**Capabilities**:
- Entity resolution across heterogeneous evidence sources
- Relationship confidence scoring with impact propagation
- Embedding-based semantic similarity (all-mpnet-base-v2 or domain-tuned model)
- Hybrid retrieval: direct ID lookup + top-k semantic search (RAG)

### 6.3 Process Point of View Generator (Consensus Algorithm)

The intellectual core of the platform. Synthesizes a consensus first-pass process view from diverse evidence.

**Algorithm Steps**:

1. **Evidence Aggregation**: Collect all evidence related to a scoped business area
2. **Entity Extraction**: Identify process elements (activities, decisions, roles, systems) from each evidence source, guided by seed list terms
3. **Cross-Source Triangulation**: Validate process elements by corroboration across multiple evidence types
4. **Cross-Source Consistency Checks**: Apply 6 automated detection rules:
   - Sequence conflict detection (contradictory orderings)
   - Role conflict detection (different performer assignments)
   - Rule conflict detection (contradictory business rules)
   - Existence conflict detection (disputed activity existence)
   - I/O mismatch detection (upstream output ≠ downstream input)
   - Control gap detection (missing governance where policy requires it)
5. **Three-Way Distinction**: For each detected inconsistency, classify as:
   - Genuine Disagreement → preserve both views with epistemic frames, mark for validation
   - Naming Variant → resolve via seed list / entity resolution
   - Temporal Shift → resolve via bitemporal validity model
6. **Process Structure Discovery**: Reconstruct process control flow from evidence:
   - Build a directly-follows graph (DFG) from `PRECEDES` edges extracted in Step 2, weighted by frequency and source confidence
   - Apply dependency threshold: prune edges below configurable frequency/confidence threshold (default: 0.1)
   - Detect parallelism: if A and B both follow C, and A and B never directly follow each other, infer parallel split (AND-gateway)
   - Detect choice: if A and B both follow C, and A and B never co-occur in the same trace/evidence, infer exclusive split (XOR-gateway)
   - Detect loops: if backward edges exist (B→A where A already precedes B), preserve as loop structure
   - When event logs (XES/SaaS) are available, use directly-follows from consecutive events as high-confidence input
   - When evidence is qualitative only (documents, interviews), mark structural inferences as Dim and flag for validation
   - Score each structural inference with brightness classification
   - Output: structured process graph with gateway types, suitable for BPMN assembly
7. **Consensus Building**: Apply weighted voting across evidence sources:
   - System data (highest weight: objective)
   - Process documentation (high weight: intentional)
   - Communications/tickets (medium weight: behavioral)
   - Interviews/workshops (medium weight: subjective but expert)
   - Survey claims (medium weight: structured but unvalidated)
   - Job aids/workarounds (lower weight: may reflect exceptions)
8. **Contradiction Resolution**: When evidence conflicts:
   - Flag contradictions with severity scoring and disagreement type
   - Create `ConflictObject` for each detected mismatch
   - Present alternative views with supporting evidence for each
   - Apply recency bias (newer evidence weighted higher for conflicts)
   - Default to "documented + observed" over "documented only"
9. **Model Assembly**: Generate BPMN 2.0 process model from the structured process graph (Step 6) with:
   - Every element traced to source evidence
   - Three-dimensional confidence score per element
   - Variant annotations where evidence supports multiple paths
   - Gap markers where evidence is insufficient (Dark segments)

**Confidence Model** (per process element):

The confidence model has two independent dimensions plus a derived visualization classification:

```
Dimension 1 — Confidence Score (0-1):

  Evidence Strength (structural coverage):
    evidence_coverage  = supporting_planes / available_planes   # normalized against evidence planes available in engagement
    evidence_agreement = agreeing_sources / total_mentioning_sources  # actual inter-source agreement ratio

  Evidence Quality (source trustworthiness):
    evidence_quality   = mean quality score of supporting evidence items
    source_reliability = weighted mean by source type (system data: 0.9, formal docs: 0.8, communications: 0.5, job aids: 0.3)
    evidence_recency   = freshness decay function (configurable half-life per evidence category)

  Composite Score:
    strength = evidence_coverage * 0.55 + evidence_agreement * 0.45
    quality  = evidence_quality * 0.40 + source_reliability * 0.35 + evidence_recency * 0.25
    confidence = min(strength, quality)  # prevents high scores when either dimension is weak

Dimension 2 — Evidence Grade (independent provenance assessment):
  Grade A: Validated by SME + corroborated by 2+ planes
  Grade B: Corroborated by 2+ planes, not yet validated
  Grade C: Single-plane evidence, reasonable confidence
  Grade D: Single-source, unvalidated claim
  Grade U: No evidence (dark room)

Derived — Brightness Classification (visualization convenience):
  Determined by: min(score_brightness, grade_brightness)
  Score-based:  Bright (>= 0.75), Dim (0.40-0.74), Dark (< 0.40)
  Grade-based:  Bright (A-B), Dim (C), Dark (D-U)
  Coherence constraint: Grade D or U caps brightness at Dim regardless of numeric score
```

**Confidence Propagation Rules**:
- When an evidence item's quality score changes (e.g., freshness decay), recompute confidence for all elements within 2 hops via `EVIDENCED_BY` edges
- Freshness decay: exponential with configurable half-life per evidence category (regulatory: 365 days, process docs: 180 days, communications: 30 days)
- If Activity A `DEPENDS_ON` Activity B and B is Dark, A's brightness is capped at Dim (structural dependency constraint)

**Minimum Viable Confidence (MVC)**: The threshold below which a process element MUST be flagged for additional evidence acquisition before publication. Default: 0.40 (boundary between Dim and Dark).

### 6.4 Regulatory-Policy-Control Overlay

The connective tissue between different items. Regulations, policies, and controls are modeled as edges (not just nodes) in the knowledge graph.

**Relationship Chain**:
```
Process --governed_by--> Policy --enforced_by--> Control --satisfies--> Regulation
```

**Capabilities**:
- Overlay visualization on process models showing governance coverage
- Compliance state tracking per process element
- Gap detection for ungoverned processes
- Effectiveness scoring per control:
  - `HIGHLY_EFFECTIVE` (>90%)
  - `EFFECTIVE` (70-90%)
  - `MODERATELY_EFFECTIVE` (50-69%)
  - `INEFFECTIVE` (<50%)

### 6.5 Target Operating Model Alignment Engine

**TOM Dimensions**:
- Process Architecture
- People and Organization
- Technology and Data
- Governance Structures
- Performance Management
- Risk and Compliance

**Gap Analysis Methodology**:
1. Graph traversal to find processes without TOM alignment
2. Embedding-based TOM deviation measurement
3. LLM-powered gap rationale generation with few-shot examples
4. Gap prioritization: business criticality x risk exposure x regulatory impact x remediation cost

**Gap Types**: `FULL_GAP`, `PARTIAL_GAP`, `DEVIATION`, `NO_GAP`

**Process Maturity Scoring**: `INITIAL` → `MANAGED` → `DEFINED` → `QUANTITATIVELY_MANAGED` → `OPTIMIZING`

**Outputs**:
- Best practices library with industry-specific reference models
- Industry benchmarking integration
- Improvement recommendations with prioritized transformation roadmap

### 6.6 Integration Framework

| Integration | Method | Data |
|------------|--------|------|
| **Celonis** | Celonis EMS API | Event log import, process model import, conformance results |
| **Soroco Scout** | Work Graph API | Desktop task mining evidence |
| **ARIS** | AML/XML import | Process model import |
| **Visio** | VSDX parsing | Process diagram conversion |
| **Salesforce/SAP/ServiceNow** | Native connectors | SaaS data with credential management, rate limiting |
| **XES Format** | Standard import | Event log interoperability |
| **API/MCP Server** | REST + MCP | Consulting firm AI platform integration |
| **APEX Clearing** | REST API | Financial clearing and settlement data (State Street) |
| **Charles River IMS** | REST API | Investment management, portfolio, trade order data |
| **Camunda CIB7** | REST + BPMN deploy | Process orchestration, workflow execution, external tasks |
| **Agent Runtime** | IPC connector | Desktop agent lifecycle, capture coordination, health monitoring |
| **Databricks** | Unity Catalog API | Analytics datalake, data lineage, silver layer |

**Connector Framework**: Authenticated connections, error handling, retry logic, data normalization. Includes schema drift detection (`src/integrations/schema_drift.py`), field mapping (`src/integrations/field_mapping.py`), sync checkpointing (`src/integrations/sync_checkpoint.py`), and schema intelligence library with extraction templates and lifecycle tables.

### 6.7 Visualization and Reporting

- Interactive HTML process flow visualizations (BPMN.js)
- Evidence mapping overlays (which evidence supports which process element)
- Confidence heatmaps across process models (Bright/Dim/Dark color coding)
- Gap analysis dashboards with TOM alignment scoring
- Regulatory-policy-control overlay visualization
- Executive-ready PDF/HTML report generation
- Client-ready deliverable packaging
- Derived RACI matrix (Proposed vs Validated status per cell)
- Cross-frame comparison views (epistemic frame lens selector)
- Disagreement report (all ConflictObjects with resolution status)
- Evidence grading progression dashboard (Grade U→D→C→B→A over time)
- Seed list coverage report (% of seed terms with evidence)
- Dark Room backlog (prioritized list of Dark segments with estimated confidence uplift)
- Report generation in PDF, Excel, and JSON formats
- Knowledge graph interactive explorer (Cytoscape.js)
- WebSocket connections for real-time dashboard updates
- Client portal with interactive evidence exploration

### 6.8 Monitoring and Continuous Intelligence

**Status**: Implemented.

Comprehensive monitoring framework with agent-based collection, deviation detection, and alerting.

**Monitoring Agent Framework**:
- Configurable collectors and schedulers with agent registry
- Agent health monitoring and lifecycle management
- Background worker-based event processing

**Deviation Detection Engine**:
- Baseline establishment from historical patterns
- Real-time comparison against baselines with anomaly scoring
- Desktop gap detection for task mining data
- Continuous monitoring pipeline with metric collection

**Alerting and Dashboards**:
- Alert routing and escalation pipelines
- Dashboard aggregation with KPI tracking
- Notification system for significant process deviations
- WebSocket-based real-time updates

**Active Intelligence**:
- AI agents that proactively identify evidence gaps
- Active inferencing engine: gap identification → targeted probes/extraction → evidence acquisition
- Telemetry-triggered micro-surveys: when system telemetry detects anomalies, generate targeted survey probes for SMEs
- Process narratives with embedded validation prompts

### 6.9 Operating Model Scenario Engine

**Status**: Implemented.

Extends KMFlow from descriptive process intelligence into structured scenario analysis for operating model design. Enables consultants to define, compare, and evaluate alternative operating model configurations with evidence-grounded scoring and uncertainty-aware decision support.

**Design Principles**:
- Consultant-in-the-loop: the system assists scenario definition and comparison, it does not autonomously generate operating models
- Honest uncertainty: every score explicitly communicates what the system does and does not know
- Evidence-first: all recommendations trace to evidence quality and coverage, consistent with the platform's core philosophy
- Incremental value: each sub-capability delivers standalone value without requiring all others

**Sub-capability 1: Scenario Comparison Workbench**

Allows consultants to define 2-5 alternative operating model scenarios and compare them side-by-side with simulation results and evidence overlays.

Each scenario is expressed as a set of modifications to the as-is process model:
- Task additions, removals, or modifications
- Role reassignments and swim lane changes
- Gateway restructuring (decision boundary shifts)
- Control additions or removals

For each scenario, the platform:
- Runs simulation (cycle time, capacity, staffing impact) using the existing simulation engine
- Computes per-element evidence confidence using the 3D confidence model
- Overlays Bright/Dim/Dark classification on the modified process model
- Produces a comparison dashboard showing all scenarios side-by-side

Scenario definition is assisted by transformation templates:
- "Consolidate adjacent tasks in same swim lane"
- "Automate gateway where all inputs are system-provided"
- "Shift decision boundary: human review → system-assisted → autonomous"
- "Remove control and assess compliance impact"

Templates suggest modifications; the consultant decides which to apply. No scenario enters the comparison pipeline without human definition or approval.

**Sub-capability 2: Epistemic Action Planner**

For each scenario under comparison, identifies the evidence gaps that most affect the reliability of the analysis and recommends specific evidence acquisition actions.

Operates per-scenario by:
1. Identifying process elements where the scenario introduces changes in areas with Dim or Dark evidence coverage
2. Ranking evidence gaps by estimated information gain: how much would the scenario's overall confidence score improve if this evidence were obtained?
3. Mapping evidence gaps to actionable shelf data requests (integrates with existing shelf data request workflow)
4. Projecting confidence uplift: "Obtaining evidence item X would raise this scenario's confidence from 0.58 to an estimated 0.72"

Outputs:
- Ranked list of evidence acquisition actions per scenario
- Estimated confidence improvement per action
- Aggregated view across all scenarios: which evidence items would improve the analysis regardless of which scenario is chosen
- Direct integration with shelf data request creation

Builds on the existing gap scanner (`src/agents/gap_scanner.py`) and evidence recommender (`src/agents/recommender.py`), extending them to operate in a scenario-comparative context.

**Sub-capability 3: Assisted Alternative Suggestion**

Uses LLM analysis to suggest operating model modifications for consultant review. Positioned explicitly as AI-assisted brainstorming, not autonomous generation.

For a given as-is process model with evidence overlay, the LLM:
- Identifies potential inefficiencies, redundancies, and automation opportunities
- Suggests specific modifications as natural language descriptions with rationale
- Flags governance considerations: which controls or regulatory constraints are affected
- Notes where evidence is insufficient to assess the viability of a suggestion

**Critical constraints**:
- All suggestions are presented as "considerations for review," not recommendations
- No suggestion enters a scenario definition without explicit consultant approval
- The system surfaces what it does NOT know alongside each suggestion (evidence gaps, unstated assumptions, constraints it cannot verify)
- Segregation of duties and regulatory compliance are flagged as risk areas when role changes are suggested, but the system does not claim to enforce constraints it cannot fully model
- Full audit trail: every suggestion records the LLM prompt, response, evidence context, and consultant disposition (accepted / modified / rejected)

**Gating criteria**: Sub-capability 3 proceeds only after Sub-capabilities 1 and 2 are validated with real engagement data.

**Financial Impact Estimation**

Requires a financial data model not present in the current platform:
- Cost per role (hourly/annual rates per swim lane actor)
- Technology cost assumptions (per-transaction, licensing, implementation)
- Volume forecasts (transaction volumes, seasonal patterns)
- Implementation cost estimates (change management, training, technology)

Financial estimates are presented as ranges with explicit assumptions, never as point estimates. Every financial output includes:
- The assumptions it depends on
- The confidence level of those assumptions
- Sensitivity analysis: which assumptions most affect the result

**What This Is Not**:

This capability does not claim to:
- Automatically generate valid operating models (it assists consultants in defining them)
- Replace consulting judgment with algorithmic recommendations
- Produce precise financial predictions (it produces ranges with stated assumptions)
- Enforce all regulatory constraints (it flags known constraints and warns about gaps in its knowledge)
- Implement active inference or any specific mathematical framework from computational neuroscience

### 6.10 Process Knowledge Capture (KM4ProcessBot Integration)

Structured elicitation of process knowledge from subject matter experts, domain documents, and system telemetry. This capability bridges the gap between passive evidence ingestion (Section 6.1) and active knowledge elicitation, ensuring that tacit knowledge, exception logic, and uncertainty are captured systematically.

#### 6.10.1 Nine Universal Process Knowledge Forms

Every process can be described through nine fundamental knowledge forms. These serve as a completeness checklist — if any form is missing evidence, the system flags it for targeted acquisition.

| # | Form | What It Captures | Graph Representation |
|---|------|------------------|---------------------|
| 1 | **Activities** | What work is done | `Activity` nodes |
| 2 | **Sequences** | In what order | `PRECEDES` edges |
| 3 | **Dependencies** | What must happen first | `DEPENDS_ON` edges |
| 4 | **Inputs/Outputs** | What is consumed and produced | `CONSUMES` / `PRODUCES` edges to data objects |
| 5 | **Rules** | What governs decisions | `GOVERNED_BY` edges to Policy nodes + gateway conditions |
| 6 | **Personas** | Who does the work | `PERFORMED_BY` edges to Role nodes |
| 7 | **Controls** | What checks and balances exist | Control nodes + `ENFORCED_BY` edges |
| 8 | **Evidence** | What proves this happens | `EVIDENCED_BY` edges to Evidence nodes |
| 9 | **Uncertainty** | What we don't know | Dark segments + ConflictObject nodes |

#### 6.10.2 Structured Survey Bot

The survey bot conducts structured elicitation sessions with SMEs, producing `SurveyClaim` objects that feed directly into the knowledge graph.

**Eight Probe Types** (one per knowledge form, plus uncertainty):

| Probe Type | Example Prompt | Expected Response Structure |
|------------|---------------|---------------------------|
| Existence | "Does activity X happen in your area?" | Yes/No + frequency + exceptions |
| Sequence | "What happens after X?" | Activity name + conditions + variants |
| Dependency | "What must be done before X can start?" | Prerequisite activities + systems |
| I/O | "What information do you need to perform X?" | Input artifacts + systems + formats |
| Rule | "What determines whether X or Y happens?" | Decision criteria + thresholds + exceptions |
| Persona | "Who typically performs X?" | Role + backup + delegation rules |
| Control | "What checks happen during or after X?" | Control type + frequency + evidence |
| Uncertainty | "How confident are you about X?" | Certainty tier + reasoning + proof expectation |

**Certainty Tiers** for claim objects:

| Tier | Label | Meaning |
|------|-------|---------|
| 1 | `KNOWN` | SME is confident; can point to evidence |
| 2 | `SUSPECTED` | SME believes this but cannot prove it |
| 3 | `UNKNOWN` | SME acknowledges they don't know |
| 4 | `CONTRADICTED` | SME asserts the opposite of another source |

**Claim Object Structure**:
```
SurveyClaim {
  id: UUID
  session_id: UUID
  probe_type: ProbeType
  respondent_role: string
  claim_text: string
  certainty_tier: CertaintyTier
  proof_expectation: string  // "What evidence would confirm this?"
  related_seed_terms: [SeedTerm]
  epistemic_frame: EpistemicFrame
  created_at: DateTime
}
```

#### 6.10.3 Seed List Pipeline

The seed list is a domain vocabulary that focuses all capture and extraction on terms relevant to the specific business area under analysis. It acts as a domain lens applied across all four evidence planes.

**Pipeline**:
1. **Domain Vocabulary Extraction**: Consultant provides initial seed terms (activity names, system names, role titles, regulatory terms specific to the business area)
2. **NLP Refinement**: System analyzes ingested evidence to discover additional domain terms (named entity recognition, noun phrase extraction, term frequency analysis)
3. **Probe Generation**: Seed terms drive generation of domain-specific survey probes (e.g., seed term "KYC Review" → existence probe "Does KYC Review happen in your area?" + sequence probe "What happens after KYC Review?")
4. **Extraction Targeting**: Seed terms focus evidence extraction (e.g., when processing a 200-page policy document, prioritize sections mentioning seed terms)

**Seed Term Structure**:
```
SeedTerm {
  id: UUID
  term: string
  domain: string           // e.g., "loan_origination"
  category: TermCategory   // activity | system | role | regulation | artifact
  source: TermSource       // consultant_provided | nlp_discovered | evidence_extracted
  status: TermStatus       // active | deprecated | merged
  merged_into: UUID?       // if merged with another term (entity resolution)
  engagement_id: UUID
}
```

#### 6.10.4 Controlled Edge Vocabulary

See Section 6.2 for the 12 typed edge kinds and their constraint rules. The controlled edge vocabulary ensures that all relationships in the knowledge graph conform to a defined schema, enabling automated consistency checking and cross-source validation.

#### 6.10.5 Cross-Source Consistency Checks

Six automated detection rules that run as part of the consensus algorithm (Section 6.3, Step 4):

| # | Check | Detection Logic | Resolution |
|---|-------|----------------|------------|
| 1 | **Sequence Conflict** | Source A asserts X→Y, Source B asserts Y→X | Flag `SEQUENCE_MISMATCH`; resolve by evidence weight + recency |
| 2 | **Role Conflict** | Source A assigns Activity Z to Role R1, Source B to R2 | Flag `ROLE_MISMATCH`; present both with confidence; mark for SME validation |
| 3 | **Rule Conflict** | Business rule from Source A contradicts rule from Source B | Flag `RULE_MISMATCH`; check effective dates (bitemporal); escalate if unresolvable |
| 4 | **Existence Conflict** | Source A asserts activity exists, Source B denies or omits | Flag `EXISTENCE_MISMATCH`; weight by source authority + recency |
| 5 | **I/O Mismatch** | Upstream output O, downstream expects input I, O ≠ I | Flag `IO_MISMATCH`; check for naming variants via seed list; escalate if true gap |
| 6 | **Control Gap** | Activity A has no governance edge, but policy P requires it | Flag `CONTROL_GAP`; generate shelf data request for evidence of control |

**Three-Way Distinction** for each mismatch:
- **Genuine Disagreement**: Sources truly conflict → preserve both views with epistemic frames, mark for validation
- **Naming Variant**: Same concept, different terminology → resolve via seed list / entity resolution
- **Temporal Shift**: Both true at different times → resolve via bitemporal validity model

### 6.11 Replay and Simulation Visualization

Three modes of process replay that let stakeholders "watch the work move" — the primary trust-building mechanism for evidence-derived process models.

**Mode 1: Single-Case Timeline Replay**
- Step-by-step replay of a single case through the process model
- Each step shows: activity performed, performer, timestamp, evidence pointers, confidence
- Evidence panel displays supporting artifacts for each step
- Achievable with existing knowledge graph data (does not require event spine)

**Mode 2: Aggregate Volume Replay**
- Animated flow showing case volumes moving through process model over time
- Visualizes accumulation at bottlenecks, throughput at gateways, variant distribution
- Requires canonical event spine (Section 7, `CanonicalActivityEvent`)
- Heat maps directly traceable to replay metrics

**Mode 3: Variant Comparison Replay**
- Side-by-side replay of two process variants
- Highlights divergence points, different performers, different cycle times
- Links divergence to evidence (why does variant B exist?)

### 6.12 Validation Hub

Structured validation workflow that closes the loop between POV generation and SME confirmation.

**Segment-Level Review Packs**:
- System generates review packs per process segment (logical grouping of 3-8 activities)
- Each pack includes: process fragment, supporting evidence, confidence scores, disagreement flags, seed list terms
- Packs routed to specific SMEs based on role-activity mapping

**Structured Reviewer Actions**:

| Action | Effect on Knowledge Graph |
|--------|--------------------------|
| `CONFIRM` | Promotes evidence grade (C→B or B→A); increases confidence |
| `CORRECT` | Creates new assertion with `SUPERSEDES` edge; retains original with `retracted_at` |
| `REJECT` | Marks assertion as rejected; creates `ConflictObject` |
| `DEFER` | Marks for follow-up; no graph change; adds to Dark Room backlog |

**Republish Cycle**:
- After validation round, system regenerates POV as v2/v3
- Version diff shows what changed (BPMN diff visualization)
- Dark-room shrink rate tracked across versions as a KPI
- Evidence grading progression visible (how many elements moved from Grade D to Grade C, etc.)

### 6.13 Desktop Agent Platform

**Status**: Implemented.

Native desktop agents for macOS and Windows that capture work-surface reality (Evidence Plane 3: KM4Work). This replaces dependency on third-party task mining tools (Soroco Scout) with a first-party capture pipeline.

**macOS Agent** (`agent/macos/`):
- Swift-based, built with Swift Package Manager
- Captures screen activity, application switching, window titles, input events
- Hardened Runtime codesigned for macOS security compliance
- Status bar UI with onboarding flow and transparency log
- IPC integration with shared Python layer

**Windows Agent** (`agent/windows/`):
- C# .NET 8 NativeAOT for minimal footprint and fast startup
- WPF UI with system tray, onboarding wizard, transparency log
- MSI/MSIX installer with Intune, SCCM, and GPO deployment support
- DPAPI-based encrypted consent storage
- Named pipe IPC client for Python communication
- Private browsing detection to respect user privacy

**Shared Python Layer** (`agent/python/kmflow_agent/`):
- Cross-platform processing: VCE pipeline, PII detection, GDPR compliance
- Platform abstraction layer (macOS/Windows implementations)
- Configuration management, health reporting, event aggregation
- Agent-to-backend authentication

**Video Capture Engine (VCE)** (`src/taskmining/vce/`):
- Frame extraction and OCR (optical character recognition)
- PII redaction before any data leaves the device
- Activity classification: rule-based engine + VLM (Vision Language Model) stub
- Trigger engine for event-based capture activation
- Analytics for capture quality metrics

**Task Correlation Engine** (`src/taskmining/correlation/`):
- Deterministic linkage: regex-based case ID extraction from window titles
- Assisted/probabilistic linkage with explainability scoring
- Role association fallback when direct correlation unavailable
- Daily diagnostics for correlation quality monitoring

**Switching Sequence Analysis** (`src/taskmining/switching.py`):
- `SwitchingTrace` and `TransitionMatrix` models
- Friction scoring for application transitions
- Ping-pong detection (rapid back-and-forth between apps)
- Graph ingest: switching data flows into Neo4j knowledge graph

**ML Classification** (`src/taskmining/ml/`):
- Hybrid rule + ML activity classifier
- Sequence mining for activity pattern discovery
- Feature extraction and dataset management for model training
- App category taxonomy for classification

**Consent Model**: Opt-in, organization-authorized, or hybrid modes per GDPR Art. 6(1)(a). Consent verification enforced before any capture activates.

### 6.14 Process Orchestration

**Status**: Implemented.

BPMN L3/L4 process models orchestrate platform workflows. L3 models (with swimlanes) serve as documentation; L4 models (flat, no swimlanes) are executable in Camunda CIB7.

**Camunda CIB7 Integration**:
- BPMN deployment and process instance management via REST API
- External task execution pattern for service integration
- Docker service on port 8081 (host) / 8080 (container)

**Orchestration Workflows** (`platform/`):

| Workflow | Description |
|----------|-------------|
| `engagement-lifecycle-orchestration.bpmn` | End-to-end engagement lifecycle from intake to closure |
| `evidence-collection-workflow.bpmn` | Evidence intake, classification, and validation |
| `evidence-lifecycle-workflow.bpmn` | Evidence state transitions (L4 executable) |
| `pov-generation-workflow.bpmn` | Consensus algorithm orchestration with RACI generation |
| `tom-gap-analysis-workflow.bpmn` | TOM alignment scoring and roadmap generation |
| `continuous-monitoring-workflow.bpmn` | Deviation detection and alerting (L4 executable) |
| `shelf-data-request-workflow.bpmn` | Client data request tracking and escalation |
| `templates/evidence-parser-template.bpmn` | Fan-out/fan-in parser orchestration template |

**Case Study Models**:
- Loan Origination: as-is process + income verification + exception handling subprocesses
- State Street APEX: integration, custody, and clearing workflows

### 6.15 Analytics Data Layer

**Status**: Implemented.

Analytics warehouse for cross-engagement insights with data lineage tracking.

**Databricks Backend** (`src/datalake/databricks_backend.py`):
- Unity Catalog integration for governed data access
- Delta Lake backend abstraction for read/write operations

**Data Lineage** (`src/datalake/lineage.py`):
- End-to-end lineage tracking from evidence ingestion through semantic graph to analytics outputs
- API endpoints for lineage visualization and impact analysis

**Silver Layer** (`src/datalake/silver.py`):
- Curated analytics tables derived from raw platform data
- Engagement-scoped with RLS enforcement

**LLM Audit Trail** (`src/api/routes/llm_audit.py`):
- All LLM interactions (Claude API calls) logged with prompt, response, evidence context, and token usage
- Audit findings classification and governance flags

---

## 7. Data Model

### 7.1 Core Entities (PostgreSQL — 96+ Models)

| Entity | Description | Key Fields |
|--------|------------|------------|
| `Engagement` | Consulting engagement scope | id, name, client, business_area, status, team |
| `ShelfDataRequest` | Evidence request to client | id, engagement_id, status, items_requested, items_received |
| `EvidenceItem` | Individual piece of evidence | id, engagement_id, category, format, quality_score, completeness_score, reliability_score, freshness_score, validation_status, content_hash |
| `EvidenceFragment` | Extracted component from evidence | id, evidence_id, type, content, embedding_vector, metadata |
| `ProcessModel` | Generated process POV | id, engagement_id, version, confidence_score, brightness, evidence_grade, status |
| `ProcessElement` | Activity/decision/gateway in model | id, model_id, type, name, confidence_score, brightness, evidence_grade, evidence_count |
| `SemanticRelationship` | Typed relationship between entities | id, source_id, target_id, type, confidence, impact_score |
| `Policy` | Regulatory/organizational policy | id, name, type, source_evidence_id, clauses |
| `Control` | Process control | id, name, effectiveness, linked_policy_ids |
| `Regulation` | Regulatory requirement | id, name, framework, obligations |
| `TargetOperatingModel` | TOM definition | id, engagement_id, dimensions, maturity_targets |
| `GapAnalysisResult` | Gap finding | id, engagement_id, type, severity, confidence, rationale, recommendation |
| `BestPractice` | Industry best practice | id, domain, industry, description, source |
| `Benchmark` | Industry benchmark data | id, metric, industry, percentiles |
| `SurveyClaim` | Structured claim from survey bot | id, session_id, probe_type, respondent_role, claim_text, certainty_tier, proof_expectation, epistemic_frame_id, engagement_id |
| `EpistemicFrame` | Partitioned knowledge context | id, frame_kind, authority_scope, access_policy, engagement_id |
| `ConflictObject` | Detected cross-source inconsistency | id, mismatch_type, source_a_id, source_b_id, severity, resolution_status, resolution_type, engagement_id |
| `SeedTerm` | Domain vocabulary term | id, term, domain, category, source, status, merged_into, engagement_id |
| `Scenario` | Alternative operating model scenario | id, engagement_id, name, description, status, modifications, simulation_results, evidence_confidence_score |
| `ScenarioModification` | Individual change within a scenario | id, scenario_id, modification_type, target_element_id, parameters, template_source |
| `EpistemicAction` | Recommended evidence acquisition action | id, scenario_id, target_element_id, evidence_gap_description, estimated_confidence_uplift, shelf_request_id |
| `CanonicalActivityEvent` | Normalized system event | id, case_id, activity_name, timestamp_utc, source_system, performer_role_ref, evidence_refs, confidence_score, brightness |
| `ValidationDecision` | SME validation action | id, review_pack_id, element_id, action, reviewer_role, comment, previous_grade, new_grade |
| `FinancialAssumption` | Cost and volume assumptions | id, engagement_id, assumption_type, value, unit, confidence, source_evidence_id |
| `AlternativeSuggestion` | LLM-generated modification suggestion | id, scenario_id, suggestion_text, rationale, governance_flags, evidence_gaps, disposition |
| `CorrelationResult` | Task correlation linkage result | id, engagement_id, source_type, confidence, linkage_method, case_id |
| `CostVolume` | Financial volume and cost data | id, engagement_id, role, hourly_rate, transaction_volume, period |
| `DarkRoom` | Uncertainty backlog entry | id, engagement_id, element_id, brightness, estimated_uplift, priority |
| `ExportLog` | Evidence export audit trail | id, engagement_id, format, recipient, timestamp, watermark_id |
| `GradingSnapshot` | Evidence grade progression snapshot | id, engagement_id, version, grade_distribution, timestamp |
| `Incident` | Security/process incident | id, classification, severity, status, detected_at, resolved_at |
| `LLMAuditFinding` | LLM interaction audit record | id, prompt_hash, model, tokens_used, governance_flags, timestamp |
| `Pattern` | Discovered process pattern | id, engagement_id, pattern_type, confidence, frequency |
| `PatternMatch` | Pattern instance in evidence | id, pattern_id, evidence_id, match_confidence |
| `PDPPolicy` | ABAC policy definition | id, name, attributes, obligations, version, status |
| `PolicyBundle` | Versioned policy collection | id, version, policies, effective_from |
| `RoleActivityMapping` | Role-to-activity assignment | id, role_id, activity_id, engagement_id, mapping_type |
| `SwitchingTrace` | Desktop app switching sequence | id, session_id, app_from, app_to, timestamp, friction_score |
| `TransitionMatrix` | Aggregate switching patterns | id, session_id, matrix_data, ping_pong_count |
| `Watermark` | Export watermark tracking | id, export_id, recipient, algorithm, embedded_at |
| `Agent` | Monitoring agent definition | id, name, type, status, config, last_heartbeat |
| `Dashboard` | Dashboard configuration | id, engagement_id, persona, layout, widgets |
| `KPIBaseline` | Baseline metric for deviation detection | id, metric_name, baseline_value, threshold, engagement_id |
| `UpliftProjection` | Confidence uplift estimate | id, element_id, evidence_gap, projected_uplift, actual_uplift |

### 7.2 Knowledge Graph Schema (Neo4j)

**Node Types**: `Process`, `Subprocess`, `Activity`, `Decision`, `Evidence`, `Policy`, `Control`, `Regulation`, `TOM`, `Gap`, `Role`, `System`, `Document`, `SurveyClaim`, `EpistemicFrame`, `ConflictObject`, `SeedTerm`, `Case`, `CanonicalActivityEvent`, `ValidationDecision`, `SwitchingTrace`, `TransitionMatrix`, `DesktopCapture`, `AppCategory`, `Pattern`, `Incident`, `Watermark`

**Relationship Types with Properties**:
```
// Existing semantic bridges
(Process)-[:SUPPORTED_BY {confidence: float, evidence_count: int}]->(Evidence)
(Process)-[:GOVERNED_BY {effectiveness: float}]->(Policy)
(Policy)-[:ENFORCED_BY {coverage: float}]->(Control)
(Control)-[:SATISFIES {compliance_level: str}]->(Regulation)
(Process)-[:DEVIATES_FROM {gap_score: float, severity: str}]->(TOM)
(Evidence)-[:CONTRADICTS {severity: str, resolution: str}]->(Evidence)
(Activity)-[:FOLLOWED_BY {frequency: float, variants: int}]->(Activity)
(Process)-[:OWNED_BY]->(Role)
(Process)-[:USES]->(System)

// Controlled edge vocabulary (new)
(Activity)-[:PRECEDES {variant_id: str, frequency: float}]->(Activity)
(Activity)-[:TRIGGERS]->(Activity)
(Activity)-[:DEPENDS_ON]->(Activity)
(Activity)-[:CONSUMES]->(DataObject)
(Activity)-[:PRODUCES]->(DataObject)
(Activity)-[:PERFORMED_BY {confidence: float}]->(Role)
(Activity)-[:EVIDENCED_BY]->(Evidence)
(Assertion)-[:SUPERSEDES]->(Assertion)
(Process)-[:DECOMPOSES_INTO]->(Subprocess)
(Activity)-[:VARIANT_OF]->(Activity)

// Survey and epistemic (new)
(SurveyClaim)-[:SUPPORTS {confidence: float}]->(ProcessElement)
(SurveyClaim)-[:CONTRADICTS {severity: str}]->(ProcessElement)
(SurveyClaim)-[:HAS_FRAME]->(EpistemicFrame)

// Event spine
(Case)-[:HAS_EVENT]->(CanonicalActivityEvent)
(CanonicalActivityEvent)-[:MAPS_TO]->(Activity)

// Validation
(ValidationDecision)-[:CONFIRMS]->(ProcessElement)
(ValidationDecision)-[:CORRECTS]->(ProcessElement)
```

All relationships carry epistemic frame properties (`frame_kind`, `authority_scope`, `access_policy`) and bitemporal validity properties (`asserted_at`, `retracted_at`, `valid_from`, `valid_to`, `superseded_by`) where applicable.

**Indexes**: Unique constraints on entity IDs, composite indexes on (engagement_id, type), full-text index on SeedTerm.term.

### 7.3 Vector Store (pgvector)

- Default embedding model: all-mpnet-base-v2 (768-dim), selected for local execution (no API cost, no data egress)
- All embeddings within an engagement MUST use the same model and dimension
- `embedding_model` and `embedding_dimension` tracked per engagement to prevent cross-model similarity queries
- Alternative models configurable per engagement (requires re-embedding all evidence for that engagement)
- Tables: `evidence_embeddings`, `process_element_embeddings`, `policy_embeddings`, `seed_term_embeddings`
- HNSW index: `CREATE INDEX USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)`
- Content chunking: target 256-384 tokens per chunk (within model sequence limits), 50-100 token overlap, semantic-boundary-aware splitting (paragraph > section > sentence boundaries)

### 7.4 Cross-Store Consistency

PostgreSQL is the **system of record** for all entities. Neo4j is a **derived projection** optimized for graph traversal. pgvector stores embeddings as columns on their respective entity tables.

**Write pattern**: Write to PostgreSQL first (within a transaction), then project to Neo4j. If Neo4j write fails, enqueue a retry via Redis with exponential backoff.

**ID strategy**: Neo4j nodes store the PostgreSQL UUID as a property. No separate Neo4j-native IDs.

**Reconciliation**: Daily batch job compares PostgreSQL entity counts and IDs with Neo4j node counts per engagement, logging discrepancies.

**GDPR erasure cascade**: PostgreSQL deletion triggers cascading deletion in Neo4j (`MATCH (n {engagement_id: $eid}) DETACH DELETE n`) and pgvector embedding cleanup via a background job.

**Failure handling**: Neo4j write failure after PostgreSQL commit queues a retry — never triggers a PostgreSQL rollback. Eventually consistent with PostgreSQL as the authority.

### 7.5 Schema Evolution Strategy

- **PostgreSQL**: 83 Alembic migrations with backward-compatible column additions (nullable or with defaults). Data backfill strategy for new required columns.
- **Neo4j**: Ontology version bumping protocol. Cypher migration scripts for adding indexes/constraints when new node types are introduced. `SchemaVersion` node in Neo4j tracks applied migrations.
- **API**: URI-based versioning (`/api/v1/`, `/api/v2/`) for breaking changes. Minimum 6-month deprecation period with `Deprecation` and `Sunset` HTTP headers. Additive changes (new fields, new endpoints) are non-breaking.

---

## 8. API Specification

**Implementation**: 67 route files, 508+ endpoints across all domain areas. All APIs follow the conventions in Section 14 (base path `/api/v1/`, JSON responses, Pydantic schemas, OAuth2 auth, `?limit=N&offset=M` pagination).

### 8.1 Evidence APIs
- `POST /api/v1/evidence/upload` - Upload evidence with metadata
- `GET /api/v1/evidence/{id}` - Retrieve evidence details
- `GET /api/v1/evidence?engagement_id=X&category=Y` - List/filter evidence
- `PATCH /api/v1/evidence/{id}/validate` - Update validation status
- `GET /api/v1/evidence/{id}/fragments` - Get extracted fragments

### 8.2 Shelf Data Request APIs
- `POST /api/v1/shelf-requests` - Create evidence request
- `GET /api/v1/shelf-requests/{id}/status` - Track request fulfillment
- `POST /api/v1/shelf-requests/{id}/intake` - Client evidence submission portal

### 8.3 Process POV APIs
- `POST /api/v1/pov/generate` - Trigger POV generation for engagement scope
- `GET /api/v1/pov/{id}` - Retrieve process model with 3D confidence scores
- `GET /api/v1/pov/{id}/evidence-map` - Get evidence-to-process mappings
- `GET /api/v1/pov/{id}/gaps` - Get identified evidence gaps
- `GET /api/v1/pov/{id}/contradictions` - Get conflicting evidence (ConflictObjects)
- `GET /api/v1/pov/{id}/disagreements` - Get disagreement report with mismatch types
- `GET /api/v1/pov/{id}/raci` - Get derived RACI matrix (Proposed/Validated status)
- `GET /api/v1/pov/{id}/dark-room` - Get Dark Room backlog (prioritized dark segments)

### 8.4 TOM Alignment APIs
- `POST /api/v1/tom` - Upload/define target operating model
- `POST /api/v1/tom/{id}/align` - Run alignment against current POV
- `GET /api/v1/tom/{id}/gaps` - Get gap analysis results
- `GET /api/v1/tom/{id}/recommendations` - Get prioritized recommendations

### 8.5 Knowledge Graph APIs
- `GET /api/v1/graph/traverse` - Graph traversal from node
- `GET /api/v1/graph/search` - Semantic search across graph
- `GET /api/v1/graph/process/{id}/evidence-chain` - Evidence lineage for process element
- `GET /api/v1/graph/query` - Cypher query execution (restricted to `admin:graph_query` permission; query complexity limits enforced: max depth 5, max results 1000, 30s timeout)

### 8.6 Engagement APIs
- `POST /api/v1/engagements` - Create engagement
- `GET /api/v1/engagements/{id}/dashboard` - Persona-specific dashboard data
- `GET /api/v1/engagements/{id}/report` - Generate deliverable report

### 8.7 Survey Bot APIs
- `POST /api/v1/surveys/sessions` - Start a new survey session
- `GET /api/v1/surveys/sessions/{id}` - Get session status and claims
- `POST /api/v1/surveys/sessions/{id}/probes` - Submit probe responses
- `GET /api/v1/surveys/probes?engagement_id=X&probe_type=Y` - List generated probes
- `GET /api/v1/surveys/claims?engagement_id=X&certainty_tier=Y` - List claims with filters
- `PATCH /api/v1/surveys/claims/{id}` - Update claim (e.g., after validation)

### 8.8 Seed List APIs
- `POST /api/v1/seed-lists` - Create seed list for engagement
- `GET /api/v1/seed-lists/{id}/terms` - Get all terms in seed list
- `POST /api/v1/seed-lists/{id}/terms` - Add terms (consultant-provided or NLP-discovered)
- `PATCH /api/v1/seed-lists/{id}/terms/{term_id}` - Update term status (active/deprecated/merged)
- `GET /api/v1/seed-lists/{id}/coverage` - Get seed list coverage report (% terms with evidence)
- `POST /api/v1/seed-lists/{id}/refine` - Trigger NLP refinement pass on ingested evidence

### 8.9 Validation Hub APIs
- `POST /api/v1/validation/review-packs` - Generate review packs for POV version
- `GET /api/v1/validation/review-packs/{id}` - Get review pack with segment details
- `POST /api/v1/validation/review-packs/{id}/decisions` - Submit reviewer action (confirm/correct/reject/defer)
- `GET /api/v1/validation/decisions?engagement_id=X` - List all validation decisions
- `POST /api/v1/validation/republish` - Trigger republish cycle (regenerate POV with validation feedback)
- `GET /api/v1/validation/grading-progression?engagement_id=X` - Evidence grading progression over versions

### 8.10 Replay APIs
- `POST /api/v1/replay/single-case` - Start single-case timeline replay
- `POST /api/v1/replay/aggregate` - Start aggregate volume replay (requires event spine)
- `POST /api/v1/replay/variant-comparison` - Start variant comparison replay
- `GET /api/v1/replay/{id}/frames` - Get replay frames (paginated)

### 8.11 RACI APIs
- `GET /api/v1/raci?engagement_id=X` - Get derived RACI matrix
- `PATCH /api/v1/raci/{id}/cells/{cell_id}` - Update RACI cell status (Proposed → Validated)
- `GET /api/v1/raci/{id}/export?format=csv` - Export RACI as CSV/XLSX

### 8.12 Scenario Engine APIs
- `POST /api/v1/scenarios` - Create a new scenario for an engagement
- `GET /api/v1/scenarios?engagement_id=X` - List scenarios for engagement
- `GET /api/v1/scenarios/{id}` - Get scenario detail with simulation results and evidence overlay
- `POST /api/v1/scenarios/{id}/simulate` - Run simulation for a scenario
- `GET /api/v1/scenarios/{id}/compare?ids=X,Y,Z` - Side-by-side comparison of multiple scenarios
- `GET /api/v1/scenarios/{id}/evidence-coverage` - Bright/Dim/Dark classification per element
- `GET /api/v1/scenarios/{id}/epistemic-plan` - Ranked evidence acquisition actions with confidence uplift
- `POST /api/v1/scenarios/{id}/suggestions` - Request LLM-assisted modification suggestions
- `PATCH /api/v1/scenarios/{id}/suggestions/{suggestion_id}` - Accept/reject/modify a suggestion

### 8.13 Desktop Task Mining APIs
- `GET /api/v1/taskmining/sessions` - List task mining sessions
- `GET /api/v1/taskmining/sessions/{id}/events` - Get captured events for session
- `GET /api/v1/taskmining/correlation/{id}` - Get correlation results for session
- `GET /api/v1/taskmining/switching/{id}` - Get switching trace analysis
- `POST /api/v1/taskmining/config` - Configure capture settings

### 8.14 Monitoring APIs
- `GET /api/v1/monitoring/agents` - List monitoring agents and status
- `GET /api/v1/monitoring/dashboards/{id}` - Get dashboard data
- `GET /api/v1/monitoring/deviations?engagement_id=X` - List detected deviations
- `POST /api/v1/monitoring/baselines` - Establish metric baselines
- `GET /api/v1/monitoring/metrics` - Platform-wide metrics and KPIs

### 8.15 Governance APIs
- `GET /api/v1/governance/policies` - List governance policies
- `POST /api/v1/governance/evaluate` - Evaluate compliance for process
- `GET /api/v1/governance/overlay/{process_id}` - Get governance overlay for process
- `GET /api/v1/governance/flags/{id}` - Get data classification flags
- `GET /api/v1/governance/effectiveness` - Control effectiveness scores

### 8.16 Security APIs
- `POST /api/v1/pdp/evaluate` - PDP policy evaluation (ABAC)
- `POST /api/v1/incidents` - Create security incident
- `GET /api/v1/incidents/{id}` - Get incident details and status
- `POST /api/v1/data-classification/{id}` - Tag evidence with classification
- `GET /api/v1/consent/{engagement_id}` - Get consent records for engagement
- `POST /api/v1/transfer-controls/evaluate` - Evaluate cross-border transfer

### 8.17 Analytics APIs
- `GET /api/v1/lineage/{entity_id}` - Get data lineage for entity
- `GET /api/v1/llm-audit?engagement_id=X` - List LLM interaction audit records
- `GET /api/v1/metrics/platform` - Platform-wide statistics

### 8.18 Pattern Library APIs
- `GET /api/v1/patterns?engagement_id=X` - List discovered patterns
- `GET /api/v1/patterns/{id}/matches` - Get pattern match instances
- `POST /api/v1/patterns/detect` - Trigger pattern detection

### 8.19 Micro-Survey APIs
- `POST /api/v1/micro-surveys/campaigns` - Create survey campaign
- `GET /api/v1/micro-surveys/campaigns/{id}` - Get campaign status and claims
- `POST /api/v1/micro-surveys/campaigns/{id}/respond` - Submit survey response

### 8.20 Camunda Orchestration APIs
- `POST /api/v1/camunda/deploy` - Deploy BPMN process definition
- `POST /api/v1/camunda/process-instances` - Start process instance
- `GET /api/v1/camunda/process-instances/{id}` - Get instance status
- `POST /api/v1/camunda/external-tasks/complete` - Complete external task

### 8.21 Portal and Copilot APIs
- `GET /api/v1/portal/{engagement_id}` - Client portal data
- `POST /api/v1/copilot/query` - RAG copilot query with evidence context
- `GET /api/v1/copilot/history` - Copilot conversation history

### 8.22 WebSocket APIs
- `WS /api/v1/ws/{engagement_id}` - Real-time dashboard updates, task progress, alert notifications

---

## 9. Security, Privacy, and Compliance

### 9.1 Data Isolation and Access Control

- **Engagement-level data isolation**: All data scoped to engagement. Implemented: PostgreSQL Row-Level Security policies on 32+ tables with `current_engagement_id` session variable set at connection time via middleware
- **Authentication**: OAuth2/OIDC (consulting firm SSO integration)
- **Authorization**: Hybrid RBAC/ABAC model. RBAC for persona-level actions (what can this role do?). ABAC for data-level decisions (can this user access this classified evidence item in this engagement context?). `access_policy` on EpistemicFrame entities uses controlled vocabulary tied to engagement roles
- **Session management**: Access token expiry (30 minutes), refresh token expiry (7 days) with single-use rotation, concurrent session policy, session revocation on suspected compromise
- **Encryption**: AES-256 at rest (column-level for credentials, file-level for evidence), TLS 1.3 in transit (including database connections in production), key rotation support with key hierarchy (master key → data encryption keys)
- **Secrets management**: Integration credentials encrypted at rest, never stored in plaintext, never returned in API responses. Separate `Credential` entity with encrypted_value, rotation tracking, and access audit logging

### 9.2 Audit Trail

- Every data mutation (create, update, delete) MUST generate an audit log entry
- Audit log entries MUST include: actor identity, timestamp, action type, affected entity, engagement scope, IP address, request_id, change delta
- Audit logs MUST be immutable (append-only; no UPDATE or DELETE operations)
- Audit log retention MUST exceed the engagement data retention period (minimum 7 years for SOX-regulated clients)
- Audit logs for GDPR-relevant operations (erasure, consent changes, data exports) retained for statutory limitation period

### 9.3 Data Classification and Handling

- Evidence tagged with sensitivity levels: Public, Internal, Confidential, Restricted
- Classification enforced at access time: RESTRICTED evidence requires elevated permissions and generates enhanced audit entries
- **Client data handling**: No cross-engagement data leakage; isolated processing pipelines

### 9.4 Lawful Basis Framework (GDPR)

Every processing activity requires a documented lawful basis per GDPR Article 6:

| Processing Activity | Lawful Basis | Article |
|---------------------|-------------|---------|
| Evidence ingestion and analysis | Contractual necessity | Art. 6(1)(b) |
| LLM processing (Claude API) | Legitimate interest with documented balancing test | Art. 6(1)(f) |
| Survey bot elicitation | Consent | Art. 6(1)(a) |
| Desktop endpoint capture | Consent | Art. 6(1)(a) |
| Task mining | Consent | Art. 6(1)(a) |

**Consent verification**: No evidence processing, copilot interaction, or survey session endpoint shall execute without verified lawful basis. Where consent is the basis, the platform verifies active consent before processing.

**Data Subject Rights** (Phase 1 — MVP):
- Art. 15 (Access): Export all personal data held for a data subject, including evidence fragments, audit logs, copilot messages, survey claims, and consent records
- Art. 16 (Rectification): Allow data subjects to correct personal data
- Art. 17 (Erasure): Automated erasure within 30 days of request, covering all stores (PostgreSQL, Neo4j, pgvector, Redis cache). Background job executes erasure — not just records the request
- Art. 20 (Portability): Export personal data in machine-readable format (JSON)
- Art. 21 (Objection): Right to object to processing based on legitimate interest

### 9.5 Cross-Border Data Transfer

| Data Flow | Destination | Legal Mechanism |
|-----------|-------------|-----------------|
| Evidence → Claude API | US (Anthropic) | SCCs + Transfer Impact Assessment |
| Evidence → OpenAI ada-002 | US (OpenAI) | SCCs + Transfer Impact Assessment |
| Evidence → SaaS connectors | Various | Per-connector DPA review |

- Configurable data residency constraints at engagement level (e.g., "EU-only processing" flag prevents evidence from being sent to US-based LLM providers)
- Transfer Impact Assessment required before activating each new integration connector
- Engagement-level flag: `data_residency_restriction` (enum: `NONE`, `EU_ONLY`, `UK_ONLY`, `CUSTOM`)

### 9.6 Incident Response

- **Incident classification**: P1 (data breach), P2 (security incident, no breach), P3 (vulnerability), P4 (policy violation)
- **Breach notification**: Supervisory authority within 72 hours (GDPR Art. 33); data subjects without undue delay for high-risk (Art. 34)
- **Client notification**: Per engagement agreement SLA
- **Forensic preservation**: Audit logs frozen upon incident detection
- **Automated detection**: Anomalous data export volumes, unauthorized cross-engagement access attempts, credential compromise indicators

### 9.7 Third-Party Risk Management

- Risk assessment required before activating any new integration or AI provider
- Data minimization matrix: specify which evidence fields are transmitted to each third party
- AI provider controls: prompt sanitization, data retention opt-out verification, training data exclusion confirmation
- Annual review of third-party SOC2 reports or equivalent security attestations
- Third-party breach response procedure integrated with incident response workflow

### 9.8 Data Retention

| Data Category | Default Retention | Regulatory Min | Notes |
|--------------|------------------|----------------|-------|
| Evidence items | Engagement + 90d | Varies by industry | GDPR Art. 5(1)(e) |
| Audit logs | 7 years | 6 years (SOX) | Immutable, separate lifecycle |
| LLM prompts/responses | 90 days | None | Data minimization |
| Survey claims | Engagement + 90d | None | Contains SME assertions |
| Consent records | 7 years | 6 years (GDPR Art. 7) | Proof of lawful basis |
| Embeddings | Same as source | Same as source | Derived data |

- Retention minimum floors override user configuration (cannot set 30 days for SOX-regulated engagement)
- **Litigation hold**: When placed on an engagement, all automated retention cleanup suspended until hold released

### 9.9 Advanced Security Controls

**Status**: All previously deferred controls are now implemented.

- **Policy Decision Point (PDP)**: Implemented. 8 ABAC attributes (department, role, clearance, location, sensitivity, data_class, project, consent). Obligation enforcement: masking, cohort suppression, watermarking, field allowlists. PEP middleware integrated into API gateway. Policy bundle versioning for atomic policy updates.
- **Export watermarking**: Implemented. PDF and narrative artifacts carry engagement-level watermarks with recipient tracking. Watermark extraction for audit verification.
- **Cohort suppression**: Implemented. Analytics suppressed below minimum cohort size to protect individual identity. Configurable thresholds per engagement.
- **Endpoint capture consent**: Implemented. Extended consent model for desktop monitoring with opt-in, organization-authorized, and hybrid modes. DPAPI-encrypted consent storage on Windows, Keychain on macOS.
- **Incident response**: Implemented. P1-P4 classification, automated detection (anomalous exports, unauthorized cross-engagement access, credential compromise), forensic preservation.
- **Data classification**: Implemented. Evidence tagged with sensitivity levels (Public, Internal, Confidential, Restricted) enforced at access time.
- **Transfer controls**: Implemented. Cross-border data transfer evaluation with DPA review integration.

---

## 10. Personas and Dashboards

| Persona | Dashboard KPIs | Access Level |
|---------|---------------|-------------|
| **Engagement Lead** | Evidence coverage %, overall confidence score, brightness distribution, evidence grade progression, TOM alignment %, gap count by severity, team progress, seed list coverage %, dark-room shrink rate | Full engagement access |
| **Process Analyst** | Evidence processing status, classification accuracy, relationship mapping progress, assigned review items, cross-source consistency check results, conflict resolution queue | Assigned processes only |
| **Subject Matter Expert** | Process elements pending review, annotation count, confidence impact of reviews, survey session history, claim confirmation rate | Assigned domain only |
| **Client Stakeholder** | Read-only findings view, confidence scores with brightness overlay, gap analysis results, recommendation status, RACI matrix (validated items) | Read-only, filtered view |

---

## 11. User Flows

### Flow 1: Engagement Setup and Evidence Collection
1. Create engagement with scope (specific business area)
2. Define seed list (initial domain vocabulary for the business area)
3. Define evidence requirements per the 12-category taxonomy
4. Generate shelf data request (structured evidence request document), guided by seed list terms
5. Deliver request to client (email/portal)
6. Client uploads evidence through intake portal
7. System auto-classifies, validates, and catalogs evidence
8. NLP refinement pass discovers additional seed terms from ingested evidence
9. Evidence dashboard shows processing status, coverage per category, quality scores, seed list coverage
10. Analyst reviews flagged items (low quality, unclassified, potential duplicates)

### Flow 2: Process Point of View Generation
1. Trigger POV generation for engagement scope
2. System runs evidence aggregation and entity extraction (guided by seed list)
3. System performs cross-source triangulation
4. Cross-source consistency checks detect mismatches (6 rules)
5. Three-way distinction classifies each mismatch (genuine disagreement / naming variant / temporal shift)
6. Consensus algorithm synthesizes consensus process model (evidence-weighted, not limited to universal agreement)
7. Three-dimensional confidence scores assigned per element (numeric + brightness + evidence grade)
8. Contradictions flagged with ConflictObjects and alternative views
9. BPMN process model generated with evidence citations
10. Derived RACI generated (all entries marked "Proposed")
11. Analyst reviews, annotates, requests SME validation
12. SME reviews assigned elements, adds context
13. Model refined based on annotations

### Flow 3: TOM Alignment and Gap Analysis
1. Upload/select target operating model(s)
2. Import best practices and industry benchmarks
3. System performs automated alignment across TOM dimensions
4. Gap analysis generates findings with evidence-backed rationale
5. Recommendations prioritized by criticality x risk x cost
6. Engagement Lead reviews and curates findings
7. Generate client-ready deliverables (HTML/PDF)
8. Facilitate consulting conversation with evidence-backed POV

### Flow 4: Structured Knowledge Elicitation
1. System generates survey probes from seed list terms and nine knowledge forms
2. Probes targeted at Dim/Dark segments identified by the Epistemic Action Planner
3. SME completes survey session, producing SurveyClaim objects with certainty tiers
4. Claims ingested into knowledge graph with epistemic frame metadata
5. Cross-source consistency checks run between claims and existing evidence
6. Confidence scores updated based on new claims
7. Dark Room backlog updated (segments with additional evidence now move from Dark → Dim)

### Flow 5: Continuous Monitoring
1. Configure monitoring agents for specific data sources
2. Agents collect evidence continuously (logs, task mining, system data)
3. Canonical event spine built from system telemetry
4. Real-time deviation detection against established POV
5. Telemetry anomalies trigger micro-survey probes for relevant SMEs
6. Alerts generated for significant process deviations
7. Dashboard updated with live process intelligence

### Flow 6: Validation and Republish
1. System generates segment-level review packs from current POV
2. Review packs routed to relevant SMEs based on role-activity mapping
3. SMEs perform structured validation (confirm/correct/reject/defer)
4. Validation decisions write back to knowledge graph
5. System regenerates POV as v2 with version diff
6. Dark-room shrink rate and evidence grading progression tracked
7. Cycle repeats until MVC threshold met across all segments

### Flow 7: Operating Model Scenario Analysis
1. After POV generation and TOM gap analysis, Engagement Lead opens Scenario Workbench
2. System displays as-is process model with Bright/Dim/Dark evidence overlay
3. Consultant defines alternative scenarios using transformation templates or manual edits
4. For each scenario, system runs simulation and computes evidence confidence
5. Side-by-side comparison dashboard shows all scenarios with simulation results and evidence coverage
6. Epistemic Action Planner identifies evidence gaps that most affect the analysis
7. Consultant reviews ranked evidence acquisition actions and creates shelf data requests
8. LLM suggests additional modifications for consultant review; consultant accepts, modifies, or rejects each
9. Financial impact estimation added with stated assumptions and ranges
10. Engagement Lead selects preferred scenario(s) for client presentation with full evidence traceability

---

## 12. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Evidence processing accuracy | >90% correct classification | Validated against analyst review |
| POV generation time | <4 hours for typical scope (100 items, 5 categories, 50 seed terms) | End-to-end from trigger to model |
| Confidence score correlation | >0.8 with expert assessment | Pearson correlation on reference engagement (expert assessment protocol: 2 independent analysts score 50 elements using the same rubric; inter-rater kappa measured) |
| Consultant time savings | 60-70% reduction in process discovery | `EngagementTimeline` entity captures phase start/end timestamps; compare across engagements (business outcome hypothesis until sufficient data) |
| Evidence coverage per engagement | >40% in 2 weeks, >60% in 4 weeks, >80% stretch | Shelf data request item-level fulfillment rate |
| Gap detection recall | >85% of gaps identified by experts | Compared to manual gap analysis on reference engagement with labeled ground-truth gaps |
| Client satisfaction | >4.5/5.0 | Post-engagement survey (delivered via survey session type, not ad-hoc) |
| Seed list term coverage rate | >70% of seed terms have supporting evidence | Seed terms with ≥1 evidence link / total seed terms |
| Survey claim confirmation rate | >60% of claims confirmed via validation | Confirmed claims / total claims |
| Disagreement resolution time | <48 hours median | Time from ConflictObject creation to resolution |
| Evidence grading progression velocity | >20% of elements improve grade per validation cycle | Elements with grade improvement / total elements |
| Dark-room shrink rate | >15% reduction per POV version | Dark segments in v(n) vs v(n-1) |
| Scenario comparison adoption | >70% of engagements use Scenario Workbench | Usage tracking per engagement |
| Evidence acquisition follow-through | >50% of epistemic planner recommendations result in shelf data requests | Shelf request creation linked to epistemic actions |
| Confidence uplift accuracy | >0.7 correlation between projected and actual confidence improvement after evidence obtained | Compare projected vs actual per epistemic action |
| Scenario evaluation speed | >50% faster than manual workshop-based scenario evaluation | Before/after engagement comparison |

---

## 13. Phased Delivery

As of v2026.03.211 (March 2026), **Phases 1-3 are fully implemented** and **Phase 4 is substantially complete**. The section below documents what was delivered in each phase and identifies remaining work.

### Phase 1 — Foundation (COMPLETE)

- Engagement management (create, scope, team)
- Evidence ingestion pipeline (19 parsers across all 12 evidence categories)
- Shelf data request workflow (compose, track, intake with 10+ states)
- Evidence quality scoring and validation
- Semantic relationship engine (Neo4j graph construction with 5 bridges)
- Process POV generation with consensus algorithm and evidence linking
- Three-dimensional confidence scoring engine (numeric + brightness + evidence grade)
- Controlled edge vocabulary (12 typed edges) in Neo4j schema
- Entity schemas: `SurveyClaim`, `EpistemicFrame`, `ConflictObject`, `SeedTerm` with bitemporal validity
- HTML process flow visualization (BPMN.js)
- Evidence provenance tracking with SHA-256 content hashing
- Engagement Lead and Process Analyst dashboards
- Security: PostgreSQL RLS on 32+ tables, OAuth2/OIDC auth, immutable audit logging, AES-256-GCM encryption
- GDPR: lawful basis framework, consent verification middleware, data subject rights (access, erasure, portability), automated erasure jobs
- Async task architecture: Redis Streams for long-running operations
- MinIO object storage for evidence file persistence

### Phase 2 — Intelligence (COMPLETE)

- Full evidence taxonomy support (all 12 categories including audio, video, images, financial regulatory)
- Advanced semantic bridges across all domain pairs (ProcessEvidence, EvidencePolicy, ProcessTOM, CommunicationDeviation, ClaimWriteBack)
- Regulatory-policy-control overlay engine with governance policy catalog
- TOM alignment, automated gap analysis, maturity scoring, roadmap generation, industry benchmarking
- Best practices library with reference models
- Celonis integration (PQL + EMS), Soroco Scout integration
- Conformance checking against reference models
- SME and Client Stakeholder portals
- Report generation (PDF, Excel, JSON)
- Gap-prioritized transformation roadmap generator
- Seed list pipeline (domain vocabulary → NLP refinement → probe generation → extraction targeting)
- Survey bot with domain-seeded probes (8 probe types, claim objects, certainty tiers)
- Process narratives with embedded validation prompts (Claude API)
- Derived RACI generation (Proposed vs Validated)
- Evidence grading ladder (Grade U through Grade A progression)
- Cross-source consistency checks (6 automated detection rules + three-way distinction)
- SaaS connector framework (ServiceNow, SAP, Salesforce)
- Schema Intelligence Library (extraction templates, lifecycle tables, correlation keys)
- Conflict detection, classification, and resolution engine

### Phase 3 — Scale and Insight (COMPLETE)

- Monitoring agent framework with deviation detection, baselines, and alerting
- Continuous evidence collection with quality monitoring
- Real-time process deviation detection with anomaly scoring
- Agentic capabilities (proactive evidence gap identification via gap scanner + recommender)
- Cross-engagement pattern library with ML classification (strict data isolation)
- Scenario Comparison Workbench (define, simulate, compare 2-5 operating model alternatives)
- Epistemic Action Planner (per-scenario evidence gap ranking with confidence uplift projection)
- Event spine builder (canonicalization + mapping rules + `CanonicalActivityEvent`)
- Replay visualization (single-case timeline, aggregate volume, variant comparison)
- Validation Hub (dark room, segment-level review packs, structured feedback, republish cycle)
- Active inferencing engine (gap identification → targeted probes/extraction)
- Telemetry-triggered micro-surveys
- Dark Room operations (uncertainty backlog, illumination planner, shrink-rate tracking)
- Desktop Agent Platform: native macOS (Swift) + Windows (C#) agents with VCE pipeline, task correlation, switching sequence analysis (replaces Soroco dependency)
- PDP/ABAC: 8 attributes, obligation enforcement, PEP middleware, policy bundle versioning
- Export watermarking with recipient tracking
- Cohort suppression below configurable thresholds
- API/MCP server for consulting platform integration
- Client portal with interactive exploration
- Process orchestration: 8 BPMN L3/L4 workflows, Camunda CIB7 integration
- Analytics data layer: Databricks backend, data lineage, LLM audit trail

### Phase 4 — Reimagination (SUBSTANTIALLY COMPLETE)

**Implemented**:
- Financial data model (cost per role, volume forecasts, technology cost assumptions)
- Financial impact estimation with ranges, assumptions, sensitivity analysis, NPV/ROI
- Assisted Alternative Suggestion (LLM-suggested modifications with suggestion review workflow)
- Transformation templates (consolidation, automation, decision boundary shift)
- BPMN diff visualization (structural comparison between as-is and scenario models)
- Scenario ranking with composite scoring (evidence confidence, simulation results, financial impact)
- Epistemic uncertainty handling
- Engagement-level scenario history and audit trail
- Reimagination dashboard integration into Engagement Lead portal

**Remaining**:
- Assessment Overlay Matrix (Value x Ability-to-Execute)
- BPM-orchestrated engagement lifecycle (activate BPMN models as live Camunda workflows — partially implemented via Camunda integration)
- Ontology derivation (from seed list + knowledge graph → domain ontology)
- Deployment flexibility (hybrid/on-prem patterns for regulated clients)

### Phase 5 — Production Hardening (Planned)

- Multi-tenant isolation (organization-level data partitioning)
- Mobile client applications
- Worker.py Redis wiring for background processing
- REST endpoints for remaining graph/semantic/ML services
- Horizontal scaling (service extraction from modular monolith)
- CI/CD pipeline hardening for production deployment
- Performance benchmarking against "typical scope" targets

---

## 14. Architecture

### System Architecture

```
+-------------------------------------------------------------------+
|                     DESKTOP AGENT LAYER                             |
|  macOS Agent (Swift)   |  Windows Agent (C#)  |  Shared Python     |
|  Screen capture, IPC   |  NativeAOT, WPF UI  |  VCE, PII, GDPR   |
+-------------------------------------------------------------------+
                              |
+-------------------------------------------------------------------+
|                     CLIENT / PORTAL LAYER                          |
|  Next.js Frontend      |  Client Intake Portal  |  Report Viewer  |
|  (Port 3000/3002)      |  Survey Bot UI         |  Copilot UI     |
+-------------------------------------------------------------------+
                              |
+-------------------------------------------------------------------+
|                     API GATEWAY (FastAPI)                           |
|                      (Port 8000/8002)                              |
|  67 route files, 508+ endpoints                                    |
|  Evidence | POV | TOM | Graph | Engagement | Survey | Seed List   |
|  Validation | Replay | Scenario | Monitoring | Governance | PDP   |
|  TaskMining | Camunda | Copilot | Portal | WebSocket              |
+-------------------------------------------------------------------+
                              |
+-------------------------------------------------------------------+
|                   PROCESSING SERVICE LAYER                         |
|                                                                    |
|  Evidence Ingestion    |  Semantic Bridge     |  Consensus         |
|  Engine (19 parsers,   |  Engine (5 bridges,  |  Algorithm         |
|   quality scoring,     |   entity resolution, |  (triangulation,   |
|   MinIO storage)       |   controlled edges)  |   model assembly)  |
|                        |                      |                    |
|  TOM Alignment         |  Gap Analysis        |  RAG Copilot       |
|  Engine (maturity,     |  Engine (graph       |  (vector+semantic  |
|   roadmap, benchmark)  |   traversal, LLM)    |   retrieval)       |
|                        |                      |                    |
|  Scenario Engine       |  Simulation Engine   |  Validation Hub    |
|  (comparison,          |  (financial, cost,   |  (dark room,       |
|   epistemic planner)   |   sensitivity, ROI)  |   grading, packs)  |
|                        |                      |                    |
|  Task Mining           |  Monitoring          |  Security          |
|  (VCE, correlation,    |  (agents, deviation, |  (PDP/ABAC,        |
|   switching, ML)       |   alerting, baseline)|   watermark, PII)  |
|                        |                      |                    |
|  Governance            |  Pattern Library     |  Replay Engine     |
|  (policy catalog,      |  (ML classifier,     |  (timeline,        |
|   compliance, export)  |   anonymizer)        |   volume, variant) |
+-------------------------------------------------------------------+
                              |
+-------------------------------------------------------------------+
|                     ORCHESTRATION LAYER                             |
|  Camunda CIB7 (Port 8081)                                         |
|  8 BPMN L3/L4 workflows | External task execution                 |
+-------------------------------------------------------------------+
                              |
+-------------------------------------------------------------------+
|                     DATA & INTELLIGENCE LAYER                      |
|                                                                    |
|  PostgreSQL 15   |  Neo4j 5.x     |  Redis 7     |  MinIO         |
|  (pgvector)      |  (Knowledge    |  (Cache/     |  (Object       |
|  96+ models      |   Graph)       |   Queue)     |   Storage)     |
|  83 migrations   |  Controlled    |  Sessions    |  Evidence      |
|  RLS on 32+      |   edges        |  Job queue   |   files        |
|   tables         |  Epistemic     |  Rate limit  |                |
|                  |   frames       |              |                |
|                  |                |              |  Databricks    |
|                  |                |              |  (Analytics    |
|                  |                |              |   datalake)    |
+-------------------------------------------------------------------+
```

**Current State**: The platform is a modular monolith — separate Python packages within a single FastAPI deployable. The architecture diagram above shows logical service boundaries, not deployment units. Service extraction will occur incrementally as scaling requirements emerge.

### Async Task Architecture

Long-running operations use an async task pattern via Redis Streams:

| Operation | Pattern | Expected Duration |
|-----------|---------|-------------------|
| Evidence upload (single item) | Synchronous response + async processing | <30s response, <5min processing |
| POV generation | Async (`202 Accepted` + task_id) | <4 hours for typical scope |
| TOM alignment | Async | <30 minutes |
| Simulation run | Async | <10 minutes |
| Evidence ingestion (batch) | Async | Varies by volume |
| GDPR erasure | Async background job | <30 days (regulatory) |
| Dashboard queries | Synchronous | <3 seconds |
| Graph traversal | Synchronous | <2 seconds |
| Vector search (top-k) | Synchronous | <500ms |

Async operations return `202 Accepted` with a `task_id`. Clients poll `GET /api/v1/tasks/{task_id}` for status or subscribe via WebSocket for completion notification. Task progress is reported as percentage with stage labels.

**"Typical scope"** for performance targets: 100 evidence items across 5 categories, average 20 pages per document, 50 seed terms, 10,000 graph nodes, 50,000 graph edges.

### Domain Events

Key events that flow between processing services via Redis Streams:

| Event | Triggers |
|-------|----------|
| `EvidenceIngested` | Graph update, embedding generation, seed list matching |
| `GraphUpdated` | Confidence recalculation |
| `POVGenerated` | RACI derivation, dark room assessment |
| `ValidationDecisionRecorded` | Evidence grade update, confidence propagation |
| `DeviationDetected` | Alert, micro-survey generation |

At-least-once delivery semantics. Event handlers must be idempotent.

### Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | Python 3.12+ (FastAPI, SQLAlchemy 2.x, Pydantic 2.x) | API and business logic |
| **Frontend** | Next.js 15+ (React 18, BPMN.js, Cytoscape, Recharts) | UI and visualization |
| **Knowledge Graph** | Neo4j 5.x with APOC plugin | Semantic relationships, controlled edge vocabulary |
| **Vector Store** | PostgreSQL 15 with pgvector | Embedding storage and similarity search |
| **Embeddings** | all-mpnet-base-v2 (768-dim) initially, Claude/OpenAI for analysis | Semantic similarity |
| **AI/ML** | Claude API | Analysis, gap rationale, RAG copilot, narrative generation, survey probe generation |
| **Cache/Queue** | Redis 7 | Caching, background job queue, survey sessions, rate limiting |
| **Object Storage** | MinIO | Evidence file persistence, content-addressable storage |
| **Process Engine** | Camunda CIB7 | BPMN workflow orchestration, external task execution |
| **Analytics** | Databricks (Unity Catalog) | Data warehouse, lineage, silver layer |
| **Desktop Agent (macOS)** | Swift (SPM) | Native screen capture, VCE, Hardened Runtime codesigned |
| **Desktop Agent (Windows)** | C# .NET 8 NativeAOT | Native screen capture, VCE, WPF UI, MSI/MSIX |
| **Desktop Agent (Shared)** | Python 3.12 | VCE pipeline, PII redaction, ML classification, IPC |
| **Process Viz** | BPMN.js | Interactive process modeling |
| **Infrastructure** | Docker Compose (7+ services) | Multi-service deployment with health checks |
| **Presentation Auth** | Cloudflare Workers (jose v6 + Descope) | OTP auth for stakeholder presentations |
| **Testing** | pytest (5,162+), Jest (635+), Playwright (E2E) | Quality assurance, >80% coverage |
