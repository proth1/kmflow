# D2: Compliance & Regulatory Audit Findings (Re-Audit #4)

**Auditor**: D2 (Compliance Auditor)
**Date**: 2026-03-19
**Previous Audits**: 2026-02-20, 2026-02-26, 2026-03-19 (prior run)
**Scope**: Audit trail completeness, GDPR considerations, LLM safety, data retention, regulatory alignment

## Summary

| Severity | Count | Change from Prior Audit |
|----------|-------|------------------------|
| CRITICAL | 0     | +0 (none)              |
| HIGH     | 2     | -1 (2 resolved, 1 new) |
| MEDIUM   | 3     | -1 (2 resolved, 1 new) |
| LOW      | 2     | -1 (1 resolved)        |
| **Total** | **7** | -3 net resolved       |

## Remediation Tracker (from Prior Audit)

| # | Finding | Severity | Status | Notes |
|---|---------|----------|--------|-------|
| 1 | Mutations without AuditLog entries | HIGH | **RESOLVED** | `cost_modeling.py`, `validation.py`, `raci.py` now all have `log_audit()` calls. |
| 2 | HttpAuditEvent discards IP/UA/resource | HIGH | **RESOLVED** | `HttpAuditEvent` model now has `ip_address`, `user_agent`, `resource_type` columns; `log_audit_event_async()` passes them through. |
| 3 | PII logging in WebSocket/auth modules | HIGH | **PARTIALLY RESOLVED** | WebSocket module no longer logs `user.email`. Auth module still logs email at DEBUG level. MCP auth uses `mask_pii()`. See updated finding below. |
| 4 | DataClassification not enforced | MEDIUM | **PARTIALLY RESOLVED** | `require_classification_access()` now called in `get_evidence()` detail route. But list, fragment, and download routes still bypass classification checks. See updated finding below. |
| 5 | AlternativeSuggestion stores prompts permanently | MEDIUM | **RESOLVED** | `cleanup_expired_engagements()` now includes `delete(AlternativeSuggestion)` at line 119. |
| 6 | Audit log records lack DB-level immutability | MEDIUM | **PARTIALLY RESOLVED** | Docstring corrected to say "Append-only by convention" (line 108). Retention cleanup no longer deletes AuditLog records (line 122: explicit comment preserving them). Still no DB trigger, but convention is clearly documented. |
| 7 | Consent not enforced before processing | MEDIUM | **STILL OPEN** | See finding below. |
| 8 | Pattern anonymizer PII incomplete | LOW | **STILL OPEN** | See finding below. |
| 9 | Retention cleanup disabled by default | LOW | **RESOLVED** | `retention_cleanup_enabled` now defaults to `True` (config.py:104). |
| 10 | No DPA template/endpoint | LOW | **STILL OPEN** | TODO comment updated to reference this audit doc, but no implementation. |

---

## Open Findings

### [HIGH] LLM-AUDIT: Copilot and TOM LLM calls not recorded in LLMAuditLog

**File**: `src/rag/copilot.py:158-164`, `src/tom/rationale_generator.py:249`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/rag/copilot.py:158-164 -- LLM call with no LLMAuditLog record
return await llm.generate(
    user_prompt,
    system=system_prompt,
    model=self.settings.copilot_model,
    max_tokens=self.settings.copilot_max_response_tokens,
    messages=msgs,
)

# src/tom/rationale_generator.py:249 -- LLM call with no LLMAuditLog record
return await llm.generate(prompt, model=model, max_tokens=1000)
```
**Description**: The platform has an `LLMAuditLog` model (Story #374) that tracks every LLM interaction including prompt text, response text, token counts, model name, and hallucination flags. However, this model is only used in one place: `src/simulation/suggestion_engine.py:77`. The two highest-volume LLM callers -- the RAG copilot (`src/rag/copilot.py`) and the TOM rationale generator (`src/tom/rationale_generator.py`) -- make LLM API calls without creating `LLMAuditLog` entries.

The copilot does persist user queries and responses as `CopilotMessage` records, but these lack the token usage, model name, and hallucination-tracking fields that `LLMAuditLog` provides. The TOM rationale generator has no persistence at all.

**Risk**: Without LLM audit logging, the platform cannot track total token consumption for cost attribution, cannot identify prompt injection attempts across the copilot, and lacks the data needed for hallucination frequency analysis. In a multi-tenant consulting platform handling client evidence, traceability of all AI interactions is a compliance expectation. EU AI Act (Article 12) requires logging of AI system operations.

**Recommendation**:
1. Add `LLMAuditLog` creation in `CopilotOrchestrator._generate_response()` and `_generate_stream()`
2. Add `LLMAuditLog` creation in `TOMRationaleGenerator`
3. Consider making LLM audit logging a cross-cutting concern in `src/core/llm.py` at the provider level, so all callers automatically get audit records

---

### [HIGH] AUDIT-TRAIL: Scenario simulation and financial assumption deletion lack audit entries

**File**: `src/api/routes/scenario_simulation.py:62-68`, `src/api/routes/simulations.py:840-847`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/api/routes/scenario_simulation.py:62-68 -- creates SimulationResult, no audit
sim_result = SimulationResult(
    id=uuid.uuid4(),
    scenario_id=scenario_id,
    status=SimulationStatus.PENDING,
)
session.add(sim_result)
await session.commit()

# src/api/routes/simulations.py:840-847 -- deletes FinancialAssumption, no audit
await session.delete(assumption)
await session.commit()
```
**Description**: Two data-modifying operations in the simulation subsystem lack audit logging:

1. **`scenario_simulation.py`**: The entire route module (trigger simulation, get status) has zero `log_audit` imports or calls. Creating a `SimulationResult` and launching a background simulation task is unaudited.
2. **`simulations.py:846`**: Financial assumption deletion performs `session.delete(assumption)` without any audit log entry, even though assumption creation (line 793) correctly calls `log_audit()`.

Additionally, the service-layer modules `src/governance/catalog.py`, `src/semantic/ontology_derivation.py`, and `src/semantic/conflict_detection.py` all perform `session.add()` and `session.delete()` operations without any audit logging. While these are internal services rather than API routes, they modify compliance-relevant data (data catalog entries, ontology classes, conflict resolution requests).

**Risk**: Financial assumption deletion is a sensitive operation in a consulting platform -- assumptions drive cost models and business cases. Unaudited deletion means a user could alter financial projections without a trace. SOC2 CC7.2 requires monitoring of configuration changes that affect system outputs.

**Recommendation**:
1. Add `log_audit()` to the financial assumption deletion endpoint in `simulations.py`
2. Add audit logging to `scenario_simulation.py` for simulation trigger events
3. Add audit logging to `governance/catalog.py` for catalog entry creation and deletion
4. Consider a decorator or middleware pattern to enforce audit logging on all DELETE operations

---

### [MEDIUM] DATA-CLASSIFICATION: Classification enforcement limited to single evidence detail route

**File**: `src/api/routes/evidence.py:324`, `src/api/routes/evidence.py:361-395`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/api/routes/evidence.py:324 -- classification enforced here
require_classification_access(evidence.classification, user)

# src/api/routes/evidence.py:361-395 -- list_evidence has NO classification check
async def list_evidence(
    engagement_id: UUID | None = None,
    classification: DataClassification | None = None,
    ...
) -> dict[str, Any]:
    # Allows filtering BY classification but does not CHECK access rights
    if classification is not None:
        query = query.where(EvidenceItem.classification == classification)
```
**Description**: `require_classification_access()` is called in exactly one place: the `get_evidence()` detail endpoint (line 324). The `list_evidence()` endpoint returns evidence items of all classification levels to any authenticated user with engagement access. Users can even explicitly request `?classification=restricted` to filter for restricted items. The `get_fragments()` endpoint (line 496) also lacks classification checks, meaning RESTRICTED evidence fragment content is accessible without additional authorization.

The `GdprComplianceService.check_classification_access()` method exists but is only used internally and not wired into any route as a dependency.

**Risk**: A `CLIENT_VIEWER` role user with engagement access can list and read RESTRICTED evidence fragments, bypassing the classification-based access control that `get_evidence()` enforces. This creates an inconsistent security posture where the same data is protected on one route but exposed on another.

**Recommendation**:
1. Add `require_classification_access()` to `list_evidence()` as a post-query filter (exclude items above the user's clearance)
2. Add the same check to `get_fragments()` by looking up the parent `EvidenceItem.classification`
3. Consider a SQLAlchemy query filter that automatically excludes RESTRICTED items for non-privileged users

---

### [MEDIUM] GDPR-CONSENT: Consent not required before evidence processing or copilot LLM calls

**File**: `src/api/routes/copilot.py:56-64`, `src/api/routes/evidence.py`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/api/routes/copilot.py:56-64 -- no consent check before LLM interaction
@router.post("/chat", response_model=ChatResponse)
async def copilot_chat(
    payload: ChatRequest,
    request: Request,
    user: User = Depends(copilot_rate_limit),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
```
**Description**: The GDPR consent tracking infrastructure exists (`UserConsent` model, consent endpoints in `gdpr.py` with types `analytics`, `data_processing`, `marketing_communications`), but no API endpoint verifies consent before processing. Evidence upload sends client data through parsing pipelines, and copilot chat sends user queries to an external LLM (Anthropic API), both without checking `data_processing` consent.

The consent service (`src/security/consent/service.py`) handles task-mining agent consent but is separate from the user-level GDPR consent flow. This finding has persisted across four audits without remediation.

**Risk**: If consent is the chosen lawful basis under GDPR Art. 6, it must be verified before processing. The existence of a consent tracking system without enforcement creates regulatory confusion about the platform's lawful basis for processing.

**Recommendation**:
1. Add a FastAPI dependency `require_consent("data_processing")` that checks `UserConsent` status
2. Apply to evidence upload, copilot chat, and other data processing endpoints
3. Alternatively, formally document that the lawful basis is "contractual necessity" (Art. 6(1)(b)) and clarify the consent types are for supplementary purposes only

---

### [MEDIUM] DATA-RETENTION: File storage not cleaned up during retention enforcement

**File**: `src/core/retention.py:102-116`, `src/core/models/evidence.py:94`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/core/retention.py:102-116 -- deletes DB rows but not file storage
# 2. Delete evidence fragments
await session.execute(delete(EvidenceFragment).where(...))

# 3. Delete evidence items.
await session.execute(delete(EvidenceItem).where(EvidenceItem.engagement_id == eng.id))

# src/core/models/evidence.py:94 -- evidence has file_path pointing to disk
file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
```
**Description**: The `cleanup_expired_engagements()` function deletes `EvidenceFragment` and `EvidenceItem` database rows during retention enforcement, and deletes the Neo4j subgraph. However, it does not delete the actual evidence files from the file system (stored under `evidence_store/{engagement_id}/`). The `EvidenceItem.file_path` column points to the physical file, but no code reads this path to unlink the file during cleanup.

Similarly, the `GdprComplianceService.enforce_retention()` method archives or deletes `EvidenceItem` database records but does not touch the underlying file storage.

**Risk**: Orphaned files on disk or in object storage violate data retention policies. After database cleanup, the evidence files remain accessible to anyone with filesystem access, defeating the purpose of retention enforcement. GDPR erasure obligations extend to all copies of personal data, including file-based storage.

**Recommendation**:
1. Before deleting `EvidenceItem` rows, collect `file_path` values and unlink the corresponding files
2. Add a `StorageBackend.delete()` method to the storage abstraction layer
3. Handle both local filesystem and future MinIO/S3 backends
4. Log file deletion in the audit trail for compliance evidence

---

### [LOW] ANONYMIZATION: Pattern anonymizer PII detection is regex-based and incomplete

**File**: `src/patterns/anonymizer.py:17-21`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
PII_PATTERNS = [
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),  # email
    re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),  # phone
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN
]
```
**Description**: The pattern anonymizer uses only three regex patterns to detect PII before storing cross-engagement patterns. The task mining module has its own PII detection (`PIIType` enum with 10 categories including credit cards, addresses, names, DOB, financial, and medical), but the pattern anonymizer does not leverage it. This finding has persisted across four audits.

**Risk**: Incomplete anonymization could leak client-identifying information into the shared pattern library.

**Recommendation**:
1. Align pattern anonymizer PII detection with the `PIIType` enum categories
2. Add credit card (Luhn), IP address, and international phone patterns at minimum

---

### [LOW] GDPR-DPA: No data processing agreement template or tracking

**File**: `src/core/config.py:100-103`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/core/config.py:100-103
# TODO(DPA): GDPR Article 28 requires Data Processing Agreements between the
# platform operator and each client. Retention periods below must align with
# agreed DPA terms. See docs/audit-findings/D2-compliance.md for full context.
retention_cleanup_enabled: bool = True
```
**Description**: No DPA template, acceptance endpoint, or tracking model exists. The TODO comment has been present since 2026-02-26 with no implementation progress. The comment now references this audit findings document, but no code changes have been made.

**Risk**: GDPR Article 28 requires written contracts between data controllers and processors. Operating without formalized DPAs exposes the platform to regulatory risk.

**Recommendation**:
1. Create a DPA template in `docs/legal/`
2. Add DPA acceptance tracking at the engagement level
3. Consider blocking engagement creation until a DPA reference is provided

---

## Positive Findings (Improvements Since Prior Audit)

1. **Audit logging gaps largely closed**: `cost_modeling.py`, `validation.py`, `raci.py`, and the copilot streaming endpoint now all have `log_audit()` calls. Five previously unaudited route modules are now compliant.

2. **HttpAuditEvent now captures full forensic data**: The model has `ip_address`, `user_agent`, and `resource_type` columns, and `log_audit_event_async()` passes all three values through. This resolves the prior HIGH finding completely.

3. **AuditLog immutability clarified**: Docstring updated from false claim ("PostgreSQL trigger prevents UPDATE and DELETE") to accurate statement ("Append-only by convention"). Retention cleanup explicitly preserves audit logs (line 122 comment: "Audit logs are intentionally NOT deleted").

4. **Retention cleanup enabled by default**: `retention_cleanup_enabled` now defaults to `True`, addressing the prior finding that data accumulated indefinitely without explicit opt-in.

5. **AlternativeSuggestion included in retention cascade**: `cleanup_expired_engagements()` now deletes `AlternativeSuggestion` records at line 119, resolving the permanent LLM prompt storage finding.

6. **Classification enforcement started**: `require_classification_access()` is now called in the `get_evidence()` detail route, providing a foundation for expansion to other routes.

7. **PII masking utility available**: `src/mcp/pii.py` provides `mask_pii()` which is used in MCP auth logging. The WebSocket module no longer logs `user.email` at INFO level.

8. **LLM cost controls maintained**: Copilot uses configurable `copilot_max_response_tokens` (default 2000) from settings, with response truncation at 10,000 characters. Rate limiting enforced at 10 queries/min per user. Streaming endpoint has length cap.

9. **Prompt injection defenses maintained**: All five domain templates include anti-injection directives. Input sanitization strips control characters and truncates to 5,000 chars. History messages filtered to only `user`/`assistant` roles. Output validated for system prompt leakage.

10. **GDPR erasure fully implemented**: `src/gdpr/erasure_job.py` and `src/gdpr/erasure_worker.py` provide cross-store erasure coordination with retry support.

---

## Audit Progression Summary

| Metric | 2026-02-20 | 2026-02-26 | Prior Run | Current |
|--------|------------|------------|-----------|---------|
| CRITICAL | 3 | 1 | 0 | 0 |
| HIGH | 5 | 3 | 3 | 2 |
| MEDIUM | 5 | 4 | 4 | 3 |
| LOW | 3 | 3 | 3 | 2 |
| **Total** | **16** | **11** | **10** | **7** |
| Resolved since prev | -- | 7 | 2 | 5 |
| New since prev | -- | 2 | 1 | 2 |

Key trends:
- All CRITICAL findings remain resolved (zero since prior audit).
- Net reduction of 3 findings (5 resolved, 2 new).
- The 2 new findings (LLM audit gap, file storage retention) represent architectural gaps rather than coding errors.
- Two findings have persisted across all four audits (consent enforcement, pattern anonymizer) -- these require product-level decisions rather than code changes.
- The platform's compliance posture has improved materially: forensic data capture is now comprehensive, retention cleanup is automatic, and audit trail coverage across API routes is near-complete.
