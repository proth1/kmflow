# B2: Data Integrity Audit Findings (Fourth Audit)

**Agent**: B2 (Data Integrity Auditor)
**Scope**: Database schema design, FK constraints, cascade deletes, migration chain integrity, Neo4j graph model, pgvector usage
**Date**: 2026-03-19
**Previous Audits**: 2026-02-20 (13 findings), 2026-02-26 (10 findings), 2026-03-19 v3 (14 findings)

## Remediation Status from Third Audit

| Previous Finding | Severity | Status |
|-----------------|----------|--------|
| B2-PHANTOM-011: search_similar() queries non-existent table | CRITICAL | **RESOLVED** -- query now correctly references `evidence_fragments` with proper JOIN |
| B2-NEO4J-001: Graph cleanup method never called | HIGH | **RESOLVED** -- now invoked from both `retention.py:90` and `engagements.py:293` |
| B2-MODEL-002: ConsentRecord model-migration type mismatch | HIGH | Open -- no change observed |
| B2-PDPAUDIT-012: PDPAuditEntry.policy_id has no FK | MEDIUM | **PARTIALLY FIXED** -- `index=True` added to model, still no FK constraint |
| B2-ORPHAN-003: JSON array columns store FK references | MEDIUM | Open -- accepted risk, documented |
| B2-ORM-004: Engagement lacks ORM cascade for 15+ children | MEDIUM | Open -- accepted risk, DB cascade works |
| B2-CHECK-005: No CHECK constraints on score columns | MEDIUM | Open -- no change |
| B2-ACTOR-006: Actor columns use String instead of FK | MEDIUM | Open -- accepted risk, documented |
| B2-INDEX-007: Missing HNSW on pattern_library_entries | MEDIUM | Open -- no change |
| B2-PIPELINE-013: pipeline_quality models omit explicit nullable=False | LOW | Open -- style inconsistency |
| B2-NULLABLE-008: JSON columns default mismatch | LOW | Open -- no change |
| B2-DIMENSION-009: Hardcoded 768 dimension | LOW | Open -- accepted risk |
| B2-SUCCESSMETRIC-010: Not engagement-scoped | LOW | Open -- by design |

**Resolved since last audit**: 2 fully resolved, 1 partially addressed
**New findings in this audit**: 3

---

## Summary (Fourth Audit)

| Severity | New | Carried Forward | Total |
|----------|-----|-----------------|-------|
| CRITICAL | 0   | 0               | 0     |
| HIGH     | 1   | 1               | 2     |
| MEDIUM   | 1   | 5               | 6     |
| LOW      | 1   | 4               | 5     |
| **Total** | **3** | **10**       | **13** |

---

## NEW Findings

### [HIGH] B2-RLS-014: 33+ engagement-scoped tables missing from RLS policy list

**File**: `src/core/rls.py:42-79`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/core/rls.py:42-79
ENGAGEMENT_SCOPED_TABLES: list[str] = [
    "annotations",
    "audit_logs",
    "case_link_edges",
    # ... 31 tables total
    "visual_context_events",
]
# Missing from this list but have engagement_id FK:
# review_packs, dark_room_snapshots, gap_findings, compliance_assessments,
# control_effectiveness_scores, incidents, reports, raci_cells, ...
```
**Description**: The `ENGAGEMENT_SCOPED_TABLES` list in `rls.py` contains 31 tables that receive Row-Level Security policies. However, a cross-reference of all SQLAlchemy models with `ForeignKey("engagements.id")` reveals at least 33 additional tables that have a non-nullable `engagement_id` column but are NOT in the RLS list. These include security-sensitive tables such as:

- `incidents` (security incidents)
- `review_packs` and `validation_decisions` (SME review workflows)
- `gap_findings` and `compliance_assessments` (compliance data)
- `dark_room_snapshots` (engagement state snapshots)
- `raci_cells` and `role_activity_mappings` (role assignments)
- `incidents` and `incident_events` (incident response)
- `transfer_impact_assessments`, `standard_contractual_clauses`, `data_transfer_log` (GDPR transfer records)
- `data_processing_activities`, `retention_policies` (GDPR processing records)
- `pipeline_stage_metrics`, `copilot_feedback`, `golden_eval_results`, `graph_health_snapshots` (quality metrics)
- `uplift_projections`, `canonical_activity_events`, `tom_alignment_runs`, `transformation_roadmaps`
- `maturity_scores`, `illumination_actions`, `survey_sessions`, `ontology_versions`
- `rejection_feedback`, `micro_surveys`, `grading_snapshots`, `assessment_matrix_entries`
- `export_logs`, `pdp_audit_entries`

The comment in rls.py explains some exclusions (nullable engagement_id, junction tables), but the majority of these tables have non-nullable `engagement_id` with `ondelete="CASCADE"` -- they are fully engagement-scoped and should have RLS policies.

**Risk**: Without RLS policies, a database connection that bypasses the application layer (or a compromised session without proper engagement context) could access data across engagement boundaries. For tables like `incidents`, `compliance_assessments`, and `transfer_impact_assessments`, this represents a cross-engagement data leak of sensitive compliance and security data. This undermines the multi-tenant isolation model.
**Recommendation**: Add all tables with non-nullable `engagement_id` FK to `ENGAGEMENT_SCOPED_TABLES`. For the few with nullable engagement_id (`export_logs` uses `ondelete="RESTRICT"`, `golden_eval_queries` uses `SET NULL`), document the explicit exclusion rationale. Consider generating the list programmatically from model introspection to prevent drift.

---

### [MEDIUM] B2-DEPTH-015: Neo4j traversal depth parameter interpolated into Cypher string

**File**: `src/semantic/graph.py:535-539`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# src/semantic/graph.py:535-539
query = f"""
MATCH (start {{id: $start_id}})-[r{rel_filter}*1..{depth}]-(connected)
RETURN DISTINCT connected, labels(connected) AS labels
LIMIT $limit
"""
```
**Description**: The `traverse()` method uses an f-string to interpolate the `depth` parameter directly into the Cypher query string. While `depth` is typed as `int` in the function signature and Neo4j's variable-length relationship syntax (`*1..N`) does not accept parameters, the value is not validated against an upper bound. A caller passing `depth=100` or `depth=999` would create an extremely expensive combinatorial traversal query that could overwhelm Neo4j.

The method checks `depth < 1` (line 525) but does not enforce an upper bound. The `rel_filter` is built from validated relationship types (line 530-532) and is safe from injection, but `depth` has no ceiling.

**Risk**: An API caller could trigger a denial-of-service on Neo4j by requesting a deep traversal (e.g., `depth=50` on a densely connected graph). While the `LIMIT $limit` clause (default 200) bounds the result set, Neo4j still must evaluate the full traversal pattern before applying LIMIT. This is a resource exhaustion vector, not an injection vector.
**Recommendation**: Add an upper bound check: `if depth > 10: depth = 10` (or raise ValueError). The default of 2 is appropriate for most use cases. An upper bound of 5-10 covers all reasonable graph exploration scenarios. This follows the same defensive pattern as the `limit=500` guard already present on `find_nodes()`.

---

### [LOW] B2-CONSENT-016: ConsentRecord.consent_type ORM-migration type drift persists (3 audits)

**File**: `src/taskmining/consent.py:69` vs `alembic/versions/028_create_consent_records_table.py:37`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
# ORM model (src/taskmining/consent.py:69)
consent_type: Mapped[ConsentType] = mapped_column(Enum(ConsentType), nullable=False)

# Migration (alembic/versions/028_create_consent_records_table.py:37)
sa.Column("consent_type", sa.String(50), nullable=False),
```
**Description**: This finding has been open since the second audit (2026-02-26, originally B2-MODEL-002). The ORM model defines `consent_type` as a PostgreSQL `ENUM` type, but the migration creates it as `String(50)`. SQLAlchemy will emit `INSERT` statements that store the enum value as a string, which works at the DB level because `String(50)` accepts any string. However, the ORM's `Enum()` type adapter performs Python-side validation that the value is a member of `ConsentType`. If raw SQL is ever used to insert rows (e.g., migration data seeds, admin scripts), non-enum values could be stored.

Downgrading from HIGH to LOW because: (1) the application works correctly at runtime since SQLAlchemy serializes enum values to strings, (2) the risk is limited to manual/raw SQL insertions, and (3) there are no reported incidents after 3 audit cycles.

**Risk**: The drift means the database schema does not enforce the enum constraint. Raw SQL inserts could store invalid values that the ORM would reject on read.
**Recommendation**: Create a migration that alters `consent_type` from `String(50)` to a proper PostgreSQL ENUM type, or change the ORM to use `String(50)` to match the migration. Given this has been open for 3 audits, the latter approach (aligning ORM to match DB) is lowest risk.

---

## Carried Forward Findings

The following findings from previous audits remain open. They are summarized here with updated status notes.

### [HIGH] B2-MODEL-002: ConsentRecord model-migration type mismatch (NOW B2-CONSENT-016)
**Status**: Reclassified as LOW (B2-CONSENT-016 above). No functional impact demonstrated across 3 audit cycles.

### [MEDIUM] B2-ORPHAN-003: JSON array columns store FK references without integrity (UNCHANGED)
**File**: Multiple models (governance, pov, monitoring, tom, simulation)
**Status**: Open. `deviation_ids`, `depends_on_ids`, `rejected_suggestion_ids`, `linked_policy_ids`, `evidence_ids` remain as JSON arrays. Accepted risk -- these are denormalized for query convenience.

### [MEDIUM] B2-ORM-004: Engagement lacks ORM cascade for 15+ children (UPDATED)
**Status**: Open. With the addition of 6 pipeline_quality tables (migration 087), the gap has grown to approximately 27+ child tables relying on DB-only cascade without ORM `cascade="all, delete-orphan"` or `passive_deletes=True`. The Engagement model only has ORM cascades for `evidence_items`, `audit_logs`, and `shelf_data_requests`.

### [MEDIUM] B2-CHECK-005: No CHECK constraints on score/confidence columns (UNCHANGED)
**Status**: Open. GoldenEvalResult adds 6 more unconstrained float score columns.

### [MEDIUM] B2-ACTOR-006: Actor columns use String instead of FK (UNCHANGED)
**Status**: Open. No new instances added.

### [MEDIUM] B2-INDEX-007: Missing HNSW on pattern_library_entries.embedding (UNCHANGED)
**Status**: Open. No new migration added.

### [LOW] B2-PDPAUDIT-012: PDPAuditEntry.policy_id has no FK (PARTIALLY FIXED)
**Status**: Index added (`index=True` on line 165 of pdp.py, migration 088 creates `ix_pdp_audit_entries_policy_id`). Still no FK constraint. Downgrading to LOW since the index addresses query performance and the lack of FK is appropriate for an audit table.

### [LOW] B2-PIPELINE-013: pipeline_quality models omit explicit nullable=False (UNCHANGED)
**Status**: Open. Style inconsistency only. SQLAlchemy 2.x infers correctly from `Mapped[T]`.

### [LOW] B2-NULLABLE-008: JSON columns default mismatch (UNCHANGED)
**Status**: Open.

### [LOW] B2-DIMENSION-009: Hardcoded 768 dimension (UNCHANGED)
**Status**: Open. Accepted risk.

---

## Architecture Notes (Updated)

### Migration Chain (088 migrations)
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
  -> 083 -> 084 -> 085 -> 086 -> 087 -> 088
```
Chain is fully linear with no branches or gaps. All `down_revision` values correctly point to the previous migration.

### FK Cascade Coverage

All ForeignKey definitions across all 40+ model files specify explicit `ondelete` policies. Zero missing `ondelete` constraints detected.

| ondelete Policy | Count |
|----------------|-------|
| CASCADE | ~58 |
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
- `search_similar()` in graph.py: FIXED -- now queries correct table with proper JOIN
- Traversal depth: CONCERN -- no upper bound on depth parameter (B2-DEPTH-015)
- Defensive null-handling: IN PROGRESS -- `graph_health.py` modified to handle null records

### pgvector Consistency
- Dimension: 768 consistent across all models, migrations, and embedding service
- HNSW index on `evidence_fragments.embedding`: Present (migration 001)
- HNSW index on `pattern_library_entries.embedding`: MISSING
- `EmbeddingService.search_similar()` in `embeddings.py`: Correct, queries `evidence_fragments`
- `KnowledgeGraphService.search_similar()` in `graph.py`: FIXED, now correctly queries `evidence_fragments`

### RLS Coverage Gap (NEW)
31 tables have RLS policies via `ENGAGEMENT_SCOPED_TABLES`. 33+ tables with `engagement_id` FK are missing from this list. See B2-RLS-014 for full details.

### Data Integrity Posture Score

| Category | Score | Change | Notes |
|----------|-------|--------|-------|
| FK Constraints | 9/10 | -- | JSON array refs still lack integrity; 2 bare UUIDs |
| Migration Chain | 10/10 | -- | Linear, no gaps, 088 migrations |
| Index Coverage | 8/10 | +0.5 | pdp_audit index added; HNSW on patterns still missing |
| ORM-Migration Alignment | 9/10 | +1 | consent_records only remaining drift (downgraded to LOW) |
| Neo4j Integrity | 8/10 | +3 | search_similar fixed; cleanup integrated; depth unbounded |
| Data Validation | 6/10 | -- | No CHECK constraints on scores/confidence |
| RLS Coverage | 5/10 | NEW | 33+ tables missing RLS policies |
| **Overall** | **7.9/10** | +0.2 | Improved from graph fixes; RLS gap is new concern |
