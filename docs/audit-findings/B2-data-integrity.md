# B2: Data Integrity Audit Findings (Third Audit)

**Agent**: B2 (Data Integrity Auditor)
**Scope**: Database schema design, FK constraints, cascade deletes, migration chain integrity, Neo4j graph model, pgvector usage
**Date**: 2026-03-19
**Previous Audits**: 2026-02-20 (13 findings), 2026-02-26 (10 findings)

## Remediation Status from Second Audit (2026-02-26)

| Previous Finding | Severity | Status |
|-----------------|----------|--------|
| B2-NEO4J-001: Graph data not cleaned on engagement delete | HIGH | **PARTIALLY FIXED** -- `delete_engagement_subgraph()` method now exists but is never called from retention/deletion code paths |
| B2-MODEL-002: ConsentRecord model-migration type mismatch | HIGH | Open -- no change observed |
| B2-ORPHAN-003: JSON array columns store FK references | MEDIUM | Open -- accepted risk, documented |
| B2-ORM-004: Engagement lacks ORM cascade for 15+ children | MEDIUM | Open -- accepted risk, DB cascade works |
| B2-CHECK-005: No CHECK constraints on score columns | MEDIUM | Open -- no change |
| B2-ACTOR-006: Actor columns use String instead of FK | MEDIUM | Open -- accepted risk, documented |
| B2-INDEX-007: Missing HNSW on pattern_library_entries | MEDIUM | Open -- no change |
| B2-NULLABLE-008: JSON columns default mismatch | LOW | Open -- no change |
| B2-DIMENSION-009: Hardcoded 768 dimension | LOW | Open -- accepted risk |
| B2-SUCCESSMETRIC-010: Not engagement-scoped | LOW | Open -- by design |

**Resolved since last audit**: 0 fully resolved (1 partially addressed)
**New findings in this audit**: 4

---

## Summary (Third Audit)

| Severity | New | Carried Forward | Total |
|----------|-----|-----------------|-------|
| CRITICAL | 1   | 0               | 1     |
| HIGH     | 1   | 2               | 3     |
| MEDIUM   | 1   | 5               | 6     |
| LOW      | 1   | 3               | 4     |
| **Total** | **4** | **10**       | **14** |

---

## NEW Findings

### [CRITICAL] B2-PHANTOM-011: search_similar() queries non-existent `fragment_embeddings` table

**File**: `src/semantic/graph.py:587-594`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/semantic/graph.py:587-594
pgvector_query = text(
    "SELECT id, entity_id, entity_type, "
    "1 - (embedding <=> :embedding::vector) AS similarity "
    "FROM fragment_embeddings "
    "WHERE (:engagement_id IS NULL OR engagement_id = :engagement_id::uuid) "
    "ORDER BY embedding <=> :embedding::vector "
    "LIMIT :top_k"
)
```
**Description**: The `KnowledgeGraphService.search_similar()` method queries a table called `fragment_embeddings` that does not exist in any migration (001-087) or ORM model. The actual table is `evidence_fragments` (defined in `src/core/models/evidence.py:167`). Furthermore, the query references columns `entity_id`, `entity_type`, and `engagement_id` which do not exist on `evidence_fragments`. The correct columns are `evidence_id` (FK to evidence_items), `fragment_type`, and engagement_id must be resolved via a JOIN to `evidence_items`. This query will raise a `ProgrammingError: relation "fragment_embeddings" does not exist` at runtime.
**Risk**: Any code path that invokes `KnowledgeGraphService.search_similar()` with a `db_session` will crash with an unrecoverable database error. The semantic search functionality through the graph service is completely broken. The exception is caught by the broad `except Exception` on line 634, which returns `[]` silently -- masking the failure and returning no results.
**Recommendation**: Rewrite the query to use the correct table and column names:
```sql
SELECT ef.id, ef.evidence_id AS entity_id, ef.fragment_type AS entity_type,
       1 - (ef.embedding <=> :embedding::vector) AS similarity
FROM evidence_fragments ef
JOIN evidence_items ei ON ef.evidence_id = ei.id
WHERE (:engagement_id IS NULL OR ei.engagement_id = :engagement_id::uuid)
  AND ef.embedding IS NOT NULL
ORDER BY ef.embedding <=> :embedding::vector
LIMIT :top_k
```
Note: The separate `EmbeddingService.search_similar()` in `src/semantic/embeddings.py:160-218` correctly queries `evidence_fragments` and works properly.

---

### [HIGH] B2-NEO4J-001: Graph cleanup method exists but is never invoked (UPDATED)

**File**: `src/semantic/graph.py:663-680`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/semantic/graph.py:663-680 -- method exists
async def delete_engagement_subgraph(self, engagement_id: str) -> int:
    """Delete all nodes and relationships for an engagement."""
    query = """
    MATCH (n {engagement_id: $engagement_id})
    DETACH DELETE n
    RETURN count(n) AS deleted
    """
    # Never called from retention.py, engagement routes, or any other module
```
**Description**: The previous audit finding (B2-NEO4J-001 from 2026-02-26) reported that no graph cleanup method existed. The method `delete_engagement_subgraph()` has since been added to `KnowledgeGraphService`. However, a grep across the entire `src/` directory shows it is defined but never called. The engagement deletion and retention cleanup code paths in `src/core/retention.py` and `src/api/routes/engagements.py` still do not invoke this method.
**Risk**: Neo4j continues to accumulate orphaned graph data for deleted engagements. This violates GDPR data minimization requirements. The method exists as dead code -- the problem is integration, not implementation.
**Recommendation**: Call `await graph_service.delete_engagement_subgraph(str(engagement_id))` from both the retention cleanup function and the engagement archive/delete route, before committing PostgreSQL deletes.

---

### [MEDIUM] B2-PDPAUDIT-012: PDPAuditEntry.policy_id has no FK constraint

**File**: `src/core/models/pdp.py:165`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/core/models/pdp.py:165
policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
# No ForeignKey("pdp_policies.id", ondelete="SET NULL") -- bare UUID column
```
**Description**: The `PDPAuditEntry` model stores a `policy_id` that logically references `pdp_policies.id`, but it is defined as a bare `UUID` column without a `ForeignKey` constraint. Every other UUID reference column in the codebase that points to another table uses an explicit `ForeignKey()` with `ondelete` policy. This column is the only exception among audit/logging tables that reference a policy.
**Risk**: The `policy_id` column can hold any UUID, including references to deleted or non-existent policies. No index exists on this column either, so querying audit entries by policy requires a full table scan. While audit tables intentionally sometimes omit FKs (to survive parent deletion), this should be an explicit design decision.
**Recommendation**: If the intent is to preserve audit entries when policies are deleted (which is likely correct for an audit log), add an explicit comment documenting this design choice and add an index: `Index("ix_pdp_audit_policy_id", "policy_id")`. If referential integrity is desired, add `ForeignKey("pdp_policies.id", ondelete="SET NULL")`.

---

### [LOW] B2-PIPELINE-013: New pipeline_quality models omit explicit `nullable=False` on required columns

**File**: `src/core/models/pipeline_quality.py:40-54`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/core/models/pipeline_quality.py:40-54
engagement_id: Mapped[uuid.UUID] = mapped_column(
    UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE")
)  # Missing nullable=False
stage: Mapped[str] = mapped_column(String(50))  # Missing nullable=False
started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # Missing nullable=False
duration_ms: Mapped[float] = mapped_column(Float)  # Missing nullable=False
```
**Description**: The new `PipelineStageMetric`, `CopilotFeedback`, `GoldenEvalQuery`, `GoldenEvalResult`, `EntityAnnotation`, and `GraphHealthSnapshot` models in `pipeline_quality.py` omit the explicit `nullable=False` annotation on most required columns. While SQLAlchemy 2.x infers `nullable=False` from the `Mapped[T]` type annotation (non-Optional), the rest of the codebase consistently specifies `nullable=False` explicitly. The migration (087) correctly creates these as `NOT NULL`, so there is no actual database issue.
**Risk**: Low -- this is a style inconsistency, not a functional bug. The migration and ORM behavior are correct. However, the inconsistency makes the models harder to audit visually for nullability rules.
**Recommendation**: Add explicit `nullable=False` to match the project's established convention in all other model files.

---

## Carried Forward Findings

The following findings from the 2026-02-26 audit remain open. They are summarized here with updated status notes.

### [HIGH] B2-MODEL-002: ConsentRecord model-migration type mismatch (UNCHANGED)
**File**: `src/taskmining/consent.py:69` vs `alembic/versions/028_create_consent_records_table.py:37`
**Status**: Open. ORM defines `Enum(ConsentType)`, migration creates `String(50)`. No new migration to resolve the drift.

### [MEDIUM] B2-ORPHAN-003: JSON array columns store FK references without integrity (UNCHANGED)
**File**: Multiple models (governance, pov, monitoring, tom, simulation)
**Status**: Open. `deviation_ids`, `depends_on_ids`, `rejected_suggestion_ids`, `linked_policy_ids`, `evidence_ids` remain as JSON arrays. Count increased to 5 columns across 4 model files.

### [MEDIUM] B2-ORM-004: Engagement lacks ORM cascade for 15+ children (UPDATED)
**Status**: Open. With the addition of 6 new pipeline_quality tables (migration 087), the gap has grown to approximately 21+ child tables relying on DB-only cascade without ORM `passive_deletes=True`.

### [MEDIUM] B2-CHECK-005: No CHECK constraints on score/confidence columns (UNCHANGED)
**Status**: Open. New `GoldenEvalResult` model adds more unconstrained float score columns (`precision_at_5`, `recall_at_5`, etc.).

### [MEDIUM] B2-ACTOR-006: Actor columns use String instead of FK (UNCHANGED)
**Status**: Open. No new instances added.

### [MEDIUM] B2-INDEX-007: Missing HNSW on pattern_library_entries.embedding (UNCHANGED)
**Status**: Open. No new migration added.

### [LOW] B2-NULLABLE-008: JSON columns default mismatch (UNCHANGED)
**Status**: Open.

### [LOW] B2-DIMENSION-009: Hardcoded 768 dimension (UNCHANGED)
**Status**: Open.

### [LOW] B2-SUCCESSMETRIC-010: Not engagement-scoped (UNCHANGED)
**Status**: Open -- by design.

---

## Architecture Notes (Updated)

### Migration Chain (087 migrations)
```
001 -> 002 -> 003 -> 004 -> 005 -> 006 -> 007 -> 008 -> 009 -> 010
  -> 011 -> 012 -> 013 -> 014 -> 015 -> 016 -> 017 -> 018 -> 019
  -> 020 -> 021 -> 022 -> 023 -> 024 -> 025 -> 026 -> 027 -> 028
  -> 029 -> 030 -> 031 -> 032 -> 033 -> 034 -> 035 -> 036 -> 037
  -> 038 -> 039 -> 040 -> 041 -> 042 -> 043 -> 044 -> 045 -> 046
  -> 047 -> 048 -> 049 -> 050 -> 051 -> 052 -> 053 -> 054 -> 055
  -> 056 -> 057 -> 058 -> 059 -> 060 -> 061 -> 062 -> 063 -> 064
  -> 065 -> 066 -> 067 -> 068 -> 069 -> 070 -> 071 -> 072 -> 073
  -> 074 -> 075 -> 076 -> 077 -> 078 -> 079 -> 080 -> 081 -> 082
  -> 083 -> 084 -> 085 -> 086 -> 087
```
Chain is fully linear with no branches or gaps. All `down_revision` values correctly point to the previous migration.

### FK Cascade Coverage

All ForeignKey definitions across all 40+ model files specify explicit `ondelete` policies. Zero missing `ondelete` constraints detected.

| ondelete Policy | Approximate Count |
|----------------|-------------------|
| CASCADE | ~55 |
| SET NULL | ~18 |
| Missing FK (bare UUID) | 2 (EvidenceItem.lineage_id, PDPAuditEntry.policy_id) |
| String-based refs | 6+ (actor, author_id, acknowledged_by, etc.) |

### Neo4j Security Posture
- Label validation: GOOD -- ontology-loaded `VALID_NODE_LABELS` whitelist
- Relationship type validation: GOOD -- `VALID_RELATIONSHIP_TYPES` whitelist
- Value parameterization: GOOD -- all values via `$parameters`
- Property key sanitization: GOOD -- `_validate_property_keys()` regex
- Write transactions: GOOD -- `execute_write()`
- Read transactions: GOOD -- `execute_read()`
- Graph cleanup method: EXISTS but NEVER CALLED -- see B2-NEO4J-001
- `search_similar()`: BROKEN -- references non-existent table -- see B2-PHANTOM-011

### pgvector Consistency
- Dimension: 768 consistent across all models, migrations, and embedding service
- HNSW index on `evidence_fragments.embedding`: Present
- HNSW index on `pattern_library_entries.embedding`: MISSING
- `EmbeddingService.search_similar()` in `embeddings.py`: Correct, queries `evidence_fragments`
- `KnowledgeGraphService.search_similar()` in `graph.py`: BROKEN, queries non-existent `fragment_embeddings`

### RLS Coverage (New Tables)
Ontology tables (085) correctly implement RLS with engagement isolation policies. Pipeline quality tables (087) do NOT have RLS policies, relying on application-level filtering via `engagement_id` FK.

### Data Integrity Posture Score

| Category | Score | Change | Notes |
|----------|-------|--------|-------|
| FK Constraints | 9/10 | -- | JSON array refs still lack integrity; PDPAuditEntry.policy_id bare |
| Migration Chain | 10/10 | -- | Linear, no gaps, 087 migrations |
| Index Coverage | 8/10 | -- | Missing HNSW on patterns; all FK indexes present |
| ORM-Migration Alignment | 8/10 | -- | consent_records type mismatch persists |
| Neo4j Integrity | 5/10 | -2 | search_similar() queries phantom table; cleanup method uncalled |
| Data Validation | 6/10 | -- | No CHECK constraints on scores/confidence |
| **Overall** | **7.7/10** | -0.3 | Regression from phantom table reference in graph.py |
