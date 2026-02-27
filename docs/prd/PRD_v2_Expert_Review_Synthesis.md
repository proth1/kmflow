# PRD v2.0.0 Expert Review Synthesis

**Date**: 2026-02-27
**Reviewers**: 10 expert perspectives (Enterprise Architect, Data Engineer, Security Specialist, KM/Ontology Expert, Process Mining Specialist, UX/Product Designer, Consulting Domain Expert, AI/ML Engineer, QA/Testability Lead, Regulatory/Compliance Officer)
**PRD Version Reviewed**: 2.0.0 (2026-02-26)

---

## Executive Summary

The PRD v2.0.0 demonstrates strong intellectual depth in its domain modeling — the evidence taxonomy, controlled edge vocabulary, epistemic frames, and three-dimensional confidence model are genuinely innovative and differentiated. However, the 10-perspective review surfaced **47 critical/high findings** across a consistent set of themes. The PRD excels at describing *what* the system should do but systematically underspecifies *how* it verifies correctness, *how* it handles failure, *how* it governs its own data processing, and *how* it maps to the operational reality of consulting delivery.

**Overarching assessment** (paraphrased from multiple reviewers):
- Enterprise Architect: *"The architectural specification does not match the complexity of the system being described."*
- Consulting Expert: *"The PRD reads more like a computer science research proposal than a consulting platform specification."*
- Process Mining Specialist: *"Without process structure discovery, KMFlow generates entity inventories, not process models."*
- Regulatory Officer: *"The platform applies its governance model only outward (analyzing clients' processes) and not inward (governing the platform's own data processing)."*
- QA Lead: *"The PRD tells you what the system should do but rarely tells you how to verify that it did it."*

---

## Consensus Themes (Raised by 3+ Experts)

### Theme 1: Controlled Edge Vocabulary is Triple-Divergent
**Raised by**: Data Engineer, KM/Ontology Expert, Process Mining Specialist

The PRD defines 12 controlled edge types (Section 6.2). The implemented ontology YAML has 16 different types. Section 7.2 mixes both sets. Only `GOVERNED_BY` and `CONTRADICTS` appear in all three. Near-synonym pairs (`PRECEDES`/`FOLLOWED_BY`, `PERFORMED_BY`/`OWNED_BY`, `DEPENDS_ON`/`REQUIRES`, `EVIDENCED_BY`/`SUPPORTED_BY`) violate the controlled vocabulary principle. Node types `DataObject` and `Assertion` referenced by edge constraints do not exist.

**Consensus recommendation**: Reconcile into a single authoritative vocabulary. Eliminate near-synonyms. Add missing node types. Make `kmflow_ontology.yaml` the single source of truth.

### Theme 2: Five Core Entities Have Zero Implementation
**Raised by**: Data Engineer, KM/Ontology Expert, QA Lead, AI/ML Engineer

`SurveyClaim`, `EpistemicFrame`, `ConflictObject`, `SeedTerm`, and `CanonicalActivityEvent` — all specified in Section 7.1 and referenced extensively throughout the PRD — have no SQLAlchemy models, no Pydantic schemas, no Neo4j node types in the ontology. Phase 1 mandates "FORMALIZE (schema + data model)" for these, but they do not exist.

**Consensus recommendation**: Create the data models as Phase 1 priority. These are prerequisites for Phase 2 capabilities (survey bot, seed list pipeline, consistency checks).

### Theme 3: Three-Dimensional Confidence Model Has Structural Problems
**Raised by**: UX Designer, KM/Ontology Expert, QA Lead, AI/ML Engineer

Four distinct issues identified:
1. **Brightness is not independent** — it's a derived threshold of the confidence score, not a true dimension (KM/Ontology, QA)
2. **Formula conflates evidence quality with coverage** — a single pristine source scores high on quality but low on coverage; many weak sources score high on coverage but low on quality. No separation of concerns (AI/ML)
3. **Contradictory states possible** — Bright (0.85) + Grade D (single-source, unvalidated) sends conflicting signals with no resolution rule (KM/Ontology, QA)
4. **Only 1 of 3 dimensions implemented** — brightness and evidence grade computation don't exist in code (QA)

**Consensus recommendation**: Restructure as a two-dimensional model (continuous score + evidence grade). Brightness becomes a visualization convenience. Add coherence constraint: Grade D caps brightness at Dim. Define `evidence_coverage` normalization denominator.

### Theme 4: Consent Architecture Wrongly Scoped and Deferred
**Raised by**: Security Specialist, Regulatory Officer, QA Lead

Section 9 defers consent to "Phase 3+, contingent on endpoint capture adoption." But Phase 1 already processes personal data across evidence ingestion, survey claims, and LLM API calls. GDPR Article 6 requires a documented lawful basis for every processing activity. The current framing treats consent as relevant only to desktop monitoring.

**Consensus recommendation**: Decouple consent from endpoint capture. Add a "Lawful Basis Framework" mapping each processing activity to its GDPR Article 6 basis. Move core consent verification to Phase 1.

### Theme 5: No Threat Model or Security Architecture
**Raised by**: Security Specialist, Enterprise Architect, Regulatory Officer

Section 9 lists security controls but never documents the threats they mitigate. No trust boundaries, no threat actors, no attack surface enumeration, no LLM-specific threats (prompt injection, data leakage). The raw Cypher query endpoint (Section 8.5) exposes database-level query language to authenticated users — an injection risk surface for a platform targeting regulated industries.

**Consensus recommendation**: Add a threat model section. Remove or restrict the Cypher query endpoint. Document trust boundaries between the client portal, API gateway, processing services, data layer, and external services.

### Theme 6: Multi-Tenancy Claims Exceed Implementation
**Raised by**: Enterprise Architect, Security Specialist, Data Engineer

Section 9 claims "row-level security" but the implementation uses only application-layer `WHERE engagement_id = X` filtering. No PostgreSQL RLS policies exist. A single missing filter clause in any route handler would expose cross-engagement data. Neo4j has no database-level isolation either.

**Consensus recommendation**: Change PRD language to "application-layer engagement scoping." Add PostgreSQL RLS as a Phase 1 requirement. Add mandatory cross-engagement isolation integration tests.

### Theme 7: No Async Processing for Long-Running Operations
**Raised by**: Enterprise Architect, UX Designer, AI/ML Engineer

POV generation takes "<4 hours" but the API is synchronous (`POST /api/v1/pov/generate`). Evidence ingestion runs inline within a single HTTP request. No task queue architecture. Users have no visibility into progress during multi-hour operations.

**Consensus recommendation**: Define an async task pattern (`202 Accepted` + task ID + polling/WebSocket). Specify which operations are sync vs async. Leverage existing Redis Streams infrastructure.

### Theme 8: BPMN Assembly Lacks Process Discovery
**Raised by**: Process Mining Specialist (critical), AI/ML Engineer (supporting)

The LCD algorithm extracts entities and counts how many sources mention each one, but never reconstructs the behavioral relationships between them. BPMN assembly sorts activities by confidence score (not temporal sequence) and connects them in a linear chain. No parallelism, branching, loops, or gateway logic. No process discovery algorithm (Alpha Miner, Heuristic Miner, etc.) exists.

**Consensus recommendation**: Add a "Process Structure Discovery" step that builds a directed graph from `PRECEDES` edges, identifies split/join patterns, and validates BPMN structural soundness. Activity ordering must derive from evidence, not confidence scores.

### Theme 9: Shelf Data Workflow Underestimates Client Friction
**Raised by**: Consulting Expert, UX Designer

Real shelf data request fulfillment is 25-40% after first submission, not 80%. Clients send evidence via email/Slack/shared drives (not portals), provide wrong formats, delegate to wrong people. The PRD models requests at request-level status but needs item-level tracking. Missing states: `PARTIAL_RESPONSE`, `WRONG_FORMAT_RECEIVED`, `ESCALATED`, `CLIENT_PUSH_BACK`.

**Consensus recommendation**: Add item-level tracking within requests. Add follow-up automation. Add evidence substitution concept. Revise 80% target to include intermediate milestones.

### Theme 10: Client Stakeholder Experience Undefined
**Raised by**: UX Designer, Consulting Expert

The Client Stakeholder persona has "Read-only, filtered view" but no dedicated user flow, no upload experience specification, no progress tracking. Clients are active co-authors of findings in consulting engagements, not passive consumers. No empty states, error states, or onboarding defined for any persona.

**Consensus recommendation**: Add a client evidence submission user flow. Define empty states for every dashboard. Add a "co-creation" access tier between read-only and full access.

### Theme 11: Cross-Border Data Transfer and GDPR Gaps
**Raised by**: Regulatory Officer, Security Specialist

EU evidence sent to US-based LLM providers (Anthropic, OpenAI) with no Transfer Impact Assessment, no SCCs, no data residency controls. GDPR data subject rights (Articles 15-22) not specified. Erasure requests accepted but never executed (confirmed by D2 audit). No incident response or breach notification procedure.

**Consensus recommendation**: Add cross-border data transfer controls. Specify GDPR data subject rights as Phase 1 requirements. Define incident response procedure with 72-hour notification timeline.

### Theme 12: Success Metrics Unmeasurable
**Raised by**: QA Lead, Consulting Expert

Four metrics require baselines the platform cannot collect (time savings, scenario speed, client satisfaction, confidence correlation). No reference engagement or ground-truth corpus defined for measuring recall/precision. "Typical scope" undefined for the 4-hour POV target.

**Consensus recommendation**: Define in-platform measurement instruments or reclassify as business hypotheses. Create a reference engagement with ground-truth labels. Define "typical scope" quantitatively.

### Theme 13: Dual-Write PostgreSQL/Neo4j Consistency
**Raised by**: Data Engineer, Enterprise Architect

Many entities exist in both stores with no defined consistency model. No specification of which store is authoritative, how writes are coordinated, or what happens on partial failure. GDPR erasure must cascade across PostgreSQL, Neo4j, and pgvector.

**Consensus recommendation**: Define PostgreSQL as system of record. Neo4j as derived projection. Write-to-PG-first with async projection to Neo4j. Add reconciliation job and cascade rules for GDPR erasure.

---

## Severity Summary

| Severity | Count | Key Areas |
|----------|-------|-----------|
| Critical | 18 | Edge vocabulary divergence, missing entities, consent deferral, BPMN assembly, security gaps, cross-border transfers |
| High | 29 | Confidence model problems, multi-tenancy, async processing, performance criteria, schema evolution, knowledge reuse |
| Medium | 6 | Simulation foundations, seed list/ontology conflation, accessibility, competitive positioning |

---

## Top 10 PRD Changes (Ranked by Consensus + Impact)

1. **Reconcile controlled edge vocabulary** — single authoritative set in ontology YAML, referenced by PRD
2. **Add Process Structure Discovery step** to Section 6.3 — evidence-derived process ordering, not confidence-ranked lists
3. **Restructure confidence model** — 2D (score + grade) with brightness as visualization; add coherence constraints
4. **Add Security Architecture section** — threat model, trust boundaries, secrets management, restrict Cypher endpoint
5. **Move consent/GDPR to Phase 1** — lawful basis framework, data subject rights, incident response
6. **Add cross-store consistency model** — PG as system of record, async Neo4j projection, cascade rules
7. **Define async task architecture** — for POV generation, evidence ingestion, simulation
8. **Expand shelf data workflow** — item-level tracking, follow-up automation, realistic milestones
9. **Add acceptance criteria** — Given/When/Then for each capability section (6.1-6.12)
10. **Define performance test criteria** — per-operation targets, "typical scope" definition, load profiles

---

## Dissenting Views (Resolved)

- **LCD terminology**: Process Mining Specialist recommended renaming "LCD" to "Evidence-Weighted Consensus" since the algorithm is permissive (includes anything mentioned), not conservative (only what everyone agrees on). **Resolution**: Keep "LCD" as David's brand term but add inline clarification throughout the PRD that the algorithm is evidence-weighted and inclusive, not limited to universal agreement. The term traces to David's original call (speech-to-text captured "least competent nominator"); the meaning is now explicit.
- **Monolith vs microservices**: Enterprise Architect recommends documenting the current state as a "modular monolith" with decomposition roadmap. **Resolution**: Applied in Section 14 — architecture diagram described as logical service boundaries, not deployment units.
- **Open/Closed World Assumption**: KM/Ontology Expert recommended OWA by default with CWA for specific queries. **Resolution**: Applied in Section 6.2 — OWA default (consistent with evidence-first philosophy and brightness model), CWA only for Control Gap detection against specific regulatory frameworks.

---

## Next Steps

1. ~~Apply the Top 10 PRD changes to `docs/prd/PRD_KMFlow_Platform.md` → version 2.1.0~~ ✓ Done
2. ~~Resolve LCD terminology and OWA/CWA decisions~~ ✓ Resolved in PRD v2.1.0
3. Decompose revised PRD into GitHub Issues backlog
