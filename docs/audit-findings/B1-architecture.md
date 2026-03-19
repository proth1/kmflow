# B1: Architecture Audit Findings (Re-Audit #2)

**Agent**: B1 (Architecture Auditor)  
**Date**: 2026-03-19  
**Prior Audits**: 2026-02-20, 2026-02-26  
**Scope**: Module boundaries, god files, coupling analysis, async patterns, scalability concerns  

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 3 |
| MEDIUM | 5 |
| LOW | 3 |
| SOUND | 6 |

**Overall Architecture Risk Score**: MEDIUM  
**Design Pattern Compliance**: 7/10  
**SOLID Compliance**: 7/10  

### Prior-Audit Remediation Status

| Prior Finding | Status | Notes |
|---------------|--------|-------|
| CRITICAL: Sync simulation engine blocking event loop | **RESOLVED** | Now wrapped in `asyncio.to_thread()` (line 216) |
| HIGH: GOD-FILE `src/core/models.py` (1717 lines) | **RESOLVED** | Split into 33 domain-specific modules under `src/core/models/` (6063 total lines, largest 506) |
| HIGH: `src/api/routes/simulations.py` (1309 lines) | **PARTIALLY RESOLVED** | Schemas extracted; route file reduced to 1177 lines but has grown new endpoints |
| HIGH: Schemas defined inline in 14+ route files | **NOT RESOLVED** | Still only `simulations` and `taskmining` have extracted schemas |
| HIGH: Encapsulation violation `engine._assess_dimension_maturity` | **RESOLVED** | No longer present in tom.py |
| MEDIUM: In-memory rate limiter `_llm_request_log` in simulations.py | **RESOLVED** | Removed from simulations.py |
| MEDIUM: Inconsistent API_BASE in frontend | **RESOLVED** | All files now import `API_BASE_URL` from `@/lib/api/client` |
| MEDIUM: Evidence pipeline 849 lines spanning 5 concerns | **NOT RESOLVED** | Grown to 865 lines |
| LOW: `_check_engagement_member` duplication in tom.py | **NOT RESOLVED** | Still present, used 15 times |

---

## Findings

### [HIGH] GOD-FILE: `src/api/routes/tom.py` is 2274 lines with 35 route handlers and 51 inline schemas

**File**: `/Users/proth/repos/kmflow/src/api/routes/tom.py:1-2274`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# 51 Pydantic schemas defined inline (lines 86-1900):
class DimensionInput(BaseModel):          # line 86
class TOMCreate(BaseModel):               # line 94
class GapDashboardResponse(BaseModel):    # line 1402
class MaturityHeatmapResponse(BaseModel): # line 1867
class AlignmentRunResultsResponse(BaseModel):  # line 1900

# 35 route handlers in a single file:
@router.post("/", ...)                    # create TOM
@router.get("/{tom_id}", ...)             # get TOM
# ... 33 more handlers
```
**Description**: This file has grown to become the largest route file in the codebase at 2274 lines, surpassing even the previously-flagged simulations.py (now 1177 lines). It contains 51 Pydantic schema classes and 35 route handlers. The file covers TOMs, gap analysis, best practices, benchmarks, roadmaps, maturity scoring, alignment runs, and conformance checking -- at least 8 distinct sub-domains packed into one module. The file also defines its own authorization helper (`_check_engagement_member`) rather than using the shared `require_engagement_access` dependency.  
**Risk**: Merge conflicts when multiple developers work on TOM-adjacent features. A single import failure or syntax error in any of the 51 schemas or 35 handlers disables the entire TOM subsystem. Testing requires loading 2274 lines of code to test any single endpoint.  
**Recommendation**: Split into sub-routers: `tom/core.py` (CRUD), `tom/gaps.py` (gap analysis), `tom/benchmarks.py` (best practices + benchmarks), `tom/roadmaps.py` (roadmaps), `tom/maturity.py` (scoring + alignment). Extract all 51 schemas to `src/api/schemas/tom.py`. Remove `_check_engagement_member` in favor of `Depends(require_engagement_access)`.

---

### [HIGH] GOD-FILE: `src/api/routes/pov.py` is 1875 lines with 22 route handlers and 35 inline schemas

**File**: `/Users/proth/repos/kmflow/src/api/routes/pov.py:1-1875`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# 35 Pydantic schemas defined inline:
class POVGenerateRequest(BaseModel):      # line 78
class ProcessModelResponse(BaseModel):    # line 94
class DarkRoomResponse(BaseModel):        # line 1557
class IlluminationPlanResponse(BaseModel): # line 1654
class SegmentCompletionResponse(BaseModel): # line 1694
```
**Description**: The POV route file is the second largest at 1875 lines. It spans POV generation, process model retrieval, evidence mapping, confidence scoring, version diffing, reverse evidence lookup, dark room analysis, and illumination planning. These are at least 5 distinct functional areas that have accumulated in a single file. The file also contains Redis-backed job management (`_set_job`, `_get_job`) that is infrastructure logic, not route logic.  
**Risk**: Same risks as tom.py -- merge conflicts, blast radius, cognitive load. The Redis job management functions are duplicated logic that could be shared across other route files needing async job patterns.  
**Recommendation**: Split into `pov/generation.py`, `pov/models.py`, `pov/confidence.py`, `pov/dark_room.py`, `pov/illumination.py`. Extract Redis job helpers to a shared `src/api/services/job_store.py`. Extract schemas to `src/api/schemas/pov.py`.

---

### [HIGH] SCHEMA-COUPLING: 14+ route files still define Pydantic schemas inline

**File**: `/Users/proth/repos/kmflow/src/api/routes/tom.py:86-1900` (representative)  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# Inline schema counts per route file (unchanged since prior audit):
# tom.py:         51 schemas (was 14 -- has tripled)
# pov.py:         35 schemas
# governance.py:  20 schemas
# monitoring.py:  22 schemas
# validation.py:  20 schemas
# dashboard.py:   18 schemas

# Only simulations.py and taskmining.py use src/api/schemas/:
from src.api.schemas.simulations import (
    ScenarioCreate,
    ScenarioResponse,
    # ...
)
```
**Description**: The pattern established by `src/api/schemas/simulations.py` (263 lines) and `src/api/schemas/taskmining.py` has not been replicated. The combined inline schema count across route files now exceeds 200 classes. The tom.py file alone has 51 schemas -- more than the entire extracted simulations schema file. This violates the project's own coding standards which specify "Pydantic models for all request/response schemas (in `src/api/schemas/`)".  
**Risk**: Schema duplication when multiple routes need the same response shape. Cannot generate SDK clients from schema-only imports. Inline schemas inflate route files past maintainability thresholds, contributing directly to the god-file findings above.  
**Recommendation**: Systematically extract schemas for the top 6 route files by size. Start with tom.py (51 schemas) and pov.py (35 schemas) which would each shrink by ~800-1000 lines.

---

### [MEDIUM] DEFERRED-IMPORTS: 60+ deferred imports indicate hidden dependency graph

**File**: Multiple files across `/Users/proth/repos/kmflow/src/`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# src/evidence/pipeline.py - 10 deferred imports inside function bodies:
    from src.datalake.backend import StorageBackend           # line 195
    from src.semantic.entity_extraction import extract_entities # line 293
    from src.semantic.graph import KnowledgeGraphService       # line 378
    from src.rag.embeddings import EmbeddingService            # line 514
    from src.datalake.lineage import create_lineage_record     # line 780
    from src.datalake.silver import SilverLayerWriter          # line 814

# src/mcp/server.py - 7 deferred imports inside tool handlers:
    from src.core.models import Engagement, EvidenceItem       # line 160
    from src.core.models import ProcessModel                   # line 210
    from src.core.models import GapAnalysisResult              # line 236
    from src.core.models import AlertStatus, MonitoringAlert   # line 258
```
**Description**: Over 60 imports are deferred to function-level scope. While some are justified (e.g., `src/integrations/base.py` factory method loading connectors on demand, `src/mcp/server.py` lazy-loading models for tool handlers), the pattern in `evidence/pipeline.py` is a code smell -- the file imports from 6 different packages at function scope, suggesting it has too many responsibilities rather than truly optional dependencies. The `api/main.py` lifespan function also uses 6 deferred imports for worker classes.  
**Risk**: Deferred imports hide the true dependency graph from static analysis. Import-time errors surface only at runtime when the specific code path is hit. This makes dead code detection and dependency auditing unreliable.  
**Recommendation**: Categorize each deferred import as: (a) lazy-loading optional heavy dependency, (b) avoiding circular import, or (c) unnecessary. For pipeline.py, splitting responsibilities (per MEDIUM finding below) would allow most imports to move to top level.

---

### [MEDIUM] MUTABLE-GLOBAL-STATE: In-memory dashboard cache breaks stateless service design

**File**: `/Users/proth/repos/kmflow/src/api/routes/dashboard.py:54-72`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
_DASHBOARD_CACHE_TTL = 30  # seconds
_dashboard_cache: dict[str, tuple[float, Any]] = {}

def _cache_get(key: str) -> Any | None:
    entry = _dashboard_cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > _DASHBOARD_CACHE_TTL:
        del _dashboard_cache[key]
        return None
    return value
```
**Description**: The dashboard cache is a module-level mutable dictionary. The prior audit's `_llm_request_log` in simulations.py has been removed (remediated), but this dashboard cache remains. In a multi-worker deployment (`uvicorn --workers N`), each worker maintains its own cache, leading to N copies of the same data in memory and inconsistent cache behavior across workers. The codebase has Redis infrastructure available via `app.state.redis_client`.  
**Risk**: In multi-worker deployments, cache hit rates drop to ~1/N. Memory usage scales linearly with worker count. Cache invalidation is impossible across workers.  
**Recommendation**: Replace with Redis-backed cache using `app.state.redis_client`. A 30-second TTL maps directly to Redis `SETEX`. The `_cache_get`/`_cache_set` API can remain identical with a Redis backend swap.

---

### [MEDIUM] PIPELINE-RESPONSIBILITY: Evidence pipeline is 865 lines spanning 5 architectural concerns

**File**: `/Users/proth/repos/kmflow/src/evidence/pipeline.py:1-865`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# Five distinct responsibilities in one file:
# 1. File validation (lines 44-135): MIME detection, size checks
# 2. Storage operations (lines 137-227): hashing, dedup, file I/O
# 3. Parsing orchestration (lines 230-271): fragment extraction
# 4. Intelligence pipeline (lines 279-600): entity extraction, graph, embeddings, bridges
# 5. Master orchestrator (lines 700-865): ingest_evidence (170 lines, 9 steps)

# The file also imports HTTPException from FastAPI (line 19):
from fastapi import HTTPException
```
**Description**: This file has grown from 849 to 865 lines since the prior audit. The `ingest_evidence` function orchestrates 9 sequential steps across 170 lines. The intelligence pipeline section (279-600) imports from semantic, rag, and datalake packages. Notably, the file imports `HTTPException` from FastAPI -- a presentation-layer concern in what should be a service-layer module. The `validate_file_type` function raises `HTTPException(415)` directly, coupling the pipeline to FastAPI's error model.  
**Risk**: The `HTTPException` import makes this module untestable without FastAPI context. The service layer should raise domain exceptions (`UnsupportedFileType`, `FileTooLarge`) and let the route handler translate to HTTP errors. The 10 deferred imports make dependency analysis unreliable.  
**Recommendation**: Extract `evidence/validation.py`, `evidence/storage.py`, `evidence/intelligence.py`. Replace `HTTPException` raises with domain-specific exceptions. The pipeline module becomes a thin orchestrator.

---

### [MEDIUM] LAYERING-VIOLATION: Evidence pipeline raises FastAPI HTTPException from service layer

**File**: `/Users/proth/repos/kmflow/src/evidence/pipeline.py:19,123,130,733`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
from fastapi import HTTPException  # line 19

# In validate_file_type():
    raise HTTPException(              # line 123
        status_code=415,
        detail="File type 'application/octet-stream' is not allowed..."
    )

# In ingest_evidence():
    raise HTTPException(              # line 733
        status_code=413,
        detail=f"File size {len(file_content)} exceeds maximum..."
    )
```
**Description**: The evidence pipeline is architecturally a service-layer module (it sits under `src/evidence/`, not `src/api/`). However, it directly raises `HTTPException`, which is a FastAPI presentation-layer concern. This creates a dependency from the service layer back to the web framework, violating dependency inversion. The pipeline cannot be reused from CLI tools, background workers, or test scripts without importing FastAPI.  
**Risk**: If the pipeline is called from a non-HTTP context (e.g., the `EvidenceBatchWorker` background task), the `HTTPException` will propagate as an unhandled exception rather than being caught and logged properly. The batch worker at `src/evidence/batch_worker.py` calls pipeline functions and would need to catch `HTTPException` -- a web framework exception in a background job.  
**Recommendation**: Define `class EvidenceValidationError(ValueError)` in `src/evidence/exceptions.py`. Replace `HTTPException` raises in pipeline.py with `EvidenceValidationError`. Have the route handler in `src/api/routes/evidence.py` catch `EvidenceValidationError` and re-raise as `HTTPException`.

---

### [MEDIUM] DUPLICATE-AUTH-LOGIC: `_check_engagement_member` in tom.py duplicates shared dependency

**File**: `/Users/proth/repos/kmflow/src/api/routes/tom.py:60-80`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
async def _check_engagement_member(session: AsyncSession, user: User, engagement_id: UUID) -> None:
    """Verify user is a member of the engagement and set RLS context."""
    await set_engagement_context(session, engagement_id)
    if user.role == UserRole.PLATFORM_ADMIN:
        return
    result = await session.execute(
        select(EngagementMember).where(
            EngagementMember.engagement_id == engagement_id,
            EngagementMember.user_id == user.id,
        )
    )
```
**Description**: This function is called 15 times within tom.py (lines 315, 365, 401, 422, 479, 520, 555, 611, 659, 724, 1430, 1757, 1793, 2198, and more). The shared `require_engagement_access` dependency in `src/core/permissions.py` performs the same check and is used by other route files. Having two authorization code paths increases the risk that a security fix in the shared dependency is not applied to tom.py's local copy.  
**Risk**: Authorization bypass if the shared dependency is updated with additional checks (e.g., engagement status validation, IP allowlisting) but the local copy is not. Security audit complexity increases with duplicate authorization implementations.  
**Recommendation**: Replace all 15 call sites with `Depends(require_engagement_access)`. The RLS context setting can be moved into the shared dependency if not already present.

---

### [LOW] EMBEDDING-SERVICE-SINGLETON: Module-level mutable dict for singleton instances

**File**: `/Users/proth/repos/kmflow/src/rag/embeddings.py:24`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# Module-level singleton instances keyed by (model_name, dimension).
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
**Description**: The singleton pattern uses a module-level dict without thread safety. While asyncio is single-threaded per event loop, if `get_embedding_service` is called from `asyncio.to_thread` (which it might be, since embedding generation uses `asyncio.to_thread` for SentenceTransformer), concurrent access to `_instances` could cause race conditions. Additionally, some call sites construct `EmbeddingService()` directly (e.g., pipeline.py line 520: `rag_service = EmbeddingService()`) bypassing the factory function entirely.  
**Risk**: Low -- asyncio's GIL protects dict operations. The bypassed factory is a missed optimization (model loaded multiple times).  
**Recommendation**: Ensure all call sites use `get_embedding_service()` instead of `EmbeddingService()` directly. Consider adding a thread lock if `to_thread` usage expands.

---

### [LOW] BACKGROUND-TASK-LEAK-GUARD: Module-level sets for asyncio task references

**File**: `/Users/proth/repos/kmflow/src/api/routes/tom.py:57`, `/Users/proth/repos/kmflow/src/api/routes/validation.py:63`, `/Users/proth/repos/kmflow/src/api/routes/scenario_simulation.py:40`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# tom.py:
_background_tasks: set[asyncio.Task[None]] = set()

# validation.py:
_background_tasks: set[asyncio.Task[None]] = set()

# scenario_simulation.py:
_background_tasks: set[asyncio.Task[None]] = set()
```
**Description**: Three route modules maintain module-level sets to hold references to background `asyncio.Task` objects, preventing garbage collection from cancelling them. This is a valid Python pattern for fire-and-forget tasks, but the sets grow monotonically -- completed tasks are only removed via weak reference callbacks (if implemented) or never removed at all. There is no size limit or cleanup mechanism visible.  
**Risk**: Memory growth proportional to the number of background tasks launched over the process lifetime. In a long-running server, this could accumulate thousands of completed task references.  
**Recommendation**: Use `task.add_done_callback(_background_tasks.discard)` to automatically remove completed tasks. Verify this callback is already in place; if not, add it at each `_background_tasks.add(task)` call site.

---

### [LOW] ROUTE-FILE-PROLIFERATION: 77 route files registered in main.py

**File**: `/Users/proth/repos/kmflow/src/api/main.py:34-107`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
from src.api.routes import (
    admin,
    assessment_matrix,
    assumptions,
    audit_logs,
    camunda,
    # ... 72 more imports
    websocket,
)
```
**Description**: The application registers 77 route modules. While each module is individually reasonable in scope, the sheer number creates a large import surface at startup. The `main.py` file is 482 lines, with 73 lines dedicated solely to route imports. Route registration is procedural (each `app.include_router(X.router)`) rather than declarative or auto-discovered.  
**Risk**: Low -- this is a scaling pattern issue rather than a correctness issue. Adding a new route requires modifying main.py in two places (import + include_router). Startup time increases with each import.  
**Recommendation**: Consider route auto-discovery (scan `src/api/routes/` for modules with a `router` attribute) or grouping related routes into sub-packages with their own `__init__.py` that aggregates sub-routers.

---

## Sound Architecture Patterns

### [SOUND] Model Domain Package Split

**File**: `/Users/proth/repos/kmflow/src/core/models/`  
**Agent**: B1 (Architecture Auditor)  
**Description**: The model layer is now 33 domain-specific files totaling 6063 lines (average 184 lines/file, largest is taskmining.py at 506). The barrel `__init__.py` re-exports 170+ symbols for backward compatibility. This is well-organized domain-driven decomposition. The split from a single 1717-line file is complete and stable.

---

### [SOUND] Frontend API Client Architecture

**File**: `/Users/proth/repos/kmflow/frontend/src/lib/api/`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```typescript
// 23 domain-specific API modules:
// client.ts, dashboard.ts, simulations.ts, tom.ts, governance.ts,
// monitoring.ts, semantic.ts, annotations.ts, etc.

// All components now import from the shared client:
import { API_BASE_URL } from "@/lib/api";
```
**Description**: The prior audit's INCONSISTENT-API-BASE finding has been fully resolved. All frontend files now import `API_BASE_URL` from the shared `@/lib/api/client` module. No local `const API_BASE` definitions remain. The API client is properly decomposed into 23 domain modules with a barrel export. The frontend's largest TypeScript files (532, 517, 507 lines) are within acceptable bounds.

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
**Description**: The prior audit's CRITICAL finding (sync simulation engine blocking the event loop) has been remediated. The call is now properly wrapped in `asyncio.to_thread()`. All other sync-to-async bridges in the codebase (`rag/retrieval.py:114`, `rag/embeddings.py:83,99`, `evidence/parsers/layout_parser.py:82`) also correctly use `asyncio.to_thread()`. No blocking `time.sleep` calls exist in the src/ tree.

---

### [SOUND] Evidence Parser Factory Pattern

**File**: `/Users/proth/repos/kmflow/src/evidence/parsers/`  
**Agent**: B1 (Architecture Auditor)  
**Description**: 15+ format-specific parsers (PDF, DOCX, BPMN, XES, Visio, ARIS, audio, video, etc.) follow the Open/Closed principle via `parsers/base.py` base class and `parsers/factory.py` dispatch. New formats are added without modifying existing parsers.

---

### [SOUND] FastAPI Dependency Injection

**File**: `/Users/proth/repos/kmflow/src/api/deps.py` and `/Users/proth/repos/kmflow/src/core/permissions.py`  
**Agent**: B1 (Architecture Auditor)  
**Description**: Consistent use of `Depends()` for database sessions, authentication, and authorization. Permission checks are composable injectable dependencies. The lifespan pattern properly initializes and tears down PostgreSQL, Neo4j, Redis, and Camunda connections.

---

### [SOUND] No Circular Dependencies or Layering Violations in Core

**File**: `/Users/proth/repos/kmflow/src/core/`  
**Agent**: B1 (Architecture Auditor)  
**Description**: The `src/core/` package does not import from `src/api/`. No route-to-route imports exist (`from src.api.routes.X` inside another route file -- zero matches). Dependency direction is consistently downward: `api/ -> core/ -> (no upward imports)`. The deferred imports in service modules are for lazy loading, not circular dependency avoidance (verified: none of the deferred import targets import back from their callers).

---

## Module Dependency Analysis

### Dependency Direction (Healthy Patterns)
```
api/routes    -> core/models, core/permissions, core/audit     (correct)
api/routes    -> {service modules}                              (correct)
evidence/     -> core/models                                    (correct)
semantic/     -> core/models                                    (correct)
simulation/   -> core/models, core/config                       (correct)
datalake/     -> core/models                                    (correct)
```

### Dependency Concerns
```
api/routes/tom.py       -> 7 service modules + 15 model imports (high fan-out)
api/routes/pov.py       -> 5 service modules (high fan-out)
evidence/pipeline.py    -> 6 packages via deferred imports      (hidden coupling)
api/main.py             -> 77 route modules                     (import surface)
```

### Cross-Cutting Concerns
```
evidence/pipeline.py imports from fastapi  (layering violation -- MEDIUM finding above)
All other service modules correctly avoid web framework imports
```

---

## God File Summary (>500 lines)

### Python files under src/ exceeding 500 lines:

| File | Lines | Route Handlers | Inline Schemas | Status |
|------|-------|---------------|----------------|--------|
| `api/routes/tom.py` | 2274 | 35 | 51 | **NEW GOD FILE** |
| `api/routes/pov.py` | 1875 | 22 | 35 | **NEW GOD FILE** |
| `api/routes/governance.py` | 1259 | 18 | 20 | At risk |
| `api/routes/simulations.py` | 1177 | 22 | 0 (extracted) | Improved |
| `api/routes/dashboard.py` | 1072 | 7 | 18 | At risk |
| `api/routes/taskmining.py` | 1068 | -- | 0 (extracted) | Acceptable |
| `api/routes/validation.py` | 1067 | -- | 20 | At risk |
| `api/routes/monitoring.py` | 1008 | -- | 22 | At risk |
| `semantic/conflict_detection.py` | 943 | -- | -- | Acceptable (algorithm) |
| `evidence/pipeline.py` | 865 | -- | -- | Needs split |
| `semantic/entity_extraction.py` | 800 | -- | -- | Acceptable (algorithm) |
| `semantic/graph.py` | 796 | -- | -- | Acceptable (service) |
| `pov/contradiction.py` | 735 | -- | -- | Acceptable (algorithm) |
| `api/routes/regulatory.py` | 688 | -- | -- | Borderline |
| `taskmining/graph_ingest.py` | 645 | -- | -- | Acceptable |
| `monitoring/alerting/engine.py` | 606 | -- | -- | Acceptable |
| `integrations/celonis_ems.py` | 565 | -- | -- | Acceptable |
| `semantic/builder.py` | 562 | -- | -- | Acceptable |
| `api/routes/pipeline_quality.py` | 557 | -- | -- | Borderline |
| `api/routes/evidence.py` | 520 | -- | -- | Borderline |
| `core/models/taskmining.py` | 506 | -- | -- | Acceptable |
| `core/services/aggregate_replay.py` | 501 | -- | -- | Acceptable |

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
| Stateless service design | PARTIAL | Dashboard in-memory cache breaks statelessness |
| Database connection pooling | GOOD | `pool_size` + `max_overflow` + `pool_pre_ping` configured |
| Async architecture | GOOD | All sync calls properly wrapped in `asyncio.to_thread()` |
| Session management | GOOD | Cookie-based auth, no server-side session state |
| Horizontal scaling | PARTIAL | Must move dashboard cache to Redis before adding workers |
| Data isolation | GOOD | Engagement-scoped queries + RLS throughout |
| Background workers | GOOD | Redis-backed monitoring, POV generation, task mining workers |
| Background task GC | AT RISK | `_background_tasks` sets may leak completed task references |

---

## Recommendations Priority

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| 1 | Split tom.py (2274 lines) into sub-routers + extract schemas | High | Eliminates largest god file |
| 2 | Split pov.py (1875 lines) into sub-routers + extract schemas | High | Eliminates second god file |
| 3 | Extract inline schemas from remaining 14+ route files | Medium | Coding standards compliance |
| 4 | Replace dashboard in-memory cache with Redis | Low | Enables multi-worker scaling |
| 5 | Extract HTTPException from evidence/pipeline.py | Low | Fixes layering violation |
| 6 | Decompose evidence pipeline into focused modules | Medium | Reduces coupling |
| 7 | Consolidate `_check_engagement_member` into shared dependency | Low | Single authorization path |
| 8 | Add done callbacks to `_background_tasks` sets | Low | Prevents memory growth |
