# B2: Data Integrity Audit Findings (Fifth Audit)

**Agent**: B2 (Data Integrity Auditor)
**Scope**: Database schema design, FK constraints, cascade deletes, migration chain integrity, Neo4j graph model, pgvector usage, dual-write consistency
**Date**: 2026-03-20
**Previous Audits**: 2026-02-20 (13 findings), 2026-02-26 (10 findings), 2026-03-19 v3 (14 findings), 2026-03-19 v4 (13 findings)

## Remediation Status from Fourth Audit

| Previous Finding | Severity | Status |
|-----------------|----------|--------|
| B2-RLS-014: 33+ tables missing from RLS policy list | HIGH | **RESOLVED** -- RLS list expanded from 31 to 66 tables; 2 tables still missing (see B2-RLS-017) |
| B2-DEPTH-015: Neo4j traversal depth unbounded | MEDIUM | **RESOLVED** -- `graph.py:534` now caps `depth > 10` to 10 |
| B2-CONSENT-016: ConsentRecord ORM-migration type drift | LOW | Open -- no change (4th audit cycle) |
| B2-ORPHAN-003: JSON array columns store FK references | MEDIUM | Open -- accepted risk |
| B2-ORM-004: Engagement lacks ORM cascade for 27+ children | MEDIUM | Open -- accepted risk |
| B2-CHECK-005: No CHECK constraints on score columns | MEDIUM | Open -- no change |
| B2-ACTOR-006: Actor columns use String instead of FK | MEDIUM | Open -- no change |
| B2-INDEX-007: Missing HNSW on pattern_library_entries | MEDIUM | **RESOLVED** -- migration 090 adds HNSW index with `vector_cosine_ops` |
| B2-PDPAUDIT-012: PDPAuditEntry.policy_id has no FK | LOW | Open -- index present, no FK (by design for audit table) |
| B2-PIPELINE-013: pipeline_quality models omit explicit nullable=False | LOW | Open -- style inconsistency |
| B2-NULLABLE-008: JSON columns default mismatch | LOW | Open -- no change |
| B2-DIMENSION-009: Hardcoded 768 dimension | LOW | Open -- accepted risk |
| B2-SUCCESSMETRIC-010: Not engagement-scoped | LOW | Open -- by design |

**Resolved since last audit**: 3 fully resolved (RLS expanded, depth capped, HNSW index added)
**New findings in this audit**: 3

---

## Summary (Fifth Audit)

| Severity | New | Carried Forward | Total |
|----------|-----|-----------------|-------|
| CRITICAL | 0   | 0               | 0     |
| HIGH     | 1   | 0               | 1     |
| MEDIUM   | 1   | 3               | 4     |
| LOW      | 1   | 5               | 6     |
| **Total** | **3** | **8**        | **11** |

---

## NEW Findings

### [HIGH] B2-RLS-017: 2 engagement-scoped tables missing from RLS policy list

**File**: `src/core/rls.py:42-113`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/core/models/cost_volume.py:26-34
class RoleRateAssumption(Base):
    __tablename__ = "role_rate_assumptions"
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )

# src/core/models/cost_volume.py:51-56
class VolumeForecast(Base):
    __tablename__ = "volume_forecasts"
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
```
**Description**: Two tables with non-nullable `engagement_id` FK and `ondelete="CASCADE"` are missing from the `ENGAGEMENT_SCOPED_TABLES` RLS list:

1. `role_rate_assumptions` -- contains hourly/annual rate data per role per engagement
2. `volume_forecasts` -- contains baseline transaction volumes with seasonal factors

The RLS list was significantly expanded since the last audit (from 31 to 66 tables), resolving the bulk of B2-RLS-014. However, these two cost-volume tables (added in migration 078) were not included.

Note: `incident_events` does not have a direct `engagement_id` FK (it has `incident_id` FK to `incidents` which is engagement-scoped), so it is correctly omitted -- RLS on the parent `incidents` table provides indirect coverage. Similarly, `dual_write_failures` has no `engagement_id` (by design -- it's a cross-engagement compensation table) and is correctly excluded.

**Risk**: Without RLS, a database connection bypassing the application layer could access cost/rate data across engagement boundaries. Financial rate assumptions (hourly rates, volume forecasts) are competitively sensitive -- leaking client-specific cost models across engagements is a confidentiality concern.
**Recommendation**: Add `"role_rate_assumptions"` and `"volume_forecasts"` to `ENGAGEMENT_SCOPED_TABLES` in `src/core/rls.py` and create a migration to apply the RLS policies.

---

### [MEDIUM] B2-DUALWRITE-018: DualWriteFailure compensation job not implemented

**File**: `src/core/models/dual_write_failure.py:20-36`, `src/semantic/claim_write_back.py:167-181`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/core/models/dual_write_failure.py:20-22
class DualWriteFailure(Base):
    """Track failed dual-writes for compensation retry."""
    __tablename__ = "dual_write_failures"

# src/semantic/claim_write_back.py:174-180
failure = DualWriteFailure(
    source_table="survey_claims",
    source_id=str(claim.id),
    target="neo4j",
    error_message=str(exc)[:500],
)
self._session.add(failure)
```
**Description**: The `DualWriteFailure` model and table (migration 092) correctly capture failed Neo4j writes during claim ingestion and conflict creation. The `retried` boolean and `created_at` columns are indexed for efficient retrieval. However, there is no compensation job that reads unretried failures and replays them to Neo4j.

The write-back service (`claim_write_back.py`) records failures at lines 174-180 (claim writes) and 356-362 (conflict writes), but the `retried` column is never set to `True` anywhere in the codebase -- no retry mechanism exists.

**Risk**: If a Neo4j write fails (network blip, Neo4j restart), the data divergence between PostgreSQL and Neo4j is permanent. Survey claims will exist in PostgreSQL but lack corresponding nodes/edges in the knowledge graph. This creates silent data inconsistency that degrades confidence scoring, conflict detection, and graph-based analytics.
**Recommendation**: Implement a periodic compensation job (e.g., Celery task or scheduled endpoint) that:
1. Queries `DualWriteFailure` where `retried = false` and `created_at > now() - interval '7 days'`
2. Re-executes the Neo4j write based on `source_table` and `source_id`
3. Sets `retried = true` on success
4. Logs and alerts on repeated failures

---

### [LOW] B2-EVALRUN-019: GoldenEvalResult.eval_run_id has no FK constraint

**File**: `src/core/models/pipeline_quality.py:114`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/core/models/pipeline_quality.py:114
eval_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
```
**Description**: `GoldenEvalResult.eval_run_id` is a bare UUID with no ForeignKey constraint. There is no `eval_runs` table -- the eval_run_id is an application-generated batch identifier. While this is a valid pattern for batch/run grouping, it means:
1. Any UUID value can be stored, including non-existent or duplicate run IDs
2. There is no cascade behavior when a "run" is conceptually deleted
3. Queries grouping by `eval_run_id` have no referential integrity backing

This was noted in the fourth audit under FK cascade coverage ("Bare UUID: GoldenEvalResult.eval_run_id") and remains unchanged.

**Risk**: Low -- eval_run_id is used as a grouping key for batch evaluation results, not as a true FK. The index `ix_golden_eval_results_eval_run_id` provides query performance.
**Recommendation**: Consider creating a lightweight `eval_runs` table with `id`, `engagement_id`, `created_at`, and `status` columns to formalize the run concept and enable cascade cleanup. Alternatively, document the pattern as intentional.

---

## Carried Forward Findings

### [MEDIUM] B2-ORPHAN-003: JSON array columns store FK references without integrity (UNCHANGED)
**File**: Multiple models (governance, pov, monitoring, tom, simulation)
**Status**: Open. `deviation_ids`, `depends_on_ids`, `rejected_suggestion_ids`, `linked_policy_ids`, `evidence_ids` remain as JSON arrays. Accepted risk -- these are denormalized for query convenience.

### [MEDIUM] B2-ORM-004: Engagement lacks ORM cascade for 27+ children (UNCHANGED)
**Status**: Open. The Engagement model only has ORM cascades for `evidence_items`, `audit_logs`, and `shelf_data_requests`. All other child tables rely on database-level `ondelete="CASCADE"`. This works correctly in PostgreSQL but means the ORM session cache won't be updated on cascade deletes.

### [MEDIUM] B2-CHECK-005: No CHECK constraints on score/confidence columns (UNCHANGED)
**Status**: Open. 30+ float score/confidence columns across models lack `CheckConstraint("col BETWEEN 0.0 AND 1.0")`. GoldenEvalResult adds 6 more unconstrained float columns.

### [LOW] B2-CONSENT-016: ConsentRecord model-migration type drift (4th audit cycle)
**File**: `src/taskmining/consent.py:69` vs `alembic/versions/028_create_consent_records_table.py:37`
**Status**: Open. ORM defines `Enum(ConsentType)`, migration uses `String(50)`. No functional impact demonstrated across 4 audit cycles.

### [LOW] B2-PDPAUDIT-012: PDPAuditEntry.policy_id has no FK (UNCHANGED)
**Status**: Open. Index present, no FK. Appropriate for an audit table that should survive policy deletion.

### [LOW] B2-PIPELINE-013: pipeline_quality models omit explicit nullable=False (UNCHANGED)
**Status**: Open. Style inconsistency only. SQLAlchemy 2.x infers correctly from `Mapped[T]`.

### [LOW] B2-NULLABLE-008: JSON columns default mismatch (UNCHANGED)
**Status**: Open.

### [LOW] B2-DIMENSION-009: Hardcoded 768 dimension (UNCHANGED)
**Status**: Open. Accepted risk. Consistent across `evidence_fragments`, `pattern_library_entries`, and `EMBEDDING_DIMENSION` constant.

---

## Architecture Notes (Updated)

### Migration Chain (92 migrations)
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
  -> 083 -> 084 -> 085 -> 086 -> 087 -> 088 -> 089 -> 090 -> 091
  -> 092
```
Chain is fully linear with no branches or gaps. All `down_revision` values correctly point to the previous migration. New migrations since last audit:
- **089**: Make `llm_audit_logs.scenario_id` nullable (schema alignment)
- **090**: Add HNSW index on `pattern_library_entries.embedding` (resolves B2-INDEX-007)
- **091**: Add `data_processing_agreements` table with RLS (GDPR Article 28)
- **092**: Add `dual_write_failures` table (cross-store compensation tracking)

### FK Cascade Coverage

All ForeignKey definitions across all 40+ model files specify explicit `ondelete` policies. Zero missing `ondelete` constraints detected.

| ondelete Policy | Count |
|----------------|-------|
| CASCADE | ~60 |
| SET NULL | ~19 |
| RESTRICT | ~4 (gdpr, export_log) |
| Bare UUID (no FK) | 2 (GoldenEvalResult.eval_run_id, PDPAuditEntry.policy_id) |
| String-based refs | 6+ (actor, author_id, acknowledged_by, etc.) |

### Neo4j Security Posture
- Label validation: GOOD -- ontology-loaded `VALID_NODE_LABELS` whitelist
- Relationship type validation: GOOD -- `VALID_RELATIONSHIP_TYPES` whitelist
- Value parameterization: GOOD -- all values via `$parameters`
- Property key sanitization: GOOD -- `_validate_property_keys()` regex
- Write transactions: GOOD -- `execute_write()`
- Read transactions: GOOD -- `execute_read()`
- Graph cleanup on engagement delete: GOOD -- called from retention.py and engagements.py
- `search_similar()` in graph.py: GOOD -- queries correct table with proper JOIN
- Traversal depth: GOOD -- capped at 10 (`graph.py:534`)
- Edge constraint validation: GOOD -- `EdgeConstraintValidator` with ontology-backed endpoint checks, acyclicity enforcement, and bidirectional edge creation

### Dual-Write Consistency
- **Recording**: GOOD -- `DualWriteFailure` model captures failed Neo4j writes with source_table, source_id, target, error_message
- **Indexed for retrieval**: GOOD -- composite indexes on (source_table, source_id) and (retried, created_at)
- **Write paths covered**: `claim_write_back.py` records failures for both claim ingestion and conflict creation
- **Compensation**: MISSING -- no retry/replay job exists (see B2-DUALWRITE-018)

### pgvector Consistency
- Dimension: 768 consistent across all models, migrations, and embedding service (`EMBEDDING_DIMENSION = 768`)
- HNSW index on `evidence_fragments.embedding`: Present (migration 001)
- HNSW index on `pattern_library_entries.embedding`: PRESENT (migration 090) -- resolved B2-INDEX-007
- `EmbeddingService.search_similar()` in `embeddings.py`: Correct, queries `evidence_fragments`
- `KnowledgeGraphService.search_similar()` in `graph.py`: Correct, queries `evidence_fragments`

### RLS Coverage (Significantly Improved)
66 tables have RLS policies via `ENGAGEMENT_SCOPED_TABLES`. 2 tables with non-nullable `engagement_id` FK are missing (see B2-RLS-017). Correctly excluded tables:
- `success_metrics`: no engagement_id (global metric definitions)
- `dual_write_failures`: no engagement_id (cross-engagement compensation)
- `incident_events`: no direct engagement_id (covered by parent `incidents` RLS)
- `engagement_members`: junction table (documented exclusion)
- `alternative_suggestions`: nullable engagement_id (documented exclusion)
- `pattern_library_entries`: uses `source_engagement_id` different column name (documented exclusion)
- `http_audit_events`: string engagement_id, no FK (documented exclusion)

### Data Integrity Posture Score

| Category | Score | Change | Notes |
|----------|-------|--------|-------|
| FK Constraints | 9/10 | -- | JSON array refs still lack integrity; 2 bare UUIDs |
| Migration Chain | 10/10 | -- | Linear, no gaps, 92 migrations |
| Index Coverage | 9/10 | +1 | HNSW on patterns resolved; all critical paths indexed |
| ORM-Migration Alignment | 9/10 | -- | consent_records only remaining drift (LOW) |
| Neo4j Integrity | 9/10 | +1 | Traversal depth capped; edge validation in place |
| Data Validation | 6/10 | -- | No CHECK constraints on scores/confidence |
| RLS Coverage | 9/10 | +4 | 66/68 engagement-scoped tables covered (was 31) |
| Dual-Write Consistency | 7/10 | NEW | Recording good; compensation job missing |
| **Overall** | **8.5/10** | +0.6 | Major improvements in RLS, Neo4j, and index coverage |
