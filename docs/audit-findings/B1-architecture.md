# B1: Architecture Audit Findings (Re-Audit #3)

**Agent**: B1 (Architecture Auditor)  
**Date**: 2026-03-19  
**Prior Audits**: 2026-02-20, 2026-02-26, 2026-03-19 (Re-Audit #2)  
**Scope**: Module boundaries, god files, coupling analysis, async patterns, scalability concerns  

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 2 |
| MEDIUM | 4 |
| LOW | 3 |
| SOUND | 8 |

**Overall Architecture Risk Score**: MEDIUM (improved from prior)  
**Design Pattern Compliance**: 8/10  
**SOLID Compliance**: 8/10  

### Prior-Audit Remediation Status

| Prior Finding | Status | Notes |
|---------------|--------|-------|
| CRITICAL: Sync simulation engine blocking event loop | **RESOLVED** | Wrapped in `asyncio.to_thread()` (simulations.py:216) |
| HIGH: GOD-FILE `src/core/models.py` (1717 lines) | **RESOLVED** | Split into 33 domain modules under `src/core/models/` |
| HIGH: `src/api/routes/simulations.py` (1309 lines) | **RESOLVED** | Schemas extracted to `src/api/schemas/simulations.py`; route file now 1177 lines |
| HIGH: Schemas defined inline in 14+ route files | **PARTIALLY RESOLVED** | 16 schema files now exist; 6 route files still have inline schemas |
| HIGH: Encapsulation violation `engine._assess_dimension_maturity` | **RESOLVED** | No longer present |
| MEDIUM: In-memory rate limiter in simulations.py | **RESOLVED** | Replaced with Redis sliding-window (lines 84-122) |
| MEDIUM: Inconsistent API_BASE in frontend | **RESOLVED** | All files import from `@/lib/api/client` |
| MEDIUM: Evidence pipeline imports HTTPException | **RESOLVED** | Now uses `EvidenceValidationError` domain exception |
| MEDIUM: Dashboard in-memory cache | **RESOLVED** | Now Redis-backed via `request.app.state.redis_client` |
| LOW: `_check_engagement_member` duplication in tom.py | **RESOLVED** | Replaced with shared `verify_engagement_member` from `src/core/permissions` |

---

## Findings

### [HIGH] GOD-FILE: Route files tom.py (1751 lines) and pov.py (1496 lines) remain oversized

**File**: `/Users/proth/repos/kmflow/src/api/routes/tom.py:1-1751`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# tom.py: 1751 lines, 35 route handlers spanning 8 sub-domains:
async def create_tom(                    # line 139 - TOM CRUD
async def create_gap(                    # line 426 - Gap analysis
async def create_best_practice(          # line 595 - Best practices
async def create_benchmark(              # line 674 - Benchmarks
async def generate_roadmap(              # line 1202 - Roadmaps
async def compute_maturity_scores(       # line 1396 - Maturity
async def trigger_alignment_scoring(     # line 1583 - Alignment runs
async def _run_alignment_scoring_async(  # line 1702 - Background task
```
**Description**: tom.py is 1751 lines with 35 async route handlers. It covers TOMs, gap analysis, best practices, benchmarks, roadmaps, maturity scoring, conformance, and alignment runs -- at least 8 distinct sub-domains. Schemas have been properly extracted to `src/api/schemas/tom.py` (539 lines), which is a significant improvement from the prior audit, but the route logic itself remains monolithic. pov.py follows the same pattern at 1496 lines with schemas extracted to `src/api/schemas/pov.py`.  
**Risk**: Merge conflicts when multiple developers work on TOM-adjacent features. A syntax error anywhere in the file disables the entire TOM subsystem (all 35 endpoints). High cognitive load for reviewers.  
**Recommendation**: Split into sub-routers: `tom/core.py` (CRUD), `tom/gaps.py`, `tom/benchmarks.py`, `tom/roadmaps.py`, `tom/maturity.py`, `tom/alignment.py`. Same for pov.py.

---

### [HIGH] SCHEMA-COUPLING: 6 route files still define 104+ Pydantic schemas inline

**File**: `/Users/proth/repos/kmflow/src/api/routes/monitoring.py:52` (representative)  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# Inline schema counts per route file (still not extracted):
# monitoring.py:      22 schemas
# governance.py:      20 schemas
# validation.py:      20 schemas
# dashboard.py:       18 schemas
# regulatory.py:      14 schemas
# pipeline_quality.py: 10 schemas
# Total inline:       104 schemas

# Meanwhile, 16 schema files already exist in src/api/schemas/:
# tom.py (539 lines), pov.py, simulations.py, taskmining.py, etc.
```
**Description**: The project coding standards mandate "Pydantic models for all request/response schemas (in `src/api/schemas/`)". While tom.py, pov.py, simulations.py, and taskmining.py schemas have been properly extracted, 6 route files still define 104+ Pydantic schema classes inline. The extraction pattern is well-established and proven; it simply has not been applied consistently.  
**Risk**: Schema duplication risk when multiple routes need the same response shape. Inline schemas inflate route files, contributing directly to god-file size. SDK/OpenAPI schema re-use becomes harder.  
**Recommendation**: Extract schemas for monitoring.py, governance.py, validation.py, dashboard.py, regulatory.py, and pipeline_quality.py. Each extraction would shrink the corresponding route file by 200-400 lines.

---

### [MEDIUM] DEFERRED-IMPORTS: 30+ deferred imports indicate hidden coupling in service modules

**File**: Multiple files across `/Users/proth/repos/kmflow/src/`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# src/mcp/server.py - 6 deferred imports inside tool handlers:
async def _tool_get_engagement(session_factory, args, *, user_id):
    from src.core.models import Engagement, EngagementMember, EvidenceItem  # line 162

# src/taskmining/worker.py - 6 deferred imports:
async def _ingest_session(session_id, redis_client):
    from src.core.config import Settings                    # line 137
    from src.core.database import async_session_factory     # line 138
    from src.core.neo4j import create_neo4j_driver          # line 139
    from src.semantic.graph import KnowledgeGraphService     # line 140

# src/api/routes/tom.py - 4 deferred imports in route handlers:
    from src.semantic.graph import KnowledgeGraphService     # line 933
    from src.tom.alignment import TOMAlignmentEngine         # line 934
```
**Description**: Over 30 imports are deferred to function-level scope across the codebase. In `mcp/server.py`, every tool handler re-imports models on each invocation. In `taskmining/worker.py`, 6 imports are deferred inside the main processing function. The tom.py route handlers also defer service imports. While some are justified (e.g., `datalake/backend.py` lazily loading optional `DatabricksBackend`), many appear to be avoiding import-time side effects or circular references rather than truly optional dependencies.  
**Risk**: Import-time errors surface only at runtime when specific code paths are hit. Static analysis tools cannot trace the full dependency graph. Performance overhead from repeated module lookups (mitigated by Python's import cache, but still a code smell).  
**Recommendation**: Categorize each deferred import as (a) lazy-loading optional heavy dependency, (b) avoiding circular import, or (c) unnecessary. Move category (c) to top level.

---

### [MEDIUM] PIPELINE-RESPONSIBILITY: Evidence pipeline is 870 lines spanning 5 architectural concerns

**File**: `/Users/proth/repos/kmflow/src/evidence/pipeline.py:1-870`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# Five distinct responsibilities in one file:
async def check_duplicate(...)           # line 150 - Storage concern
async def store_file(...)                # line 171 - Storage concern
async def process_evidence(...)          # line 231 - Parse orchestration
async def extract_fragment_entities(...) # line 280 - NLP/semantic
async def build_fragment_graph(...)      # line 358 - Knowledge graph
async def generate_fragment_embeddings(...)  # line 501 - RAG
async def run_semantic_bridges(...)      # line 555 - Semantic linking
async def run_intelligence_pipeline(...) # line 616 - Orchestrator
async def ingest_evidence(...)           # line 702 - Master orchestrator
```
**Description**: This file orchestrates the entire evidence lifecycle from upload through intelligence extraction. It imports from 6 packages (`core`, `evidence`, `semantic`, `rag`, `datalake`, `quality`). The layering violation (FastAPI HTTPException import) from the prior audit has been resolved -- the file now correctly uses `EvidenceValidationError` from `src/evidence/exceptions.py`. However, the file still mixes storage operations, parse orchestration, entity extraction, graph building, embedding generation, and semantic bridging in a single module.  
**Risk**: Testing any single pipeline stage requires loading the entire 870-line module. Changes to the embedding step risk breaking the parsing step through shared state.  
**Recommendation**: Extract `evidence/storage.py` (store_file, check_duplicate), `evidence/intelligence.py` (extract, graph, embeddings, bridges). Keep `pipeline.py` as a thin orchestrator composing these modules.

---

### [MEDIUM] BACKGROUND-TASK-PATTERN: Module-level mutable sets in 3 route files for asyncio task GC prevention

**File**: `/Users/proth/repos/kmflow/src/api/routes/tom.py:92`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# Three separate route modules maintain identical patterns:
# tom.py:92
_background_tasks: set[asyncio.Task[None]] = set()
# validation.py:65
_background_tasks: set[asyncio.Task[None]] = set()
# scenario_simulation.py:40
_background_tasks: set[asyncio.Task[None]] = set()

# Usage pattern (tom.py:1640-1648):
task = asyncio.create_task(
    _run_alignment_scoring_async(run_id=run_id, ...)
)
_background_tasks.add(task)
task.add_done_callback(_background_tasks.discard)
```
**Description**: Three route modules independently implement the same fire-and-forget task pattern with module-level `set()` for GC prevention. The `add_done_callback(discard)` pattern is correctly used to clean up completed tasks, so the prior audit's memory leak concern is addressed. However, the pattern is duplicated across 3 files with no shared abstraction. Additionally, these sets are not drained during application shutdown (the lifespan shutdown only cancels `app.state.worker_tasks`).  
**Risk**: On graceful shutdown, background tasks in these sets may be orphaned or interrupted mid-operation without cleanup. DRY violation makes it easy to add a new background task site without the done callback.  
**Recommendation**: Create a shared `BackgroundTaskManager` class (or use FastAPI's built-in `BackgroundTasks`) registered in `app.state`. Centralize the add/discard/shutdown pattern.

---

### [MEDIUM] MUTABLE-GLOBAL-STATE: Embedding service singleton dict without thread safety

**File**: `/Users/proth/repos/kmflow/src/rag/embeddings.py:24`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
_instances: dict[tuple[str, int], EmbeddingService] = {}

def get_embedding_service(
    model_name: str = "nomic-ai/nomic-embed-text-v1.5",
    dimension: int = EMBEDDING_DIMENSION,
) -> EmbeddingService:
    key = (model_name, dimension)
    if key not in _instances:
        _instances[key] = EmbeddingService(model_name=model_name, dimension=dimension)
    return _instances[key]
```
**Description**: The singleton factory uses a module-level dict without thread-safety. The `EmbeddingService` is used via `asyncio.to_thread()` (lines 83, 99), meaning model inference runs in a thread pool. While `get_embedding_service()` itself is only called from the async context (protected by the GIL for dict operations), the check-then-set pattern is a TOCTOU race if called from multiple async tasks simultaneously.  
**Risk**: Low in practice (Python GIL protects dict operations), but if the factory is ever called from `to_thread`, concurrent initialization could create duplicate model instances consuming significant GPU/CPU memory.  
**Recommendation**: Use `functools.lru_cache` or a `threading.Lock` to make the singleton pattern thread-safe.

---

### [LOW] ROUTE-FILE-PROLIFERATION: 77 route modules registered in main.py

**File**: `/Users/proth/repos/kmflow/src/api/main.py:34-117`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
from src.api.routes import (
    admin,
    assessment_matrix,
    assumptions,
    audit_logs,
    camunda,
    # ... 72 more imports across 4 import blocks
    websocket,
)
```
**Description**: The application registers 77 route modules in main.py across 4 import blocks (lines 34-117). Each requires a corresponding `app.include_router()` call. Adding a new route requires modifying main.py in two places.  
**Risk**: Low -- this is a maintainability concern, not a correctness issue.  
**Recommendation**: Consider route auto-discovery or grouping related routes into sub-packages.

---

### [LOW] GOD-FILE-RISK: 8 route files between 500-1259 lines trending toward god-file threshold

**File**: Multiple route files  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# Route files in the 500-1259 line danger zone:
# governance.py:      1259 lines, 20 inline schemas
# validation.py:      1099 lines, 20 inline schemas
# dashboard.py:       1079 lines, 18 inline schemas
# taskmining.py:      1068 lines (schemas extracted)
# monitoring.py:      1008 lines, 22 inline schemas
# regulatory.py:       688 lines, 14 inline schemas
# pipeline_quality.py:  559 lines, 10 inline schemas
# evidence.py:          526 lines
```
**Description**: Eight route files are between 500-1259 lines. Those with inline schemas (governance, validation, dashboard, monitoring) would each drop 200-400 lines simply by extracting schemas. After extraction, only governance.py might still exceed the 500-line threshold, requiring further sub-router decomposition.  
**Risk**: Without schema extraction, these files will continue growing as features are added.  
**Recommendation**: Prioritize schema extraction for governance.py (20 schemas), monitoring.py (22 schemas), and validation.py (20 schemas) as the highest-leverage cleanup.

---

### [LOW] EMBEDDING-SERVICE-BYPASS: Some call sites construct EmbeddingService() directly

**File**: `/Users/proth/repos/kmflow/src/api/routes/tom.py:1725-1727`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# tom.py line 1725-1727 (inside _run_alignment_scoring_async):
embedding_service = None
try:
    from src.rag.embeddings import EmbeddingService
    embedding_service = EmbeddingService()
```
**Description**: The `get_embedding_service()` factory was created to ensure singleton behavior and avoid reloading the SentenceTransformer model, but some call sites still construct `EmbeddingService()` directly, bypassing the cache.  
**Risk**: The SentenceTransformer model may be loaded multiple times, consuming extra memory. In the alignment scoring background task, this happens once per run, so impact is low.  
**Recommendation**: Replace `EmbeddingService()` with `get_embedding_service()` at all call sites.

---

## Sound Architecture Patterns

### [SOUND] Model Domain Package Split

**File**: `/Users/proth/repos/kmflow/src/core/models/`  
**Agent**: B1 (Architecture Auditor)  
**Description**: 33 domain-specific model files totaling 6064 lines (average 184 lines/file, largest taskmining.py at 506). The barrel `__init__.py` (466 lines) re-exports 170+ symbols. This is clean domain-driven decomposition, fully resolved from the original 1717-line monolith.

---

### [SOUND] Frontend API Client Architecture

**File**: `/Users/proth/repos/kmflow/frontend/src/lib/api/`  
**Agent**: B1 (Architecture Auditor)  
**Description**: 23 domain-specific API modules with a shared `client.ts` (151 lines) providing typed generic `apiGet/apiPost/apiPut/apiPatch/apiDelete` helpers. All frontend files import from the shared client. The largest TypeScript files (532, 517, 507 lines) are within acceptable bounds. Cookie-based auth with `credentials: "include"` is consistent across all helpers.

---

### [SOUND] Async Pattern Compliance

**File**: `/Users/proth/repos/kmflow/src/api/routes/simulations.py:216`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
engine_result = await asyncio.to_thread(
    run_simulation,
    process_graph=process_graph.get("process_graph", {"elements": [], "connections": []}),
    parameters=scenario.parameters or {},
    simulation_type=scenario.simulation_type.value
```
**Description**: All sync-to-async bridges correctly use `asyncio.to_thread()`: simulations engine, embedding generation (2 call sites), cross-encoder reranking, and layout parsing. No `time.sleep` or blocking `requests` calls exist in `src/`. The prior CRITICAL finding is fully resolved and the pattern is consistently applied.

---

### [SOUND] Evidence Pipeline Layering (Remediated)

**File**: `/Users/proth/repos/kmflow/src/evidence/pipeline.py` and `/Users/proth/repos/kmflow/src/evidence/exceptions.py`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# exceptions.py - Domain exception with HTTP hint:
class EvidenceValidationError(ValueError):
    def __init__(self, message: str, *, status_hint: int = 400) -> None:
        super().__init__(message)
        self.status_hint = status_hint

# pipeline.py line 123 - Uses domain exception, not HTTPException:
raise EvidenceValidationError(
    "File type 'application/octet-stream' is not allowed...",
    status_hint=415,
)
```
**Description**: The prior MEDIUM layering violation (pipeline importing FastAPI HTTPException) has been resolved. The pipeline now raises `EvidenceValidationError` with a `status_hint`, and the API route handler translates it to HTTPException. This properly separates service-layer concerns from presentation-layer concerns.

---

### [SOUND] Dashboard Redis Cache (Remediated)

**File**: `/Users/proth/repos/kmflow/src/api/routes/dashboard.py:58-76`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
async def _cache_get(request: Request, key: str) -> Any | None:
    redis_client = request.app.state.redis_client
    raw = await redis_client.get(f"dashboard:{key}")
    if raw is not None:
        return json.loads(raw)

async def _cache_set(request: Request, key: str, value: Any) -> None:
    redis_client = request.app.state.redis_client
    await redis_client.setex(f"dashboard:{key}", _DASHBOARD_CACHE_TTL, json.dumps(value, default=str))
```
**Description**: The prior MEDIUM finding (in-memory dict cache breaking stateless design) has been resolved. The dashboard cache now uses Redis via `request.app.state.redis_client` with `SETEX` for TTL. Graceful fallback on Redis errors preserves availability. This correctly supports multi-worker horizontal scaling.

---

### [SOUND] Shared Authorization (Remediated)

**File**: `/Users/proth/repos/kmflow/src/api/routes/tom.py:82`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
from src.core.permissions import require_engagement_access, require_permission, verify_engagement_member
# Used 15 times throughout the file:
await verify_engagement_member(session, user, payload.engagement_id)  # line 145
await verify_engagement_member(session, user, engagement_id)          # line 195
```
**Description**: The prior MEDIUM finding (duplicated `_check_engagement_member` local function) has been resolved. All 15 call sites now use `verify_engagement_member` from `src/core/permissions`, ensuring a single authorization code path.

---

### [SOUND] No Circular Dependencies or Layering Violations

**File**: `/Users/proth/repos/kmflow/src/core/`  
**Agent**: B1 (Architecture Auditor)  
**Description**: `src/core/` does not import from `src/api/`. No route-to-route imports exist (zero matches for `from src.api.routes.X` inside another route file). Dependency direction is consistently downward: `api/ -> core/ -> (no upward imports)`. The evidence pipeline no longer imports from FastAPI.

---

### [SOUND] Evidence Parser Factory Pattern

**File**: `/Users/proth/repos/kmflow/src/evidence/parsers/`  
**Agent**: B1 (Architecture Auditor)  
**Description**: 15+ format-specific parsers follow the Open/Closed principle via `parsers/base.py` base class and `parsers/factory.py` dispatch. New formats are added without modifying existing parsers.

---

## Module Dependency Analysis

### Dependency Direction (Healthy Patterns)
```
api/routes    -> core/models, core/permissions, core/audit     (correct)
api/routes    -> api/schemas/{domain}                           (correct)
api/routes    -> {service modules}                              (correct)
evidence/     -> core/models, evidence/exceptions               (correct)
semantic/     -> core/models                                    (correct)
simulation/   -> core/models, core/config                       (correct)
datalake/     -> core/models                                    (correct)
```

### Dependency Concerns
```
api/routes/tom.py       -> 7 service modules (high fan-out, justified by domain breadth)
evidence/pipeline.py    -> 6 packages via deferred imports (hidden coupling)
mcp/server.py           -> 6 deferred imports per tool handler (lazy loading pattern)
api/main.py             -> 77 route modules (import surface)
```

### Cross-Cutting Concerns
```
All service modules correctly avoid web framework imports (0 violations)
```

---

## God File Summary (>500 lines)

### Python files under src/ exceeding 500 lines:

| File | Lines | Route Handlers | Inline Schemas | Status |
|------|-------|---------------|----------------|--------|
| `api/routes/tom.py` | 1751 | 35 | 0 (extracted) | **GOD FILE** - needs sub-router split |
| `api/routes/pov.py` | 1496 | 34 | 0 (extracted) | **GOD FILE** - needs sub-router split |
| `api/routes/governance.py` | 1259 | 18 | 20 | At risk - extract schemas |
| `api/routes/simulations.py` | 1177 | 22 | 0 (extracted) | Improved |
| `api/routes/validation.py` | 1099 | -- | 20 | At risk - extract schemas |
| `api/routes/dashboard.py` | 1079 | 7 | 18 | At risk - extract schemas |
| `api/routes/taskmining.py` | 1068 | -- | 0 (extracted) | Acceptable |
| `api/routes/monitoring.py` | 1008 | -- | 22 | At risk - extract schemas |
| `semantic/conflict_detection.py` | 943 | -- | -- | Acceptable (algorithm) |
| `evidence/pipeline.py` | 870 | -- | -- | Needs responsibility split |
| `semantic/entity_extraction.py` | 800 | -- | -- | Acceptable (algorithm) |
| `semantic/graph.py` | 798 | -- | -- | Acceptable (service) |
| `pov/contradiction.py` | 735 | -- | -- | Acceptable (algorithm) |
| `api/routes/regulatory.py` | 688 | -- | 14 | Borderline - extract schemas |
| `taskmining/graph_ingest.py` | 645 | -- | -- | Acceptable |
| `monitoring/alerting/engine.py` | 613 | -- | -- | Acceptable |
| `integrations/celonis_ems.py` | 565 | -- | -- | Acceptable |
| `semantic/builder.py` | 562 | -- | -- | Acceptable |
| `api/routes/pipeline_quality.py` | 559 | -- | 10 | Borderline - extract schemas |
| `api/schemas/tom.py` | 539 | -- | -- | Acceptable (schema-only) |
| `api/routes/evidence.py` | 526 | -- | -- | Borderline |
| `core/models/taskmining.py` | 506 | -- | -- | Acceptable |

### TypeScript/TSX files under frontend/src/ exceeding 500 lines:

| File | Lines | Status |
|------|-------|--------|
| `app/conformance/page.tsx` | 532 | Borderline |
| `app/simulations/page.tsx` | 517 | Borderline |
| `lib/api/simulations.ts` | 507 | Acceptable (types + functions) |

---

## Scalability Assessment

| Concern | Rating | Notes |
|---------|--------|-------|
| Stateless service design | GOOD | Dashboard cache moved to Redis (remediated) |
| Database connection pooling | GOOD | `pool_size` + `max_overflow` + `pool_pre_ping` configured |
| Async architecture | GOOD | All sync calls properly wrapped in `asyncio.to_thread()` |
| Session management | GOOD | Cookie-based auth, no server-side session state |
| Horizontal scaling | GOOD | Redis-backed caching and rate limiting throughout |
| Data isolation | GOOD | Engagement-scoped queries + RLS throughout |
| Background workers | GOOD | Redis-backed monitoring, POV generation, task mining workers |
| Background task shutdown | AT RISK | Module-level `_background_tasks` sets not drained on shutdown |

---

## Recommendations Priority

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| 1 | Extract inline schemas from 6 remaining route files (104 schemas) | Medium | Standards compliance; shrinks 6 files by 200-400 lines each |
| 2 | Split tom.py (1751 lines) into sub-routers | Medium | Eliminates largest god file |
| 3 | Split pov.py (1496 lines) into sub-routers | Medium | Eliminates second god file |
| 4 | Decompose evidence pipeline into focused modules | Medium | Reduces coupling and improves testability |
| 5 | Centralize background task management pattern | Low | DRY; enables graceful shutdown |
| 6 | Audit and rationalize deferred imports | Low | Improves static analysis accuracy |
| 7 | Use `get_embedding_service()` factory consistently | Low | Prevents duplicate model loading |
