# BPMN Generation Pipeline: From Evidence to Process Model

## Overview

BPMN generation runs through an **8-step consensus algorithm** (`src/pov/generator.py`). It works primarily from **PostgreSQL** (evidence items + fragments), NOT directly from Neo4j or pgvector. The knowledge graph and vector search serve parallel purposes (analytics, RAG copilot) but are decoupled from the BPMN generation pipeline.

---

## The Full Pipeline

### Phase 1: Evidence Ingestion (Prerequisite)

When you upload mortgage lending documents — SOPs, process maps, interview transcripts, system exports, task mining logs — the evidence pipeline (`src/evidence/pipeline.py`) classifies, parses, fragments, and stores them in PostgreSQL. Each fragment gets a quality score, reliability score, and freshness score. Embeddings are computed and stored via pgvector. The knowledge graph (Neo4j) is built in parallel — entities (activities, roles, systems) become nodes, relationships (FOLLOWED_BY, PERFORMED_BY, USES_SYSTEM) become edges.

But none of that *directly* produces BPMN. It's all preparation.

### Phase 2: The 8-Step Consensus Algorithm

When you trigger `POST /api/v1/pov/generate`, here's what happens:

#### Step 1 — Evidence Aggregation

**File**: `src/pov/aggregation.py`

Queries PostgreSQL for all validated evidence items scoped to this engagement. Pulls fragments.

#### Step 2 — Entity Extraction

**File**: `src/pov/extraction.py`

Processes all fragments in async batches (semaphore of 10) to extract entities — activities, decisions, roles, systems, documents. Deduplicates near-duplicates via `resolve_entities()`.

#### Step 3 — Cross-Source Triangulation

**File**: `src/pov/triangulation.py`

This is where multi-source corroboration kicks in. For each entity, it computes a triangulation score and classifies corroboration strength.

**Base Score**: `source_count / total_sources` — the raw ratio of how many evidence sources mention this entity.

**Multi-Source Bonus** (applied to the triangulation score): Rewards breadth of corroboration beyond the raw ratio:

| Sources Mentioning Entity | Bonus |
|---|---|
| 3 or more | **+0.15** |
| 2 | **+0.05** |
| 1 | +0.00 |

For example, if an entity appears in 3 out of 10 sources, the base score is 0.30, but with the multi-source bonus it becomes 0.45.

**Cross-Plane Bonus** (applied to the evidence agreement factor): If corroboration spans **2 or more evidence planes**, an additional **+0.15** is added to the agreement score. The four evidence planes are:

- **System/Behavioral** — system logs, task mining data, structured exports
- **Documented/Formal** — SOPs, policies, BPM models, process documentation
- **Observed/Field** — field observations, workshop notes, walkthroughs
- **Human Interpretation** — interviews, surveys, SME input

The rationale: an activity confirmed by both a system log (System/Behavioral) and an SOP (Documented/Formal) is stronger than one confirmed by two documents from the same plane. Different *types* of evidence agreeing is worth more than the same type agreeing multiple times. The bonuses reward **diversity of evidence**, not just volume.

**Corroboration Classification**: Based on the final triangulation score, each entity is tagged as STRONGLY, MODERATELY, or WEAKLY corroborated.

So if "Verify Income" appears in the SOP (Documented/Formal), the task mining logs (System/Behavioral), AND an interview transcript (Human Interpretation), it gets the multi-source bonus (+0.15 for 3+ sources), the cross-plane bonus (+0.15 for spanning 3 planes), and is tagged STRONGLY corroborated.

#### Step 4 — Consensus Building (Weighted Voting)

**File**: `src/pov/consensus.py`

Weighted voting by evidence type authority:

| Evidence Type | Weight |
|---|---|
| Structured data | **1.00** (highest) |
| Task mining | **0.90** |
| BPM models | **0.85** |
| Documents | **0.75** |
| Interviews | lower |

This produces a `weighted_vote_score` for each entity. It also detects **variants** — divergent process paths where evidence disagrees on the sequence.

#### Step 5 — Contradiction Resolution

**File**: `src/pov/contradiction.py`

When evidence actively conflicts (e.g., one SOP says "manager approves" and another says "system auto-approves"), conflict stubs are resolved using weighted evidence authority. The winner becomes the consensus view; the conflict is logged with resolution rationale.

#### Step 6 — Confidence Scoring

**File**: `src/pov/scoring.py`

Each element gets a composite score from 5 weighted factors:

| Factor | Weight | Description |
|---|---|---|
| Coverage | **30%** | How many sources mention it |
| Agreement | **25%** | Do sources agree on its attributes |
| Quality | **20%** | Quality scores of contributing evidence |
| Reliability | **15%** | Reliability of sources |
| Recency | **10%** | Freshness bias |

Classified as: VERY_HIGH (≥0.90), HIGH (≥0.75), MEDIUM (≥0.50), LOW (≥0.25), VERY_LOW (<0.25).

#### Step 7 — BPMN Assembly

**File**: `src/pov/assembly.py`

**This is where the XML is actually generated.** It:

1. **Filters & sorts** to ACTIVITY + DECISION entities only, sorted by confidence descending (highest-confidence activities come first in the flow)
2. **Creates BPMN elements**: activities → `<bpmn:task>`, decisions → `<bpmn:exclusiveGateway>`
3. **Adds three-dimensional confidence** to each element via `kmflow:*` extensions:
   - **Score**: 0.0–1.0
   - **Brightness**: BRIGHT (≥0.75) / DIM (≥0.40) / DARK (<0.40)
   - **Evidence Grade**: A through U (based on multi-plane corroboration)
4. **Adds evidence citations** (source count + evidence IDs)
5. **Flags DARK elements** (score < 0.40) with gap markers — process steps we think exist but don't have strong evidence for
6. **Adds variant annotations** for multi-path evidence
7. **Connects everything**: Start → Task1 → Task2 → ... → End, with condition expressions on gateway flows
8. **Adds data stores** (SYSTEM entities) and **data objects** (DOCUMENT entities)
9. **Lays out automatically** using KMFlow standards (100x80 tasks, 52px spacing, left-to-right)

#### Step 8 — Evidence Gap Detection

**File**: `src/pov/gaps.py`

Identifies single-source gaps, weak evidence areas, and missing categories. These become recommendations for where to collect more evidence.

---

## Data Store Roles

| Data Store | Used For | NOT Used For |
|---|---|---|
| **PostgreSQL** | Evidence items, fragments, the entire 8-step consensus pipeline, BPMN storage | — |
| **Neo4j** | Visualization, conformance checking, TOM gap analysis, semantic exploration | BPMN generation |
| **pgvector** | RAG copilot search, activity↔evidence semantic matching (bridge layer) | BPMN generation |

This decoupling is intentional — the consensus algorithm can generate BPMN even if the knowledge graph is still being built. Neo4j and pgvector feed *downstream* analysis (TOM alignment, gap analysis, copilot Q&A) rather than upstream generation.

---

## What Comes Out

For the mortgage lending demo, the output is a BPMN 2.0 XML where:

- **BRIGHT activities** (like "Verify Income", "Run Credit Check") are well-corroborated across multiple evidence types
- **DIM activities** have moderate evidence — maybe only from documents and one interview
- **DARK activities** are suspected process steps with thin evidence — flagged for further investigation
- **Contradictions** are logged (e.g., "Manual underwriting" vs "Automated underwriting" — resolved in favor of the higher-weight evidence source)
- **Gaps** tell you where to dig deeper ("No task mining data for the closing subprocess")

The frontend visualizes this with confidence coloring, and the TOM alignment engine (`src/tom/alignment.py`) then compares this as-is BPMN against target operating model specs to find maturity gaps.

---

## API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/pov/generate` | POST | Trigger async consensus algorithm (returns job_id) |
| `/api/v1/pov/models/{engagement_id}` | GET | Retrieve all process models for engagement |
| `/api/v1/pov/{model_id}` | GET | Get process model (includes BPMN XML) |
| `/api/v1/pov/{model_id}/bpmn` | GET | Get BPMN XML only (Content-Type: application/xml) |
| `/api/v1/pov/{model_id}/elements` | GET | Get process elements with confidence scores |
| `/api/v1/pov/{model_id}/contradictions` | GET | Get detected contradictions |
| `/api/v1/pov/{model_id}/gaps` | GET | Get evidence gaps |

### Generation Flow

```
POST /api/v1/pov/generate {engagement_id, scope}
  → Enqueues job → runs generate_pov() → persists ProcessModel with bpmn_xml
  → Poll: GET /api/v1/tasks/{job_id}
  → Complete: GET /api/v1/pov/models/{engagement_id}
```

---

## Key Source Files

| File | Purpose |
|---|---|
| `src/pov/generator.py` | Main orchestrator (8-step pipeline) |
| `src/pov/aggregation.py` | Step 1: Evidence collection |
| `src/pov/extraction.py` | Step 2: Entity extraction |
| `src/pov/triangulation.py` | Step 3: Cross-source scoring |
| `src/pov/consensus.py` | Step 4: Weighted voting consensus |
| `src/pov/contradiction.py` | Step 5: Conflict resolution |
| `src/pov/scoring.py` | Step 6: Confidence scoring |
| `src/pov/assembly.py` | Step 7: BPMN XML generation |
| `src/pov/gaps.py` | Step 8: Gap detection |
| `src/pov/constants.py` | Weights, thresholds, evidence planes |
| `src/pov/bpmn_generator.py` | Low-level BPMN XML utility |
| `src/api/routes/pov.py` | API endpoints |
| `src/semantic/graph.py` | Neo4j service (parallel, not for BPMN) |
| `src/semantic/builder.py` | Knowledge graph construction |
| `src/tom/alignment.py` | TOM gap analysis (post-BPMN) |
| `src/rag/retrieval.py` | Vector search (RAG copilot) |
