# A2: Injection & Input Validation Audit Findings

**Auditor**: A2 (Injection Auditor)
**Date**: 2026-02-26 (Re-audit)
**Previous Audit**: 2026-02-20
**Scope**: OWASP injection vectors, file upload security, LLM prompt injection, XSS, SSRF, XML parsing, Cypher injection

## Executive Summary

This re-audit evaluates the current injection posture after Phase 0-2 remediation work. The codebase has improved substantially since the initial audit on 2026-02-20. Six of the eleven original findings have been fully remediated, including both CRITICAL findings (raw Cypher query endpoint removal and XXE fixes in all XML parsers). The remaining open findings are primarily MEDIUM and LOW severity, with one new MEDIUM finding identified during this re-audit.

**Security Score**: 7.5/10 (up from 5.0/10 on 2026-02-20)

## Finding Summary

| Severity | Count (Current) | Count (Previous) | Change |
|----------|-----------------|-------------------|--------|
| CRITICAL | 0               | 2                 | -2 (FIXED) |
| HIGH     | 0               | 3                 | -3 (FIXED) |
| MEDIUM   | 4               | 4                 | 0 (1 fixed, 1 new) |
| LOW      | 2               | 2                 | 0 (same) |
| **Total** | **6**          | **11**            | **-5** |

## Remediation Status from Previous Audit

| Finding | Severity | Status | Notes |
|---------|----------|--------|-------|
| CYPHER-INJECTION: Raw query endpoint | CRITICAL | FIXED | Endpoint completely removed from `graph.py` |
| XXE: Unsafe XML parsing (BPMN/XES/Visio) | CRITICAL | FIXED | All parsers now use `XMLParser(resolve_entities=False, no_network=True)`. Visio parser also adds zip-slip validation via `os.path.normpath`. |
| LLM-PROMPT-INJECTION: Unsanitized prompts | HIGH | FIXED | All prompt templates now use XML delimiters (`<user_query>`, `<evidence_context>`) with explicit instructions to treat tagged content as data. `_sanitize_input()` strips control characters and truncates to 5000 chars. |
| SOQL-INJECTION: Salesforce queries | HIGH | FIXED | `_validate_sobject_name()` and `_validate_field_name()` added with regex allowlists. Raw `soql_query` kwarg replaced with internal `_soql_override`. |
| CYPHER-INJECTION: Property key injection | HIGH | FIXED | `_validate_property_keys()` added with regex `^[a-zA-Z_][a-zA-Z0-9_]*$` applied in `create_node`, `find_nodes`, `create_relationship`, `batch_create_nodes`. |
| BROAD-MIME-ALLOWLIST: octet-stream allowed | MEDIUM | FIXED | `application/octet-stream` removed from allowlist. Secondary extension check via `_OCTET_STREAM_ALLOWED_EXTENSIONS` for `.bpmn`, `.bpmn2`, `.xes`, `.vsdx` only. |
| MAGIC-FALLBACK: Falls back to client MIME | MEDIUM | OPEN | Still falls back to client-provided MIME type when python-magic unavailable |
| ZIP-SLIP-PARTIAL: Visio zip entries | MEDIUM | FIXED | Zip-slip protection added: `os.path.normpath()` + `os.path.isabs()` + `startswith("..")` check |
| CYPHER-WRITE-BYPASS: Keyword blocklist | MEDIUM | FIXED | Endpoint removed entirely (no blocklist needed) |
| INTERNAL-PATH-EXPOSURE: file_path in API | LOW | OPEN | `file_path` still exposed in `EvidenceResponse` |
| ERROR-DETAIL-LEAKAGE: Exception details | LOW | PARTIAL | Graph build now returns generic "Graph build failed" but some endpoints still leak details |

---

## Current Open Findings

### [MEDIUM] MAGIC-FALLBACK: File Type Detection Falls Back to Client MIME Type

**File**: `/Users/proth/repos/kmflow/src/evidence/pipeline.py:90-113`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
def validate_file_type(file_content: bytes, file_name: str, mime_type: str | None = None) -> str:
    detected_type = mime_type or "application/octet-stream"
    try:
        import magic
        detected_type = magic.from_buffer(file_content[:8192], mime=True)
    except ImportError:
        logger.debug("python-magic not available, using client-provided MIME type")
    except Exception:
        logger.debug("Magic detection failed, using client-provided MIME type")
```
**Description**: If `python-magic` is not installed (it is an optional dependency), the function falls back to the untrusted client-provided MIME type. The allowlist check then runs against the attacker-controlled value. While `application/octet-stream` was removed from the main allowlist (fixing the previous BROAD-MIME-ALLOWLIST finding), a user can still spoof any of the 25+ allowed MIME types in the `Content-Type` header to bypass content-based detection.
**Risk**: In deployments where `python-magic` is not installed, a user could upload a malicious file (e.g., an executable) by setting `Content-Type: application/pdf`. The file would pass the MIME allowlist check despite not being a PDF.
**Recommendation**:
1. Make `python-magic` a required (not optional) dependency
2. If `magic` import fails at startup, log a WARNING and consider rejecting uploads entirely rather than silently degrading
3. Add extension-to-MIME cross-validation as a secondary gate

---

### [MEDIUM] CYPHER-INJECTION-TRAVERSAL: Unvalidated Relationship Types Interpolated into Cypher

**File**: `/Users/proth/repos/kmflow/src/semantic/graph.py:430-447`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
async def get_relationships(
    self, node_id: str, direction: str = "both",
    relationship_type: str | None = None,
) -> list[GraphRelationship]:
    rel_filter = f":{relationship_type}" if relationship_type else ""
    # ...
    query = f"""
    MATCH (a {{id: $node_id}})-[r{rel_filter}]->(b)
    RETURN r, a.id AS from_id, b.id AS to_id, type(r) AS rel_type
    """
```
**Description**: The `get_relationships()` method interpolates `relationship_type` directly into the Cypher query string without validation. While `create_relationship()` and `batch_create_relationships()` correctly validate against `VALID_RELATIONSHIP_TYPES`, the read-side `get_relationships()` does not. The same issue exists in `traverse()` at line 498-503, where `relationship_types` from a user-supplied comma-separated list are joined with `|` and interpolated into the query. The API route at `/api/v1/graph/traverse/{node_id}` passes user-supplied `relationship_types` query parameter directly through to this method.
**Risk**: A user could inject Cypher syntax through the `relationship_types` query parameter of the traverse endpoint. For example, `relationship_types=FOLLOWS]->(b) RETURN b.secret_data AS from_id //` could alter the query semantics. This is a read-only transaction (`execute_read`), which limits the blast radius to data exfiltration rather than mutation.
**Recommendation**:
1. Validate `relationship_type` against `VALID_RELATIONSHIP_TYPES` in `get_relationships()`, matching the pattern used in write methods
2. Validate each entry in `relationship_types` list in `traverse()` before interpolation
3. In the API route, validate the comma-separated input: `for rt in rel_types: if rt not in VALID_RELATIONSHIP_TYPES: raise HTTPException(400, ...)`

---

### [MEDIUM] DELTA-DELETE-INJECTION: String Interpolation in Delta Lake Delete Predicate

**File**: `/Users/proth/repos/kmflow/src/datalake/backend.py:396`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
async def delete(self, path: str) -> bool:
    # ...
    try:
        from deltalake import DeltaTable
        self._ensure_table()
        dt = DeltaTable(self._table_path)
        dt.delete(f"file_path = '{path}'")
    except Exception:
        logger.warning("Failed to remove Delta table row for %s", path)
```
**Description**: The `path` parameter is interpolated directly into the Delta Lake delete predicate string without escaping or parameterization. If `path` contains a single quote, it could break out of the string literal. For example, a crafted path like `' OR 1=1 --` could delete all rows in the Delta table. The `_validate_path()` method is called earlier in the `delete()` flow to verify the path is under the storage boundary, but it does not sanitize the path string against SQL/predicate injection. Delta Lake uses a SQL-like predicate syntax for `dt.delete()`.
**Risk**: A file path containing a single quote could cause unintended row deletion in the Delta metadata table. Exploitation requires the attacker to control the `path` argument, which typically flows from stored `file_path` values. The `_validate_path()` boundary check provides partial mitigation since paths must be under the storage root, but the injection vector remains if a legitimate-looking path contains quotes.
**Recommendation**:
1. Escape single quotes in the path before interpolation: `safe_path = path.replace("'", "''")`
2. Or use Delta Lake's predicate parameterization if the library supports it
3. Validate that the path string contains no single quotes or other SQL metacharacters

---

### [MEDIUM] SERVICENOW-TABLE-INJECTION: Unvalidated Table Name in URL Path

**File**: `/Users/proth/repos/kmflow/src/integrations/servicenow.py:85-99`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
async def sync_data(self, engagement_id: str, **kwargs: Any) -> dict[str, Any]:
    table_name = kwargs.get("table_name", "incident")
    # ...
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, auth=self._auth()) as client:
        url = f"{self._base_url}/api/now/table/{table_name}"
```
**Description**: The `table_name` parameter from `kwargs` is interpolated directly into the ServiceNow API URL without validation. While ServiceNow's REST API itself validates table names server-side (returning 404 for invalid tables), a crafted `table_name` like `incident?sysparm_query=active=true` or `../api/sn_ind_incident` could potentially alter the URL path or inject query parameters. The Salesforce connector was correctly remediated with `_validate_sobject_name()` regex validation, but the same pattern was not applied to the ServiceNow connector's `table_name`.
**Risk**: URL path injection could allow access to unintended ServiceNow API endpoints or bypass query filters. The impact is limited by ServiceNow's server-side access controls and the fact that authentication credentials scope access.
**Recommendation**:
1. Add a regex validation for `table_name`: `re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name)` matching the Salesforce pattern
2. Consider an allowlist of known ServiceNow tables for the integration

---

### [LOW] INTERNAL-PATH-EXPOSURE: File Paths Exposed in API Responses

**File**: `/Users/proth/repos/kmflow/src/api/routes/evidence.py:54`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
class EvidenceResponse(BaseModel):
    # ...
    file_path: str | None = None
```
**Description**: The `EvidenceResponse` model includes `file_path`, which exposes internal server filesystem paths to API consumers. These paths reveal the directory structure (e.g., `evidence_store/{engagement_id}/{file}`) and deployment environment details.
**Risk**: Information disclosure of internal server paths. Low direct impact but useful for reconnaissance in path traversal attacks.
**Recommendation**: Remove `file_path` from the response model, or replace with a download URL/token that abstracts the server path.

---

### [LOW] SALESFORCE-SINCE-UNVALIDATED: Unsanitized Timestamp in SOQL WHERE Clause

**File**: `/Users/proth/repos/kmflow/src/integrations/salesforce.py:171`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
async def sync_incremental(self, engagement_id: str, since: str | None = None, **kwargs: Any) -> dict[str, Any]:
    if since:
        object_type = _validate_sobject_name(kwargs.get("object_type", "Case"))
        fields = [_validate_field_name(f) for f in kwargs.get("fields", [...])]
        kwargs["_soql_override"] = f"SELECT {', '.join(fields)} FROM {object_type} WHERE LastModifiedDate > {since}"
```
**Description**: While `object_type` and `fields` are now properly validated with regex allowlists (fixing the previous HIGH finding), the `since` timestamp parameter is still interpolated directly into the SOQL WHERE clause without validation. A crafted `since` value like `2024-01-01T00:00:00Z OR Name LIKE '%'` could modify the query logic. However, `since` is a `str | None` type parameter that flows from the API/integration layer, not directly from end-user HTTP input, which reduces the attack surface.
**Risk**: Low. SOQL injection via timestamp manipulation. Salesforce itself enforces some query validation server-side, and the `since` parameter is not typically directly exposed to end users.
**Recommendation**:
1. Validate `since` as an ISO 8601 timestamp before interpolation: `datetime.fromisoformat(since)` as a format check
2. Or use SOQL bind variables if the Salesforce API supports them for timestamp comparisons

---

## Controls That Passed Audit

| Area | Finding |
|------|---------|
| SQL Injection | No raw SQL found. All database queries use SQLAlchemy ORM with parameterized queries. The `__import__("sqlalchemy").text("SELECT 1")` in health check is a static literal. |
| XSS (Frontend) | No `dangerouslySetInnerHTML`, `innerHTML`, `eval()`, `Function()`, or `document.write` found in React components. BPMNViewer uses `html` template literals for bpmn-js overlays, but values are numeric (confidence scores and evidence counts), not user-controlled strings. |
| XXE (XML Parsers) | All XML parsers now use `XMLParser(resolve_entities=False, no_network=True)`. BPMN parser at line 54, XES parser at lines 74-75 and 94-95. ARIS parser uses `defusedxml`. |
| Command Injection | `create_subprocess_exec` in video parser uses fixed arguments (`"ffmpeg", "-i", file_path, ...`). The `file_path` is from an internal storage path, not direct user input. Uses `exec` variant (argument list), not `shell` variant. |
| Path Traversal (Upload) | `store_file()` strips directory components with `Path(file_name).name`, prefixes with UUID, and validates resolved path stays under engagement directory. Both `LocalFilesystemBackend` and `DeltaLakeBackend` have `_validate_path()` boundary checks. |
| Path Traversal (Migration) | `_read_local_file()` in governance migration validates resolved paths against `evidence_store/` boundary. |
| Zip-Slip (Visio) | Visio parser validates zip entry paths with `os.path.normpath()`, `os.path.isabs()`, and `startswith("..")` checks before reading entries. |
| CSRF | FastAPI uses JSON request bodies (not form submissions), mitigating traditional CSRF. Cookie auth uses `SameSite=Lax` by default. |
| SSRF | HTTP clients in integrations use configured base URLs from environment/config, not user-supplied URLs. No `follow_redirects` or `allow_redirects` overrides found. All connectors use httpx `AsyncClient` with explicit timeout. |
| Deserialization | No `pickle.load()`, `eval()`, `exec()`, or `yaml.load()` (unsafe) found. All YAML uses `yaml.safe_load()` (3 instances verified). |
| Content Hash Integrity | SHA-256 hashing for uploaded files enables duplicate detection and tampering verification. |
| Input Length Limits | Copilot query limited to 5000 chars. Simulation suggester limits: name 200 chars, description 1000 chars, context 500 chars, modifications 20 lines. |
| Rate Limiting | Per-IP rate limiting via custom middleware + slowapi. Copilot and auth endpoints have dedicated rate limits. Rate limiter uses `request.client.host` (not spoofable X-Forwarded-For). |
| Neo4j Property Injection | Property keys validated against `^[a-zA-Z_][a-zA-Z0-9_]*$` regex in `_validate_property_keys()`. Applied in `create_node`, `find_nodes`, `create_relationship`, `batch_create_nodes`. |
| Neo4j Label Injection | Node labels validated against `VALID_NODE_LABELS` (frozen set from ontology YAML). Relationship types validated against `VALID_RELATIONSHIP_TYPES` in write methods. |
| LLM Prompt Injection | Copilot uses XML delimiters (`<user_query>`, `<evidence_context>`) with explicit anti-injection instructions. Suggester uses same pattern with `<scenario_data>`, `<additional_context>`. Both sanitize control characters. |
| SOQL Injection | Salesforce connector validates object names and field names with regex allowlists. Raw SOQL input removed. |
| Security Headers | Full suite: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, Cache-Control, CSP, Permissions-Policy, HSTS (non-debug). |
| CORS | Restricted to `cors_origins` setting (default `["http://localhost:3000"]`), configurable per environment. Credentials enabled with specific allowed headers. |
| File Upload Validation | Size limit (100MB pipeline, 50MB portal), MIME allowlist (content-based via python-magic when available), extension validation (portal), duplicate detection (SHA-256). |
| Error Handling | Generic 500 handler returns "Internal server error" with request ID. Graph build returns "Graph build failed". Bridge execution returns "Bridge execution failed". |
| Raw Cypher Endpoint | REMOVED. No arbitrary query execution endpoint exists. |

---

## New Finding Details (Not in Previous Audit)

The CYPHER-INJECTION-TRAVERSAL finding (relationship type interpolation in `get_relationships()` and `traverse()`) was not identified in the previous audit because attention was focused on the now-removed raw query endpoint and the property key injection vectors. With the raw endpoint removed, these remaining interpolation points in the graph service become the primary Cypher injection surface.

The DELTA-DELETE-INJECTION finding was not in the previous audit as the Delta Lake backend was not yet fully implemented.

The SERVICENOW-TABLE-INJECTION finding was implicit in the previous SOQL-INJECTION finding's scope but was not explicitly called out. The Salesforce fix was not applied symmetrically to ServiceNow.

---

## Risk Assessment

**Overall Risk**: LOW-MEDIUM

The application has no CRITICAL or HIGH injection vulnerabilities. The remaining MEDIUM findings require an authenticated attacker with specific integration access or engagement-level permissions. The read-only nature of the Cypher traversal endpoints limits the blast radius of the most impactful remaining finding.

**Priority remediation order**:
1. CYPHER-INJECTION-TRAVERSAL -- Direct user input to Cypher query interpolation via public API
2. SERVICENOW-TABLE-INJECTION -- Inconsistent validation pattern across connectors
3. DELTA-DELETE-INJECTION -- Predicate injection in storage layer
4. MAGIC-FALLBACK -- Deployment-dependent file upload bypass
5. SALESFORCE-SINCE-UNVALIDATED -- Limited attack surface
6. INTERNAL-PATH-EXPOSURE -- Information disclosure only
