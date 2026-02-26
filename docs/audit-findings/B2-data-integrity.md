# B2: Data Integrity Audit Findings (Re-Audit)

**Agent**: B2 (Data Integrity Auditor)
**Scope**: Database schema design, FK constraints, cascade deletes, migration chain integrity, Neo4j graph model, pgvector usage
**Date**: 2026-02-26
**Previous Audit**: 2026-02-20 (13 findings)

## Remediation Status from Previous Audit

| Previous Finding | Severity | Status |
|-----------------|----------|--------|
| MIGRATION-CHAIN: 005/006 branch | CRITICAL | **FIXED** -- 006 now has `down_revision = "005"` |
| FK-MISSING-ONDELETE: 4 FKs | CRITICAL | **FIXED** -- Migration 020 added ondelete to all 4 |
| SCHEMA-MISMATCH: LargeBinary vs Vector(768) | HIGH | **FIXED** -- Migration 021 converted column type |
| NEO4J-INJECTION: Property key injection | HIGH | **FIXED** -- `_validate_property_keys()` regex added |
| ORPHAN-RISK: Engagement cascades | HIGH | Partially addressed -- see B2-ORM-004 below |
| MIGRATION-018-ONDELETE: created_by FK | HIGH | **FIXED** -- Migration 020 added SET NULL |
| MODEL-MIGRATION-DRIFT: ondelete mismatch | MEDIUM | **FIXED** -- Model now matches migration |
| NULLABLE-OVERUSE: 119 nullable columns | MEDIUM | Open -- no change |
| INDEX-MISSING: FK columns without indexes | MEDIUM | **FIXED** -- Migrations 022 and 029 added indexes |
| MISSING-UNIQUE: BestPractice/Benchmark | MEDIUM | **FIXED** -- Migration 022 added unique constraints |
| ALEMBIC-HARDCODED-CREDS | LOW | **FIXED** -- Password changed to `changeme`, env var note added |
| PGVECTOR-DIMENSION: Hardcoded 768 | LOW | Open -- informational, no code change |
| NEO4J-READ-TRANSACTION: session.run() | LOW | **FIXED** -- Now uses `execute_read()` |

**Resolved**: 10 of 13 findings
**Open/Residual**: 3 (1 partially addressed, 2 accepted risk)

---

## Summary (Re-Audit)

| Severity | Count |
|----------|-------|
| CRITICAL | 0     |
| HIGH     | 2     |
| MEDIUM   | 5     |
| LOW      | 3     |
| **Total** | **10** |

---

## HIGH Findings

### [HIGH] B2-NEO4J-001: Neo4j graph data not cleaned when PostgreSQL engagement is deleted

**File**: `src/core/retention.py:57-109` and `src/api/routes/engagements.py:257-277`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/core/retention.py:57-64
async def cleanup_expired_engagements(session: AsyncSession) -> int:
    """Delete evidence data for expired engagements and archive the engagement record.
    For each expired engagement:
    1. Delete evidence fragments (FK child of evidence_items).
    2. Delete evidence items.
    3. Delete engagement-scoped audit logs.
    4. Mark engagement as ARCHIVED (engagement record kept for reference).
    """
```
**Description**: When an engagement is deleted or its data is cleaned up via the retention process, all PostgreSQL tables are cascaded properly via `ondelete="CASCADE"`. However, the engagement's knowledge graph nodes and relationships in Neo4j are never cleaned up. The `KnowledgeGraphService` in `src/semantic/graph.py` has no `delete_engagement_subgraph()` method. All Neo4j nodes carry an `engagement_id` property, so they become orphaned references to a deleted PostgreSQL engagement.
**Risk**: Neo4j accumulates orphaned graph data indefinitely. This violates data minimization requirements for GDPR compliance (engagement retention policy cleanup explicitly deletes PostgreSQL data but forgets Neo4j). Stale graph data for deleted engagements could surface in cross-engagement search results or graph traversals if an engagement_id filter is not strictly applied.
**Recommendation**: Add a `delete_engagement_subgraph(engagement_id)` method to `KnowledgeGraphService` that executes `MATCH (n {engagement_id: $eid}) DETACH DELETE n`. Call it from `cleanup_expired_engagements()` and from the engagement archive/delete route before committing PostgreSQL changes.

---

### [HIGH] B2-MODEL-002: ConsentRecord model-migration type mismatch for consent_type column

**File**: `src/taskmining/consent.py:69` vs `alembic/versions/028_create_consent_records_table.py:37`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/taskmining/consent.py:69 (ORM model)
consent_type: Mapped[ConsentType] = mapped_column(Enum(ConsentType), nullable=False)

# alembic/versions/028_create_consent_records_table.py:37 (migration)
sa.Column("consent_type", sa.String(50), nullable=False),
```
**Description**: The ORM model defines `consent_type` as `Enum(ConsentType)`, which creates a PostgreSQL ENUM type (e.g., `consenttype`). However, the migration creates it as `sa.String(50)`, which is a plain VARCHAR. These are fundamentally different column types. When `alembic upgrade` runs, it creates a VARCHAR column. When the ORM inserts a row, SQLAlchemy will attempt to write an enum value into a VARCHAR column. While this may work silently (PostgreSQL will accept the string), an `alembic autogenerate` will detect a type mismatch and propose a migration to change String to Enum, indicating the schema is inconsistent.
**Risk**: Running `alembic check` or `alembic revision --autogenerate` will always detect drift. If the column is ever properly converted to Enum, existing string values may fail the type migration if they don't match enum members. Additionally, no CHECK constraint exists on the VARCHAR column to enforce valid values at the database level, so any arbitrary string up to 50 characters can be stored.
**Recommendation**: Either (a) change the migration to use `sa.Enum(ConsentType, values_callable=...)` to match the model, or (b) change the model to use `mapped_column(String(50))` to match the migration. The Enum approach is preferred for type safety at the database level.

---

## MEDIUM Findings

### [MEDIUM] B2-ORPHAN-003: JSON array columns store FK references without referential integrity

**File**: `src/core/models/governance.py:88`, `src/core/models/pov.py:124,150`, `src/core/models/monitoring.py:287`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/core/models/governance.py:88
linked_policy_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

# src/core/models/pov.py:124
evidence_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

# src/core/models/monitoring.py:287
deviation_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
```
**Description**: Four columns across three model files store lists of UUID references as JSON arrays instead of using proper junction tables with foreign key constraints. `Control.linked_policy_ids` references `policies.id`, `ProcessElement.evidence_ids` and `Contradiction.evidence_ids` reference `evidence_items.id`, and `MonitoringAlert.deviation_ids` references `process_deviations.id`. None of these references are enforced by the database. When a referenced record is deleted (via CASCADE on the parent engagement), the JSON arrays silently retain stale UUIDs.
**Risk**: Application code that resolves these UUID arrays will either (a) get empty results for deleted records, silently losing data, or (b) raise 404/null errors if it expects the referenced records to exist. The stale UUIDs can never be cleaned up without scanning every row that contains JSON arrays.
**Recommendation**: For each JSON array column, create a proper junction table (e.g., `control_policies`, `element_evidence`, `alert_deviations`) with foreign keys and appropriate `ondelete` behavior. If the JSON approach is intentional (for denormalization performance), document the trade-off and add a cleanup job that scrubs stale IDs.

---

### [MEDIUM] B2-ORM-004: Engagement model lacks ORM cascade for 15+ child tables

**File**: `src/core/models/engagement.py:77-85`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/core/models/engagement.py:77-85 -- only 3 ORM cascades defined
evidence_items: Mapped[list["EvidenceItem"]] = relationship(
    "EvidenceItem", back_populates="engagement", cascade="all, delete-orphan"
)
audit_logs: Mapped[list["AuditLog"]] = relationship(
    "AuditLog", back_populates="engagement", passive_deletes=True
)
shelf_data_requests: Mapped[list["ShelfDataRequest"]] = relationship(
    "ShelfDataRequest", back_populates="engagement", cascade="all, delete-orphan"
)
```
**Description**: The Engagement model defines ORM-level `cascade="all, delete-orphan"` for only 3 of its 18+ child tables (evidence_items, audit_logs, shelf_data_requests). All other child tables (process_models, policies, controls, regulations, target_operating_models, gap_analysis_results, monitoring_jobs, monitoring_alerts, process_deviations, simulation_scenarios, conformance_results, etc.) rely solely on PostgreSQL `ondelete="CASCADE"` without ORM cascade. This creates a dual-path deletion model.
**Risk**: If `session.delete(engagement)` is used instead of `session.execute(delete(Engagement).where(...))`, SQLAlchemy's unit of work will cascade to the 3 configured relationships but leave the other 15+ child tables to PostgreSQL's database-level cascade. This works but the ORM identity map may contain stale references to the database-cascaded children, potentially causing `DetachedInstanceError` on subsequent access within the same session. The `retention.py` cleanup correctly uses raw SQL deletes, but other code paths (e.g., the archive endpoint) could encounter this.
**Recommendation**: Add `passive_deletes=True` to the remaining child relationships on Engagement (matching the pattern used for audit_logs). This tells SQLAlchemy to let the database handle cascade deletes without loading children into the session. Alternatively, document that engagement deletion must always use `session.execute(delete(...))`.

---

### [MEDIUM] B2-CHECK-005: No database-level CHECK constraints on score/confidence columns

**File**: `src/core/models/evidence.py:97-100`, `src/core/models/pov.py:74,118-119`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/core/models/evidence.py:97-100
completeness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
reliability_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
freshness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
consistency_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

# src/core/models/pov.py:74,118-119
confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
triangulation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
```
**Description**: The platform uses numerous 0.0-1.0 score/confidence columns across EvidenceItem (4 quality scores), ProcessModel (confidence_score), ProcessElement (confidence_score, triangulation_score), GapAnalysisResult (severity, confidence), and others. None of these columns have PostgreSQL CHECK constraints to enforce the valid range. The `quality_score` property computes an average assuming values are in [0.0, 1.0], but the database does not enforce this.
**Risk**: A bug in any service that writes scores (evidence quality scoring, LCD algorithm, gap analysis engine) could write values outside [0.0, 1.0] (e.g., negative scores, scores > 1.0), silently corrupting derived metrics like quality_score averages and priority_score products.
**Recommendation**: Add CHECK constraints via a new migration: `ALTER TABLE evidence_items ADD CONSTRAINT chk_completeness_score CHECK (completeness_score >= 0 AND completeness_score <= 1)`. Apply the same pattern to all score/confidence columns.

---

### [MEDIUM] B2-ACTOR-006: Actor/author reference columns use plain strings instead of FK to users

**File**: `src/core/models/monitoring.py:130,289`, `src/core/models/audit.py:102`, `src/core/models/pattern.py:71`, `src/core/models/taskmining.py:152,304`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/core/models/monitoring.py:130
author_id: Mapped[str] = mapped_column(String(255), nullable=False)

# src/core/models/audit.py:102
actor: Mapped[str] = mapped_column(String(255), nullable=False, default="system")

# src/core/models/pattern.py:71
granted_by: Mapped[str] = mapped_column(String(255), nullable=False)

# src/core/models/taskmining.py:152
approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
```
**Description**: Six columns across four model files store user references as plain `String(255)` instead of `ForeignKey("users.id")`. These include `Annotation.author_id`, `AuditLog.actor`, `PatternAccessRule.granted_by`, `MonitoringAlert.acknowledged_by`, `TaskMiningAgent.approved_by`, and `PIIQuarantine.reviewed_by`. These columns accept any string value with no referential integrity to the `users` table.
**Risk**: If user identifiers change format (e.g., from email to UUID), these columns cannot be automatically migrated. Queries that join to the users table must use string matching instead of FK joins, which is slower and error-prone. Additionally, there is no database-level protection against storing invalid user references.
**Recommendation**: For new code, use `ForeignKey("users.id", ondelete="SET NULL")` for actor/author columns. For existing data, plan a migration that resolves string values to user UUIDs. If the columns intentionally accept non-user actors (e.g., "system", "scheduler"), document this explicitly and consider a discriminator column.

---

### [MEDIUM] B2-INDEX-007: Missing HNSW index on pattern_library_entries.embedding after type fix

**File**: `alembic/versions/021_fix_pattern_embedding_type.py`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# alembic/versions/021_fix_pattern_embedding_type.py:19-27
def upgrade() -> None:
    # Convert LargeBinary to Vector(768)
    op.alter_column(
        "pattern_library_entries",
        "embedding",
        type_=Vector(768),
        postgresql_using="embedding::vector(768)",
        existing_nullable=True,
    )
    # No HNSW index created after type conversion
```
**Description**: Migration 021 correctly converted the `pattern_library_entries.embedding` column from `LargeBinary` to `Vector(768)`. However, unlike the `evidence_fragments` table (which has an HNSW index created in migration 001), no HNSW index was created on `pattern_library_entries.embedding`. The `evidence_fragments` table correctly has: `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`, but the pattern library table lacks an equivalent index.
**Risk**: Cosine similarity searches on the pattern library will perform sequential scans instead of using approximate nearest neighbor search. With a growing pattern library, this will become increasingly slow.
**Recommendation**: Create a new migration that adds: `CREATE INDEX ix_pattern_library_entries_embedding ON pattern_library_entries USING hnsw (embedding vector_cosine_ops)`.

---

## LOW Findings

### [LOW] B2-NULLABLE-008: JSON columns default to list/dict in ORM but accept NULL in database

**File**: `src/core/models/engagement.py:66`, `src/core/models/pov.py:124`, `src/core/models/monitoring.py:287`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/core/models/engagement.py:66
team: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

# src/core/models/pov.py:124
evidence_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

# src/core/models/monitoring.py:287
deviation_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
```
**Description**: Multiple JSON columns specify `default=list` (or `default=dict`) at the ORM level but are `nullable=True` at the database level with no `server_default`. This means ORM-created rows get `[]`, but rows inserted by raw SQL, migrations, or external tools get `NULL`. Application code must handle both `None` and `[]` for the same semantic concept of "empty list," adding defensive checks throughout.
**Risk**: Inconsistency between ORM-created and SQL-created rows. Code like `len(control.linked_policy_ids)` will raise `TypeError` on NULL rows. PostgreSQL JSON operators (`->`, `->>`, `jsonb_array_length`) return NULL on NULL input, not 0.
**Recommendation**: Add `server_default="'[]'"` (for list columns) or `server_default="'{}'"` (for dict columns) to these JSON columns to ensure the database always provides a non-NULL default. Then change `nullable=True` to `nullable=False`.

---

### [LOW] B2-DIMENSION-009: Embedding dimension 768 hardcoded in 4 separate locations

**File**: `src/core/models/evidence.py:165`, `src/core/models/pattern.py:42`, `src/rag/embeddings.py:19`, `alembic/versions/001_enable_pgvector_and_create_core_tables.py:116`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/core/models/evidence.py:165
embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

# src/core/models/pattern.py:42
embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

# src/rag/embeddings.py:19
EMBEDDING_DIMENSION = 768
```
**Description**: The embedding dimension 768 is specified as a literal in the two ORM model files and in the migration, and as a named constant in `src/rag/embeddings.py`. The `EMBEDDING_DIMENSION` constant exists but is not used by the model definitions. If the embedding model changes (e.g., to 1536-dimension), four files must be updated simultaneously.
**Risk**: Low -- the dimension is stable for the current `all-mpnet-base-v2` model. But a model upgrade that changes dimensions requires coordinated updates across models, migrations, and the service layer.
**Recommendation**: Reference `EMBEDDING_DIMENSION` from the model definitions instead of literal 768, and document the dimension choice in the PRD or architecture docs.

---

### [LOW] B2-SUCCESSMETRIC-010: SuccessMetric table is not engagement-scoped

**File**: `src/core/models/monitoring.py:78-95`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/core/models/monitoring.py:78-95
class SuccessMetric(Base):
    __tablename__ = "success_metrics"
    __table_args__ = (UniqueConstraint("name", "category", name="uq_success_metric_name_category"),)
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(100), nullable=False)
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    # No engagement_id column
```
**Description**: The `SuccessMetric` table defines global metric definitions (name, unit, target_value, category) without an `engagement_id` column. This is intentionally a shared reference table -- metric definitions are reused across engagements, and `MetricReading` links specific readings to both a metric and an engagement. However, this design means that if different engagements need different target values for the same metric (e.g., "Average Cycle Time" with different targets per engagement), it is not possible without creating duplicate metric definitions.
**Risk**: Low -- the design is intentional and `MetricReading` properly scopes readings to engagements. However, the unique constraint `(name, category)` prevents engagement-specific metric targets.
**Recommendation**: Document the design decision that `SuccessMetric` is a shared catalog. If engagement-specific targets are needed in the future, consider adding a `MetricTarget` junction table with `(metric_id, engagement_id, target_value)`.

---

## Architecture Notes (Informational)

### Migration Chain (029 migrations)
```
001 -> 002 -> 003 -> 004 -> 005 -> 006 -> 007 -> 008 -> 009 -> 010
  -> 011 -> 012 -> 013 -> 014 -> 015 -> 016 -> 017 -> 018 -> 019
  -> 020 -> 021 -> 022 -> 023 -> 024 -> 025 -> 026 -> 027 -> 028 -> 029
```
Chain is fully linear with no branches or gaps. All `down_revision` values correctly point to the previous migration.

### FK Cascade Coverage (61 total FK definitions across all models including consent.py)

| ondelete Policy | Count | Percentage |
|----------------|-------|------------|
| CASCADE | 43 | 70% |
| SET NULL | 16 | 26% |
| Missing (RESTRICT) | 0 | 0% |
| No FK (String ref) | 2 | 3% (lineage_id, engagement_id on HttpAuditEvent) |

All ForeignKey definitions now have explicit `ondelete` policies. The two exceptions are:
- `EvidenceItem.lineage_id`: bare UUID, no FK constraint (by design -- lineage record may not exist yet)
- `HttpAuditEvent.engagement_id`: String(36), intentionally not a FK (audit events must survive engagement deletion)

### ORM Cascade Coverage

| Parent Model | ORM cascade configured | Child tables with DB-only cascade |
|-------------|----------------------|----------------------------------|
| Engagement | 3 (evidence_items, audit_logs, shelf_data_requests) | 15+ tables (policies, controls, regulations, TOMs, monitoring, simulation, conformance, task mining, etc.) |
| User | 2 (engagement_memberships, consents) | 1 (mcp_api_keys) |
| ProcessModel | 3 (elements, contradictions, evidence_gaps) | 0 |
| SimulationScenario | 1 (modifications) | 3 (results, epistemic_actions, suggestions) |
| SuccessMetric | 1 (readings) | 0 |
| TaskMiningAgent | 1 (sessions) | 1 (consent_records) |

### Neo4j Security Posture
- Label validation: GOOD -- checked against ontology-loaded `VALID_NODE_LABELS`
- Relationship type validation: GOOD -- checked against `VALID_RELATIONSHIP_TYPES`
- Value parameterization: GOOD -- all values passed as `$parameters`
- Property key sanitization: GOOD -- `_validate_property_keys()` with regex `^[a-zA-Z_][a-zA-Z0-9_]*$`
- Write transactions: GOOD -- uses `execute_write()`
- Read transactions: GOOD -- now uses `execute_read()` (fixed since previous audit)
- Graph data cleanup on engagement deletion: MISSING -- see B2-NEO4J-001

### pgvector Consistency
- Dimension: 768 everywhere (consistent across models, migrations, and service)
- HNSW index on `evidence_fragments.embedding`: Present (good)
- HNSW index on `pattern_library_entries.embedding`: MISSING (column type fixed, but index never added)
- Cosine distance operator: correctly used in `embeddings.py` search queries

### Data Integrity Posture Score

| Category | Score | Notes |
|----------|-------|-------|
| FK Constraints | 9/10 | All FKs have ondelete; JSON array refs lack integrity |
| Migration Chain | 10/10 | Linear, no gaps, no branches |
| Index Coverage | 8/10 | Missing HNSW on patterns; all FK indexes present |
| ORM-Migration Alignment | 8/10 | consent_records type mismatch |
| Neo4j Integrity | 7/10 | No graph cleanup on engagement deletion |
| Data Validation | 6/10 | No CHECK constraints on scores/confidence |
| **Overall** | **8.0/10** | Significant improvement from previous audit |
