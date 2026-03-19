# KMFlow Platform Code Audit Report — 2026-03-19

## Executive Summary

- **Total findings: 108**
- **By severity: 3 CRITICAL / 29 HIGH / 41 MEDIUM / 35 LOW**
- **By squad: Security (17) / Architecture (35) / Quality (26) / Coverage (30)**

| Squad | Agent | C | H | M | L | Total | Score |
|-------|-------|---|---|---|---|-------|-------|
| A: Security | A1 AuthZ | 0 | 2 | 2 | 1 | 5 | 8.0/10 |
| | A2 Injection | 0 | 0 | 3 | 2 | 5 | 7.5/10 |
| | A3 Infrastructure | 0 | 1 | 3 | 3 | 7 | 8.6/10 |
| B: Architecture | B1 Architecture | 0 | 2 | 4 | 3 | 9 | 8/10 |
| | B2 Data Integrity | 0 | 2 | 6 | 5 | 13 | 7.9/10 |
| | B3 API Compliance | 1 | 3 | 5 | 4 | 13 | 7.5/10 |
| C: Quality | C1 Python | 0 | 5 | 3 | 2 | 10 | 6.5/10 |
| | C2 Frontend | 0 | 1 | 0 | 3 | 4 | 7.5/10 |
| | C3 Performance | 1 | 4 | 4 | 3 | 12 | HIGH risk |
| D: Coverage | D1 Tests | 1 | 5 | 4 | 2 | 12 | WARNING |
| | D2 Compliance | 0 | 2 | 3 | 2 | 7 | — |
| | D3 Dependencies | 0 | 2 | 4 | 5 | 11 | MED-HIGH |
| **Total** | | **3** | **29** | **41** | **35** | **108** | |

### Remediation Progress

This is the 4th comprehensive audit. Significant progress since the initial audit (2026-02-20):

- **30+ prior findings resolved** across all squads
- Several pre-identified findings from the audit checklist were already remediated:
  - `require_engagement_access()` is now called in 44+ route files
  - MCP `validate_api_key()` now performs proper DB lookup + HMAC comparison
  - Redis has `--requirepass` authentication
  - CORS uses explicit method/header lists (not wildcards)
  - Default secrets are blocked by production startup validator
  - Fernet KDF upgraded to PBKDF2 with 600K iterations
  - JWT stored in HttpOnly cookies (not localStorage)
  - RAG copilot now sanitizes user queries and conversation history

---

## Top 10 Critical & High Findings

1. **[CRITICAL] N+1 Graph Read in `search_similar`** — `src/semantic/graph.py:612` — Every copilot/semantic search issues 10 sequential Neo4j sessions (one per pgvector result row). Batch fetch with `WHERE n.id IN $ids` eliminates this.

2. **[CRITICAL] Auth Rate Limiter IP-Only, Not Per-Account** — `src/api/routes/auth.py:46` — `slowapi` is per-process (not Redis-backed) and IP-only. Distributed credential stuffing from multiple IPs evades all controls.

3. **[CRITICAL] Coverage Threshold Below Mandate** — `pyproject.toml` — `fail_under = 80` while 246 of 408 source modules have no test file. CI passes while critical security paths are untested.

4. **[HIGH] IDOR: POV Model-ID Routes Skip Engagement Check** — `src/api/routes/pov.py:445` — 6 endpoints check `require_permission("pov:read")` but skip engagement membership on model-ID routes. Cross-tenant data access.

5. **[HIGH] IDOR: Evidence Routes Skip Engagement Check** — `src/api/routes/evidence.py:309` — `get_evidence`, `update_validation_status`, `get_fragments` skip engagement membership. Cross-tenant data access and mutation.

6. **[HIGH] 33+ Tables Missing from RLS Engagement Scoping** — `src/core/rls.py:42` — Only 31 tables have RLS policies; 33+ engagement-scoped tables (including `incidents`, `compliance_assessments`) are missing.

7. **[HIGH] requirements.lock Stale — Docker Builds with CVE-Vulnerable Packages** — `requirements.lock` — Pins `cryptography==43.0.3` (floor is `>=46.0.5`), `pyjwt==2.11.0` (CVE-2026-32597), omits `pyopenssl`/`pyasn1`.

8. **[HIGH] requirements.lock Lacks Hash Verification** — No SHA-256 hashes for supply chain tamper detection in Docker builds.

9. **[HIGH] Memory Leak in AlertEngine** — `src/monitoring/alerting/engine.py` — Unbounded lists grow for process lifetime with linear scan on every query.

10. **[HIGH] LLM Calls Not Recorded in LLMAuditLog** — `src/rag/copilot.py:158` — Copilot and TOM rationale generator create no audit records. EU AI Act Art. 12 compliance gap.

---

## CRITICAL Findings

### [CRITICAL] PERFORMANCE: N+1 Graph Read in `search_similar`
**File**: `src/semantic/graph.py:612`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
rows = result.fetchall()
results: list[dict[str, Any]] = []
for row in rows:
    entity_id = str(row.evidence_id)
    node = await self.get_node(entity_id)   # one Neo4j round-trip per row
```
**Description**: After every pgvector similarity query, the function calls `get_node()` once per result row. Each call opens/closes a Neo4j session. For `top_k=10`, this is 10 sequential Neo4j sessions per semantic search, called on every copilot query.
**Risk**: 20-50ms added to every semantic search. Under 20 concurrent copilot sessions, generates 200 sequential Neo4j queries.
**Recommendation**: Batch fetch: `MATCH (n) WHERE n.id IN $ids RETURN n, labels(n)`.

---

### [CRITICAL] API: Auth Endpoint Rate Limiter Not Per-Account
**File**: `src/api/routes/auth.py:46`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

@router.post("/token", response_model=TokenResponse)
@limiter.limit("5/minute")
async def get_token(request: Request, payload: TokenRequest, ...) -> dict[str, Any]:
```
**Description**: `slowapi` limits by IP only (no per-email lockout), is per-process (not Redis-backed), and multi-worker deployments multiply the per-IP window.
**Risk**: Distributed credential stuffing from multiple IPs evades all controls.
**Recommendation**: (1) Back slowapi with Redis. (2) Add per-email lockout counter in Redis.

---

### [CRITICAL] COVERAGE: Coverage Threshold Below Audit Mandate
**File**: `pyproject.toml`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```toml
[tool.coverage.report]
fail_under = 80
```
**Description**: The `fail_under` threshold is 80% while 246 of 408 source modules have no corresponding test file. CI passes while entire subsystems (simulation engine, GDPR agent, watermark extractor) are untested.
**Risk**: Critical security and compliance paths can reach production without test coverage.
**Recommendation**: Raise to 90 after addressing critical coverage gaps.

---

## HIGH Findings

### [HIGH] AUTHZ: IDOR on POV Model-ID Routes
**File**: `src/api/routes/pov.py:445-469`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
@router.get("/{model_id}", response_model=ProcessModelResponse)
async def get_process_model(
    model_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    result = await session.execute(select(ProcessModel).where(ProcessModel.id == model_uuid))
```
**Description**: Six POV endpoints check `require_permission("pov:read")` but skip engagement membership on model-ID routes.
**Risk**: Cross-tenant data leakage — process models, BPMN XML, evidence maps from other engagements accessible by UUID.
**Recommendation**: Call `_check_engagement_member(session, user, model.engagement_id)` after fetching the model.

---

### [HIGH] AUTHZ: IDOR on Evidence Detail/Mutation Routes
**File**: `src/api/routes/evidence.py:309-519`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
@router.get("/{evidence_id}", response_model=EvidenceDetailResponse)
async def get_evidence(
    evidence_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("evidence:read")),
) -> dict[str, Any]:
```
**Description**: `get_evidence`, `update_validation_status`, `get_fragments` skip engagement membership verification. `list_evidence` allows enumeration across all engagements.
**Risk**: Cross-tenant data access and data integrity violation.
**Recommendation**: Call `verify_engagement_member(session, user, evidence.engagement_id)` after fetching.

---

### [HIGH] INFRA: Production Overlay Missing CIB7/MinIO Overrides
**File**: `docker-compose.prod.yml`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```yaml
# docker-compose.yml:104-105 (CIB7 -- exposed with no auth override)
    ports:
      - "${CIB7_PORT:-8081}:8080"
```
**Description**: Production overlay sets `ports: []` for postgres, neo4j, redis but has no entries for CIB7, MinIO, or Mailpit.
**Risk**: CIB7's REST API allows unauthenticated process deployment. MinIO console uses default credentials.
**Recommendation**: Add `ports: []` for CIB7, MinIO, Mailpit in `docker-compose.prod.yml`.

---

### [HIGH] DATA: 33+ Tables Missing from RLS Engagement Scoping
**File**: `src/core/rls.py:42-79`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
ENGAGEMENT_SCOPED_TABLES: list[str] = [
    "annotations", "audit_logs", "case_link_edges",
    # ... 31 tables total
]
# Missing: incidents, review_packs, compliance_assessments,
# transfer_impact_assessments, dark_room_snapshots, ...
```
**Description**: 31 tables have RLS policies. 33+ tables with non-nullable `engagement_id` FK are missing, including security-sensitive tables.
**Risk**: Cross-engagement data leak bypassing application layer.
**Recommendation**: Add all tables with non-nullable `engagement_id` FK. Consider generating the list programmatically.

---

### [HIGH] API: Unbounded Query in `graph_analytics.py`
**File**: `src/api/routes/graph_analytics.py:137`
**Agent**: B3 (API Compliance Auditor)
**Description**: Fetches all evidence items with no `.limit()`, then calls `extract_entities()` in O(N) loop.
**Risk**: Memory exhaustion and timeout on large engagements.
**Recommendation**: Add pagination with `le=500` cap.

---

### [HIGH] API: Unbounded Query in `correlation.py`
**File**: `src/api/routes/correlation.py:63`
**Agent**: B3 (API Compliance Auditor)
**Description**: Fetches all `CanonicalActivityEvent` rows unboundedly.
**Risk**: Memory exhaustion proportional to event volume.
**Recommendation**: Process in batches or as a background task.

---

### [HIGH] API: ~35 Endpoints Missing `response_model`
**File**: Multiple — `governance.py:330`, `data_classification.py:97`, `consent.py:76`, `camunda.py:53`
**Agent**: B3 (API Compliance Auditor)
**Description**: ~35 route handlers have no `response_model`. `governance.py /policies` exposes server filesystem path.
**Risk**: Response drift undetectable; information disclosure; ~8% of endpoints undocumented in OpenAPI.
**Recommendation**: Define Pydantic response models for all 35 endpoints.

---

### [HIGH] ARCHITECTURE: God Route Files (tom.py 1751 lines, pov.py 1496 lines)
**File**: `src/api/routes/tom.py`, `src/api/routes/pov.py`
**Agent**: B1 (Architecture Auditor)
**Description**: tom.py has 35 route handlers spanning 8 sub-domains. Schemas extracted but route logic monolithic.
**Risk**: Merge conflicts; syntax error disables entire subsystem.
**Recommendation**: Split into sub-routers by domain.

---

### [HIGH] ARCHITECTURE: 104 Inline Pydantic Schemas in 6 Route Files
**File**: `monitoring.py` (22), `governance.py` (20), `validation.py` (20), `dashboard.py` (18), `regulatory.py` (14), `pipeline_quality.py` (10)
**Agent**: B1 (Architecture Auditor)
**Description**: 104 schemas defined inline, violating project coding standards requiring schemas in `src/api/schemas/`.
**Risk**: Schema duplication; inflated route files.
**Recommendation**: Extract schemas for all 6 files (each drops 200-400 lines).

---

### [HIGH] QUALITY: 138 Broad `except Exception` Catches (~56 Unjustified)
**File**: Multiple — `semantic/conflict_detection.py` (6), `conflict_classifier.py` (6), `websocket.py` (5)
**Agent**: C1 (Python Quality Auditor)
**Description**: 138 total `except Exception` catches. ~22 carry justification comments; ~56 are unjustified.
**Risk**: Programming errors masked alongside infrastructure errors.
**Recommendation**: Catch specific exceptions; add justification comments to intentionally broad catches.

---

### [HIGH] QUALITY: 168 `Any` Type Annotations
**File**: Multiple — `semantic/conflict_detection.py`, `mcp/server.py`, `monitoring/pipeline/continuous.py`
**Agent**: C1 (Python Quality Auditor)
**Description**: All 6 detector classes accept `graph_service: Any`; all 8 MCP tool functions use `session_factory: Any`.
**Risk**: `mypy` cannot validate attribute access. Method renames fail only at runtime.
**Recommendation**: Replace with concrete types.

---

### [HIGH] QUALITY: 10 God Classes Exceeding 300 Lines
**File**: `src/semantic/graph.py:94` (705 lines), + 9 more
**Agent**: C1 (Python Quality Auditor)
**Description**: `KnowledgeGraphService` at 705 lines has 8+ responsibilities, injected into 12+ modules.
**Recommendation**: Split into `GraphReadService`, `GraphWriteService`, `GraphSearchService`.

---

### [HIGH] QUALITY: 3 Functions Exceeding 200 Lines
**File**: `src/data/seeds.py:12` (224), `src/api/main.py:258` (221), `src/pov/generator.py:72` (205)
**Agent**: C1 (Python Quality Auditor)
**Recommendation**: Move seed data to YAML; extract helpers from `create_app`; decompose pipeline.

---

### [HIGH] QUALITY: Stub Implementations (Including GDPR Consent)
**File**: `src/taskmining/worker.py:43`, `src/security/consent/service.py:96`
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```python
deletion_task_id = uuid.uuid4()
# returns tracking ID but never stores, dispatches, or tracks it
```
**Description**: Consent service returns deletion task ID without any deletion mechanism. GDPR Art. 17 risk.
**Recommendation**: Implement Redis Stream dispatch or change response to indicate manual deletion pending.

---

### [HIGH] QUALITY: `as unknown as` Casts in BPMNViewer
**File**: `frontend/src/components/BPMNViewer.tsx:95`
**Agent**: C2 (Frontend Quality Auditor)
**Description**: Six `as unknown as BpmnViewer` double casts bypass TypeScript's type system.
**Risk**: Library API changes silently ignored by compiler.
**Recommendation**: Use typed service retrieval; single cast at import point.

---

### [HIGH] PERFORMANCE: N+1 Graph Write in `build_fragment_graph`
**File**: `src/evidence/pipeline.py:466`
**Agent**: C3 (Performance Auditor)
**Description**: CO_OCCURS_WITH relationships created one-at-a-time in nested loop. `batch_create_relationships()` exists but isn't used here.
**Risk**: 30 entities generate 435 sequential Neo4j sessions (~1-2s per document).
**Recommendation**: Collect tuples and call `batch_create_relationships` once.

---

### [HIGH] PERFORMANCE: N+1 Graph Reads in `build_governance_chains`
**File**: `src/core/regulatory.py:171`
**Agent**: C3 (Performance Auditor)
**Description**: Per-process-node `get_relationships()` + per-relationship `get_node()` calls.
**Risk**: 50 processes generates 250+ sequential Neo4j sessions.
**Recommendation**: Single Cypher join; replace existence check with `MERGE`.

---

### [HIGH] PERFORMANCE: Unbounded Graph Traversal in `_count_components`
**File**: `src/evaluation/graph_health.py:94`
**Agent**: C3 (Performance Auditor)
**Description**: Fetches all edges in engagement with no LIMIT, streams into Python union-find.
**Recommendation**: Add `LIMIT 10000`; consider background job.

---

### [HIGH] COVERAGE: Flaky Timing-Dependent Tests (27 instances)
**File**: `tests/monitoring/test_agent_framework_bdd.py`, `tests/core/tasks/test_worker_wiring_bdd.py`
**Agent**: D1 (Test Coverage Auditor)
**Description**: 27 `asyncio.sleep()` calls with wall-clock assertions (0.05s-0.5s).
**Recommendation**: Replace with event-driven synchronization.

---

### [HIGH] COVERAGE: Simulation Engine Untested
**File**: `src/simulation/engine.py`
**Agent**: D1 (Test Coverage Auditor)
**Description**: Core `run_simulation` function has no test file.
**Risk**: Bugs in simulation engine corrupt client deliverables.

---

### [HIGH] COVERAGE: Worker Dispatch Stubs Untested
**File**: `src/taskmining/worker.py`, `src/monitoring/worker.py`
**Agent**: D1 (Test Coverage Auditor)
**Description**: Redis Stream consumers with stubs and real code paths — zero test coverage.

---

### [HIGH] COVERAGE: Agent GDPR Subsystem Untested
**File**: `agent/python/kmflow_agent/gdpr/purge.py`, `audit_logger.py`, `retention.py`
**Agent**: D1 (Test Coverage Auditor)
**Description**: GDPR Art. 17 compliance modules with no tests. Purge manager opens real SQLite without isolation.

---

### [HIGH] COVERAGE: Watermark Extractor Untested
**File**: `src/security/watermark/extractor.py`
**Agent**: D1 (Test Coverage Auditor)
**Description**: HMAC-SHA256 tamper detection for exported documents has no tests.

---

### [HIGH] COMPLIANCE: LLM Calls Not Recorded in LLMAuditLog
**File**: `src/rag/copilot.py:158`, `src/tom/rationale_generator.py:249`
**Agent**: D2 (Compliance Auditor)
**Description**: `LLMAuditLog` model exists but only used in simulation suggestion engine. Copilot and TOM rationale generator create no audit records.
**Risk**: Cannot track token consumption or prompt injection attempts. EU AI Act Art. 12 gap.

---

### [HIGH] COMPLIANCE: Simulation/Assumption Deletion Unaudited
**File**: `src/api/routes/scenario_simulation.py:62`, `src/api/routes/simulations.py:840`
**Agent**: D2 (Compliance Auditor)
**Description**: Financial assumption deletion has no `log_audit()` call (creation correctly logs). SOC2 CC7.2 violation.

---

### [HIGH] DEPENDENCIES: requirements.lock Stale
**File**: `requirements.lock`
**Agent**: D3 (Dependency Auditor)
**Evidence**:
```
cryptography==43.0.3     # pyproject.toml requires >=46.0.5
```
**Description**: Lock compiled 2026-02-20, never updated. Docker builds install CVE-vulnerable versions.
**Recommendation**: `uv pip compile pyproject.toml -o requirements.lock --generate-hashes`.

---

### [HIGH] DEPENDENCIES: requirements.lock Lacks Hash Verification
**File**: `requirements.lock`
**Agent**: D3 (Dependency Auditor)
**Description**: No SHA-256 hashes for supply chain tamper detection. Agent's `requirements.txt` and frontend's `package-lock.json` both have integrity hashes.
**Recommendation**: Regenerate with `--generate-hashes`; add `--require-hashes` to Dockerfile.

---

## MEDIUM Findings

### Squad A: Security (8 findings)

| # | Finding | File | Agent |
|---|---------|------|-------|
| 1 | Dev mode auto-authenticates as platform_admin at DEBUG level | `src/core/auth.py:311` | A1 |
| 2 | Hardcoded default credentials with env-dependent guard | `src/core/config.py:42-69` | A1 |
| 3 | File type detection falls back to client MIME type | `src/evidence/pipeline.py:105` | A2 |
| 4 | Delta Lake delete predicate string interpolation | `src/datalake/backend.py:396` | A2 |
| 5 | ServiceNow table_name URL interpolation without validation | `src/integrations/servicenow.py:85` | A2 |
| 6 | PBKDF2 salt derived deterministically from secret | `src/core/encryption.py:37` | A3 |
| 7 | Neo4j and PostgreSQL use unencrypted connections | `src/core/config.py:48` | A3 |
| 8 | Redis URL fallback omits password | `src/core/config.py:216` | A3 |

### Squad B: Architecture & Data (15 findings)

| # | Finding | File | Agent |
|---|---------|------|-------|
| 9 | 30+ deferred imports hide dependency graph | Multiple | B1 |
| 10 | Evidence pipeline 870 lines spanning 5 concerns | `src/evidence/pipeline.py` | B1 |
| 11 | Duplicated background task GC pattern in 3 files | `tom.py`, `validation.py`, `scenario_simulation.py` | B1 |
| 12 | Embedding service singleton without thread safety | `src/rag/embeddings.py:24` | B1 |
| 13 | Neo4j traversal depth no upper bound | `src/semantic/graph.py:535` | B2 |
| 14 | JSON array columns store FK references without integrity | Multiple models | B2 |
| 15 | Engagement lacks ORM cascade for 27+ children | `src/core/models/` | B2 |
| 16 | No CHECK constraints on score/confidence columns | Multiple models | B2 |
| 17 | Actor columns use String instead of FK | Multiple models | B2 |
| 18 | Missing HNSW index on pattern_library_entries | Migrations | B2 |
| 19 | PATCH /engagements/{id}/archive without body | `src/api/routes/engagements.py:271` | B3 |
| 20 | DELETE /seed-lists returns 200 vs convention 204 | `src/api/routes/seed_lists.py:161` | B3 |
| 21 | Inconsistent limit ceilings (100 to 2000) | Multiple route files | B3 |
| 22 | Rate limit 429 response shapes differ | `security.py:148`, `main.py:275` | B3 |
| 23 | Governance /policies returns filesystem path | `src/api/routes/governance.py:330` | B3 |

### Squad C: Quality & Performance (7 findings)

| # | Finding | File | Agent |
|---|---------|------|-------|
| 24 | 5 TODO comments (2 linked to stubs) | Multiple | C1 |
| 25 | `_parse_timestamp` duplicated 3x with divergent behavior | 3 modules | C1 |
| 26 | `Any` for datetime fields in Pydantic schemas | Multiple route files | C1 |
| 27 | Missing Neo4j indexes on 9 node labels | `src/core/neo4j.py:84` | C3 |
| 28 | Full file read into memory before size validation | `src/api/routes/evidence.py:180` | C3 |
| 29 | EmbeddingService() constructed per-request | `src/api/routes/graph.py:238` | C3 |
| 30 | O(N^2) Python cosine similarity in semantic bridge | `src/taskmining/semantic_bridge.py:122` | C3 |

### Squad D: Coverage & Compliance (11 findings)

| # | Finding | File | Agent |
|---|---------|------|-------|
| 31 | `re_encrypt_value` and key rotation fallback untested | `src/core/encryption.py:116` | D1 |
| 32 | Worker wiring tests use wall-clock sleeps | `tests/core/tasks/test_worker_wiring_bdd.py` | D1 |
| 33 | Unspec'd MagicMock() in POV tests | `tests/pov/test_generator.py` | D1 |
| 34 | 40+ API route modules lack HTTP-layer tests | `src/api/routes/` | D1 |
| 35 | Agent platform modules untested | `agent/python/kmflow_agent/platform/` | D1 |
| 36 | Classification enforcement limited to single route | `src/api/routes/evidence.py:324` | D2 |
| 37 | GDPR consent not enforced before processing (4th audit) | `src/api/routes/copilot.py:56` | D2 |
| 38 | File storage not cleaned during retention enforcement | `src/core/retention.py:102` | D2 |
| 39 | CVE floor packages absent from lock file | `requirements.lock` | D3 |
| 40 | Worker package.json uses caret ranges for jose | Worker package.json files | D3 |
| 41 | aiofiles declared without upper version cap | `pyproject.toml:38` | D3 |

---

## LOW Findings

| # | Finding | File | Agent |
|---|---------|------|-------|
| 1 | Default password in Neo4j validation utility | `src/semantic/ontology/validate.py:95` | A1 |
| 2 | Internal file paths in API responses | `src/api/routes/evidence.py:55` | A2 |
| 3 | Salesforce SOQL timestamp interpolation | `src/integrations/salesforce.py:177` | A2 |
| 4 | Frontend-dev volume mounts lack :ro flag | `docker-compose.yml:294` | A3 |
| 5 | AUTH_DEV_MODE not explicit in prod overlay | `docker-compose.prod.yml:78` | A3 |
| 6 | PostgreSQL superuser password naming asymmetry | `docker-compose.yml:12` | A3 |
| 7 | 77 route modules in main.py | `src/api/main.py:34` | B1 |
| 8 | 8 route files trending toward god-file | Multiple | B1 |
| 9 | Call sites bypass embedding factory | `src/api/routes/tom.py:1725` | B1 |
| 10 | ConsentRecord ORM-migration type drift | `src/taskmining/consent.py:69` | B2 |
| 11 | PDPAuditEntry.policy_id no FK (partially fixed) | `src/core/models/pdp.py` | B2 |
| 12 | pipeline_quality models omit nullable=False | Multiple | B2 |
| 13 | JSON columns default mismatch | Multiple | B2 |
| 14 | Hardcoded 768 embedding dimension | `src/semantic/embeddings.py` | B2 |
| 15 | 3 route files hardcode /api/v1/ in decorators | `users.py`, `gdpr.py`, `health.py` | B3 |
| 16 | Manual validation instead of Query bounds | `src/api/routes/graph.py:217` | B3 |
| 17 | DELETE /orchestration lacks explicit status_code | `orchestration.py:202` | B3 |
| 18 | TOM seed creates duplicates on repeat calls | `src/api/routes/tom.py:739` | B3 |
| 19 | 2 functions missing type annotations | `rate_limiter.py:21`, `gdpr.py:254` | C1 |
| 20 | 90-entry stopwords set inline in method | `src/rag/retrieval.py` | C1 |
| 21 | No per-route error.tsx boundaries | `frontend/src/app/layout.tsx` | C2 |
| 22 | Silent error discard in ontology page | `frontend/src/app/ontology/page.tsx:85` | C2 |
| 23 | Index keys in 3 list renders | `copilot/page.tsx`, `RoadmapTimeline.tsx`, `conformance/page.tsx` | C2 |
| 24 | Embedding vectors serialized as ASCII | `src/semantic/embeddings.py:124` | C3 |
| 25 | Pool defaults can exceed max_connections | `src/core/database.py:39` | C3 |
| 26 | Rate limiter fail-opens during Redis outage | `src/api/middleware/security.py:98` | C3 |
| 27 | Test DB infrastructure checks config not runtime | `tests/core/test_database_infrastructure.py` | D1 |
| 28 | `src/api/deps.py` untested | `src/api/deps.py` | D1 |
| 29 | Pattern anonymizer only 3 regex patterns | `src/patterns/anonymizer.py:17` | D2 |
| 30 | No DPA template or tracking | `src/core/config.py:100` | D2 |
| 31 | minio/mc uses floating :latest tag | `docker-compose.yml` | D3 |
| 32 | Base images use floating minor tags | `Dockerfile.backend:1` | D3 |
| 33 | minimatch override lacks CVE comment | `frontend/package.json:41` | D3 |
| 34 | Wrangler version inconsistency | Worker package.json files | D3 |
| 35 | langdetect at end of maintenance | `pyproject.toml:48` | D3 |

---

## Squad Reports

### A: Security & Authorization

Full findings: [`A1-authz.md`](audit-findings/A1-authz.md), [`A2-injection.md`](audit-findings/A2-injection.md), [`A3-infra-security.md`](audit-findings/A3-infra-security.md)

**Overall Security Posture: GOOD (8.0/10)**

13+ prior findings remediated including Redis auth, CORS hardening, default secret validation, Fernet KDF upgrade, XXE prevention, LLM prompt sanitization, SecretStr migration, worker XSS fixes. Remaining: 2 IDOR vulnerabilities, CIB7/MinIO exposure, 3 integration connector injection vectors, deterministic PBKDF2 salt, unencrypted DB connections.

### B: Architecture & Data Integrity

Full findings: [`B1-architecture.md`](audit-findings/B1-architecture.md), [`B2-data-integrity.md`](audit-findings/B2-data-integrity.md), [`B3-api-compliance.md`](audit-findings/B3-api-compliance.md)

**Architecture: 8/10 | Data Integrity: 7.9/10 | API: 7.5/10**

7 of 9 prior architecture findings resolved. Core models split into 33 domain modules. Dashboard cache moved to Redis. No circular dependencies. Remaining: god route files, inline schemas, RLS gap (33+ tables), auth rate limiter gap, 88 migrations fully linear.

### C: Code Quality & Performance

Full findings: [`C1-python-quality.md`](audit-findings/C1-python-quality.md), [`C2-frontend-quality.md`](audit-findings/C2-frontend-quality.md), [`C3-performance.md`](audit-findings/C3-performance.md)

**Python: 6.5/10 | Frontend: 7.5/10 | Performance: HIGH risk**

Zero bare excepts, zero `datetime.utcnow()`, zero f-string loggers. Frontend improved from 11 to 4 findings; JWT now secure (HttpOnly cookies). Remaining: N+1 graph patterns (batch infra exists), AlertEngine memory leak, 138 broad catches, 168 Any annotations, 10 god classes.

### D: Coverage, Compliance & Risk

Full findings: [`D1-test-coverage.md`](audit-findings/D1-test-coverage.md), [`D2-compliance.md`](audit-findings/D2-compliance.md), [`D3-dependencies.md`](audit-findings/D3-dependencies.md)

**Coverage: WARNING | Compliance: 7 findings (down from 16) | Supply Chain: MEDIUM-HIGH**

5,772 tests across 312 files. Critical auth/JWT/GDPR paths well-tested. Compliance improved materially: forensic capture comprehensive, retention automatic. Stale lock file is the highest-impact supply chain issue.

---

## Recommendations

Top 10 highest-impact actions ranked by risk reduction:

1. **Regenerate `requirements.lock` with hashes** — `uv pip compile pyproject.toml -o requirements.lock --generate-hashes` — fixes 2 HIGH supply chain findings immediately.

2. **Add engagement membership checks to POV and evidence ID-based routes** — fixes 2 HIGH IDOR cross-tenant access vulnerabilities.

3. **Batch-fetch Neo4j nodes in `search_similar`** — single `WHERE n.id IN $ids` query eliminates CRITICAL N+1 on every copilot query.

4. **Add all engagement-scoped tables to `ENGAGEMENT_SCOPED_TABLES`** — fixes HIGH RLS gap affecting 33+ tables.

5. **Back slowapi with Redis + add per-email lockout** — fixes CRITICAL auth rate limiter gap.

6. **Add CIB7, MinIO, Mailpit overrides to `docker-compose.prod.yml`** — fixes HIGH production port exposure.

7. **Wire `batch_create_relationships` into `build_fragment_graph`** — fixes HIGH N+1 graph write (existing function, just needs connecting).

8. **Create test files for simulation engine, watermark extractor, GDPR agent** — addresses 3 HIGH coverage gaps.

9. **Add `LLMAuditLog` creation to copilot and TOM rationale generator** — fixes HIGH EU AI Act Art. 12 compliance gap.

10. **Extract inline Pydantic schemas from 6 route files** — fixes HIGH coding standards violation, shrinks 6 files by 200-400 lines each.
