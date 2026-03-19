# D2: Compliance & Regulatory Audit Findings (Re-Audit #3)

**Auditor**: D2 (Compliance Auditor)
**Date**: 2026-03-19
**Previous Audits**: 2026-02-20, 2026-02-26
**Scope**: Audit trail completeness, GDPR considerations, LLM safety, data retention, regulatory alignment

## Summary

| Severity | Count | Change from 2026-02-26 |
|----------|-------|------------------------|
| CRITICAL | 0     | -1 (1 resolved)        |
| HIGH     | 3     | +0 (1 resolved, 1 new) |
| MEDIUM   | 4     | +0 (1 resolved, 1 new) |
| LOW      | 3     | +0 (0 resolved, 0 new) |
| **Total** | **10** | -1 net resolved      |

## Remediation Tracker (from 2026-02-26 Audit)

| # | Finding | Severity | Status | Notes |
|---|---------|----------|--------|-------|
| 1 | GDPR erasure job not implemented | CRITICAL | **RESOLVED** | `src/gdpr/erasure_job.py` + `src/gdpr/erasure_worker.py` now implement background erasure with cross-store coordination (PG + Neo4j + Redis). |
| 2 | Integration/governance mutations lack AuditLog | HIGH | **PARTIALLY RESOLVED** | `integrations.py` now has `log_audit()` calls on create, update, delete. `cost_modeling.py`, `validation.py`, `raci.py` still missing. |
| 3 | GDPR export missing copilot messages | HIGH | **RESOLVED** | `DataExportResponse` now includes `user_consents` and `copilot_messages`. Export collects from 6 sources. |
| 4 | PII logging in MCP auth | HIGH | **STILL OPEN** | `user.email` still logged. See finding below. |
| 5 | DataClassification not enforced | MEDIUM | **STILL OPEN** | Classification stored but not checked at access time. |
| 6 | AlternativeSuggestion stores prompts permanently | MEDIUM | **STILL OPEN** | No retention cleanup for this model. |
| 7 | No DB-level audit log immutability | MEDIUM | **STILL OPEN** | No PostgreSQL trigger preventing UPDATE/DELETE. Retention cleanup still deletes audit logs. |
| 8 | Consent not enforced before processing | MEDIUM | **STILL OPEN** | Consent infrastructure exists but is never checked pre-processing. |
| 9 | Pattern anonymizer PII detection incomplete | LOW | **STILL OPEN** | Still only 3 regex patterns. |
| 10 | Retention cleanup disabled by default | LOW | **STILL OPEN** | `retention_cleanup_enabled` still defaults to `False`. |
| 11 | No DPA template/endpoint | LOW | **STILL OPEN** | TODO comment only. |

---

## Open Findings

### [HIGH] AUDIT-TRAIL: Multiple route modules perform mutations without AuditLog entries

**File**: `src/api/routes/cost_modeling.py:123`, `src/api/routes/validation.py:569`, `src/api/routes/raci.py:190`, `src/api/routes/tom.py:918`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/api/routes/cost_modeling.py:116-126 -- creates role rate, no AuditLog
rate = RoleRateAssumption(
    engagement_id=engagement_id,
    role_name=payload.role_name,
    hourly_rate=payload.hourly_rate,
    annual_rate=payload.annual_rate,
)
session.add(rate)
await session.commit()

# src/api/routes/cost_modeling.py:161-171 -- creates volume forecast, no AuditLog
forecast = VolumeForecast(...)
session.add(forecast)
await session.commit()
```
**Description**: Several route modules perform data-modifying operations (`session.add`, `session.delete`) without corresponding AuditLog creation. The following routes have zero `log_audit()` calls despite containing mutations:

1. **cost_modeling.py**: Role rate creation (line 123), volume forecast creation (line 168) -- zero audit entries.
2. **validation.py**: POV republishing (line 569), review pack generation (line 776), sentinel writes (line 802) -- zero audit entries.
3. **raci.py**: RACI cell creation via auto-derive (line 190) -- zero audit entries despite creating potentially dozens of RACI cells per call.
4. **tom.py**: Best practice creation (line 918), benchmark creation (line 997), seed data insertion (lines 1061-1067) -- zero audit entries for reference data mutations.
5. **simulations.py**: Financial assumption deletion (line 846) -- `session.delete(assumption)` with no audit, even though creation (line 793) has `log_audit()`.

Additionally, the copilot streaming endpoint (`POST /copilot/chat/stream` at `src/api/routes/copilot.py:204`) does not create any audit trail entry, while the non-streaming endpoint (`POST /copilot/chat` at line 146) does log via `AuditAction.DATA_ACCESS`.

**Risk**: Incomplete audit trail prevents forensic reconstruction of who changed financial assumptions, RACI assignments, or process validation decisions. SOC2 CC7.2 requires monitoring of configuration changes. The streaming endpoint gap means copilot usage volume is underreported.

**Recommendation**:
1. Add `log_audit()` calls to all data-modifying endpoints in `cost_modeling.py`, `validation.py`, `raci.py`
2. Add `log_audit()` to the streaming copilot endpoint matching the non-streaming endpoint pattern
3. Add audit logging for the financial assumption deletion in `simulations.py`
4. Consider a reusable FastAPI dependency or event hook that automatically creates audit entries for all POST/PUT/PATCH/DELETE routes

---

### [HIGH] AUDIT-TRAIL: HttpAuditEvent silently discards IP address, user agent, and resource type

**File**: `src/core/audit.py:62-72`, `src/core/models/audit.py:145-169`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/core/audit.py:62-72 -- ip_address, user_agent, resource_type silently dropped
if session is not None:
    event = HttpAuditEvent(
        method=method,
        path=path,
        user_id=user_id,
        status_code=status_code,
        engagement_id=engagement_id,
        duration_ms=duration_ms,
    )
    session.add(event)
    await session.commit()
```
**Description**: The `log_audit_event_async()` function accepts `ip_address`, `user_agent`, and `resource_type` as parameters (passed from the audit middleware which extracts these from every request). However, when creating the `HttpAuditEvent` database record, these three fields are silently discarded -- the model has no columns for them, and they are not passed to the constructor.

The middleware at `src/api/middleware/audit.py:117-129` carefully extracts IP (with X-Forwarded-For support), user agent (truncated to 512 chars), and resource type -- then passes all three to `_persist_audit_event()`. The data flows through to `log_audit_event_async()` as named parameters, but is never persisted.

The structured log line at `src/core/audit.py:51-59` does include `ip_address`, so the data survives in application logs if SIEM ingests them, but not in the database audit table.

**Risk**: IP address and user agent are critical for security investigations (detecting brute force attacks, identifying compromised sessions, correlating with VPN/geo data). Without these in the database, investigators must cross-reference application logs with database records -- a significant forensic burden. The `AuditLog` model (line 132-133) has `ip_address` and `user_agent` columns, demonstrating the platform recognizes their importance, yet `HttpAuditEvent` omits them.

**Recommendation**:
1. Add `ip_address: Mapped[str | None]`, `user_agent: Mapped[str | None]`, and `resource_type: Mapped[str | None]` columns to the `HttpAuditEvent` model
2. Create an Alembic migration to add these three columns
3. Pass the values through in `log_audit_event_async()` when constructing the `HttpAuditEvent`

---

### [HIGH] PII-LOGGING: User email addresses logged at INFO level in WebSocket and auth modules

**File**: `src/api/routes/websocket.py:317,342,348`, `src/core/auth.py:321`, `src/mcp/auth.py:55`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/api/routes/websocket.py:317
logger.info("Task mining WS connected for user %s", user.email)

# src/api/routes/websocket.py:342
logger.debug("Task mining WS client disconnected (user %s)", user.email)

# src/api/routes/websocket.py:348
logger.info("Task mining WS cleaned up for user %s", user.email)

# src/core/auth.py:321
logger.debug("Auth dev mode: auto-authenticated as %s", dev_user.email)
```
**Description**: Multiple modules log `user.email` at INFO level, which typically flows to log aggregation systems (CloudWatch, Datadog, ELK). The WebSocket module logs email on every connection, disconnection, and cleanup. The MCP auth module (flagged in the 2026-02-20 audit) continues to log `user_id` and `client_name` correlation data at INFO level.

While UUIDs would be sufficient for operational debugging (and are already available via `user.id`), email addresses constitute directly identifiable personal data under GDPR.

**Risk**: GDPR Article 5(1)(c) requires data minimization. Logging email addresses to centralized log stores creates an uncontrolled copy of PII that may not be subject to the same retention and erasure controls as the database. If logs are retained longer than the GDPR erasure grace period, anonymised users' emails could persist in log archives.

**Recommendation**:
1. Replace `user.email` with `user.id` in all INFO-level log statements
2. Reserve email logging for DEBUG level only (not enabled in production)
3. Audit all `logger.*` calls across the codebase for PII leakage using a grep pattern like `logger\..*(email|\.name\b)`
4. Ensure log retention policies are documented and aligned with GDPR data retention requirements

---

### [MEDIUM] DATA-CLASSIFICATION: Classification stored on evidence but not enforced at access time

**File**: `src/core/models/evidence.py:129-135`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/core/models/evidence.py:129-135
# Data sensitivity classification -- defaults to INTERNAL
classification: Mapped[DataClassification] = mapped_column(
    Enum(DataClassification, values_callable=lambda e: [x.value for x in e]),
    default=DataClassification.INTERNAL,
    server_default="internal",
    nullable=False,
)
```
**Description**: The `DataClassification` enum (PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED) is stored on `EvidenceItem` records but is never checked during access control decisions. Any authenticated user with engagement-level access can retrieve RESTRICTED evidence with no additional authorization check. This finding has persisted across two prior audits without remediation.

**Risk**: Classification without enforcement provides a false sense of security. SOC2 CC6.1 requires access controls commensurate with data sensitivity. Regulatory auditors reviewing the data model would see classification fields and reasonably assume enforcement exists.

**Recommendation**:
1. Add a middleware or FastAPI dependency that checks `evidence.classification` against the requesting user's role level
2. At minimum, add audit logging via `AuditAction.DATA_ACCESS` when CONFIDENTIAL or RESTRICTED evidence is accessed
3. Document the classification policy and intended enforcement roadmap

---

### [MEDIUM] LLM-SAFETY: AlternativeSuggestion stores full LLM prompts permanently with no retention

**File**: `src/simulation/suggester.py:144`, `src/core/retention.py`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/simulation/suggester.py:144 -- full prompt sent to LLM
return await llm.generate(prompt, model=model, max_tokens=2000)

# AlternativeSuggestion model stores prompt and response (no cleanup exists)
# llm_prompt: Mapped[str] = mapped_column(Text, nullable=False)
# llm_response: Mapped[str] = mapped_column(Text, nullable=False)
```
**Description**: While `CopilotMessage` records have retention cleanup via `cleanup_old_copilot_messages()`, the `AlternativeSuggestion` model stores full LLM prompts (containing client evidence context and scenario descriptions) and full LLM responses permanently. The retention cleanup in `cleanup_expired_engagements()` does not cascade to delete `AlternativeSuggestion` records. This finding has persisted across two prior audits.

**Risk**: Client evidence and proprietary process data stored permanently alongside AI interactions. No mechanism to comply with data minimization (GDPR Art. 5(1)(c)). Stored prompts could be exposed in a breach.

**Recommendation**:
1. Add `cleanup_old_suggestions()` to `src/core/retention.py`
2. Include `AlternativeSuggestion` in the engagement-level retention cleanup cascade
3. Consider replacing `llm_prompt` storage with a hash or truncated summary

---

### [MEDIUM] AUDIT-TRAIL: Audit log records lack database-level immutability protection

**File**: `src/core/models/audit.py:104-142`, `src/core/retention.py:90`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/core/retention.py:90 -- explicitly deletes audit logs
await session.execute(delete(AuditLog).where(AuditLog.engagement_id == eng.id))

# src/core/models/audit.py:104-108 -- docstring claims append-only but no enforcement
class AuditLog(Base):
    """Audit log for tracking engagement mutation operations.

    Append-only: a PostgreSQL trigger prevents UPDATE and DELETE on this table.
    """
```
**Description**: The `AuditLog` model docstring (line 105-107) claims "a PostgreSQL trigger prevents UPDATE and DELETE on this table," but no such trigger exists in the Alembic migrations. Meanwhile, `cleanup_expired_engagements()` explicitly deletes audit logs at line 90, contradicting both the docstring claim and the `ondelete="SET NULL"` FK design. This finding has persisted across two prior audits.

**Risk**: SOX/SOC2 compliance typically requires immutable audit trails. The docstring creates a false assurance of immutability. The explicit deletion in retention cleanup means audit records for expired engagements are permanently lost.

**Recommendation**:
1. Either implement the PostgreSQL trigger claimed in the docstring, or correct the docstring
2. Remove the audit log deletion from `cleanup_expired_engagements()` -- audit logs should be preserved even after engagement data is purged
3. Consider a `checksum` column for tamper detection

---

### [MEDIUM] GDPR-CONSENT: Consent not required before evidence processing or copilot LLM calls

**File**: `src/api/routes/copilot.py:83-89`, `src/api/routes/evidence.py`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/api/routes/copilot.py:83-89 -- no consent check before LLM interaction
@router.post("/chat", response_model=ChatResponse)
async def copilot_chat(
    payload: ChatRequest,
    request: Request,
    user: User = Depends(copilot_rate_limit),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
```
**Description**: The GDPR consent tracking infrastructure exists (`UserConsent` model, consent endpoints in `gdpr.py` with types `analytics`, `data_processing`, `marketing_communications`), but no API endpoint verifies consent before processing. Evidence upload sends client data through parsing pipelines, and copilot chat sends user queries to an external LLM (Anthropic API), both without checking `data_processing` consent. The endpoint consent service (`src/security/consent/service.py`) handles participant-level consent but is separate from the user-level GDPR consent flow. This finding has persisted across two prior audits.

**Risk**: If consent is the chosen lawful basis under GDPR Art. 6, it must be verified before processing. The existence of a consent tracking system without enforcement creates regulatory confusion about the platform's lawful basis for processing.

**Recommendation**:
1. Add a FastAPI dependency `require_consent("data_processing")` that checks `UserConsent` status
2. Apply to evidence upload, copilot chat, and other data processing endpoints
3. Alternatively, formally document that the lawful basis is "contractual necessity" (Art. 6(1)(b)) and clarify the consent types are for supplementary purposes only

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
**Description**: The pattern anonymizer uses only three regex patterns to detect PII before storing cross-engagement patterns. The task mining module has its own PII detection (`PIIType` enum with 10 categories including credit cards, addresses, names, DOB, financial, and medical), but the pattern anonymizer does not leverage it. This finding has persisted across three audits.

**Risk**: Incomplete anonymization could leak client-identifying information into the shared pattern library.

**Recommendation**:
1. Align pattern anonymizer PII detection with the `PIIType` enum categories
2. Add credit card (Luhn), IP address, and international phone patterns at minimum

---

### [LOW] DATA-RETENTION: Automated retention cleanup disabled by default with incomplete coverage

**File**: `src/core/config.py:103`, `src/core/retention.py`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/core/config.py (retention_cleanup_enabled)
retention_cleanup_enabled: bool = False
```
**Description**: `retention_cleanup_enabled` defaults to `False`. The six cleanup functions in `src/core/retention.py` (engagements, copilot messages, HTTP audit events, task mining events, task mining actions, PII quarantine) are not invoked by any automated scheduler. Additionally, the GDPR erasure worker (`src/gdpr/erasure_worker.py`) exists but its scheduling mechanism is not configured -- it relies on being triggered via the task queue.

**Risk**: Without automated cleanup, data accumulates indefinitely. Five of six cleanup functions are only reachable via manual admin action.

**Recommendation**:
1. Enable `retention_cleanup_enabled` by default or require explicit opt-out
2. Add scheduled job entries for all cleanup functions
3. Document the expected scheduling configuration in deployment documentation

---

### [LOW] GDPR-DPA: No data processing agreement template or tracking

**File**: `src/core/config.py:100-102`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
# src/core/config.py
# TODO(DPA): GDPR Article 28 requires Data Processing Agreements between the
# platform operator and each client. Retention periods below must align with
# agreed DPA terms.
```
**Description**: No DPA template, acceptance endpoint, or tracking model exists. The TODO comment has been present since 2026-02-26 with no implementation progress.

**Risk**: GDPR Article 28 requires written contracts between data controllers and processors. Operating without formalized DPAs exposes the platform to regulatory risk.

**Recommendation**:
1. Create a DPA template in `docs/legal/`
2. Add DPA acceptance tracking at the engagement level
3. Consider blocking engagement creation until a DPA reference is provided

---

## Positive Findings (Improvements Since 2026-02-26)

1. **GDPR erasure background job implemented** (`src/gdpr/erasure_job.py`, `src/gdpr/erasure_worker.py`): Full cross-store erasure coordination across PostgreSQL (user anonymization + audit log actor cleanup), Neo4j graph node removal (pending driver wiring via KMFLOW-62), and Redis cache purge (session/token/user keys). The `GdprErasureWorker` extends `TaskWorker` with progress reporting and retry support (`max_retries=3`). This resolves the sole CRITICAL finding from the 2026-02-26 audit.

2. **GDPR data export now comprehensive** (`src/api/routes/gdpr.py:180-242`): The `DataExportResponse` now includes six data sources: user profile, memberships, audit entries, annotations, user consents, and copilot messages. This resolves the previous HIGH finding about incomplete data subject access requests.

3. **Integration routes now have audit logging** (`src/api/routes/integrations.py:172,241,264,346`): Connection creation, update, deletion, and sync operations all create AuditLog entries using `AuditAction.INTEGRATION_CONNECTED`.

4. **LLM cost controls in place**: The copilot uses configurable `copilot_max_response_tokens` (default 2000) from settings, with response truncation at 10,000 characters in `_validate_response()` and streaming. The suggester uses `max_tokens=2000`. Rate limiting is enforced at 10 queries/min per user via `copilot_rate_limit`.

5. **Prompt injection defenses maintained**: All five domain templates in `src/rag/prompts.py` include the anti-injection directive. Input sanitization (`_sanitize_input`) strips control characters and truncates to 5,000 chars. Output validation (`_validate_response`) truncates and strips system prompt leakage.

6. **Comprehensive audit action taxonomy**: 56 distinct `AuditAction` enum values covering the full platform lifecycle including PII detection events, consent tracking, conflict resolution, and cohort suppression.

7. **Immutable consent records**: `UserConsent` uses append-only design (one row per event, never updated in place) with IP address capture for forensic traceability.

8. **Data classification model exists**: `DataClassification` enum (PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED) on `EvidenceItem` provides the foundation for sensitivity-based access control, even though enforcement is not yet implemented.

---

## Audit Progression Summary

| Metric | 2026-02-20 | 2026-02-26 | 2026-03-19 |
|--------|------------|------------|------------|
| CRITICAL | 3 | 1 | 0 |
| HIGH | 5 | 3 | 3 |
| MEDIUM | 5 | 4 | 4 |
| LOW | 3 | 3 | 3 |
| **Total** | **16** | **11** | **10** |
| Resolved since prev | -- | 7 | 2 |
| New since prev | -- | 2 | 1 |

Key trend: All CRITICAL findings have been resolved. The remaining findings are predominantly long-standing issues (4 of 10 findings have persisted across all three audits) that require architectural decisions rather than simple code changes.
