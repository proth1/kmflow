# B2: Data Integrity Audit Findings (Seventh Audit)

**Agent**: architecture-reviewer (B2 Data Integrity)
**Scope**: Database schema design, FK constraints, cascade deletes, migration chain integrity, Neo4j graph model, pgvector usage, dual-write consistency, RLS completeness
**Date**: 2026-03-20
**Previous Audits**: 2026-02-20 (13), 2026-02-26 (10), 2026-03-19 v3 (14), 2026-03-19 v4 (13), 2026-03-19 v5 (11)

## Remediation Status from Previous Audit

| Previous Finding | Severity | Status |
|-----------------|----------|--------|
| B2-RLS-017: 2 engagement-scoped tables missing from RLS | HIGH | **RESOLVED** -- `role_rate_assumptions` and `volume_forecasts` now in `ENGAGEMENT_SCOPED_TABLES` (lines 93, 114) |
| B2-DUALWRITE-018: DualWriteFailure compensation job not implemented | MEDIUM | Open -- no retry/replay mechanism exists (see below) |
| B2-EVALRUN-019: GoldenEvalResult.eval_run_id has no FK | LOW | Open -- by design (batch grouping key) |
| B2-ORPHAN-003: JSON array columns store FK references | MEDIUM | Open -- accepted risk |
| B2-ORM-004: Engagement lacks ORM cascade for 27+ children | MEDIUM | Open -- accepted risk |
| B2-CHECK-005: No CHECK constraints on score columns | MEDIUM | Open -- no change |
| B2-ACTOR-006: Actor columns use String instead of FK | MEDIUM | Open -- no change |
| B2-CONSENT-016: ConsentRecord ORM-migration type drift | LOW | Open -- no change (5th audit cycle) |
| B2-PDPAUDIT-012: PDPAuditEntry.policy_id has no FK | LOW | Open -- by design |
| B2-PIPELINE-013: pipeline_quality models omit explicit nullable=False | LOW | Open -- style inconsistency |
| B2-NULLABLE-008: JSON columns default mismatch | LOW | Open -- no change |
| B2-DIMENSION-009: Hardcoded 768 dimension | LOW | Open -- accepted risk |
| B2-SUCCESSMETRIC-010: Not engagement-scoped | LOW | Open -- by design |

**Resolved since last audit**: 1 (B2-RLS-017)
**New findings in this audit**: 2

---

## Summary (Seventh Audit)

| Severity | New | Carried Forward | Total |
|----------|-----|-----------------|-------|
| CRITICAL | 0   | 0               | 0     |
| HIGH     | 1   | 0               | 1     |
| MEDIUM   | 1   | 3               | 4     |
| LOW      | 0   | 6               | 6     |
| **Total** | **2** | **9**        | **11** |

---

## NEW Findings

### [HIGH] B2-RLS-020: Consent tables with engagement_id missing from RLS policy list

**File**: `src/core/rls.py:42-115`, `src/security/consent/models.py:39-113`
**Agent**: architecture-reviewer (B2 Data Integrity)
**Evidence**:
```python
# src/security/consent/models.py:39-58
class PolicyBundle(Base):
    __tablename__ = "policy_bundles"
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="RESTRICT"), nullable=False
    )

# src/security/consent/models.py:64-113
class EndpointConsentRecord(Base):
    __tablename__ = "endpoint_consent_records"
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="RESTRICT"), nullable=False
    )
```
**Description**: Two consent-related tables with non-nullable `engagement_id` FK are missing from `ENGAGEMENT_SCOPED_TABLES`:

1. `policy_bundles` -- version-controlled consent policy bundles per engagement
2. `endpoint_consent_records` -- immutable consent grants linking participants to engagements

These tables are defined in `src/security/consent/models.py`, separate from the main `src/core/models/` directory, which likely explains the oversight. Both use `ondelete="RESTRICT"` (appropriate for compliance records that should block engagement deletion if consent records exist).

Note: The existing `ENGAGEMENT_SCOPED_TABLES` list documents 4 categories of exclusions (comment at lines 37-41), but these consent tables do not fall into any of those categories.

**Risk**: Without RLS, a database session could read consent records across engagements. Consent records contain participant IDs, consent types, and policy bundle versions -- this is GDPR-sensitive personal data. Cross-engagement leakage of consent records is a compliance risk under GDPR Article 5(1)(f) (integrity and confidentiality).
**Recommendation**: Add `"endpoint_consent_records"` and `"policy_bundles"` to `ENGAGEMENT_SCOPED_TABLES`. Since these use `ondelete="RESTRICT"`, the RLS USING clause works identically -- it only filters reads/writes by engagement context.

---

### [MEDIUM] B2-DUALWRITE-018: DualWriteFailure compensation job not implemented (UNCHANGED)

**File**: `src/core/models/dual_write_failure.py:20-36`, `src/semantic/claim_write_back.py:167-181`
**Agent**: architecture-reviewer (B2 Data Integrity)
**Evidence**:
```
# Confirmed: no code sets retried=True anywhere in the codebase
# grep for "retried.*True" or "retried.*=.*true" returns zero matches
```
**Description**: The `DualWriteFailure` model and table (migration 092) correctly capture failed Neo4j writes during claim ingestion and conflict creation. However, no compensation job exists to replay failed writes. The `retried` boolean column is never set to `True` anywhere in the codebase.

Write paths that record failures:
- `claim_write_back.py:174-180` (claim writes to Neo4j)
- `claim_write_back.py:356-362` (conflict writes to Neo4j)

**Risk**: If a Neo4j write fails (network blip, Neo4j restart), the data divergence between PostgreSQL and Neo4j is permanent. Survey claims exist in PostgreSQL but lack corresponding nodes/edges in the knowledge graph. This creates silent data inconsistency that degrades confidence scoring, conflict detection, and graph analytics.
**Recommendation**: Implement a periodic compensation job that:
1. Queries `DualWriteFailure` where `retried = false` and `created_at > now() - interval '7 days'`
2. Re-executes the Neo4j write based on `source_table` and `source_id`
3. Sets `retried = true` on success
4. Logs and alerts on repeated failures

---

## Carried Forward Findings

### [MEDIUM] B2-ORPHAN-003: JSON array columns store FK references without integrity (UNCHANGED)
**File**: Multiple models (governance, pov, monitoring, tom, simulation)
**Status**: Open. `deviation_ids`, `depends_on_ids`, `rejected_suggestion_ids`, `linked_policy_ids`, `evidence_ids` remain as JSON arrays. Accepted risk -- denormalized for query convenience.

### [MEDIUM] B2-ORM-004: Engagement lacks ORM cascade for 27+ children (UNCHANGED)
**Status**: Open. The Engagement model only has ORM cascades for `evidence_items`, `audit_logs`, and `shelf_data_requests`. All other child tables rely on database-level `ondelete="CASCADE"`. PostgreSQL cascades work correctly; ORM session cache will not auto-update.

### [MEDIUM] B2-CHECK-005: No CHECK constraints on score/confidence columns (UNCHANGED)
**Status**: Open. 30+ float score/confidence columns across models lack `CheckConstraint("col BETWEEN 0.0 AND 1.0")`. Only `semantic_relationship.py` uses CheckConstraint. `GoldenEvalResult` adds 6 more unconstrained float columns.

### [LOW] B2-CONSENT-016: ConsentRecord model-migration type drift (5th audit cycle)
**File**: `src/taskmining/consent.py:69` vs `alembic/versions/028_create_consent_records_table.py:37`
**Status**: Open. ORM defines `Enum(ConsentType)`, migration uses `String(50)`. No functional impact demonstrated across 5 audit cycles.

### [LOW] B2-PDPAUDIT-012: PDPAuditEntry.policy_id has no FK (UNCHANGED)
**Status**: Open. Index present, no FK. Appropriate for audit table that should survive policy deletion.

### [LOW] B2-EVALRUN-019: GoldenEvalResult.eval_run_id has no FK (UNCHANGED)
**Status**: Open. Bare UUID used as batch grouping key. Index present.

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
Chain is fully linear with no branches or gaps. All `down_revision` values correctly point to the previous migration. No new migrations since last audit.

### FK Cascade Coverage

All ForeignKey definitions across all 41 model files specify explicit `ondelete` policies. Zero missing `ondelete` constraints detected.

| ondelete Policy | Count |
|----------------|-------|
| CASCADE | ~62 |
| SET NULL | ~19 |
| RESTRICT | ~6 (consent/models.py, gdpr.py, export_log.py) |
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
- `search_similar()` in graph.py: GOOD -- queries with proper JOIN and parameterized engagement_id
- Traversal depth: GOOD -- capped at 10 (`graph.py:534`)
- Edge constraint validation: GOOD -- `EdgeConstraintValidator` with ontology-backed endpoint checks
- Uniqueness constraints: GOOD -- 17 node labels have `REQUIRE id IS UNIQUE`
- Engagement-scoped indexes: GOOD -- 17 labels indexed on `engagement_id`

### Dual-Write Consistency
- **Recording**: GOOD -- `DualWriteFailure` model captures failed Neo4j writes with source_table, source_id, target, error_message
- **Indexed for retrieval**: GOOD -- composite indexes on (source_table, source_id) and (retried, created_at)
- **Write paths covered**: `claim_write_back.py` records failures for both claim ingestion and conflict creation
- **Compensation**: MISSING -- no retry/replay job exists (B2-DUALWRITE-018 still open)

### pgvector Consistency
- Dimension: 768 consistent across all models, migrations, and embedding service (`EMBEDDING_DIMENSION = 768`)
- HNSW index on `evidence_fragments.embedding`: Present (migration 001)
- HNSW index on `pattern_library_entries.embedding`: Present (migration 090)
- `EmbeddingService.search_similar()` in `embeddings.py`: Correct, queries `evidence_fragments`
- `KnowledgeGraphService.search_similar()` in `graph.py`: Correct, queries `evidence_fragments`

### RLS Coverage
66 tables have RLS policies via `ENGAGEMENT_SCOPED_TABLES`. 2 consent tables with non-nullable `engagement_id` FK are missing (see B2-RLS-020). Correctly excluded tables:
- `success_metrics`: no engagement_id (global metric definitions)
- `dual_write_failures`: no engagement_id (cross-engagement compensation)
- `incident_events`: no direct engagement_id (covered by parent `incidents` RLS)
- `engagement_members`: junction table (documented exclusion)
- `alternative_suggestions`: nullable engagement_id (documented exclusion)
- `pattern_library_entries`: uses `source_engagement_id` different column name (documented exclusion)
- `http_audit_events`: string engagement_id, no FK (documented exclusion)
- `survey_claim_history`: no engagement_id (child of `survey_claims` which has RLS)
- `llm_audit_logs`: no engagement_id (child of `simulation_scenarios` which has RLS)
- `ontology_classes/properties/axioms`: no engagement_id (children of `ontology_versions` which has RLS)
- `best_practices`, `benchmarks`: no engagement_id (global reference data)
- `process_elements`, `contradictions`, `evidence_gaps`: no engagement_id (children of `process_models` which has RLS)
- `simulation_results`, `scenario_modifications`, `epistemic_actions`: no engagement_id (children of `simulation_scenarios` which has RLS)
- `financial_assumption_versions`: no engagement_id (child of `financial_assumptions` which has RLS)
- `tom_alignment_results`: no engagement_id (child of `tom_alignment_runs` which has RLS)
- `follow_up_reminders`, `shelf_data_request_items`, `shelf_data_request_tokens`: no engagement_id (children of `shelf_data_requests` which has RLS)
- `evidence_fragments`, `evidence_lineage`: no engagement_id (children of `evidence_items` which has RLS)
- `users`, `user_consents`, `mcp_api_keys`: global user tables (not engagement-scoped)

### Data Integrity Posture Score

| Category | Score | Change | Notes |
|----------|-------|--------|-------|
| FK Constraints | 9/10 | -- | JSON array refs still lack integrity; 2 bare UUIDs |
| Migration Chain | 10/10 | -- | Linear, no gaps, 92 migrations |
| Index Coverage | 9/10 | -- | All critical paths indexed; HNSW on both vector columns |
| ORM-Migration Alignment | 9/10 | -- | consent_records only remaining drift (LOW) |
| Neo4j Integrity | 9/10 | -- | Robust constraints, parameterization, depth capping |
| Data Validation | 6/10 | -- | No CHECK constraints on scores/confidence |
| RLS Coverage | 9/10 | -- | 66/68 engagement-scoped tables covered; 2 consent tables missing |
| Dual-Write Consistency | 7/10 | -- | Recording good; compensation job missing |
| **Overall** | **8.5/10** | -- | Stable; consent RLS gap is the only new actionable finding |
