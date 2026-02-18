# KMFlow Platform - Product Requirements Document

**Version**: 1.0.0
**Status**: Draft
**Last Updated**: 2026-02-15
**Author**: David Johnson, Paul Roth
**Classification**: Internal - Confidential

---

## 1. Executive Summary

KMFlow is an AI-powered Process Intelligence platform designed for consulting engagements. It occupies genuine white space at the intersection of Process Mining (Celonis, Signavio), AI-powered consulting tools (McKinsey Lilli, KPMG Workbench), and qualitative evidence analysis.

**Core Innovation**: KMFlow is evidence-first, not event-log-first. It starts with the diverse evidence consultants actually collect (documents, interviews, system exports, policies) rather than requiring structured event log extracts that take months to configure.

**What KMFlow Does**:
- Ingests diverse client evidence per business area (not cross-enterprise)
- Builds semantic relationships across all evidence items
- Synthesizes a "least common denominator" first-pass process point of view
- Scores every process element with confidence based on evidence coverage
- Aligns against Target Operating Models, best practices, and industry benchmarks
- Generates prioritized gap analysis with evidence-backed recommendations
- Models regulations, policies, and controls as connective tissue between process elements

**Strategic Positioning**: No existing product combines evidence ingestion from consulting engagements, semantic relationship building across qualitative and quantitative data, confidence-scored process model generation, and automated TOM gap analysis.

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

---

## 3. Product Vision

KMFlow transforms consulting delivery by enabling data-driven process conversations from day one of client engagement.

**Vision Statement**: Ingest a focused body of evidence related to a specific business area. Create consistent semantic relationships between all evidence items. Produce a "least common denominator" first-pass point of view across the evidence corpus. Score every process element with confidence based on evidence coverage, quality, and agreement. Align against TOMs, best practices, and industry benchmarks. Generate prioritized gap analysis with evidence-backed recommendations.

**Guiding Principles**:
- Evidence-first: every assertion is traceable to source evidence
- Focused scope: one business area at a time, not cross-enterprise
- Confidence transparency: no black-box outputs; every score is explainable
- Consulting-native: designed for how consultants actually work
- Regulations, policies, and controls as connective tissue between items

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

**KMFlow's Unique Position**: Consulting-first process intelligence. The only platform that combines evidence ingestion from consulting engagements, semantic relationship building, confidence-scored process models, and automated TOM gap analysis.

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
| 7 | **KM4Work** | BPMN 2.0 XML, EPC, DMN | Contextualized ways of working from log files, desktop task mining, artifacts |
| 8 | **BPM Process Models** | BPMN 2.0 XML, EPC, ARIS, Flowable/Camunda | Extraction pipeline for activities, sequences, gateways, swim lanes, decision points |
| 9 | **Regulatory and Policy** | Regulatory filings, policy docs, compliance frameworks, SOP libraries | Clause-level extraction with requirement linkage and obligation mapping |
| 10 | **Controls and Evidence** | Control matrices, evidence logs, monitoring outputs, audit trails | Control-to-process linkage with compliance state tracking |
| 11 | **Domain Communications** | Email archives, chat transcripts, tickets, incident reports | Pattern extraction: actual process execution vs. documented procedures |
| 12 | **Job Aids and Edge Cases** | Decision trees, quick reference cards, exception guides, workarounds | Rule extraction for ambiguous edge cases and undocumented decision logic |

---

## 6. Core Platform Capabilities

### 6.1 Evidence Ingestion Engine

Multi-format document processing pipeline with format-specific parsers for all 12 evidence categories.

**Key Features**:
- Shelf data request management: compose requests, deliver to clients, track responses, match received evidence to requested items, follow-up automation
- Evidence cataloging with automated metadata extraction
- Evidence quality scoring across four dimensions:
  - **Completeness** (0.0-1.0): How much of the requested evidence is present
  - **Reliability** (0.0-1.0): Source credibility and document integrity
  - **Freshness** (0.0-1.0): How current the evidence is
  - **Consistency** (0.0-1.0): Agreement with other evidence items
- Evidence validation workflow: automated classification -> human review -> approval/rejection
- Duplicate detection and conflicting evidence flagging
- Evidence lifecycle: `PENDING` -> `VALIDATED` -> `ACTIVE` -> `EXPIRED` -> `ARCHIVED`
- Content hashing (SHA-256) for integrity verification
- Complete audit trail for evidence provenance

### 6.2 Semantic Relationship Engine

Knowledge graph construction using Neo4j with typed nodes and relationships.

**Semantic Bridges**:
- `ProcessEvidenceBridge`: Process <-> Evidence (confidence-weighted)
- `EvidencePolicyBridge`: Evidence <-> Policy/Regulation/Control
- `ProcessTOMBridge`: Process <-> Target Operating Model (gap-scored)
- `CommunicationDeviationBridge`: Communications <-> Documented procedures (deviation detection)

**Capabilities**:
- Entity resolution across heterogeneous evidence sources
- Relationship confidence scoring with impact propagation
- Embedding-based semantic similarity (all-mpnet-base-v2 or domain-tuned model)
- Hybrid retrieval: direct ID lookup + top-k semantic search (RAG)
- Relationship types: `SUPPORTED_BY`, `GOVERNED_BY`, `DEVIATES_FROM`, `IMPLEMENTS`, `CONTRADICTS`, `MITIGATES`, `REQUIRES`

### 6.3 Process Point of View Generator (Consensus Algorithm)

The intellectual core of the platform. Synthesizes a consensus first-pass process view from diverse evidence.

**Algorithm Steps**:

1. **Evidence Aggregation**: Collect all evidence related to a scoped business area
2. **Entity Extraction**: Identify process elements (activities, decisions, roles, systems) from each evidence source
3. **Cross-Source Triangulation**: Validate process elements by corroboration across multiple evidence types
4. **Consensus Building**: Apply weighted voting across evidence sources:
   - System data (highest weight: objective)
   - Process documentation (high weight: intentional)
   - Communications/tickets (medium weight: behavioral)
   - Interviews/workshops (medium weight: subjective but expert)
   - Job aids/workarounds (lower weight: may reflect exceptions)
5. **Contradiction Resolution**: When evidence conflicts:
   - Flag contradictions with severity scoring
   - Present alternative views with supporting evidence for each
   - Apply recency bias (newer evidence weighted higher for conflicts)
   - Default to "documented + observed" over "documented only"
6. **Model Assembly**: Generate BPMN-style process model with:
   - Every element traced to source evidence
   - Confidence score per element
   - Variant annotations where evidence supports multiple paths
   - Gap markers where evidence is insufficient

**Confidence Scoring Model** (per process element):

```
confidence = (
    evidence_coverage  * 0.30 +    # How many evidence types support this element
    evidence_agreement * 0.25 +    # Cross-source corroboration
    evidence_quality   * 0.20 +    # Quality scores of supporting evidence
    source_reliability * 0.15 +    # Credibility of evidence sources
    evidence_recency   * 0.10      # Freshness of supporting evidence
)

Levels:
  VERY_HIGH (0.9+)
  HIGH (0.75-0.89)
  MEDIUM (0.50-0.74)
  LOW (0.25-0.49)
  VERY_LOW (<0.25)
```

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

**Process Maturity Scoring**: `INITIAL` -> `MANAGED` -> `DEFINED` -> `QUANTITATIVELY_MANAGED` -> `OPTIMIZING`

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

**Connector Framework**: Authenticated connections, error handling, retry logic, data normalization.

### 6.7 Visualization and Reporting

- Interactive HTML process flow visualizations (BPMN.js)
- Evidence mapping overlays (which evidence supports which process element)
- Confidence heatmaps across process models
- Gap analysis dashboards with TOM alignment scoring
- Regulatory-policy-control overlay visualization
- Executive-ready PDF/HTML report generation
- Client-ready deliverable packaging

### 6.8 Monitoring and Continuous Intelligence (Phase 3)

- Monitoring agent for log analysis and process deviation detection
- Desktop task mining integration (via Soroco Scout / KM4Work)
- Continuous evidence collection with quality monitoring
- Real-time dashboards and alerting
- Agentic capabilities: AI agents that proactively identify evidence gaps

### 6.9 Operating Model Scenario Engine (Phases 3-4)

Extends KMFlow from descriptive process intelligence into structured scenario analysis for operating model design. Enables consultants to define, compare, and evaluate alternative operating model configurations with evidence-grounded scoring and uncertainty-aware decision support.

**Design Principles**:
- Consultant-in-the-loop: the system assists scenario definition and comparison, it does not autonomously generate operating models
- Honest uncertainty: every score explicitly communicates what the system does and does not know
- Evidence-first: all recommendations trace to evidence quality and coverage, consistent with the platform's core philosophy
- Incremental value: each sub-capability delivers standalone value without requiring all others

**Sub-capability 1: Scenario Comparison Workbench (Phase 3)**

Allows consultants to define 2-5 alternative operating model scenarios and compare them side-by-side with simulation results and evidence overlays.

Each scenario is expressed as a set of modifications to the as-is process model:
- Task additions, removals, or modifications
- Role reassignments and swim lane changes
- Gateway restructuring (decision boundary shifts)
- Control additions or removals

For each scenario, the platform:
- Runs simulation (cycle time, capacity, staffing impact) using the existing simulation engine
- Computes per-element evidence confidence using the existing scoring model
- Overlays evidence coverage classification (Bright / Dim / Dark) on the modified process model
- Produces a comparison dashboard showing all scenarios side-by-side

Scenario definition is assisted by transformation templates:
- "Consolidate adjacent tasks in same swim lane"
- "Automate gateway where all inputs are system-provided"
- "Shift decision boundary: human review → system-assisted → autonomous"
- "Remove control and assess compliance impact"

Templates suggest modifications; the consultant decides which to apply. No scenario enters the comparison pipeline without human definition or approval.

**Evidence Coverage Classification**:
- **Bright**: Process element supported by 3+ evidence sources with ≥0.75 confidence
- **Dim**: Process element supported by 1-2 evidence sources or confidence between 0.40-0.74
- **Dark**: Process element with no supporting evidence or confidence <0.40

**Sub-capability 2: Epistemic Action Planner (Phase 3)**

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

**Sub-capability 3: Assisted Alternative Suggestion (Phase 4)**

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

**Financial Impact Estimation (Phase 4 prerequisite)**

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

---

## 7. Data Model

### 7.1 Core Entities (PostgreSQL)

| Entity | Description | Key Fields |
|--------|------------|------------|
| `Engagement` | Consulting engagement scope | id, name, client, business_area, status, team |
| `ShelfDataRequest` | Evidence request to client | id, engagement_id, status, items_requested, items_received |
| `EvidenceItem` | Individual piece of evidence | id, engagement_id, category, format, quality_score, completeness_score, reliability_score, freshness_score, validation_status, content_hash |
| `EvidenceFragment` | Extracted component from evidence | id, evidence_id, type, content, embedding_vector, metadata |
| `ProcessModel` | Generated process POV | id, engagement_id, version, confidence_score, status |
| `ProcessElement` | Activity/decision/gateway in model | id, model_id, type, name, confidence_score, evidence_count |
| `SemanticRelationship` | Typed relationship between entities | id, source_id, target_id, type, confidence, impact_score |
| `Policy` | Regulatory/organizational policy | id, name, type, source_evidence_id, clauses |
| `Control` | Process control | id, name, effectiveness, linked_policy_ids |
| `Regulation` | Regulatory requirement | id, name, framework, obligations |
| `TargetOperatingModel` | TOM definition | id, engagement_id, dimensions, maturity_targets |
| `GapAnalysisResult` | Gap finding | id, engagement_id, type, severity, confidence, rationale, recommendation |
| `BestPractice` | Industry best practice | id, domain, industry, description, source |
| `Benchmark` | Industry benchmark data | id, metric, industry, percentiles |
| `Scenario` | Alternative operating model scenario (Phase 3) | id, engagement_id, name, description, status, modifications, simulation_results, evidence_confidence_score |
| `ScenarioModification` | Individual change within a scenario (Phase 3) | id, scenario_id, modification_type, target_element_id, parameters, template_source |
| `EpistemicAction` | Recommended evidence acquisition action (Phase 3) | id, scenario_id, target_element_id, evidence_gap_description, estimated_confidence_uplift, shelf_request_id |
| `FinancialAssumption` | Cost and volume assumptions for financial estimation (Phase 4) | id, engagement_id, assumption_type, value, unit, confidence, source_evidence_id |
| `AlternativeSuggestion` | LLM-generated modification suggestion (Phase 4) | id, scenario_id, suggestion_text, rationale, governance_flags, evidence_gaps, disposition |

### 7.2 Knowledge Graph Schema (Neo4j)

**Node Types**: `Process`, `Subprocess`, `Activity`, `Decision`, `Evidence`, `Policy`, `Control`, `Regulation`, `TOM`, `Gap`, `Role`, `System`, `Document`

**Relationship Types with Properties**:
```
(Process)-[:SUPPORTED_BY {confidence: float, evidence_count: int}]->(Evidence)
(Process)-[:GOVERNED_BY {effectiveness: float}]->(Policy)
(Policy)-[:ENFORCED_BY {coverage: float}]->(Control)
(Control)-[:SATISFIES {compliance_level: str}]->(Regulation)
(Process)-[:DEVIATES_FROM {gap_score: float, severity: str}]->(TOM)
(Evidence)-[:CONTRADICTS {severity: str, resolution: str}]->(Evidence)
(Activity)-[:FOLLOWED_BY {frequency: float, variants: int}]->(Activity)
(Process)-[:OWNED_BY]->(Role)
(Process)-[:USES]->(System)
```

**Indexes**: Unique constraints on entity IDs, composite indexes on (engagement_id, type).

### 7.3 Vector Store (pgvector)

- Embedding dimension: 768 (all-mpnet-base-v2) or 1536 (OpenAI ada-002)
- Tables: `evidence_embeddings`, `process_element_embeddings`, `policy_embeddings`
- HNSW index for approximate nearest neighbor search

---

## 8. API Specification

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
- `GET /api/v1/pov/{id}` - Retrieve process model with confidence scores
- `GET /api/v1/pov/{id}/evidence-map` - Get evidence-to-process mappings
- `GET /api/v1/pov/{id}/gaps` - Get identified evidence gaps
- `GET /api/v1/pov/{id}/contradictions` - Get conflicting evidence

### 8.4 TOM Alignment APIs
- `POST /api/v1/tom` - Upload/define target operating model
- `POST /api/v1/tom/{id}/align` - Run alignment against current POV
- `GET /api/v1/tom/{id}/gaps` - Get gap analysis results
- `GET /api/v1/tom/{id}/recommendations` - Get prioritized recommendations

### 8.5 Knowledge Graph APIs
- `GET /api/v1/graph/query` - Cypher query execution
- `GET /api/v1/graph/traverse` - Graph traversal from node
- `GET /api/v1/graph/search` - Semantic search across graph

### 8.6 Engagement APIs
- `POST /api/v1/engagements` - Create engagement
- `GET /api/v1/engagements/{id}/dashboard` - Persona-specific dashboard data
- `GET /api/v1/engagements/{id}/report` - Generate deliverable report

### 8.7 Scenario Engine APIs (Phase 3-4)
- `POST /api/v1/scenarios` - Create a new scenario for an engagement
- `GET /api/v1/scenarios?engagement_id=X` - List scenarios for engagement
- `GET /api/v1/scenarios/{id}` - Get scenario detail with simulation results and evidence overlay
- `POST /api/v1/scenarios/{id}/simulate` - Run simulation for a scenario
- `GET /api/v1/scenarios/{id}/compare?ids=X,Y,Z` - Side-by-side comparison of multiple scenarios
- `GET /api/v1/scenarios/{id}/evidence-coverage` - Bright/Dim/Dark classification per element
- `GET /api/v1/scenarios/{id}/epistemic-plan` - Ranked evidence acquisition actions with confidence uplift
- `POST /api/v1/scenarios/{id}/suggestions` - (Phase 4) Request LLM-assisted modification suggestions
- `PATCH /api/v1/scenarios/{id}/suggestions/{suggestion_id}` - (Phase 4) Accept/reject/modify a suggestion

---

## 9. Security and Multi-Tenancy

- **Engagement-level data isolation**: All data scoped to engagement with row-level security
- **Authentication**: OAuth2/OIDC (consulting firm SSO integration)
- **Authorization**: Role-based access per persona type
- **Encryption**: AES-256 at rest, TLS 1.3 in transit
- **Audit logging**: Complete trail of all data access and modifications
- **Data classification**: Evidence tagged with sensitivity levels (Public, Internal, Confidential, Restricted)
- **Client data handling**: No cross-engagement data leakage; isolated processing pipelines
- **Retention policies**: Configurable per engagement with automated cleanup
- **Compliance**: SOC2 Type II, GDPR data processing agreements

---

## 10. Personas and Dashboards

| Persona | Dashboard KPIs | Access Level |
|---------|---------------|-------------|
| **Engagement Lead** | Evidence coverage %, overall confidence score, TOM alignment %, gap count by severity, team progress | Full engagement access |
| **Process Analyst** | Evidence processing status, classification accuracy, relationship mapping progress, assigned review items | Assigned processes only |
| **Subject Matter Expert** | Process elements pending review, annotation count, confidence impact of reviews | Assigned domain only |
| **Client Stakeholder** | Read-only findings view, confidence scores, gap analysis results, recommendation status | Read-only, filtered view |

---

## 11. User Flows

### Flow 1: Engagement Setup and Evidence Collection
1. Create engagement with scope (specific business area)
2. Define evidence requirements per the 12-category taxonomy
3. Generate shelf data request (structured evidence request document)
4. Deliver request to client (email/portal)
5. Client uploads evidence through intake portal
6. System auto-classifies, validates, and catalogs evidence
7. Evidence dashboard shows processing status, coverage per category, quality scores
8. Analyst reviews flagged items (low quality, unclassified, potential duplicates)

### Flow 2: Process Point of View Generation
1. Trigger POV generation for engagement scope
2. System runs evidence aggregation and entity extraction
3. System performs cross-source triangulation
4. LCD algorithm synthesizes consensus process model
5. Confidence scores assigned per element
6. Contradictions flagged with alternative views
7. BPMN process model generated with evidence citations
8. Analyst reviews, annotates, requests SME validation
9. SME reviews assigned elements, adds context
10. Model refined based on annotations

### Flow 3: TOM Alignment and Gap Analysis
1. Upload/select target operating model(s)
2. Import best practices and industry benchmarks
3. System performs automated alignment across TOM dimensions
4. Gap analysis generates findings with evidence-backed rationale
5. Recommendations prioritized by criticality x risk x cost
6. Engagement Lead reviews and curates findings
7. Generate client-ready deliverables (HTML/PDF)
8. Facilitate consulting conversation with evidence-backed POV

### Flow 4: Continuous Monitoring (Phase 3)
1. Configure monitoring agents for specific data sources
2. Agents collect evidence continuously (logs, task mining, system data)
3. Real-time deviation detection against established POV
4. Alerts generated for significant process deviations
5. Dashboard updated with live process intelligence

### Flow 5: Operating Model Scenario Analysis (Phases 3-4)
1. After POV generation and TOM gap analysis, Engagement Lead opens Scenario Workbench
2. System displays as-is process model with Bright/Dim/Dark evidence overlay
3. Consultant defines alternative scenarios using transformation templates or manual edits
4. For each scenario, system runs simulation and computes evidence confidence
5. Side-by-side comparison dashboard shows all scenarios with simulation results and evidence coverage
6. Epistemic Action Planner identifies evidence gaps that most affect the analysis
7. Consultant reviews ranked evidence acquisition actions and creates shelf data requests
8. (Phase 4) LLM suggests additional modifications for consultant review; consultant accepts, modifies, or rejects each
9. (Phase 4) Financial impact estimation added with stated assumptions and ranges
10. Engagement Lead selects preferred scenario(s) for client presentation with full evidence traceability

---

## 12. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Evidence processing accuracy | >90% correct classification | Validated against analyst review |
| POV generation time | <4 hours for typical scope | End-to-end from trigger to model |
| Confidence score correlation | >0.8 with expert assessment | Pearson correlation coefficient |
| Consultant time savings | 60-70% reduction in process discovery | Before/after engagement comparison |
| Evidence coverage per engagement | >80% of requested items received | Shelf data request fulfillment rate |
| Gap detection recall | >85% of gaps identified by experts | Compared to manual gap analysis |
| Client satisfaction | >4.5/5.0 | Post-engagement survey |
| Scenario comparison adoption | >70% of engagements use Scenario Workbench | Usage tracking per engagement |
| Evidence acquisition follow-through | >50% of epistemic planner recommendations result in shelf data requests | Shelf request creation linked to epistemic actions |
| Confidence uplift accuracy | >0.7 correlation between projected and actual confidence improvement after evidence obtained | Compare projected vs actual per epistemic action |
| Scenario evaluation speed | >50% faster than manual workshop-based scenario evaluation | Before/after engagement comparison |

---

## 13. Phased Delivery

### Phase 1 - Foundation (MVP)
- Engagement management (create, scope, team)
- Evidence ingestion pipeline (documents, structured data, BPM models: categories 1, 5, 8)
- Shelf data request workflow (compose, track, intake)
- Evidence quality scoring and validation
- Basic semantic relationship engine (Neo4j graph construction)
- Process POV generation with consensus algorithm and evidence linking
- Confidence scoring engine
- Simple HTML process flow visualization
- Evidence provenance tracking
- Engagement Lead and Process Analyst dashboards
- Security: engagement-level isolation, auth, audit logging

### Phase 2 - Intelligence
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

### Phase 3 - Scale and Autonomy
- Monitoring agent integration (log analysis, task mining)
- Continuous evidence collection
- Real-time process deviation detection
- Agentic capabilities (proactive evidence gap identification)
- Cross-engagement pattern library (with strict data isolation)
- Process simulation and what-if analysis
- SaaS connectors (Salesforce, SAP, ServiceNow)
- Client portal with interactive exploration
- API/MCP server for consulting platform integration
- Evidence coverage classification (Bright / Dim / Dark per process element)
- Scenario Comparison Workbench (define, simulate, and compare 2-5 operating model alternatives)
- Epistemic Action Planner (per-scenario evidence gap ranking with confidence uplift projection)

### Phase 4 - Reimagination
- Financial data model (cost per role, volume forecasts, technology cost assumptions)
- Financial impact estimation with ranges, assumptions, and sensitivity analysis
- Assisted Alternative Suggestion (LLM-suggested operating model modifications for consultant review)
- BPMN diff visualization (structural comparison between as-is and scenario models)
- Scenario ranking with composite scoring (evidence confidence, simulation results, financial impact)
- Engagement-level scenario history and audit trail
- Reimagination dashboard integration into Engagement Lead portal

**Phase 4 gating criteria**: Phase 3 Scenario Comparison Workbench and Epistemic Action Planner validated with real engagement data before proceeding.

---

## 14. Architecture

### System Architecture

```
+-------------------------------------------------------------------+
|                     CLIENT / PORTAL LAYER                          |
|  Next.js Frontend  |  Client Intake Portal  |  Report Viewer      |
|     (Port 3000)    |                        |                      |
+-------------------------------------------------------------------+
                              |
+-------------------------------------------------------------------+
|                     API GATEWAY (FastAPI)                           |
|                        (Port 8000)                                 |
|  Evidence API | POV API | TOM API | Graph API | Engagement API    |
|  Scenario API (Phase 3)                                            |
+-------------------------------------------------------------------+
                              |
+-------------------------------------------------------------------+
|                   PROCESSING SERVICE LAYER                         |
|                                                                    |
|  Evidence Ingestion    |  Semantic Bridge     |  Consensus         |
|  Engine                |  Engine              |  Algorithm         |
|  (format parsers,      |  (relationship       |  (triangulation,   |
|   quality scoring,     |   detection,         |   consensus,       |
|   validation)          |   entity resolution) |   model assembly)  |
|                        |                      |                    |
|  TOM Alignment         |  Gap Analysis        |  RAG Copilot       |
|  Engine                |  Engine              |  (hybrid search,   |
|  (gap scoring,         |  (graph traversal,   |   query answering, |
|   recommendations)     |   LLM rationale)     |   evidence Q&A)    |
|                        |                      |                    |
|  Scenario Engine       |  Epistemic Planner   |  Simulation        |
|  (scenario definition, |  (evidence gap       |  Engine            |
|   comparison,          |   ranking, shelf     |  (what-if,         |
|   evidence overlay)    |   data integration)  |   capacity, cost)  |
+-------------------------------------------------------------------+
                              |
+-------------------------------------------------------------------+
|                     DATA & INTELLIGENCE LAYER                      |
|                                                                    |
|  PostgreSQL 15         |  Neo4j 5.x           |  Redis 7           |
|  (pgvector)            |  (Knowledge Graph)   |  (Cache/Queue)     |
|  - Evidence store      |  - Semantic graph    |  - Session cache   |
|  - Engagement data     |  - Process models    |  - Job queue       |
|  - Vector embeddings   |  - Relationship graph|  - Rate limiting   |
+-------------------------------------------------------------------+
```

### Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | Python 3.12+ (FastAPI, SQLAlchemy 2.x, Pydantic 2.x) | API and business logic |
| **Frontend** | Next.js 14+ (React 18, BPMN.js, D3/Cytoscape) | UI and visualization |
| **Knowledge Graph** | Neo4j 5.x with APOC plugin | Semantic relationships |
| **Vector Store** | PostgreSQL 15 with pgvector | Embedding storage and similarity search |
| **Embeddings** | all-mpnet-base-v2 (768-dim) initially, Claude/OpenAI for analysis | Semantic similarity |
| **AI/ML** | Claude API | Analysis, gap rationale, RAG copilot |
| **Cache/Queue** | Redis 7 | Caching, background job queue |
| **Process Viz** | BPMN.js | Interactive process modeling |
| **Infrastructure** | Docker Compose (dev), containerized deployment (prod) | Environment management |
| **Testing** | pytest (backend), Playwright (E2E), Jest (frontend) | Quality assurance |
