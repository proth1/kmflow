# B2: Data Integrity Audit Findings

**Agent**: B2 (Data Integrity Auditor)
**Scope**: Database schema design, FK constraints, cascade deletes, migration chain integrity, Neo4j graph model, pgvector usage
**Date**: 2026-02-20

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2     |
| HIGH     | 4     |
| MEDIUM   | 4     |
| LOW      | 3     |
| **Total** | **13** |

---

## CRITICAL Findings

### [CRITICAL] MIGRATION-CHAIN: Migration 005 and 006 both descend from 004 — branched revision chain

**File**: `alembic/versions/005_create_security_tables.py:17` and `alembic/versions/006_create_pov_tables.py:19`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# 005_create_security_tables.py
down_revision: Union[str, None] = "004"

# 006_create_pov_tables.py
down_revision: Union[str, None] = "004"
```
**Description**: Both migration 005 and 006 declare `down_revision = "004"`, creating a branched migration tree. Alembic supports multi-head migrations, but running `alembic upgrade head` with two heads will fail unless the user explicitly merges them or specifies which head. The remaining chain (007 -> 006, 008 -> 007, etc.) proceeds linearly from 006, leaving 005 as an orphaned branch that may or may not have been applied.
**Risk**: Running `alembic upgrade head` on a fresh database will fail with "Multiple head revisions" error. If 005 was applied before 006 (which depends only on 004, not 005), the `users` and `engagement_members` tables may exist or not depending on run order. Migration 007 (regulatory tables) depends on 006 but NOT 005, so the `users` table could be missing when later migrations reference it (e.g., 011 creates `mcp_api_keys` with FK to `users`).
**Recommendation**: Create a merge migration that declares `down_revision = ("005", "006")` or fix 006 to have `down_revision = "005"` so the chain is linear: 004 -> 005 -> 006 -> 007 -> ...

---

### [CRITICAL] FK-MISSING-ONDELETE: Four ForeignKey definitions lack ondelete behavior

**File**: `src/core/models.py:930-931, 948, 1484`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# Line 930 — MetricReading.metric_id
metric_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("success_metrics.id"), nullable=False)

# Line 931 — MetricReading.engagement_id
engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id"), nullable=False)

# Line 948 — Annotation.engagement_id
engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id"), nullable=False)

# Line 1484 — AlternativeSuggestion.created_by
created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
```
**Description**: These four ForeignKey columns lack `ondelete=` specification. The default PostgreSQL behavior is `NO ACTION` (or `RESTRICT`), which will prevent parent row deletion entirely. For `MetricReading` and `Annotation`, deleting an engagement will fail with a FK violation. For `AlternativeSuggestion.created_by`, deleting a user will fail.
**Risk**: Engagement deletion (a core business operation for GDPR compliance and data retention) will fail silently at the database level if any metric readings or annotations exist for that engagement. The ORM-level `cascade="all, delete-orphan"` on the Engagement model does NOT cover these tables because there are no corresponding relationship() definitions on Engagement for MetricReading, Annotation, or AlternativeSuggestion.
**Recommendation**: Add `ondelete="CASCADE"` to all four FK definitions. Also add corresponding `relationship()` with `cascade="all, delete-orphan"` on the Engagement model for MetricReading and Annotation, and on the User model for AlternativeSuggestion (or use `ondelete="SET NULL"` if the record should survive user deletion).

---

## HIGH Findings

### [HIGH] SCHEMA-MISMATCH: Migration 010 stores embedding as LargeBinary but model uses Vector(768)

**File**: `alembic/versions/010_create_patterns_simulation_tables.py:52` vs `src/core/models.py:1258`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# Migration 010 — pattern_library_entries table
sa.Column("embedding", sa.LargeBinary(), nullable=True),  # pgvector would be better

# ORM model — PatternLibraryEntry
embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
```
**Description**: The migration creates the `embedding` column on `pattern_library_entries` as `LargeBinary`, but the ORM model declares it as `Vector(768)` (pgvector). These are incompatible column types. Attempting to use the ORM to store or query embeddings on this table will either fail or produce corrupt data, depending on whether a subsequent migration altered the column type (none found).
**Risk**: Pattern similarity search on `pattern_library_entries` is broken. Any attempt to use cosine distance operators (`<=>`) on a `LargeBinary` column will raise a PostgreSQL error.
**Recommendation**: Create a new migration that uses `ALTER COLUMN ... TYPE vector(768) USING embedding::vector(768)` to convert the column, or add an HNSW index like the one on `evidence_fragments`.

---

### [HIGH] NEO4J-INJECTION: Dynamic property keys in Cypher queries allow property injection

**File**: `src/semantic/graph.py:175-176`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
set_clauses = ", ".join(f"n.{k} = ${k}" for k in props)
query = f"CREATE (n:{label}) SET {set_clauses} RETURN n.id AS id"
```
**Description**: While the `label` is validated against `VALID_NODE_LABELS` (good), and values are passed as parameters (good), the property **keys** from the `props` dict are interpolated directly into the Cypher query string as `n.{k}`. If a caller passes a property key containing Cypher syntax (e.g., `"id} DETACH DELETE n //"`), it would be injected into the query. The same pattern appears at lines 232 and 284.
**Risk**: If any upstream code passes user-controlled property keys to `create_node()`, `find_nodes()`, or `create_relationship()`, an attacker could inject arbitrary Cypher. Currently the `properties` dict comes from internal service code which reduces exploitability, but the service API has no validation on property key names.
**Recommendation**: Add a property key validation function that restricts keys to `^[a-zA-Z_][a-zA-Z0-9_]*$` (valid Cypher identifiers). Apply it before building the SET clause.

---

### [HIGH] ORPHAN-RISK: ProcessModel has no cascade relationship from Engagement for 6+ dependent tables

**File**: `src/core/models.py:502-503`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# ProcessModel — has relationship to Engagement but no back_populates cascade
engagement: Mapped[Engagement] = relationship("Engagement")

# Engagement model only cascades: evidence_items, audit_logs, shelf_data_requests
evidence_items: Mapped[list[EvidenceItem]] = relationship(
    "EvidenceItem", back_populates="engagement", cascade="all, delete-orphan"
)
```
**Description**: The `Engagement` model defines `cascade="all, delete-orphan"` relationships for only 3 tables: `evidence_items`, `audit_logs`, and `shelf_data_requests`. However, 15+ additional tables have `ForeignKey("engagements.id", ondelete="CASCADE")` including `process_models`, `policies`, `controls`, `regulations`, `target_operating_models`, `monitoring_jobs`, `monitoring_alerts`, `simulation_scenarios`, etc. The database-level `ondelete="CASCADE"` will handle deletion at the PostgreSQL level, but ORM-level operations like `session.delete(engagement)` will not cascade to these child tables because no SQLAlchemy relationship with `cascade="all, delete-orphan"` exists. This creates a dual-path deletion model where behavior depends on whether deletion happens at the ORM or SQL level.
**Risk**: If code uses `session.delete(engagement)` instead of a raw SQL DELETE, PostgreSQL will still cascade (via FK constraint), but SQLAlchemy's identity map may retain stale references to deleted children, causing `DetachedInstanceError` or `StaleDataError` on subsequent access.
**Recommendation**: Either (a) add `cascade="all, delete-orphan"` relationships on the Engagement model for all child tables, or (b) document that engagement deletion must always use raw SQL / `session.execute(delete(...))` rather than `session.delete()`.

---

### [HIGH] MIGRATION-MISSING-ONDELETE: Migration 018 creates alternative_suggestions.created_by FK without ondelete

**File**: `alembic/versions/018_add_phase4_models.py:101-106`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
sa.Column(
    "created_by",
    UUID(as_uuid=True),
    sa.ForeignKey("users.id"),
    nullable=False,
),
```
**Description**: The migration for `alternative_suggestions.created_by` references `users.id` without any `ondelete` clause. The ORM model also has `ForeignKey("users.id")` without `ondelete`. This means deleting a user who has created suggestions will fail with a FK constraint violation at the database level.
**Risk**: User deactivation/deletion workflows will break if the user has created any alternative suggestions. Unlike other FK references that use `ondelete="CASCADE"` or `ondelete="SET NULL"`, this is a hard block.
**Recommendation**: Add `ondelete="SET NULL"` (and make the column nullable) or `ondelete="CASCADE"` depending on whether suggestion records should be preserved after user deletion.

---

## MEDIUM Findings

### [MEDIUM] MIGRATION-MISSING-ONDELETE-MISMATCH: Migration 014 adds ondelete to metric_readings but ORM model lacks it

**File**: `alembic/versions/014_add_phase8_tables.py:63-69` vs `src/core/models.py:930-931`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# Migration 014 — metric_readings correctly has ondelete="CASCADE"
sa.ForeignKey("success_metrics.id", ondelete="CASCADE"),
sa.ForeignKey("engagements.id", ondelete="CASCADE"),

# ORM model — MetricReading lacks ondelete
metric_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("success_metrics.id"), nullable=False)
engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id"), nullable=False)
```
**Description**: The migration correctly specifies `ondelete="CASCADE"` for both FK columns, so the database behavior is correct. However, the ORM model definition lacks `ondelete`. This is a model-vs-migration drift. If someone regenerates migrations from the ORM model (autogenerate), the ondelete clause would be lost.
**Risk**: Medium — the database is currently correct, but model drift could cause future migration issues.
**Recommendation**: Update the ORM model to match the migration: add `ondelete="CASCADE"` to both FK definitions.

---

### [MEDIUM] NULLABLE-OVERUSE: 119 nullable=True columns across ~40 models

**File**: `src/core/models.py` (throughout)
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# Examples of columns that may warrant NOT NULL
description: Mapped[str | None] = mapped_column(Text, nullable=True)       # Engagement
metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)    # Many tables
config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)      # IntegrationConnection
```
**Description**: The models contain 119 `nullable=True` column definitions. While many are legitimately optional (file_path, source_date, metadata_json), some represent a permissive schema that could allow incomplete records. Key examples: `Engagement.description` (every engagement should have a description), `IntegrationConnection.config_json` (a connection without config is useless), and widespread nullable JSON columns that default to empty dicts but accept NULL.
**Risk**: Application code must handle both NULL and empty values for JSON columns, increasing complexity. NULL JSON columns cannot use JSON operators without COALESCE, which is easy to forget.
**Recommendation**: Audit nullable columns and set `server_default="'{}'"` for JSON columns that default to `list` or `dict` in the ORM, converting them to NOT NULL with an empty JSON default.

---

### [MEDIUM] INDEX-MISSING: Several frequently queried FK columns lack indexes

**File**: `src/core/models.py`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# EvidenceFragment.evidence_id — no index defined (line 346-349)
evidence_id: Mapped[uuid.UUID] = mapped_column(
    UUID(as_uuid=True),
    ForeignKey("evidence_items.id", ondelete="CASCADE"),
    nullable=False,
)
# No index on evidence_fragments.evidence_id in model or migration 001
```
**Description**: The `evidence_fragments.evidence_id` column has a ForeignKey but no explicit index. This column is used in joins for pgvector similarity search (`JOIN evidence_items ei ON ef.evidence_id = ei.id` in `embeddings.py:141`). While PostgreSQL creates indexes for primary keys and unique constraints, it does NOT automatically index FK columns. Other missing FK indexes: `evidence_items.duplicate_of_id`, `conformance_results.pov_model_id`, `evidence_lineage.parent_version_id`.
**Risk**: Full table scans on evidence_fragments when joining to evidence_items during similarity search. With large fragment tables, this will cause significant performance degradation.
**Recommendation**: Add explicit B-tree indexes on `evidence_fragments.evidence_id`, `evidence_items.duplicate_of_id`, `conformance_results.pov_model_id`, and `evidence_lineage.parent_version_id`.

---

### [MEDIUM] MISSING-UNIQUE: BestPractice and Benchmark tables lack uniqueness constraints

**File**: `src/core/models.py:853-886`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
class BestPractice(Base):
    __tablename__ = "best_practices"
    # No unique constraint — same domain+industry+description can be inserted multiple times

class Benchmark(Base):
    __tablename__ = "benchmarks"
    # No unique constraint — same metric_name+industry can be inserted multiple times
```
**Description**: The `best_practices` table has no unique constraint on `(domain, industry, description)` or any natural key. The `benchmarks` table has no unique constraint on `(metric_name, industry)`. These are reference data tables that should prevent duplicate entries. Similarly, `SuccessMetric` has no unique constraint on `(name, category)`.
**Risk**: Duplicate reference data can silently accumulate, leading to incorrect benchmark comparisons and inflated best practice lists. No deduplication protection at the database level.
**Recommendation**: Add `UniqueConstraint("metric_name", "industry", name="uq_benchmark_metric_industry")` to Benchmark and `UniqueConstraint("name", "category", name="uq_success_metric_name_category")` to SuccessMetric.

---

## LOW Findings

### [LOW] ALEMBIC-HARDCODED-CREDS: alembic.ini contains plaintext database credentials

**File**: `alembic.ini:6`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```ini
sqlalchemy.url = postgresql+asyncpg://kmflow:kmflow_dev_password@localhost:5432/kmflow
```
**Description**: The alembic.ini file contains a hardcoded database URL with username `kmflow` and password `kmflow_dev_password`. While this is clearly a development credential, this file is checked into version control and the password pattern could be reused in production.
**Risk**: Low for development, but the file should use environment variable interpolation to prevent credential leakage.
**Recommendation**: Use `sqlalchemy.url = %(DATABASE_URL)s` with env var interpolation via `alembic/env.py`, or use `config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])` in env.py.

---

### [LOW] PGVECTOR-DIMENSION: Embedding dimension is consistent at 768 across all usage points

**File**: `src/core/models.py:353, 1258`, `src/rag/embeddings.py:19`, `alembic/versions/001_enable_pgvector_and_create_core_tables.py:116`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# models.py:353 — EvidenceFragment
embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

# models.py:1258 — PatternLibraryEntry
embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

# rag/embeddings.py:19
EMBEDDING_DIMENSION = 768

# Migration 001 — evidence_fragments
sa.Column("embedding", Vector(768), nullable=True),
```
**Description**: The dimension 768 is hardcoded in 4 separate locations. While currently consistent, this is a maintenance risk if the embedding model changes (e.g., to a 1536-dimension model). The RAG service uses a constant `EMBEDDING_DIMENSION = 768`, but the ORM models and migrations use literal `768`.
**Risk**: Low — if the embedding dimension changes, updates in multiple files could be missed, causing silent dimension mismatches that corrupt similarity search.
**Recommendation**: Consider referencing `EMBEDDING_DIMENSION` from a single config location in the ORM models, and documenting the dimension choice.

---

### [LOW] NEO4J-READ-TRANSACTION: Read queries use session.run() instead of execute_read()

**File**: `src/semantic/graph.py:112-115`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
async def _run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    async with self._driver.session() as session:
        result = await session.run(query, parameters or {})
        records = await result.data()
        return records
```
**Description**: Read queries use `session.run()` directly instead of `session.execute_read()`. The write path correctly uses `session.execute_write()` (line 140), but the read path does not use the corresponding read transaction function. In a Neo4j cluster, `execute_read()` routes reads to replica nodes and provides automatic retry on transient errors.
**Risk**: In a clustered Neo4j deployment, all reads go to the leader node instead of being distributed to replicas. No automatic retry on transient failures for read queries.
**Recommendation**: Refactor `_run_query` to use `session.execute_read()` for consistency with the write path.

---

## Architecture Notes (No Finding — Informational)

### Migration Chain Summary
```
001 (core tables)
  └─ 002 (team field)
       └─ 003 (audit_logs)
            └─ 004 (evidence fields, shelf requests)
                 ├─ 005 (users, engagement_members)  ← BRANCH HEAD 1
                 └─ 006 (POV tables)                 ← BRANCH HEAD 2
                      └─ 007 → 008 → 009 → 010 → 011 → 012 → 013 → 014 → 015 → 016 → 017 → 018 → 019
```

### FK Cascade Coverage (47 total FK definitions)
- **With ondelete="CASCADE"**: 33 (70%)
- **With ondelete="SET NULL"**: 10 (21%)
- **Without ondelete (default RESTRICT)**: 4 (9%) — all flagged above

### ORM Cascade Coverage
- **Engagement children with ORM cascade**: 3 of 18+ child tables
- **Other parents with ORM cascade**: ProcessModel (3), ShelfDataRequest (1), User (1), TargetOperatingModel (1), SimulationScenario (1)

### Neo4j Security Posture
- Label validation: GOOD (checked against VALID_NODE_LABELS)
- Relationship type validation: GOOD (checked against VALID_RELATIONSHIP_TYPES)
- Value parameterization: GOOD (all values passed as $parameters)
- Property key sanitization: MISSING (keys interpolated into Cypher)
- Write transactions: GOOD (uses execute_write)
- Read transactions: SUBOPTIMAL (uses session.run instead of execute_read)

### pgvector Consistency
- Dimension: 768 everywhere (consistent)
- HNSW index: exists on evidence_fragments.embedding (good)
- HNSW index: MISSING on pattern_library_entries.embedding (column type wrong anyway)
- Cosine distance operator: correctly used in embeddings.py search queries
