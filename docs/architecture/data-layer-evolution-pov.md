# KMFlow Data Layer Evolution: Architecture Point of View

**Status**: In Progress (Phase A complete, Phases B–F planned)
**Date**: 2026-02-17
**Author**: KMFlow Engineering
**Audience**: Internal engineering team

---

## Table of Contents

1. [Current State Assessment](#1-current-state-assessment)
2. [Target State: Medallion Architecture](#2-target-state-medallion-architecture)
3. [Architecture Decision Records](#3-architecture-decision-records)
4. [Medallion Layer Schemas](#4-medallion-layer-schemas)
5. [Data Governance Framework Design](#5-data-governance-framework-design)
6. [Databricks Upgrade Path](#6-databricks-upgrade-path)
7. [Phased Roadmap](#7-phased-roadmap)
8. [Key File References](#8-key-file-references)

---

## 1. Current State Assessment

### 1.1 Data Stores

KMFlow currently uses three data stores, each serving distinct but sometimes overlapping purposes.

#### PostgreSQL 15 + pgvector

The transactional spine of the platform. Managed via SQLAlchemy 2.x async ORM (`src/core/database.py`, `src/core/models.py`) with 14 Alembic migrations (`alembic/versions/001` through `014`). As of Phase 8 there are 31 mapped ORM classes across the following logical groupings:

| Group | Models |
|---|---|
| Core engagement | `Engagement`, `EngagementMember`, `User` |
| Evidence | `EvidenceItem`, `EvidenceFragment`, `EvidenceLineage` (Phase A) |
| Process POV | `ProcessModel`, `ProcessElement`, `Contradiction`, `EvidenceGap` |
| Regulatory | `Policy`, `Control`, `Regulation` |
| TOM | `TargetOperatingModel`, `GapAnalysisResult`, `BestPractice`, `Benchmark` |
| Monitoring | `ProcessBaseline`, `MonitoringJob`, `ProcessDeviation`, `MonitoringAlert` |
| Integration | `IntegrationConnection` |
| Patterns | `PatternLibraryEntry`, `PatternAccessRule` |
| Simulation | `SimulationScenario`, `SimulationResult` |
| Compliance | `ReferenceProcessModel`, `ConformanceResult` |
| Copilot | `CopilotMessage` |
| MCP | `MCPAPIKey` |
| Success tracking | `SuccessMetric`, `MetricReading`, `Annotation` |
| Governance (Phase A) | `DataCatalogEntry` |
| Audit | `AuditLog`, `ShelfDataRequest`, `ShelfDataRequestItem` |

Fragment embeddings use pgvector: `EvidenceFragment.embedding` is a `Vector(768)` column. The embedding model is `all-mpnet-base-v2` (768-dim), configurable via `Settings.embedding_model` and `Settings.embedding_dimension`.

#### Neo4j 5.x

The knowledge graph that links extracted entities across evidence. `KnowledgeGraphService` in `src/semantic/graph.py` provides the Neo4j interface. The graph has:

- **13 node types**: `Activity`, `Decision`, `Role`, `System`, `Evidence`, `Document`, `Process`, `Subprocess`, `Policy`, `Control`, `Regulation`, `TOM`, `Gap`
- **12 relationship types**: `SUPPORTED_BY`, `GOVERNED_BY`, `DEVIATES_FROM`, `IMPLEMENTS`, `CONTRADICTS`, `MITIGATES`, `REQUIRES`, `FOLLOWED_BY`, `OWNED_BY`, `USES`, `CO_OCCURS_WITH`, `SIMILAR_TO`

Until Phase A, these were hardcoded as `frozenset` constants directly in `graph.py` and `builder.py`. They are now loaded from `src/semantic/ontology/kmflow_ontology.yaml` via the loader in `src/semantic/ontology/loader.py`. The module-level constants in `graph.py` are kept for backward compatibility but delegate to the loader at import time.

#### Redis 7

Used for session caching, rate limiting (`src/core/rate_limiter.py`), and the monitoring event stream (`monitoring_stream_max_len = 10000`). Connection is managed via `src/core/redis.py`.

#### Local Filesystem

Evidence files are stored under `evidence_store/{engagement_id}/` by the `store_file()` function in `src/evidence/pipeline.py`. The default base path is `DEFAULT_EVIDENCE_STORE = "evidence_store"`. There is no versioning, no lineage link from filesystem path back to source system, and no audit trail for file mutations beyond the `AuditLog` table entry at upload time.

### 1.2 Current Pipeline Flow

The evidence ingestion path in `src/evidence/pipeline.py` (`ingest_evidence()`) follows this sequence:

```
File bytes
  → compute_content_hash()          # SHA-256, dedup check
  → classify_by_extension()         # EvidenceCategory auto-detection
  → store_file()                     # Write to evidence_store/{engagement_id}/
  → EvidenceItem (Postgres)         # ORM record created
  → process_evidence()              # Parser invoked, EvidenceFragment records created
  → run_intelligence_pipeline()
      → extract_fragment_entities() # entity_extraction.py
      → build_fragment_graph()      # Neo4j node + CO_OCCURS_WITH edges
      → generate_fragment_embeddings() # pgvector storage
      → run_semantic_bridges()      # SUPPORTED_BY, GOVERNED_BY, DEVIATES_FROM, etc.
  → AuditLog entry
```

### 1.3 Identified Gaps

| Gap | Description | Fixed In |
|---|---|---|
| G1: Code-only ontology | Node/relationship types were `frozenset` constants with no schema document | Phase A (done) |
| G2: No evidence lineage | `file_path` stores a relative local path; no record of source system, transformation history, or version chain | Phase B/C |
| G3: No data governance | No data catalog, no classification enforcement, no retention policy engine beyond per-engagement `retention_days` | Phase D |
| G4: No medallion layers | Raw bytes and parsed fragments are stored without clear layer separation; no Bronze/Silver/Gold distinction | Phase B/C |
| G5: No Databricks path | `store_file()` is hardcoded to local filesystem; no abstraction to allow backend substitution | Phase B |

The `EvidenceItem` model already has placeholder fields added in Phase A for lineage integration: `source_system`, `delta_path`, and `lineage_id`. The `EvidenceLineage` and `DataCatalogEntry` models are defined in `src/core/models.py` but not yet wired into the ingestion pipeline.

---

## 2. Target State: Medallion Architecture

### 2.1 Overview

The target architecture adds a Delta Lake medallion layer alongside (not replacing) the existing PostgreSQL and Neo4j stores. Each store keeps its primary responsibility:

```
┌─────────────────────────────────────────────────────────────────┐
│                        KMFlow Data Layer                         │
├──────────────────┬──────────────────┬────────────────────────────┤
│  Delta Lake      │  PostgreSQL 15   │  Neo4j 5.x                 │
│  (medallion)     │  (transactional) │  (knowledge graph)         │
│                  │                  │                             │
│  Bronze          │  engagements     │  Activity, Role, System...  │
│  └─ raw files    │  evidence_items  │  SUPPORTED_BY, FOLLOWED_BY  │
│  └─ metadata     │  evidence_frags  │  ...12 relationship types   │
│                  │  (+ 28 tables)   │                             │
│  Silver          │                  │                             │
│  └─ parsed frags │  ← fragments     │  ← graph nodes              │
│  └─ entities     │    written here  │    created from Silver       │
│  └─ quality      │                  │                             │
│                  │                  │                             │
│  Gold            │                  │                             │
│  └─ lineage      │  ← lineage_id    │                             │
│  └─ patterns     │    FK to PG      │                             │
│  └─ snapshots    │                  │                             │
└──────────────────┴──────────────────┴────────────────────────────┘
           │
    StorageBackend
    Protocol (ADR-003)
           │
  ┌────────┴────────┐
  │                 │
  Local FS      DeltaLake     (future: Databricks)
  Backend       Backend
```

PostgreSQL remains the system of record for all transactional data. Delta Lake provides the immutable, versioned evidence store with ACID transactions and time travel. Neo4j continues to serve graph traversal and semantic bridging.

### 2.2 Bronze Layer: Immutable Landing Zone

Raw evidence files land here unchanged. Nothing in Bronze is ever modified after initial write — this is the audit-proof record of what the client delivered.

Every write to Bronze produces a Delta table entry with the raw bytes path, content hash, ingestion timestamp, and source provenance metadata. The `EvidenceItem.delta_path` field (already on the model) points to the Bronze Delta table path for a given evidence item.

### 2.3 Silver Layer: Parsed and Quality-Scored Records

Parsed fragments, extracted entities, and quality scores live here. Silver is derived from Bronze via the existing intelligence pipeline steps. Silver records are recomputable from Bronze — if a parser is updated, we can re-process Bronze records to produce a new Silver version.

The key addition: Silver Delta tables expose time travel. If the `document_parser.py` or `bpmn_parser.py` is updated, we can `RESTORE` to a previous Silver checkpoint or compare Silver versions to understand what changed.

### 2.4 Gold Layer: Analytical and Cross-Engagement Aggregates

Gold is the consumption layer for dashboards, gap analysis, and pattern discovery. Gold tables are:

- Evidence lineage chains (full provenance from raw file to graph node)
- Quality score history (trend data per engagement, per evidence item)
- Cross-engagement patterns (anonymized, aggregated from `PatternLibraryEntry`)
- Governance snapshots (point-in-time catalog exports for client delivery)

Gold tables are written by scheduled jobs, not by the real-time ingestion path.

---

## 3. Architecture Decision Records

### ADR-001: YAML Ontology Schema (not OWL/RDF)

**Status**: Implemented (Phase A)

**Context**: The knowledge graph had 13 node types and 12 relationship types hardcoded as `frozenset` constants in `src/semantic/graph.py` and `src/semantic/builder.py`. Any change required modifying Python source. There was no schema document, no validation tool, and no way for a non-engineer to inspect or extend the ontology.

**Decision**: Define the ontology as a YAML file at `src/semantic/ontology/kmflow_ontology.yaml`, loaded by a Python module at `src/semantic/ontology/loader.py`.

**Rationale**:

OWL/RDF was considered and rejected. The domain has 13 entities — OWL's expressiveness (class hierarchies, property restrictions, reasoner support) is not needed here and would add substantial tooling complexity. YAML gives us:

- Human-readable schema checked into version control
- Direct Python consumption via `yaml.safe_load()` with `functools.cache` for zero-overhead repeated access
- A validation CLI (`src/semantic/ontology/validate.py`) for CI integration
- A clear upgrade path: if we ever need OWL, the YAML is the source of truth to translate from

The loader provides six typed accessor functions that replace the hardcoded constants:

```python
get_valid_node_labels()        -> frozenset[str]
get_valid_relationship_types() -> frozenset[str]
get_extractable_types()        -> dict[str, str]   # entity_type -> Neo4j label
get_entity_type_to_label()     -> dict[str, str]   # alias for get_extractable_types
get_node_type_definition()     -> dict | None
get_relationship_definition()  -> dict | None
```

**Consequences**: Any new node type or relationship type is added to the YAML, not to Python code. The `validate.py` CLI can be run in CI to catch schema errors before deployment.

---

### ADR-002: delta-rs for Delta Lake (not PySpark)

**Status**: Planned (Phase B)

**Context**: We need Delta Lake for evidence versioning, lineage, and the upgrade path to Databricks. The standard Delta Lake implementation requires PySpark and a JVM.

**Decision**: Use the `deltalake` Python package (delta-rs), which implements Delta Lake in Rust with Python bindings. No JVM, no Spark cluster.

**Rationale**:

| Criterion | PySpark Delta | delta-rs |
|---|---|---|
| JVM dependency | Yes (heavy) | No |
| Python-native | No | Yes |
| ACID transactions | Yes | Yes |
| Time travel | Yes | Yes |
| Schema evolution | Yes | Yes |
| Databricks compatibility | Native | Same Delta format |
| Local dev experience | Poor (cluster overhead) | Fast |
| Cloud storage (S3/ADLS) | Yes | Yes |

The Delta format itself is the same regardless of compute engine. A table written by delta-rs can be read by Databricks. The upgrade path (ADR-006 coverage) is: swap out delta-rs calls for Databricks runtime calls; the table files are portable.

**Consequences**: `deltalake` must be added to `pyproject.toml`. The `StorageBackend` protocol (ADR-003) insulates the rest of the codebase from the specific library.

---

### ADR-003: StorageBackend Protocol for Evidence Pipeline

**Status**: Planned (Phase B)

**Context**: `store_file()` in `src/evidence/pipeline.py` writes directly to the local filesystem. The path is returned as a plain string stored in `EvidenceItem.file_path`. There is no abstraction; the pipeline is coupled to local storage.

**Decision**: Introduce a Python `Protocol` class `StorageBackend` with a defined interface, and two initial implementations: `LocalFilesystemBackend` (wrapping current behavior) and `DeltaLakeBackend`.

```python
# src/evidence/storage.py (planned)
from typing import Protocol, runtime_checkable

@runtime_checkable
class StorageBackend(Protocol):
    async def store(
        self,
        content: bytes,
        file_name: str,
        engagement_id: str,
        metadata: dict,
    ) -> StorageResult:
        """Store raw evidence bytes and return location metadata."""
        ...

    async def retrieve(self, path: str) -> bytes:
        """Retrieve raw bytes by storage path."""
        ...

    async def exists(self, path: str) -> bool:
        """Check if a path exists in the backend."""
        ...
```

`StorageResult` will carry the storage path, Delta table path (if applicable), and version number. `ingest_evidence()` in `pipeline.py` will accept a `StorageBackend` instance and call `backend.store()` instead of `store_file()`.

Backend selection is configuration-driven:

```python
# Settings.storage_backend: "local" | "delta"
# DI at startup in src/api/main.py app lifespan
```

**Rationale**: Dependency inversion. The pipeline logic (hash, classify, parse, fragment, embed) does not care where bytes land. Separating storage from processing allows us to test the pipeline with a mock backend, swap to Delta Lake in Phase B, and swap to Databricks in Phase F without touching any parsing or intelligence code.

**Consequences**: `store_file()` becomes an implementation detail of `LocalFilesystemBackend`. The `EvidenceItem.file_path` field semantics expand: for the local backend it remains a relative path; for the Delta backend it will be a Delta table path. `EvidenceItem.delta_path` (already on the model) captures the Delta-specific path explicitly.

---

### ADR-004: Governance as a Separable Module

**Status**: Planned (Phase D)

**Context**: KMFlow is a consulting tool. Clients receiving engagement outputs also need data governance for the processes and evidence we analyze. Data governance cannot be an internal-only capability; it needs to be exportable.

**Decision**: Create `src/governance/` as a standalone module with YAML-driven policies, a policy engine, and an export function that bundles the data catalog, lineage records, and policies into a self-contained package deliverable to clients.

**Rationale**: The `DataCatalogEntry` and `EvidenceLineage` models (already in `src/core/models.py`) are designed to be portable — `DataCatalogEntry.engagement_id` is nullable so platform-level catalog entries can exist without an engagement scope. The governance export aligns with the consulting value proposition: we leave clients with documented data governance, not just a report.

**Consequences**: `src/governance/` will have no dependencies on FastAPI routes or database sessions beyond what it receives via injection. The export function produces a zip archive containing JSON catalog, lineage graph, and policy YAML — importable into a client's own governance tooling.

---

## 4. Medallion Layer Schemas

These schemas describe Delta Lake tables. All tables use `engagement_id` as a partition column for isolation and query efficiency.

### 4.1 Bronze Layer

**Table: `bronze_evidence_raw`**

| Column | Type | Notes |
|---|---|---|
| `bronze_id` | string (UUID) | Delta table primary key |
| `engagement_id` | string (UUID) | Partition column |
| `evidence_item_id` | string (UUID) | FK to PostgreSQL `evidence_items.id` |
| `file_name` | string | Original filename |
| `content_hash` | string | SHA-256 hex, 64 chars |
| `file_bytes_path` | string | Path to raw file (local or object store) |
| `mime_type` | string | MIME type |
| `size_bytes` | long | |
| `category` | string | `EvidenceCategory` enum value |
| `source_system` | string | Origin system (e.g., `"salesforce"`, `"upload"`) |
| `source_url` | string | nullable |
| `source_identifier` | string | External ID in source system, nullable |
| `ingested_at` | timestamp | Ingestion wall-clock time |
| `ingested_by` | string | User ID or `"system"` |
| `metadata_json` | string | JSON blob of additional metadata |

**Invariant**: Bronze rows are append-only. No updates, no deletes. Re-ingestion of the same file (detected by `content_hash`) creates a new Bronze row with a different `bronze_id` but the same `evidence_item_id` pointing to the deduplicated PostgreSQL record.

---

**Table: `bronze_ingestion_log`**

| Column | Type | Notes |
|---|---|---|
| `log_id` | string (UUID) | |
| `engagement_id` | string (UUID) | Partition column |
| `bronze_id` | string (UUID) | FK to `bronze_evidence_raw` |
| `pipeline_version` | string | e.g., `"1.3.2"` |
| `status` | string | `"success"` / `"failed"` |
| `error_message` | string | nullable |
| `duration_ms` | long | Wall clock ingestion time |
| `logged_at` | timestamp | |

---

### 4.2 Silver Layer

**Table: `silver_evidence_fragments`**

| Column | Type | Notes |
|---|---|---|
| `silver_id` | string (UUID) | |
| `bronze_id` | string (UUID) | Source Bronze row |
| `fragment_id` | string (UUID) | FK to PostgreSQL `evidence_fragments.id` |
| `engagement_id` | string (UUID) | Partition column |
| `evidence_item_id` | string (UUID) | |
| `fragment_type` | string | `FragmentType` enum: `text`, `table`, `image`, `entity`, `relationship`, `process_element` |
| `content` | string | Fragment text content |
| `char_count` | long | |
| `parser_name` | string | e.g., `"document_parser"`, `"bpmn_parser"` |
| `parser_version` | string | |
| `quality_score` | double | 0.0–1.0 composite |
| `completeness_score` | double | |
| `reliability_score` | double | |
| `metadata_json` | string | JSON with entities, entity_count, etc. |
| `processed_at` | timestamp | |

---

**Table: `silver_extracted_entities`**

| Column | Type | Notes |
|---|---|---|
| `entity_silver_id` | string (UUID) | |
| `fragment_silver_id` | string (UUID) | FK to `silver_evidence_fragments` |
| `engagement_id` | string (UUID) | Partition column |
| `entity_id` | string | Entity ID from `extract_entities()` |
| `entity_type` | string | `EntityType` enum value |
| `entity_name` | string | |
| `confidence` | double | |
| `neo4j_node_id` | string | Node ID in Neo4j after graph write, nullable |
| `extracted_at` | timestamp | |

---

**Table: `silver_quality_events`**

| Column | Type | Notes |
|---|---|---|
| `quality_event_id` | string (UUID) | |
| `engagement_id` | string (UUID) | Partition column |
| `evidence_item_id` | string (UUID) | |
| `completeness_score` | double | |
| `reliability_score` | double | |
| `freshness_score` | double | |
| `consistency_score` | double | |
| `composite_score` | double | Average of four dimensions |
| `computed_at` | timestamp | |
| `pipeline_version` | string | |

Quality score history is append-only. The current score lives on `EvidenceItem` in PostgreSQL; Silver preserves the history for trend analysis.

---

### 4.3 Gold Layer

**Table: `gold_evidence_lineage_chains`**

| Column | Type | Notes |
|---|---|---|
| `chain_id` | string (UUID) | |
| `engagement_id` | string (UUID) | Partition column |
| `evidence_item_id` | string (UUID) | FK to PostgreSQL |
| `lineage_id` | string (UUID) | FK to `evidence_lineage` in PostgreSQL |
| `source_system` | string | |
| `source_url` | string | nullable |
| `bronze_id` | string (UUID) | Entry point in Bronze |
| `silver_fragment_count` | long | Number of Silver fragments |
| `neo4j_node_count` | long | Graph nodes created |
| `transformation_chain` | string | JSON array of transformation steps |
| `version` | long | Lineage version (maps to `EvidenceLineage.version`) |
| `version_hash` | string | SHA-256 of content at this version |
| `materialized_at` | timestamp | When this Gold row was written |

---

**Table: `gold_cross_engagement_patterns`**

| Column | Type | Notes |
|---|---|---|
| `pattern_id` | string (UUID) | FK to PostgreSQL `pattern_library_entries.id` |
| `category` | string | `PatternCategory` enum |
| `industry` | string | nullable |
| `engagement_count` | long | Number of engagements contributing |
| `anonymized_data` | string | JSON, client-identifying fields stripped |
| `effectiveness_score` | double | |
| `last_updated` | timestamp | |

---

**Table: `gold_governance_snapshots`**

| Column | Type | Notes |
|---|---|---|
| `snapshot_id` | string (UUID) | |
| `engagement_id` | string (UUID) | Partition column |
| `snapshot_type` | string | `"catalog"` / `"lineage"` / `"policy"` / `"full"` |
| `catalog_json` | string | Serialized `DataCatalogEntry` records |
| `lineage_json` | string | Serialized `EvidenceLineage` records |
| `policy_yaml` | string | Exported policy YAML |
| `row_count` | long | Rows covered in snapshot |
| `snapshotted_at` | timestamp | |
| `exported_by` | string | User ID |

---

## 5. Data Governance Framework Design

### 5.1 Data Catalog

The `DataCatalogEntry` model in `src/core/models.py` provides the PostgreSQL-side catalog. Key fields:

- `layer`: `DataLayer` enum — `BRONZE`, `SILVER`, `GOLD`
- `classification`: `DataClassification` enum — `PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `RESTRICTED`
- `quality_sla`: JSON blob defining expected quality thresholds per dimension
- `delta_table_path`: Path to the Delta table this catalog entry describes
- `retention_days`: Per-dataset retention (complements the per-engagement `retention_days` on `Engagement`)

The planned `src/governance/` module will provide:

```python
class DataCatalogService:
    async def register_dataset(self, ...) -> DataCatalogEntry: ...
    async def get_catalog(self, engagement_id: UUID | None) -> list[DataCatalogEntry]: ...
    async def classify_dataset(self, dataset_id: UUID, classification: DataClassification) -> None: ...
    async def export_catalog(self, engagement_id: UUID) -> dict: ...
```

### 5.2 Lineage Tracking

The `EvidenceLineage` model captures:

- `source_system`: Where the evidence originated (e.g., `"salesforce"`, `"sharepoint"`, `"direct_upload"`)
- `source_url`: The exact URL or path in the source system
- `source_identifier`: The external record ID (e.g., Salesforce document ID)
- `transformation_chain`: JSON array of transformation steps from raw to current state — each step records the transformer name, version, and timestamp
- `version` and `parent_version_id`: Enables a version chain. Re-processing Bronze creates a new `EvidenceLineage` row with incremented `version` and `parent_version_id` pointing to the previous record
- `refresh_schedule`: Cron expression for incremental refresh from source system

The `EvidenceItem.lineage_id` field (added in Phase A, nullable) will be populated by the Phase B pipeline. The FK relationship:

```
EvidenceItem (1) ──► (many) EvidenceLineage
                             └─ self-referential via parent_version_id for version chain
```

### 5.3 Policy Engine

The governance policy engine will be YAML-driven, analogous to the ontology pattern established in Phase A:

```yaml
# src/governance/policies/default.yaml
policies:
  evidence_retention:
    rule: "evidence_items older than {retention_days} days must be archived"
    applies_to: [BRONZE, SILVER]
    enforcement: "advisory"  # advisory | blocking

  classification_required:
    rule: "all GOLD datasets must have a DataClassification other than PUBLIC"
    applies_to: [GOLD]
    enforcement: "blocking"

  lineage_completeness:
    rule: "evidence_items with source_system != 'direct_upload' must have a lineage record"
    applies_to: [SILVER]
    enforcement: "advisory"
```

Policy evaluation runs as a background job after each ingestion and on demand via an API endpoint. Violations are surfaced as advisory notes or blocking errors depending on enforcement level.

### 5.4 Quality SLAs

Each `DataCatalogEntry.quality_sla` JSON field defines per-dataset quality expectations:

```json
{
  "completeness": {"min": 0.7, "target": 0.9},
  "reliability": {"min": 0.6, "target": 0.8},
  "freshness": {"min": 0.5, "target": 0.7},
  "consistency": {"min": 0.6, "target": 0.8}
}
```

The existing four-dimensional quality scoring on `EvidenceItem` (computed as `(completeness_score + reliability_score + freshness_score + consistency_score) / 4.0`) feeds the SLA check. SLA breaches are recorded in `gold_governance_snapshots` and surfaced to the engagement dashboard.

### 5.5 Data Classification

`DataClassification` enum values map to handling requirements:

| Level | Description | Handling |
|---|---|---|
| `PUBLIC` | No sensitivity restrictions | Exportable without redaction |
| `INTERNAL` | Internal KMFlow use only | Requires authentication |
| `CONFIDENTIAL` | Client-sensitive | Encrypted at rest, access-logged |
| `RESTRICTED` | Regulatory or PII | Encrypted, access-controlled, shorter retention |

All `EvidenceItem` records default to `INTERNAL` via the `DataCatalogEntry` default. The classification can be overridden per engagement or per dataset via the governance module.

The existing encryption infrastructure (`src/core/encryption.py`) and audit logging (`AuditLog` with `DATA_ACCESS` action) provide the enforcement mechanisms. The governance module adds the classification metadata layer on top.

### 5.6 Retention Rules

Retention is currently a single field on `Engagement.retention_days`. Phase D adds granularity:

- `DataCatalogEntry.retention_days`: Per-dataset retention, overrides engagement default
- Bronze: Default 7 years (regulatory minimum for consulting evidence)
- Silver: Default 3 years (recomputable from Bronze)
- Gold: Default 1 year (aggregates can be regenerated)

The existing `src/core/retention.py` module handles per-engagement cleanup. Phase D extends this to respect the per-dataset catalog entries and layer-specific defaults.

### 5.7 Client Portability Export

The governance export function (planned for `src/governance/export.py`) produces a self-contained package:

```
governance_export_{engagement_id}_{date}.zip
├── catalog.json          # DataCatalogEntry records for this engagement
├── lineage.json          # EvidenceLineage records with transformation chains
├── policies.yaml         # Active policies (engagement overrides merged)
├── quality_report.json   # Quality SLA compliance summary
└── README.md             # Human-readable guide to interpreting the package
```

This package can be imported into a client's own data governance tooling (Collibra, Alation, etc.) or delivered as a standalone audit artifact.

---

## 6. Databricks Upgrade Path

### 6.1 What is Abstracted Now

The `StorageBackend` protocol (ADR-003, Phase B) is the primary Databricks enablement. Once it is in place, the entire evidence ingestion path — from `ingest_evidence()` in `pipeline.py` through the intelligence pipeline — will be storage-agnostic.

The ontology loader (`src/semantic/ontology/loader.py`) uses only the Python standard library plus PyYAML. It has no dependency on any storage backend and will function unchanged in a Databricks environment.

PostgreSQL is used only for transactional state (engagement records, user management, audit logs, copilot history). None of this moves to Databricks in the upgrade; Databricks is for analytical workloads, not OLTP.

Neo4j remains the graph database. Databricks does not replace Neo4j's graph traversal capability.

### 6.2 What Changes for Databricks

| Component | Local / delta-rs | Databricks |
|---|---|---|
| `StorageBackend` implementation | `DeltaLakeBackend` (delta-rs) | `DatabricksBackend` (Databricks Connect / Unity Catalog API) |
| Delta table writes | `deltalake.write_deltalake()` | `spark.write.format("delta")` via Databricks Connect |
| Delta table reads | `deltalake.DeltaTable()` | `spark.read.format("delta")` |
| Storage path | Local path or S3/ADLS via delta-rs | Unity Catalog volume path |
| Catalog entries | PostgreSQL `data_catalog_entries` | Unity Catalog (mapped via `DataCatalogEntry.delta_table_path`) |
| Scheduled jobs | Background tasks in FastAPI | Databricks Workflows |
| Cross-engagement aggregation | Python process in Gold materialization | Databricks SQL or notebook |

The switch is a single `DatabricksBackend` class implementing `StorageBackend`, plus a settings flag:

```python
# Settings
storage_backend: str = "local"   # "local" | "delta" | "databricks"
databricks_host: str | None = None
databricks_token: str | None = None
databricks_catalog: str | None = None
databricks_schema: str | None = None
```

### 6.3 Unity Catalog Mapping

The `DataCatalogEntry` table maps directly to Databricks Unity Catalog concepts:

| PostgreSQL `DataCatalogEntry` field | Unity Catalog concept |
|---|---|
| `layer` (BRONZE/SILVER/GOLD) | Schema (e.g., `kmflow.bronze`) |
| `dataset_name` | Table name |
| `classification` | Unity Catalog tag |
| `owner` | Unity Catalog owner |
| `delta_table_path` | Managed table path in Unity Catalog |
| `quality_sla` | Quality expectations (manual mapping to DQ constraints) |
| `retention_days` | Unity Catalog table property `delta.logRetentionDuration` |

The `DataCatalogEntry` rows become the source of truth for generating Unity Catalog DDL during migration.

### 6.4 What Stays the Same

- All PostgreSQL transactional models — no migration
- Neo4j graph operations — no migration
- Redis session and rate limiting — no migration
- The ontology YAML and loader — unchanged
- All FastAPI routes — unchanged
- All parser logic in `src/evidence/parsers/` — unchanged
- The intelligence pipeline steps (entity extraction, embedding generation, semantic bridges) — unchanged, just called with a different storage backend

The Delta table format written by delta-rs is byte-compatible with Databricks. A `bronze_evidence_raw` table written locally by delta-rs can be registered in Unity Catalog and immediately read by a Databricks cluster without any conversion.

---

## 7. Phased Roadmap

### Phase A: Ontology + Architecture POV (Done — this session)

**Duration**: 1 session (2026-02-17)

**Deliverables**:
- `src/semantic/ontology/kmflow_ontology.yaml` — formal YAML schema replacing hardcoded frozensets
- `src/semantic/ontology/loader.py` — typed accessor functions with `functools.cache`
- `src/semantic/ontology/validate.py` — CLI validation tool for CI
- `src/semantic/graph.py` — rewired to load constants from ontology at import time
- `src/semantic/builder.py` — rewired to use `get_entity_type_to_label()` from loader
- `src/evidence/pipeline.py` — rewired to use `get_entity_type_to_label()` from loader
- `src/core/models.py` — `EvidenceLineage`, `DataCatalogEntry`, `DataLayer`, `DataClassification` models added; `EvidenceItem` gets `source_system`, `delta_path`, `lineage_id` fields
- This document: `docs/architecture/data-layer-evolution-pov.md`

**Quality gate**: All existing tests pass. Ontology validation passes (`python -m src.semantic.ontology.validate`).

---

### Phase B: Storage Abstraction + Delta Lake Bronze (~2 weeks)

**Objective**: Replace the hardcoded `store_file()` with a `StorageBackend` protocol and write raw evidence to a Bronze Delta table alongside the local filesystem.

**Deliverables**:
- `src/evidence/storage.py` — `StorageBackend` Protocol, `StorageResult` dataclass, `LocalFilesystemBackend`, `DeltaLakeBackend`
- `pyproject.toml` — add `deltalake` dependency
- `src/evidence/pipeline.py` — `ingest_evidence()` accepts `StorageBackend` kwarg, calls `backend.store()` instead of `store_file()`; populates `EvidenceItem.source_system` and `EvidenceItem.delta_path`
- Alembic migration — for any new columns not already present (most already landed in Phase A model changes)
- `bronze_evidence_raw` and `bronze_ingestion_log` Delta tables written on each ingestion
- `DataCatalogEntry` rows auto-created for new Bronze tables
- `src/core/config.py` — `storage_backend`, `delta_lake_path` settings added

**Tests**: Unit tests for `LocalFilesystemBackend` and `DeltaLakeBackend` with mock content. Integration test verifying Bronze table row is created after `ingest_evidence()`.

---

### Phase C: Silver + Gold Layers + Lineage API (~2 weeks)

**Objective**: Write parsed fragments and entities to Silver Delta tables. Materialize Gold lineage chains. Expose lineage data via a new API route.

**Deliverables**:
- `silver_evidence_fragments` and `silver_extracted_entities` Delta tables written by the intelligence pipeline
- `silver_quality_events` Delta table written after quality scoring
- `gold_evidence_lineage_chains` materialize job (can be a FastAPI background task initially)
- `EvidenceLineage` records created in PostgreSQL at ingestion time (wiring `EvidenceItem.lineage_id`)
- `src/api/routes/lineage.py` — `GET /api/v1/engagements/{id}/evidence/{evidence_id}/lineage` returning transformation chain and version history

**Tests**: End-to-end test: upload file → assert `EvidenceLineage` row exists → assert Bronze and Silver Delta rows exist → assert lineage API returns correct chain.

---

### Phase D: Data Governance Framework (~2 weeks)

**Objective**: Build the `src/governance/` module with policy engine, catalog management, and client export.

**Deliverables**:
- `src/governance/__init__.py`
- `src/governance/catalog.py` — `DataCatalogService` with CRUD and classification
- `src/governance/policy.py` — YAML policy loader, `PolicyEngine.evaluate()`
- `src/governance/policies/default.yaml` — default policy set
- `src/governance/export.py` — `export_governance_package()` producing zip artifact
- `src/governance/quality.py` — SLA checker comparing `EvidenceItem` scores against `DataCatalogEntry.quality_sla`
- `src/api/routes/governance.py` — catalog, policy, export endpoints
- `gold_governance_snapshots` Delta table written on each export
- `src/core/retention.py` — extended to respect `DataCatalogEntry.retention_days` and layer defaults

**Tests**: Policy evaluation unit tests. Export integration test: export zip contains expected files with valid JSON/YAML.

---

### Phase E: Migration + Monitoring Integration (~2 weeks)

**Objective**: Migrate existing evidence data to populate Bronze and Silver Delta tables retroactively. Integrate governance SLA breaches with the monitoring/alerting system.

**Deliverables**:
- `src/governance/migration.py` — bulk migration job: for each existing `EvidenceItem`, read file from `evidence_store/`, write Bronze row, re-run intelligence pipeline to write Silver rows
- Migration CLI (`python -m src.governance.migration --engagement-id <id>`)
- `MonitoringAlert` integration: SLA breach creates a `MonitoringAlert` with `AlertSeverity.MEDIUM` and links to the failing catalog entry
- `DataCatalogEntry` rows created for all existing tables (not just newly ingested evidence)
- Dashboard integration: governance health widget showing SLA compliance rates

**Tests**: Migration test with a fixture engagement. Alert creation test when SLA breach is detected.

---

### Phase F: Databricks Preparation (~2 weeks)

**Objective**: Make the Databricks upgrade a configuration change, not a code change. Validate that local Delta tables can be registered in Unity Catalog and read by a Databricks cluster.

**Deliverables**:
- `src/evidence/storage.py` — `DatabricksBackend` implementation using Databricks Connect
- `src/core/config.py` — `databricks_host`, `databricks_token`, `databricks_catalog`, `databricks_schema` settings
- `src/governance/unity_catalog.py` — `generate_unity_catalog_ddl()` from `DataCatalogEntry` records; `register_tables()` bulk registration
- Documentation: upgrade runbook (`docs/architecture/databricks-upgrade-runbook.md`)
- Test: `DatabricksBackend` unit tests with mocked Databricks Connect

**Validation**: Manually run local Delta tables through `databricks-connect` against a dev Databricks workspace to confirm format compatibility before declaring Phase F complete.

---

## 8. Key File References

### Existing Files — Roles and Phase A Changes

| File | Role | Phase A Changes |
|---|---|---|
| `src/core/models.py` | All SQLAlchemy ORM models | Added `EvidenceLineage`, `DataCatalogEntry`, `DataLayer`, `DataClassification`; added `source_system`, `delta_path`, `lineage_id` to `EvidenceItem` |
| `src/core/database.py` | Async engine and session factory | None |
| `src/core/config.py` | Application settings (Pydantic Settings v2) | None — `storage_backend` and Delta settings planned for Phase B |
| `src/evidence/pipeline.py` | Evidence ingestion orchestration; `ingest_evidence()` entry point | Rewired `build_fragment_graph()` to use `get_entity_type_to_label()` from ontology loader instead of hardcoded dict |
| `src/semantic/graph.py` | `KnowledgeGraphService`, `GraphNode`, `GraphRelationship` | `VALID_NODE_LABELS` and `VALID_RELATIONSHIP_TYPES` now loaded from ontology at import time instead of hardcoded |
| `src/semantic/builder.py` | `KnowledgeGraphBuilder` — higher-level graph construction | Rewired to use ontology loader |
| `src/semantic/ontology/kmflow_ontology.yaml` | **New** — canonical ontology schema | Created |
| `src/semantic/ontology/loader.py` | **New** — typed accessor functions for ontology | Created |
| `src/semantic/ontology/validate.py` | **New** — CLI validation tool | Created |
| `src/semantic/entity_extraction.py` | Entity extraction from fragment text; `EntityType` enum, `extract_entities()`, `resolve_entities()` | None |
| `src/semantic/embeddings.py` | `EmbeddingService.store_embedding()` — stores fragment embeddings in pgvector | None |
| `src/rag/embeddings.py` | `EmbeddingService.generate_embeddings()` — batch embedding generation | None |
| `alembic/versions/001` – `014` | 14 Alembic migrations covering all ORM models | Migration 014 adds Phase 8 tables (`success_metrics`, `metric_readings`, `annotations`) |

### Planned New Files — By Phase

| File | Phase | Purpose |
|---|---|---|
| `src/evidence/storage.py` | B | `StorageBackend` Protocol, `LocalFilesystemBackend`, `DeltaLakeBackend` |
| `alembic/versions/015_add_delta_lineage_fields.py` | B | Alembic migration for any Phase B model additions |
| `src/governance/__init__.py` | D | Governance module entry point |
| `src/governance/catalog.py` | D | `DataCatalogService` |
| `src/governance/policy.py` | D | `PolicyEngine`, YAML policy loader |
| `src/governance/policies/default.yaml` | D | Default policy set |
| `src/governance/export.py` | D | `export_governance_package()` |
| `src/governance/quality.py` | D | SLA checker |
| `src/governance/migration.py` | E | Bulk evidence migration job |
| `src/governance/unity_catalog.py` | F | Unity Catalog DDL generation and table registration |
| `src/api/routes/lineage.py` | C | Lineage REST endpoints |
| `src/api/routes/governance.py` | D | Governance REST endpoints |

### Files That Will Not Change

These files are explicitly not in scope for the data layer evolution. They do their job and the storage changes are designed not to touch them:

- `src/evidence/parsers/` — all 14 parsers (document, BPMN, XES, ARIS, controls, SaaS, etc.)
- `src/pov/` — LCD algorithm and POV generation
- `src/tom/` — TOM alignment
- `src/conformance/` — BPMN conformance checking
- `src/monitoring/` — process monitoring and alerting (Phase E adds a new alert type but does not modify existing code)
- `src/rag/` — RAG copilot
- `src/integrations/` — Salesforce, SAP, ServiceNow, Celonis, Soroco connectors
- `src/mcp/` — MCP server
- `frontend/` — no frontend changes planned for Phases B–F

---

*This document is a living architecture reference. Update it when ADR decisions are revised or new gaps are identified.*
