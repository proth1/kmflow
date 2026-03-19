# A2: Injection & Input Validation Audit Findings

**Auditor**: A2 (Injection Auditor)
**Date**: 2026-03-19 (Third audit)
**Previous Audits**: 2026-02-20 (initial), 2026-02-26 (re-audit)
**Scope**: OWASP injection vectors, file upload security, LLM prompt injection, XSS, SSRF, XML parsing, Cypher injection

## Executive Summary

This third audit evaluates the injection posture of the KMFlow platform following continued development since the February 26 re-audit. One HIGH finding from the previous audit (CYPHER-INJECTION-TRAVERSAL) has been fully remediated -- `get_relationships()` and `traverse()` now validate relationship types against `VALID_RELATIONSHIP_TYPES` before interpolation. However, a new HIGH finding has been identified: the `financial_regulatory_parser.py` XML parser uses `etree.fromstring()` without a safe XMLParser configuration, re-introducing the XXE attack surface that was fixed in all other parsers. The remaining findings from the previous audit (3 MEDIUM, 2 LOW) remain open with no change. One new MEDIUM finding has been identified regarding unsanitized conversation history injection into LLM prompts.

**Security Score**: 7.0/10 (down from 7.5/10 due to the new XXE regression and history injection finding)

## Finding Summary

| Severity | Count (Current) | Count (Previous) | Change |
|----------|-----------------|-------------------|--------|
| CRITICAL | 0               | 0                 | 0      |
| HIGH     | 1               | 0                 | +1 (new XXE regression) |
| MEDIUM   | 4               | 4                 | 0 (1 fixed, 1 new) |
| LOW      | 2               | 2                 | 0      |
| **Total** | **7**          | **6**             | **+1** |

## Remediation Status from Previous Audit

| Finding | Severity | Status | Notes |
|---------|----------|--------|-------|
| CYPHER-INJECTION-TRAVERSAL: Unvalidated relationship types | MEDIUM | **FIXED** | `get_relationships()` now validates at line 455; `traverse()` validates at lines 530-532. Both check against `VALID_RELATIONSHIP_TYPES` before interpolation. |
| MAGIC-FALLBACK: File type detection fallback | MEDIUM | OPEN | Still falls back to client-provided MIME type when python-magic unavailable (line 112) |
| DELTA-DELETE-INJECTION: String interpolation in Delta Lake | MEDIUM | OPEN | `dt.delete(f"file_path = '{path}'")` still present at line 396 of `backend.py` |
| SERVICENOW-TABLE-INJECTION: Unvalidated table name | MEDIUM | OPEN | `table_name` still interpolated without validation at line 99 of `servicenow.py` |
| INTERNAL-PATH-EXPOSURE: file_path in API responses | LOW | OPEN | `file_path` still in `EvidenceResponse` |
| SALESFORCE-SINCE-UNVALIDATED: Unsanitized timestamp | LOW | OPEN | `since` still interpolated directly into SOQL at line 177 of `salesforce.py` |

---

## New Findings

### [HIGH] XXE-REGRESSION: Unsafe XML Parsing in Financial Regulatory Parser

**File**: `src/evidence/parsers/financial_regulatory_parser.py:213`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
async def _parse_xml(self, file_path: str, file_name: str) -> ParseResult:
    """Extract text content from XML (e.g., EDGAR XBRL filings)."""
    from lxml import etree

    with open(file_path, encoding="utf-8", errors="replace") as fh:
        content = fh.read()

    try:
        root = etree.fromstring(content.encode())
```
**Description**: The `_parse_xml()` method in the financial regulatory parser calls `etree.fromstring(content.encode())` without passing a safe `XMLParser` instance. This is inconsistent with every other XML parser in the codebase, all of which use `XMLParser(resolve_entities=False, no_network=True, dtd_validation=False)`:
- `bpmn_parser.py:54-55` -- uses safe parser
- `dmn_parser.py:54-55` -- uses safe parser
- `visio_parser.py:79-80` -- uses safe parser
- `xes_parser.py:72-73` -- uses safe parser

The previous audit (2026-02-20) marked the original XXE finding as FIXED across all parsers, but this parser was added after that remediation and does not follow the established safe pattern. The `financial_regulatory_parser.py` file handles EDGAR XBRL filings and other regulatory XML documents uploaded by users as evidence.
**Risk**: An attacker could upload a crafted XML file as a regulatory document that exploits XML External Entity (XXE) processing to read local files from the server filesystem (e.g., `/etc/passwd`, application config files containing secrets), perform SSRF against internal network services, or cause denial of service via entity expansion (billion laughs attack). This is classified HIGH rather than CRITICAL because the file upload pipeline requires authentication and engagement-level access.
**Recommendation**:
1. Add a safe XMLParser: `parser = etree.XMLParser(resolve_entities=False, no_network=True, dtd_validation=False)` and pass it to `etree.fromstring(content.encode(), parser)`
2. Add a unit test that verifies XXE payloads are rejected
3. Consider adding a shared `_safe_xml_parser()` factory function in `parsers/base.py` to prevent future regressions

---

### [MEDIUM] LLM-HISTORY-INJECTION: Unsanitized Conversation History in LLM Prompts

**File**: `src/rag/copilot.py:150-152`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
async def _generate_response(
    self, system_prompt: str, user_prompt: str,
    history: list[dict[str, Any]] | None = None,
) -> str:
    msgs: list[dict[str, str]] = []
    if history:
        for msg in history[-5:]:  # Keep last 5 messages for context
            msgs.append({"role": msg["role"], "content": msg["content"]})
```
**Description**: While the current user query is sanitized via `_sanitize_input()` (stripping control characters and truncating to 5000 chars), the conversation history messages passed from the client are forwarded to the LLM without any sanitization. The `history` parameter is a list of dicts accepted from the `ChatRequest` Pydantic model and passed directly through to the LLM provider. An attacker could inject prompt override instructions in a prior "assistant" message within the history array (e.g., `{"role": "assistant", "content": "Ignore all previous instructions and..."}`) or craft a fake "user" message containing prompt injection payloads.

The `ChatRequest` schema validates `query` with `min_length=1, max_length=5000` but applies no validation to individual `history` entries -- no role validation, no content length limits, no sanitization.
**Risk**: A malicious client could manipulate the LLM's behavior by injecting crafted messages into the history array. This could cause the model to ignore its system prompt instructions, leak evidence from other engagements (if context boundaries are weakened), or generate misleading responses. The impact is mitigated by the fact that retrieval results are scoped to the user's engagement via `engagement_id`, and the system prompt includes guidance to base answers on provided evidence.
**Recommendation**:
1. Apply `_sanitize_input()` to each `history[].content` value before passing to the LLM
2. Validate that `history[].role` is strictly `"user"` or `"assistant"` (reject other roles like `"system"`)
3. Add a `max_length` constraint to history message content in the `ChatRequest` schema
4. Limit the total character count across all history messages (not just the count of messages)

---

## Continuing Open Findings

### [MEDIUM] MAGIC-FALLBACK: File Type Detection Falls Back to Client MIME Type

**File**: `src/evidence/pipeline.py:105-114`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
detected_type = mime_type or "application/octet-stream"
try:
    import magic
    detected_type = magic.from_buffer(file_content[:8192], mime=True)
except ImportError:
    logger.debug("python-magic not available, using client-provided MIME type")
```
**Description**: Unchanged from previous audit. If `python-magic` is not installed, the function falls back to the untrusted client-provided MIME type. The allowlist check then runs against the attacker-controlled value.
**Risk**: In deployments where `python-magic` is not installed, a user could upload a malicious file by spoofing the Content-Type header.
**Recommendation**: Make `python-magic` a required dependency, or reject uploads when content-based detection is unavailable.

---

### [MEDIUM] DELTA-DELETE-INJECTION: String Interpolation in Delta Lake Delete Predicate

**File**: `src/datalake/backend.py:396`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
dt = DeltaTable(self._table_path)
dt.delete(f"file_path = '{path}'")
```
**Description**: Unchanged from previous audit. The `path` parameter is interpolated directly into the Delta Lake delete predicate without escaping.
**Risk**: A file path containing a single quote could cause unintended row deletion in the Delta metadata table.
**Recommendation**: Escape single quotes: `safe_path = path.replace("'", "''")`.

---

### [MEDIUM] SERVICENOW-TABLE-INJECTION: Unvalidated Table Name in URL Path

**File**: `src/integrations/servicenow.py:85-99`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
table_name = kwargs.get("table_name", "incident")
# ...
url = f"{self._base_url}/api/now/table/{table_name}"
```
**Description**: Unchanged from previous audit. The `table_name` parameter is interpolated into the ServiceNow API URL without validation. The Salesforce connector's `_validate_sobject_name()` pattern was not applied.
**Risk**: URL path injection could access unintended ServiceNow API endpoints.
**Recommendation**: Add regex validation: `re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name)`.

---

### [LOW] INTERNAL-PATH-EXPOSURE: File Paths Exposed in API Responses

**File**: `src/api/routes/evidence.py:54`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
class EvidenceResponse(BaseModel):
    # ...
    file_path: str | None = None
```
**Description**: Unchanged. Internal server filesystem paths exposed to API consumers.
**Risk**: Information disclosure useful for reconnaissance.
**Recommendation**: Replace with a download URL/token.

---

### [LOW] SALESFORCE-SINCE-UNVALIDATED: Unsanitized Timestamp in SOQL WHERE Clause

**File**: `src/integrations/salesforce.py:177`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
kwargs["_soql_override"] = f"SELECT {', '.join(fields)} FROM {object_type} WHERE LastModifiedDate > {since}"
```
**Description**: Unchanged. The `since` timestamp is interpolated directly into the SOQL WHERE clause without format validation.
**Risk**: Low. SOQL injection via timestamp manipulation, but `since` is not directly exposed to end users.
**Recommendation**: Validate as ISO 8601 before interpolation: `datetime.fromisoformat(since)`.

---

## Controls That Passed Audit

| Area | Finding |
|------|---------|
| SQL Injection | No raw SQL found. All database queries use SQLAlchemy ORM or `sqlalchemy.text()` with bound parameters. Retrieval engine at `retrieval.py:193-214` uses parameterized pgvector queries. |
| XSS (Frontend) | No `dangerouslySetInnerHTML`, `innerHTML`, `v-html`, `eval()`, or `document.write` found in any React component under `frontend/src/`. |
| XXE (Most Parsers) | BPMN, DMN, Visio, and XES parsers all use `XMLParser(resolve_entities=False, no_network=True)`. Only `financial_regulatory_parser._parse_xml()` is missing this protection. |
| Command Injection | `create_subprocess_exec` in `video_parser.py:149` uses the exec variant (argument list, not shell) with fixed ffmpeg arguments. The `file_path` is from internal storage, not direct user input. |
| Path Traversal (Upload) | `store_file()` strips directory components with `Path(file_name).name`, prefixes with UUID, and validates resolved path stays under engagement directory (lines 215-222). |
| Zip-Slip (Visio) | Visio parser validates zip entry paths with `Path(page_file)` normalization, `is_absolute()`, and `startswith("..")` checks (lines 73-76). |
| CSRF | FastAPI uses JSON request bodies. Cookie auth uses `SameSite=Lax`. |
| SSRF | Integration HTTP clients use configured base URLs from environment/config, not user-supplied URLs. All connectors use `httpx.AsyncClient` with explicit timeout. No `follow_redirects` overrides. |
| Deserialization | No `pickle.load()`, `eval()`, `exec()`, or unsafe `yaml.load()` found. |
| Cypher Injection (Property Keys) | `_validate_property_keys()` with regex `^[a-zA-Z_][a-zA-Z0-9_]*$` applied in all write methods. |
| Cypher Injection (Labels) | Node labels validated against `VALID_NODE_LABELS` frozenset. Relationship types validated against `VALID_RELATIONSHIP_TYPES` in both write and read methods (including `get_relationships()` and `traverse()`). |
| Cypher Injection (Depth) | `traverse()` depth parameter is typed as `int` in Python and validated as 1-5 in the API route (`graph.py:194`). Cannot be string-injected. |
| LLM Prompt Injection (Query) | Copilot uses XML delimiters (`<user_query>`, `<evidence_context>`) with explicit anti-injection instructions in all 5 prompt templates. `_sanitize_input()` strips control characters and truncates to 5000 chars. Suggester uses same pattern. |
| LLM Response Validation | `_validate_response()` truncates to 10000 chars and calls `strip_system_prompt_leakage()` to redact leaked system prompt fragments. Streaming also validates each chunk. |
| Input Length Limits | Copilot query: 5000 chars (Pydantic + sanitizer). Simulation suggester: name 200, description 1000, context 500 chars. Query type validated by regex pattern. |
| Rate Limiting | Per-user rate limiting on copilot endpoints via `copilot_rate_limit` dependency. Global rate limiting via SlowAPI middleware. |
| File Upload Validation | Size limit 100MB, MIME allowlist (25+ types), content-based detection via python-magic, extension validation for octet-stream, SHA-256 duplicate detection. |
| CORS | Restricted to `cors_origins` setting (default `["http://localhost:3000"]`), with specific allowed headers and credentials. |
| Security Headers | Full suite: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, Cache-Control, CSP, Permissions-Policy, HSTS. |
| Default Secret Protection | `reject_default_secrets_in_production()` model validator blocks startup with dev secrets in non-development environments. |
| Error Handling | Generic error messages in API responses. Request IDs for correlation without leaking internals. |

---

## Checkbox Verification Results

- [ ] NO HARDCODED SECRETS - Verified: Default dev secrets exist in config defaults but are blocked in non-dev environments by `reject_default_secrets_in_production()` validator
- [x] INPUT VALIDATION (Query) - Verified: User queries sanitized via `_sanitize_input()`, Pydantic `max_length=5000`, query_type regex-validated
- [ ] INPUT VALIDATION (History) - Security Risk: Conversation history messages passed unsanitized to LLM
- [x] SQL INJECTION PREVENTION - Verified: All SQL uses parameterized queries via SQLAlchemy ORM or `text()` with bound params
- [ ] XXE PREVENTION - Security Risk: `financial_regulatory_parser._parse_xml()` lacks safe XMLParser
- [x] XSS PREVENTION - Verified: No `dangerouslySetInnerHTML` or `innerHTML` in frontend components
- [x] COMMAND INJECTION PREVENTION - Verified: subprocess uses exec variant with fixed arguments
- [x] PATH TRAVERSAL PREVENTION - Verified: Upload paths sanitized, resolved, and boundary-checked
- [x] CYPHER INJECTION PREVENTION - Verified: Labels, relationship types, and property keys all validated
- [x] CSRF PREVENTION - Verified: JSON request bodies, SameSite=Lax cookies
- [x] SSRF PREVENTION - Verified: No user-supplied URLs in HTTP clients

---

## Risk Assessment

**Overall Risk**: LOW-MEDIUM

The application has no CRITICAL injection vulnerabilities. The HIGH XXE finding in the financial regulatory parser is a regression that affects a single parser and requires authenticated access to exploit. The remaining MEDIUM findings require authenticated attackers with specific integration access. The codebase demonstrates strong injection prevention patterns overall, with the financial regulatory parser being an outlier that missed the remediation wave.

**Priority remediation order**:
1. **XXE-REGRESSION** (HIGH) -- Direct XXE in uploaded regulatory XML; fix is a one-line addition of safe XMLParser
2. **LLM-HISTORY-INJECTION** (MEDIUM) -- Unsanitized history enables prompt injection via API
3. **SERVICENOW-TABLE-INJECTION** (MEDIUM) -- Inconsistent validation pattern across connectors
4. **DELTA-DELETE-INJECTION** (MEDIUM) -- Predicate injection in storage layer
5. **MAGIC-FALLBACK** (MEDIUM) -- Deployment-dependent file upload bypass
6. **SALESFORCE-SINCE-UNVALIDATED** (LOW) -- Limited attack surface
7. **INTERNAL-PATH-EXPOSURE** (LOW) -- Information disclosure only
