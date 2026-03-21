# A2: Injection & Input Validation Audit Findings

**Auditor**: A2 (Injection Auditor)
**Date**: 2026-03-20 (Fifth audit)
**Previous Audits**: 2026-02-20 (initial), 2026-02-26 (re-audit), 2026-03-19 (third), 2026-03-19 (fourth)
**Scope**: OWASP injection vectors, file upload security, LLM prompt injection, XSS, SSRF, XML parsing, Cypher injection

## Executive Summary

This fifth audit evaluates the injection posture of the KMFlow platform following the fourth audit and subsequent remediation work. Four of the five previously-open findings have been fully remediated:

- **DELTA-DELETE-INJECTION** (MEDIUM): Fixed -- single quotes are now escaped via `str(path).replace("'", "''")` at `backend.py:396`.
- **SERVICENOW-TABLE-INJECTION** (MEDIUM): Fixed -- `_VALID_TABLE_NAME.match(table_name)` regex validation added at `servicenow.py:89-92`.
- **SALESFORCE-SINCE-UNVALIDATED** (LOW): Fixed -- `datetime.fromisoformat(since)` validation added at `salesforce.py:172-175`.
- **INTERNAL-PATH-EXPOSURE** (LOW): Fixed -- `file_path` replaced with `download_url` in `EvidenceResponse` schema.

The MAGIC-FALLBACK finding remains partially open: the `ImportError` path now raises (preventing silent fallback when python-magic is absent), but the `(ValueError, OSError)` exception handler still falls back to the client-provided MIME type when magic detection fails at runtime. No new findings were identified.

**Security Score**: 8.5/10 (up from 7.5/10; four findings remediated, one partially improved)

## Finding Summary

| Severity | Count (Current) | Count (Previous) | Change |
|----------|-----------------|-------------------|--------|
| CRITICAL | 0               | 0                 | 0      |
| HIGH     | 0               | 0                 | 0      |
| MEDIUM   | 1               | 3                 | -2 (Delta Lake + ServiceNow fixed) |
| LOW      | 0               | 2                 | -2 (Salesforce + path exposure fixed) |
| **Total** | **1**          | **5**             | **-4** |

## Remediation Status from Previous Audit

| Finding | Severity | Status | Notes |
|---------|----------|--------|-------|
| DELTA-DELETE-INJECTION: String interpolation in Delta Lake | MEDIUM | **FIXED** | Line 396 now escapes quotes: `safe_path = str(path).replace("'", "''")` |
| SERVICENOW-TABLE-INJECTION: Unvalidated table name | MEDIUM | **FIXED** | Lines 89-92 now validate with `_VALID_TABLE_NAME.match(table_name)` regex before URL interpolation |
| SALESFORCE-SINCE-UNVALIDATED: Unsanitized timestamp | LOW | **FIXED** | Lines 172-175 now validate with `datetime.fromisoformat(since)` before SOQL interpolation |
| INTERNAL-PATH-EXPOSURE: file_path in API responses | LOW | **FIXED** | `EvidenceResponse` now uses `download_url` field instead of `file_path` |
| MAGIC-FALLBACK: File type detection fallback | MEDIUM | **PARTIALLY FIXED** | `ImportError` now raises instead of silent fallback; `(ValueError, OSError)` path still uses client MIME type |

---

## Open Findings

### [MEDIUM] MAGIC-FALLBACK: File Type Detection Falls Back to Client MIME Type on Magic Errors

**File**: `src/evidence/pipeline.py:109-121`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
detected_type = mime_type or "application/octet-stream"

try:
    import magic
except ImportError as exc:
    raise ImportError(
        "python-magic is required for file type validation. ..."
    ) from exc

try:
    detected_type = magic.from_buffer(file_content[:8192], mime=True)
except (ValueError, OSError):
    logger.debug("Magic detection failed, using client-provided MIME type")
```
**Description**: The `ImportError` path has been hardened (now raises instead of silently falling back). However, if `python-magic` is installed but `magic.from_buffer()` raises `ValueError` or `OSError` at runtime (e.g., corrupt file, damaged libmagic database), the function falls back to the untrusted client-provided `mime_type` value stored in `detected_type`. The allowlist check then runs against this attacker-controllable value.
**Risk**: An attacker who can trigger a magic detection failure (e.g., via a specially-crafted file that causes libmagic to error) could bypass the content-based detection and have their spoofed Content-Type header accepted against the allowlist. Requires authenticated access and an engagement membership.
**Recommendation**: When `magic.from_buffer()` fails, reject the upload or fall back to `"application/octet-stream"` (which is only accepted for a narrow set of extensions) rather than trusting the client MIME type. Example:
```python
except (ValueError, OSError):
    logger.warning("Magic detection failed for uploaded file")
    detected_type = "application/octet-stream"  # Safe fallback
```

---

## Controls That Passed Audit

| Area | Finding |
|------|---------|
| SQL Injection | No raw SQL with string interpolation. All database queries use SQLAlchemy ORM or `sqlalchemy.text()` with bound parameters. pgvector queries in `retrieval.py:291-312` and `embeddings.py:128-160` use `:param` binding. |
| XSS (Frontend) | No `dangerouslySetInnerHTML`, `innerHTML`, `v-html`, `eval()`, or `document.write` found in any React component under `frontend/src/`. |
| XXE (All Parsers) | All 6 XML parsers use `XMLParser(resolve_entities=False, no_network=True, dtd_validation=False)`: `bpmn_parser.py:54`, `dmn_parser.py:54`, `visio_parser.py:79`, `xes_parser.py:72-73,92-93`, `financial_regulatory_parser.py:213-214`. |
| Command Injection | `create_subprocess_exec` in `video_parser.py:149` uses the exec variant (argument list, not shell) with fixed ffmpeg arguments. The `file_path` comes from internal storage. |
| Path Traversal (Upload) | `store_file()` strips directory components with `Path(file_name).name`, prefixes with UUID, and validates resolved path stays under engagement directory. |
| Path Traversal (Download) | `download_evidence()` resolves file path and checks `is_relative_to(evidence_root)` at `evidence.py:606-613`. Logs traversal attempts. |
| Zip-Slip (Visio) | Visio parser validates zip entry paths: normalizes with `Path()`, rejects `is_absolute()` and `startswith("..")` entries (`visio_parser.py:73-76`). |
| CSRF | Double-submit cookie CSRF protection via `src/api/middleware/csrf.py`. JSON request bodies for API mutations. |
| SSRF (Integrations) | All integration HTTP clients (SAP, Celonis, Soroco, ServiceNow, Salesforce, APEX, Charles River, Camunda) use configured base URLs from encrypted DB storage, not user-supplied URLs per-request. All use `httpx.AsyncClient` with explicit timeouts. |
| Deserialization | No `pickle.load()`, `eval()`, `exec()`, or unsafe `yaml.load()` found in `src/`. One `__import__("sqlalchemy")` in `health.py:55` is safe (static constant). |
| Cypher Injection (Property Keys) | `_validate_property_keys()` with regex `^[a-zA-Z_][a-zA-Z0-9_]*$` applied in all write methods: `create_node`, `find_nodes`, `create_relationship`, `batch_create_nodes`, `batch_create_relationships` (`graph.py:31-35`). |
| Cypher Injection (Labels) | Node labels validated against `VALID_NODE_LABELS` frozenset loaded from YAML ontology (`graph.py:40`). All label-interpolating methods check before use. |
| Cypher Injection (Relationships) | Relationship types validated against `VALID_RELATIONSHIP_TYPES` frozenset (`graph.py:41`). Checked in `create_relationship`, `batch_create_relationships`, `get_relationships`, and `traverse`. |
| Cypher Injection (Graph Traversal) | `traverse()` depth parameter is typed as `int` in Python. Neo4j query uses `$depth` parameter. API route validates 1-5 range. |
| LLM Prompt Injection (Query) | Copilot uses XML delimiters (`<user_query>`, `<evidence_context>`) with explicit anti-injection instructions. `_sanitize_input()` strips control characters and truncates to 5000 chars (`copilot.py:24-29`). |
| LLM Prompt Injection (History) | Both `_generate_response()` and `chat_streaming()` validate role is `"user"` or `"assistant"` and apply `_sanitize_input()` to content. Non-standard roles are rejected (`copilot.py:254-259`). |
| LLM Response Validation | `_validate_response()` truncates to 10000 chars and `strip_system_prompt_leakage()` redacts leaked system prompt fragments (`prompts.py:87-93`). Streaming path enforces same limit per-chunk (`copilot.py:270-273`). |
| File Upload Validation | Size limit checked via Content-Length header (`evidence.py:192-198`), MIME allowlist (25+ types in `ALLOWED_MIME_TYPES`), content-based detection via python-magic, extension validation for octet-stream files, SHA-256 duplicate detection, engagement-scoped storage. |
| SVG XSS Prevention | SVG files served with `Content-Disposition: attachment` to prevent browser rendering of untrusted SVG content (`evidence.py:628-629`). |
| Delta Lake Injection | Delete predicate now escapes single quotes (`backend.py:396`). |
| ServiceNow URL Safety | Table name validated with `_VALID_TABLE_NAME` regex before URL interpolation (`servicenow.py:20,89`). |
| Salesforce SOQL Safety | `since` timestamp validated with `datetime.fromisoformat()` before SOQL interpolation (`salesforce.py:172-175`). `object_type` and `fields` validated by `_validate_sobject_name()` and `_validate_field_name()` respectively. |
| RLS DDL Generation | `_validate_table_name()` with regex `^[a-z_][a-z0-9_]*$` prevents SQL injection in RLS policy DDL (`rls.py:31,167-178`). |
| Unity Catalog DDL | `_safe_identifier()` strips non-alphanumeric characters (`unity_catalog.py:185-193`). Backtick-quoted identifiers. `_escape_sql_string()` escapes single quotes in comments (`unity_catalog.py:196-198`). |
| CORS | Restricted to `cors_origins` setting (default `["http://localhost:3000"]`). |
| Security Headers | Full suite: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, Cache-Control, CSP, Permissions-Policy, HSTS. |
| Rate Limiting | Per-IP rate limiting via Redis-backed Lua script (atomic INCR+EXPIRE). Copilot endpoints have additional per-user rate limiting. |
| Redis Eval Safety | Rate limit script is a static Lua string constant, not constructed from user input (`security.py`). |
| API Path Exposure | `EvidenceResponse` now uses `download_url` instead of exposing internal `file_path`. |

---

## Checkbox Verification Results

- [x] NO HARDCODED SECRETS - Verified: Default dev secrets exist in config defaults but are blocked in non-dev environments by `reject_default_secrets_in_production()` validator
- [x] INPUT VALIDATION (Query) - Verified: User queries sanitized via `_sanitize_input()`, Pydantic `max_length=5000`, query_type regex-validated
- [x] INPUT VALIDATION (History) - Verified: Conversation history messages sanitized with role validation and `_sanitize_input()` on content
- [x] SQL INJECTION PREVENTION - Verified: All SQL uses parameterized queries via SQLAlchemy ORM or `text()` with bound params
- [x] XXE PREVENTION - Verified: All XML parsers (6 total) use safe XMLParser with `resolve_entities=False, no_network=True`
- [x] XSS PREVENTION - Verified: No `dangerouslySetInnerHTML` or `innerHTML` in frontend components; SVG forced to attachment download
- [x] COMMAND INJECTION PREVENTION - Verified: subprocess uses exec variant with fixed arguments
- [x] PATH TRAVERSAL PREVENTION - Verified: Upload paths sanitized, download paths resolved and boundary-checked
- [x] CYPHER INJECTION PREVENTION - Verified: Labels, relationship types, property keys, and depth all validated
- [x] CSRF PREVENTION - Verified: Double-submit cookie CSRF middleware in place
- [x] SSRF PREVENTION - Verified: No user-supplied URLs in HTTP clients; base URLs from encrypted config
- [x] DELTA LAKE INJECTION - **NOW FIXED**: Single quotes escaped in delete predicate
- [x] SERVICENOW URL SAFETY - **NOW FIXED**: Table name validated with regex before URL interpolation
- [x] SALESFORCE SOQL SAFETY - **NOW FIXED**: Timestamp validated as ISO 8601 before SOQL interpolation
- [x] API PATH EXPOSURE - **NOW FIXED**: `file_path` replaced with `download_url` in response schema
- [ ] FILE TYPE VALIDATION - Partial: Content-based detection degrades to client MIME type when `magic.from_buffer()` raises `ValueError`/`OSError`

---

## Risk Assessment

**Overall Risk**: LOW

The application has zero CRITICAL or HIGH injection vulnerabilities. Four of the five previously-open findings have been fully remediated in this cycle, leaving only a single MEDIUM finding (MAGIC-FALLBACK) which has itself been partially improved -- the `ImportError` path now raises instead of silently falling back. The remaining attack surface requires an authenticated user to craft a file that triggers a libmagic error while simultaneously spoofing a Content-Type header matching the MIME allowlist.

The codebase demonstrates mature, consistent injection prevention patterns across all attack vectors:
- All 6 XML parsers use safe configuration (`resolve_entities=False, no_network=True`)
- All Neo4j queries use parameterized values with allowlist-validated labels/types/property keys
- All SQL uses SQLAlchemy ORM or parameterized `text()` queries
- All integration connectors validate identifiers before URL/query interpolation
- LLM prompt injection is mitigated with sanitization, XML delimiters, and anti-injection instructions on both query and history paths
- File uploads are validated by size, MIME type, content detection, and path sanitization
- Download endpoint has path traversal defense with `is_relative_to()` check

**Priority remediation**:
1. **MAGIC-FALLBACK** (MEDIUM) -- Change the `(ValueError, OSError)` fallback from client MIME type to `"application/octet-stream"` to eliminate the last trust-boundary gap in file upload validation
