# D2: Compliance & Regulatory Audit Findings (Re-Audit #6)

**Auditor**: D2 (Compliance Auditor)
**Date**: 2026-03-20
**Previous Audits**: 2026-02-20, 2026-02-26, 2026-03-19 (x2), 2026-03-20 (cycle 6)
**Scope**: Audit trail completeness, GDPR considerations, LLM safety, data retention, consent, data classification enforcement

## Summary

| Severity | Count | Change from Prior Audit |
|----------|-------|------------------------|
| CRITICAL | 0     | +0 (none)              |
| HIGH     | 1     | +0 (prior resolved, 1 new) |
| MEDIUM   | 2     | +0 (unchanged)         |
| LOW      | 2     | +0 (unchanged, 1 partially resolved) |
| **Total** | **5** | -0 net (1 resolved, 1 new) |

## Remediation Tracker (from Prior Audit)

| # | Finding | Severity | Status | Notes |
|---|---------|----------|--------|-------|
| 1 | Mutations without AuditLog entries | HIGH | **RESOLVED** | All prior flagged routes have `log_audit()` calls. |
| 2 | HttpAuditEvent discards IP/UA/resource | HIGH | **RESOLVED** | Model has full forensic columns; `log_audit_event_async()` passes them through. |
| 3 | PII logging in WebSocket/auth modules | HIGH | **RESOLVED** | Auth module DEBUG lines reference "email lockout" contextually but do not log the email value itself. MCP auth uses `mask_pii()`. |
| 4 | DataClassification not enforced | MEDIUM | **MOSTLY RESOLVED** | `require_classification_access()` called in `get_evidence()` (line 367), `get_fragments()` (line 565), and `download_evidence()` (line 598). `list_evidence()` filters RESTRICTED from CLIENT_VIEWER (line 442-444). See open finding below for remaining gap. |
| 5 | AlternativeSuggestion stores prompts permanently | MEDIUM | **RESOLVED** | `cleanup_expired_engagements()` deletes `AlternativeSuggestion` at line 145. |
| 6 | Audit log records lack DB-level immutability | MEDIUM | **RESOLVED** | Convention documented and enforced in code. Accepted as sufficient for current scale. |
| 7 | Consent not enforced before processing | MEDIUM | **STILL OPEN** | See finding below. No `require_consent` dependency exists anywhere in the codebase. |
| 8 | Pattern anonymizer PII incomplete | LOW | **RESOLVED** | `PII_PATTERNS` now has 6 entries. |
| 9 | Retention cleanup disabled by default | LOW | **RESOLVED** | Enabled by default. |
| 10 | No DPA template/endpoint | LOW | **RESOLVED** | Full DPA CRUD at `src/api/routes/dpa.py`. |
| 11 | Copilot and TOM LLM calls not recorded in LLMAuditLog | HIGH | **RESOLVED** | Both copilot and TOM rationale generator now create `LLMAuditLog` entries. |
| 12 | Scenario simulation and financial assumption deletion lack audit entries | HIGH | **RESOLVED** | Both now call `log_audit()`. |
| 13 | File storage not cleaned up during retention enforcement | MEDIUM | **RESOLVED** | `retention.py:116-137` now reads file paths and calls `Path.unlink()`. |
| 14 | GDPR export omits LLMAuditLog and CopilotFeedback | HIGH | **RESOLVED** | `DataExportResponse` now includes `llm_audit_logs` and `copilot_feedback` fields (lines 89-90). Export queries both tables (lines 270-300). See new finding below for incomplete field coverage. |
| 15 | GDPR anonymize does not cover LLMAuditLog or CopilotFeedback | LOW | **PARTIALLY RESOLVED** | Admin endpoint (`gdpr.py:546-555`) now nullifies `llm_audit_logs.user_id` and deletes `copilot_feedback` rows. However, background `erasure_job.py` does not include these tables, and `copilot_messages.content` is not anonymized. See open findings below. |

---

## Open Findings

### [HIGH] GDPR-ERASURE-JOB: Background erasure job does not anonymize LLMAuditLog, CopilotFeedback, or CopilotMessage content

**File**: `src/gdpr/erasure_job.py:22-54`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/gdpr/erasure_job.py:22-54 -- _anonymize_user only handles users + audit_logs
async def _anonymize_user(user_id: uuid.UUID, db: AsyncSession) -> None:
    # ...anonymises user row...
    await db.execute(
        text("UPDATE audit_logs SET actor = 'anonymized' WHERE actor = :uid"),
        {"uid": user_id_str},
    )
    # Missing: llm_audit_logs, copilot_feedback, copilot_messages
```
**Description**: The admin anonymization endpoint (`gdpr.py:546-555`) was updated in the last cycle to handle `llm_audit_logs` and `copilot_feedback`. However, the background erasure job (`erasure_job.py:_anonymize_user`) -- which is the production path for processing scheduled erasure requests -- was NOT updated in parallel. It only anonymizes the `users` table and `audit_logs.actor` field. This means that when a user requests erasure through the self-service endpoint and the grace period expires, the background job will:

1. Anonymize the user row and audit logs (correct)
2. Leave `llm_audit_logs` records with the user's UUID intact (gap)
3. Leave `copilot_feedback` records with user_id and correction_text intact (gap)
4. Leave `copilot_messages.content` with user's chat text intact (gap)

The admin endpoint handles (2) and (3) but NOT (4). Neither path handles `copilot_messages.content`.

**Risk**: The background erasure job is the primary production path for GDPR Art. 17 compliance. Users who request erasure via self-service will have incomplete anonymization. This is higher severity than the admin-only gap because it affects the automated compliance path.

**Recommendation**:
1. Add to `erasure_job.py:_anonymize_user`:
   - `UPDATE llm_audit_logs SET user_id = NULL WHERE user_id = :uid::uuid`
   - `DELETE FROM copilot_feedback WHERE user_id = :uid::uuid`
   - `UPDATE copilot_messages SET content = 'anonymized' WHERE user_id = :uid::uuid`
2. Add the same `copilot_messages` anonymization to the admin endpoint at `gdpr.py`
3. Consider extracting a shared `_anonymize_related_tables()` helper to prevent future divergence between the two paths

---

### [MEDIUM] GDPR-CONSENT: Consent not required before evidence processing or copilot LLM calls

**File**: `src/api/routes/copilot.py:39-45`, `src/api/routes/evidence.py`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/api/routes/copilot.py:39-45 -- no consent check before LLM interaction
@router.post("/chat", response_model=ChatResponse)
async def copilot_chat(
    payload: ChatRequest,
    request: Request,
    user: User = Depends(copilot_rate_limit),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
```
**Description**: The GDPR consent tracking infrastructure is fully operational (`UserConsent` model, consent endpoints in `gdpr.py` with types `analytics`, `data_processing`, `marketing_communications`), but no API endpoint verifies consent before processing. No `require_consent` or equivalent dependency exists anywhere in the codebase (confirmed via grep). Evidence upload sends client data through parsing pipelines, and copilot chat sends user queries to an external LLM (Anthropic API), both without checking `data_processing` consent. This finding has persisted across six audits without remediation.

**Risk**: If consent is the chosen lawful basis under GDPR Art. 6, it must be verified before processing. The existence of a consent tracking system without enforcement creates regulatory confusion about the platform's lawful basis for processing.

**Recommendation**:
1. Add a FastAPI dependency `require_consent("data_processing")` that checks `UserConsent` status
2. Apply to evidence upload, copilot chat, and other data processing endpoints
3. Alternatively, formally document that the lawful basis is "contractual necessity" (Art. 6(1)(b)) and clarify the consent types are for supplementary purposes only -- the DPA routes already default to `Art. 6(1)(f)` which suggests this may be the intended approach. This documentation-only resolution would close the finding.

---

### [MEDIUM] DATA-CLASSIFICATION: list_evidence classification enforcement incomplete for non-CLIENT_VIEWER roles

**File**: `src/api/routes/evidence.py:440-444`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/api/routes/evidence.py:440-444 -- only CLIENT_VIEWER filtered
if user.role == UserRole.CLIENT_VIEWER:
    items = [item for item in items if item.classification != DataClassification.RESTRICTED]
    count_query = count_query.where(EvidenceItem.classification != DataClassification.RESTRICTED)
```
**Description**: The `list_evidence()` endpoint filters RESTRICTED items from `CLIENT_VIEWER` users but does not use `require_classification_access()` (which enforces a multi-level classification hierarchy). Other roles that should not see RESTRICTED data (e.g., `CONSULTANT` without explicit clearance) are not filtered. The `get_evidence()`, `get_fragments()`, and `download_evidence()` routes all use `require_classification_access()` which checks the full classification hierarchy, creating an inconsistency where a user can see RESTRICTED items in the list but be denied access when clicking through to details.

**Risk**: Information leakage through the list endpoint (item names, categories, quality scores of RESTRICTED evidence) even if the actual content is protected. This is a lower risk than before since the actual content is now gated.

**Recommendation**:
1. Apply `require_classification_access()` as a post-query filter in `list_evidence()` to match the enforcement used in detail/fragment/download routes
2. This ensures consistent behavior: items visible in the list are always accessible in detail

---

### [LOW] AUDIT-GAP: Intake token creation and copilot feedback lack audit logging

**File**: `src/api/routes/intake.py:128-134`, `src/api/routes/copilot.py:263-273`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/api/routes/intake.py:128-134 -- no audit log for token creation
token_record = generate_intake_token(
    request_id=request_id,
    created_by=created_by,
    expiry_days=expiry_days,
)
session.add(token_record)
await session.commit()

# src/api/routes/copilot.py:263-273 -- no audit log for feedback submission
feedback = CopilotFeedback(
    copilot_message_id=payload.copilot_message_id,
    engagement_id=payload.engagement_id,
    user_id=user.id,
    ...
)
session.add(feedback)
await session.commit()
```
**Description**: Two route modules create database records without corresponding audit log entries:

1. **`intake.py`**: Intake token generation creates a `ShelfDataRequestToken` record (line 133) without any `log_audit()` call. Intake tokens grant unauthenticated upload access, making their creation a security-relevant event.
2. **`copilot.py`**: The `submit_feedback` endpoint (line 263-273) creates `CopilotFeedback` records without audit logging. While lower risk than token creation, feedback includes user-authored correction text and hallucination flags.

**Risk**: Intake tokens are security-sensitive -- they bypass authentication for evidence upload. Unaudited token creation means there is no trail if tokens are generated inappropriately.

**Recommendation**:
1. Add `log_audit()` to intake token creation with the engagement/request context
2. Add `log_audit()` to copilot feedback submission

---

### [LOW] GDPR-EXPORT-FIELDS: LLM audit log export omits prompt_text and response_text

**File**: `src/api/routes/gdpr.py:273-284`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/api/routes/gdpr.py:273-284 -- export includes metadata but not content
llm_audit_logs = [
    {
        "id": str(e.id),
        "scenario_id": str(e.scenario_id) if e.scenario_id else None,
        "prompt_tokens": e.prompt_tokens,
        "completion_tokens": e.completion_tokens,
        "model_name": e.model_name,
        "hallucination_flagged": e.hallucination_flagged,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
    for e in llm_audit_result.scalars().all()
]
# Missing: prompt_text (user's query to LLM), response_text (LLM's response)
```
**Description**: The GDPR data export now includes `LLMAuditLog` records (resolving the prior HIGH finding for table inclusion). However, the serialization omits `prompt_text` and `response_text` -- the two columns that contain the actual content of the user's LLM interactions. The `LLMAuditLog` model defines these as `prompt_text: Mapped[str]` (line 35) and `response_text: Mapped[str | None]` (line 36). The `prompt_text` contains the full prompt sent to the LLM on behalf of the user, which may include the user's natural language question embedded within the prompt template. The `response_text` contains the LLM's response.

Similarly, the `copilot_feedback` export (lines 290-300) omits `correction_text` -- user-authored text that is personal data.

**Risk**: GDPR Art. 15 requires providing "all personal data" being processed. The prompt text and correction text contain user-generated content that constitutes personal data. Exporting only metadata (token counts, model name, timestamps) without the actual content is an incomplete response to a data subject access request.

**Recommendation**:
1. Add `"prompt_text": e.prompt_text` and `"response_text": e.response_text` to the LLM audit log serialization
2. Add `"correction_text": f.correction_text` to the copilot feedback serialization
3. Consider adding a truncation note if prompt_text is extremely large, but it must still be provided

---

## Positive Findings (Improvements Since Prior Audit)

1. **GDPR export now includes LLMAuditLog and CopilotFeedback tables**: `DataExportResponse` schema updated with `llm_audit_logs` and `copilot_feedback` fields (lines 89-90). Export queries both tables filtered by `user_id` (lines 270-300). This resolves the prior HIGH finding for table-level inclusion.

2. **Admin anonymization covers LLMAuditLog and CopilotFeedback**: `admin_anonymize_user()` now nullifies `llm_audit_logs.user_id` (line 547) and deletes `copilot_feedback` rows (line 553). This partially resolves the prior LOW finding.

3. **LLM audit logging fully implemented**: Both the RAG copilot and TOM rationale generator create `LLMAuditLog` entries with prompt text, response text, token estimates, and model name.

4. **Scenario simulation audit trail complete**: Both simulation creation and financial assumption deletion are audited.

5. **File storage cleanup implemented**: `retention.py:116-137` now reads `EvidenceItem.file_path` values and calls `Path.unlink()` before deleting database rows.

6. **DPA lifecycle fully operational**: `src/api/routes/dpa.py` provides create, get, list history, update, and activate endpoints with full audit logging.

7. **Classification enforcement expanded**: `require_classification_access()` called in 3 evidence routes (get, fragments, download). `list_evidence()` filters RESTRICTED from CLIENT_VIEWER role.

8. **LLM cost controls maintained**: Copilot uses configurable `copilot_max_response_tokens` (default 2000), response truncation at 10,000 characters, rate limiting at 10 queries/min per user.

9. **Prompt injection defenses maintained**: All five domain templates include anti-injection directives. Input sanitization strips control characters and truncates to 5,000 chars. History messages filtered to only `user`/`assistant` roles.

10. **GDPR erasure infrastructure operational**: `src/gdpr/erasure_job.py` + `src/gdpr/erasure_worker.py` provide cross-store erasure coordination with Neo4j + Redis purge support.

11. **Consent withdrawal records correctly**: `ConsentService.withdraw_consent()` properly marks the `EndpointConsentRecord` as WITHDRAWN with timestamp before raising `NotImplementedError` for cross-store deletion (tracked as KMFLOW-382). The consent state change is persisted even though downstream deletion is not yet implemented.

---

## Audit Progression Summary

| Metric | 2026-02-20 | 2026-02-26 | 2026-03-19a | 2026-03-19b | Cycle 6 | Current |
|--------|------------|------------|-------------|-------------|---------|---------|
| CRITICAL | 3 | 1 | 0 | 0 | 0 | 0 |
| HIGH | 5 | 3 | 3 | 2 | 1 | 1 |
| MEDIUM | 5 | 4 | 4 | 3 | 2 | 2 |
| LOW | 3 | 3 | 3 | 2 | 2 | 2 |
| **Total** | **16** | **11** | **10** | **7** | **5** | **5** |
| Resolved since prev | -- | 7 | 2 | 5 | 4 | 1 |
| New since prev | -- | 2 | 1 | 2 | 2 | 1 |

Key trends:
- All CRITICAL findings remain resolved (zero since 2026-03-19).
- Net change of 0: 1 resolved (GDPR export table inclusion), 1 new (erasure job gap).
- The prior HIGH (GDPR-EXPORT missing tables) is now resolved -- export includes both `LLMAuditLog` and `CopilotFeedback`. A new LOW was raised for missing content fields (`prompt_text`, `response_text`, `correction_text`).
- The new HIGH (GDPR-ERASURE-JOB) is a divergence issue: the admin anonymization endpoint was updated to cover new tables, but the background erasure job was not updated in parallel. This is the more critical path since it handles self-service erasure requests.
- The consent enforcement finding has persisted across all six audits. This is a product-level decision about lawful basis (consent vs. legitimate interest vs. contractual necessity) rather than a code change. Documenting the chosen basis would close this finding.
- The `ConsentService.withdraw_consent()` still raises `NotImplementedError` for cross-store deletion (KMFLOW-382), but the consent status change itself is correctly persisted.
- The platform's compliance posture is stable: GDPR data lifecycle coverage is expanding as new tables are created, but the gap between admin and background erasure paths needs attention.
