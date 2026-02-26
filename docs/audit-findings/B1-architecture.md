# B1: Architecture Audit Findings (Re-Audit)

**Agent**: B1 (Architecture Auditor)  
**Date**: 2026-02-26  
**Prior Audit**: 2026-02-20  
**Scope**: Module boundaries, god files, coupling analysis, async patterns, scalability concerns  

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 3 |
| MEDIUM | 5 |
| LOW | 3 |
| SOUND | 5 |

**Overall Architecture Risk Score**: MEDIUM-HIGH  
**Design Pattern Compliance**: 6/10  
**SOLID Compliance**: 7/10  

### Prior-Audit Remediation Status

| Prior Finding | Status | Notes |
|---------------|--------|-------|
| GOD-FILE: `src/core/models.py` (1717 lines) | **RESOLVED** | Split into 11 domain-specific modules under `src/core/models/` |
| GOD-FILE: `src/api/routes/simulations.py` (1309 lines) | **PARTIALLY RESOLVED** | Schemas extracted to `src/api/schemas/simulations.py`; route file still 1038 lines |
| Schemas defined inline in route files | **PARTIALLY RESOLVED** | Only simulations and taskmining have dedicated schema files; 14+ route files still define schemas inline |

---

## Findings

### [CRITICAL] ASYNC-SYNC-MIX: Synchronous simulation engine called from async route handler

**File**: `/Users/proth/repos/kmflow/src/api/routes/simulations.py:188-209`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
    from src.simulation.engine import run_simulation
    # ...
    try:
        process_graph = scenario.parameters or {}
        engine_result = run_simulation(
            process_graph=process_graph.get("process_graph", {"elements": [], "connections": []}),
            parameters=scenario.parameters or {},
            simulation_type=scenario.simulation_type.value
```

The simulation engine (`/Users/proth/repos/kmflow/src/simulation/engine.py`) is entirely synchronous:
```python
def run_simulation(
    process_graph: dict[str, Any],
    parameters: dict[str, Any],
    simulation_type: str,
) -> dict[str, Any]:
    """Execute a process simulation."""
    start = time.monotonic()
```
**Description**: The `run_scenario` async route handler directly calls the synchronous `run_simulation()` function without wrapping it in `asyncio.to_thread()` or `loop.run_in_executor()`. This blocks the entire asyncio event loop for the duration of the simulation computation. Since FastAPI uses a single event loop per worker, this means ALL concurrent requests (health checks, dashboard queries, WebSocket connections) are blocked while a simulation runs.  
**Risk**: Under load, a single long-running simulation can cause all other requests to time out. WebSocket connections may drop. Health checks will fail, causing load balancers to mark the instance as unhealthy. This is a denial-of-service vector -- a user can trigger a complex simulation and block the entire worker.  
**Recommendation**: Wrap the synchronous call with `asyncio.to_thread(run_simulation, ...)` at the call site. For longer-running simulations, consider offloading to a background task queue (Redis + worker pattern already exists in the codebase for monitoring workers).

---

### [HIGH] GOD-FILE: `src/api/routes/simulations.py` remains 1038 lines with embedded business logic

**File**: `/Users/proth/repos/kmflow/src/api/routes/simulations.py:1-1038`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# Route handler directly constructs complex SQL subqueries:
    latest_subq = (
        select(
            SimulationResult.scenario_id,
            sa_func.max(SimulationResult.completed_at).label("max_completed"),
        )
        .where(
            SimulationResult.scenario_id.in_(all_ids),
            SimulationResult.status == SimulationStatus.COMPLETED,
        )
        .group_by(SimulationResult.scenario_id)
        .subquery()
    )
```
**Description**: Although Pydantic schemas were extracted to `src/api/schemas/simulations.py` (263 lines), the route file still contains 1038 lines. Route handlers embed complex SQL subqueries (lines 451-472, 1003-1024), service instantiation (lines 360-365, 474-480), and inline response dict construction (lines 377-396, 510-520). The `compare_scenarios` handler alone is 136 lines (402-537). A `SimulationService` class should encapsulate the query, compute, and transform logic.  
**Risk**: Route handlers are untestable without a full FastAPI test client. Business logic duplication -- the "latest result per scenario" subquery pattern appears twice (lines 453-464 and 1006-1017). Changes to comparison logic require modifying a route file rather than a domain service.  
**Recommendation**: Create `src/simulation/comparison_service.py` for comparison and ranking logic. Move the "latest result per scenario" query into a reusable repository method. Route handlers should be thin: parse request, call service, return response.

---

### [HIGH] SCHEMA-COUPLING: 14+ route files define Pydantic schemas inline, violating separation of concerns

**File**: `/Users/proth/repos/kmflow/src/api/routes/tom.py:61-188` (representative)  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# tom.py defines 12 schemas inline within the route file:
class TOMCreate(BaseModel):
    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=512)
    dimensions: dict[str, Any] | None = None
    maturity_targets: dict[str, Any] | None = None

class GapCreate(BaseModel):
    engagement_id: UUID
    tom_id: UUID
    gap_type: TOMGapType
```

Inline schema count by file:
- `governance.py`: 11 schemas (565 lines)
- `tom.py`: 14 schemas (748 lines)
- `monitoring.py`: 12 schemas (669 lines)
- `evidence.py`: 7 schemas (413 lines)
- `regulatory.py`: 12 schemas (442 lines)
- `dashboard.py`: 8 schemas (451 lines)
- `conformance.py`: 8 schemas (363 lines)
- `pov.py`: 8 schemas (528 lines)
- `engagements.py`: 7 schemas (351 lines)
- `graph.py`: 10 schemas (411 lines)
- `shelf_requests.py`: 9 schemas (404 lines)
- `auth.py`: 7 schemas (381 lines)
- `gdpr.py`: 6 schemas (456 lines)
- `patterns.py`: 8 schemas (~200 lines)

Only `simulations.py` and `taskmining.py` have extracted their schemas to `src/api/schemas/`.

**Description**: The project established a schema extraction pattern with `src/api/schemas/simulations.py` and `src/api/schemas/taskmining.py`, but this pattern was not propagated to the other 14+ route files. Schemas co-located with routes cannot be imported by other modules (e.g., for OpenAPI client generation, test factories, or inter-service contracts) without pulling in route-layer dependencies.  
**Risk**: Schema duplication risk when multiple routes need the same response shape. Prevents automated SDK generation from schema-only imports. Increases cognitive load -- developers must scan past schema definitions to find route handlers.  
**Recommendation**: Complete the extraction pattern for all route files. Create `src/api/schemas/{domain}.py` for each route module. Use the same barrel-export pattern (`src/api/schemas/__init__.py`) for backward compatibility.

---

### [HIGH] ENCAPSULATION-VIOLATION: Route handler accesses private method on service class

**File**: `/Users/proth/repos/kmflow/src/api/routes/tom.py:587`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
    scores = {}
    for dim in TomDimension:
        scores[dim] = engine._assess_dimension_maturity(dim, stats)
```
**Description**: The `get_maturity_scores` route handler directly calls `engine._assess_dimension_maturity()` -- a private method (denoted by the leading underscore) on the `TOMAlignmentEngine` class. This breaks encapsulation and creates tight coupling between the presentation layer and the internal implementation details of the alignment engine. If the engine refactors its internal method, the route handler breaks.  
**Risk**: Fragile coupling. The private method's signature and semantics can change without notice since private methods carry no API stability guarantee. This also bypasses any validation or orchestration the engine's public API might perform.  
**Recommendation**: Add a public `get_maturity_scores(engagement_id)` method to `TOMAlignmentEngine` that wraps the internal logic. The route handler should only call public methods.

---

### [MEDIUM] DEFERRED-IMPORTS: 60+ deferred imports indicate hidden circular dependency pressure

**File**: Multiple files across `/Users/proth/repos/kmflow/src/`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# src/api/routes/simulations.py - 10 deferred imports inside function bodies:
    from src.simulation.engine import run_simulation       # line 188
    from src.simulation.impact import calculate_cascading_impact  # line 217
    from src.semantic.graph import KnowledgeGraphService    # line 360
    from src.simulation.coverage import EvidenceCoverageService   # line 361
    from src.simulation.suggester import AlternativeSuggesterService  # line 804
    from src.simulation.financial import compute_financial_impact  # line 924
    from src.simulation.ranking import rank_scenarios       # line 968

# src/evidence/pipeline.py - 10 deferred imports:
    from src.datalake.backend import StorageBackend         # line 194
    from src.semantic.entity_extraction import extract_entities  # line 287
    from src.semantic.graph import KnowledgeGraphService    # line 371
    from src.rag.embeddings import EmbeddingService         # line 498
    from src.datalake.lineage import create_lineage_record  # line 764
    from src.datalake.silver import SilverLayerWriter       # line 798

# src/mcp/server.py - 7 deferred imports inside tool handlers
# src/integrations/base.py - 5 deferred imports in factory method
```
**Description**: Over 60 imports are deferred to function-level scope across the codebase. While some may be intentional lazy-loading for optional dependencies (e.g., Neo4j driver not available), the density suggests import-time coupling pressure. The `evidence/pipeline.py` file alone imports from 6 different packages at function scope. The `simulations.py` route file imports from 7 service modules inside handlers.  
**Risk**: Deferred imports hide the true dependency graph. They mask circular dependency risks that would surface as `ImportError` at module load time. They also prevent static analysis tools from building accurate dependency trees.  
**Recommendation**: Audit whether each deferred import is (a) breaking a true circular dependency, (b) lazy-loading an optional heavy dependency, or (c) unnecessary. For case (c), move to top-level imports. For case (a), refactor the dependency direction. For case (b), document the intent with a comment.

---

### [MEDIUM] MUTABLE-GLOBAL-STATE: In-memory rate limiter and cache dicts in route modules

**File**: `/Users/proth/repos/kmflow/src/api/routes/simulations.py:82`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# simulations.py:
_LLM_RATE_LIMIT = 5
_LLM_RATE_WINDOW = 60  # seconds
_LLM_MAX_TRACKED_USERS = 10_000
_llm_request_log: dict[str, list[float]] = {}

# dashboard.py:
_DASHBOARD_CACHE_TTL = 30  # seconds
_dashboard_cache: dict[str, tuple[float, Any]] = {}
```
**Description**: Two route modules maintain mutable module-level dictionaries: `_llm_request_log` in simulations.py and `_dashboard_cache` in dashboard.py. The code comments acknowledge the limitation ("This is per-process only. In multi-worker deployments...") but this remains a design concern. Module-level mutable state violates the stateless service principle, makes testing harder (state leaks between tests), and will silently fail under multi-worker deployments.  
**Risk**: In production with `uvicorn --workers N`, the rate limiter's effective limit becomes `N * 5 = 5N` requests per minute per user, not 5. The dashboard cache duplicates data across N processes. Both waste memory proportional to worker count.  
**Recommendation**: The codebase already has Redis infrastructure (`src/core/redis.py`, verified in lifespan). Move both the rate limiter and dashboard cache to Redis. The `slowapi` rate limiter already registered in `main.py` could potentially replace the custom LLM rate limiter entirely.

---

### [MEDIUM] INCONSISTENT-API-BASE: Frontend components use 3 different API_BASE definitions

**File**: `/Users/proth/repos/kmflow/frontend/src/app/conformance/page.tsx:5`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```typescript
// conformance/page.tsx (port 8000 default):
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// lib/api/client.ts (port 8002 default for browser):
export const API_BASE_URL =
  typeof window === "undefined"
    ? process.env.API_URL || "http://localhost:8000"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

// EvidenceUploader.tsx and reports/page.tsx (port 8002 default for browser):
const API_BASE =
  typeof window === "undefined"
    ? process.env.API_URL || "http://localhost:8000"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";
```
**Description**: Three distinct patterns exist for API base URL resolution. The canonical `client.ts` uses SSR-aware detection with port 8002 for browser. But `conformance/page.tsx` hardcodes port 8000 without SSR detection. Other pages (`EvidenceUploader.tsx`, `reports/page.tsx`) duplicate the SSR-aware pattern instead of importing from `client.ts`. This means `conformance/page.tsx` will use the wrong port in deployments where the API runs on 8002.  
**Risk**: Requests from the conformance page will fail in environments where the API is only accessible on port 8002. The duplicated definitions mean a URL change requires updating 3+ files.  
**Recommendation**: All components should import `API_BASE_URL` from `@/lib/api/client`. Remove local `API_BASE` constants. The conformance page should be refactored to use the shared API client functions (`apiGet`, `apiPost`) rather than raw `fetch`.

---

### [MEDIUM] DUAL-SESSION-PATTERN: Route dependency yields uncommitted session while routes commit explicitly

**File**: `/Users/proth/repos/kmflow/src/api/deps.py:14-22`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# deps.py - the dependency used by all routes:
async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session

# database.py - the original dependency (not used by routes):
async def get_db_session(session_factory):
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```
**Description**: Two session dependency patterns exist. The `deps.py` version (used by all routes) yields a bare session with no auto-commit and no rollback. Routes must manually call `await session.commit()` (82 occurrences across 20 route files). The `database.py` version has auto-commit/rollback but is not used. This means if any route handler raises an exception after modifying the session but before calling `commit()`, the session state is indeterminate -- the `async with` block will close it, but SQLAlchemy's behavior for uncommitted sessions depends on configuration.  
**Risk**: Partial writes on unhandled exceptions. If a route does `session.add(x); await session.flush(); ... raise HTTPException(...)`, the flush may or may not be committed depending on error handling. The 82 explicit commits are also a maintenance burden.  
**Recommendation**: Adopt a consistent pattern. Either: (a) switch `deps.py` to use the auto-commit/rollback pattern from `database.py`, and remove explicit commits from routes, or (b) add explicit `try/except/rollback` guards in `deps.py` to match the safety of `database.py`. Option (a) is cleaner but requires verifying that all 82 commit sites don't need specific transaction boundaries.

---

### [MEDIUM] PIPELINE-RESPONSIBILITY: Evidence pipeline is 849 lines spanning 5 architectural concerns

**File**: `/Users/proth/repos/kmflow/src/evidence/pipeline.py:1-849`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# Five distinct responsibilities in one file:
# 1. File validation and security (lines 44-134): MIME type detection, octet-stream handling
# 2. Storage operations (lines 137-226): hashing, dedup, file storage with backend abstraction
# 3. Parsing orchestration (lines 229-266): fragment extraction
# 4. Intelligence pipeline (lines 274-678): entity extraction, graph building, embeddings, bridges
# 5. Master orchestrator (lines 681-849): ingest_evidence combining all above + lineage + audit

# The intelligence pipeline alone imports from 6 packages:
from src.semantic.entity_extraction import extract_entities, resolve_entities
from src.semantic.graph import KnowledgeGraphService
from src.semantic.ontology.loader import get_entity_type_to_label
from src.rag.embeddings import EmbeddingService
from src.semantic.bridges.process_evidence import ProcessEvidenceBridge
from src.datalake.silver import SilverLayerWriter
```
**Description**: The evidence pipeline file combines file validation, storage, parsing, intelligence (entity extraction + graph + embeddings + bridges), lineage, and audit logging. The `ingest_evidence` function alone is 170 lines (681-849) with 9 sequential steps. Each step is a different architectural concern. The intelligence pipeline section (274-678) could be its own module.  
**Risk**: A change to embedding generation risks breaking file validation logic due to shared module scope. Testing requires mocking 6+ external services. The 10 deferred imports make the dependency graph opaque.  
**Recommendation**: Extract to at least 3 focused modules: `evidence/validation.py` (MIME + size + hash), `evidence/storage.py` (file storage + dedup), `evidence/intelligence.py` (entity extraction + graph + embeddings + bridges). The `pipeline.py` file becomes a thin orchestrator calling these modules.

---

### [LOW] OS-PATH-USAGE: `os.path.exists` used instead of `pathlib.Path.exists()`

**File**: `/Users/proth/repos/kmflow/src/evidence/pipeline.py:244`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
import os
# ...
if not evidence_item.file_path or not os.path.exists(evidence_item.file_path):
    logger.warning("Evidence item %s has no valid file path", evidence_item.id)
    return []
```
**Description**: The coding standards mandate `pathlib.Path` over `os.path`. The pipeline already imports `pathlib.Path` (line 16) and uses it elsewhere (lines 118, 210, 214), but falls back to `os.path.exists` here. Similarly, `visio_parser.py` uses `os.path.normpath` and `os.path.isabs`.  
**Risk**: Low -- functional correctness is not affected. This is a coding standards consistency issue.  
**Recommendation**: Replace with `Path(evidence_item.file_path).exists()`.

---

### [LOW] CONFORMANCE-PAGE-BYPASSES-API-CLIENT: Raw fetch calls instead of shared API client

**File**: `/Users/proth/repos/kmflow/frontend/src/app/conformance/page.tsx:64-68`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```typescript
const loadReferenceModels = async () => {
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/conformance/reference-models`
      );
      if (!response.ok) throw new Error("Failed to load reference models");
```
**Description**: The conformance page uses raw `fetch()` calls instead of the shared `apiGet`/`apiPost` helpers from `@/lib/api/client.ts`. This bypasses the centralized `credentials: "include"` setting, the standard error handling, and the consistent `API_BASE_URL` resolution. The page also does not pass `credentials: "include"`, so authentication cookies will not be sent in cross-origin scenarios.  
**Risk**: Authentication will fail when the API is on a different origin. Error handling is inconsistent with the rest of the app. Any future changes to auth (e.g., adding CSRF tokens) will miss this page.  
**Recommendation**: Refactor to use `apiGet<ReferenceModel[]>("/api/v1/conformance/reference-models")` and `apiPost<ConformanceResult>(...)` from the shared client.

---

### [LOW] NAMING-INCONSISTENCY: `_check_engagement_member` duplicates `require_engagement_access`

**File**: `/Users/proth/repos/kmflow/src/api/routes/tom.py:41-55`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# tom.py defines its own authorization check:
async def _check_engagement_member(session: AsyncSession, user: User, engagement_id: UUID) -> None:
    """Verify user is a member of the engagement. Platform admins bypass."""
    if user.role == UserRole.PLATFORM_ADMIN:
        return
    result = await session.execute(
        select(EngagementMember).where(
            EngagementMember.engagement_id == engagement_id,
            EngagementMember.user_id == user.id,
        )
    )

# But the same file also uses the shared dependency on other routes:
    _engagement_user: User = Depends(require_engagement_access),
```
**Description**: The TOM routes define a local `_check_engagement_member` function AND use the shared `require_engagement_access` dependency on some endpoints. Both perform the same check (verify user is a member of the engagement, skip for platform admins). This creates two authorization code paths in the same file.  
**Risk**: If the authorization logic changes (e.g., adding role-based access within engagements), the local function may not be updated. Inconsistent authorization patterns increase audit complexity.  
**Recommendation**: Remove `_check_engagement_member` and use `Depends(require_engagement_access)` consistently on all engagement-scoped endpoints.

---

## Sound Architecture Patterns

### [SOUND] Model Domain Package Split

**File**: `/Users/proth/repos/kmflow/src/core/models/__init__.py`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
"""This package re-exports all models and enums from domain-specific modules
so that existing code using ``from src.core.models import X`` continues to work."""

from src.core.models.audit import AuditAction, AuditLog, HttpAuditEvent
from src.core.models.auth import CopilotMessage, EngagementMember, MCPAPIKey, User, ...
from src.core.models.evidence import DataCatalogEntry, EvidenceCategory, EvidenceItem, ...
```
**Description**: The prior audit's top finding (1717-line god file) has been addressed. Models are now split into 11 domain-specific modules (auth, audit, conformance, engagement, evidence, governance, monitoring, pattern, pov, simulation, taskmining, tom). A barrel `__init__.py` re-exports all symbols for backward compatibility. Individual model files range from 95-310 lines -- well within maintainability bounds. This is a textbook domain-driven decomposition.

---

### [SOUND] Frontend API Client Architecture

**File**: `/Users/proth/repos/kmflow/frontend/src/lib/api/`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```typescript
// index.ts barrel export:
export * from "./client";
export * from "./dashboard";
export * from "./tom";
export * from "./simulations";
// ... 14 domain modules

// Backward-compatible shim in lib/api.ts:
export * from "./api/index";
```
**Description**: The frontend API client has been properly decomposed from a monolithic file into domain-specific modules (14 modules) under `frontend/src/lib/api/`. A barrel export maintains backward compatibility. The base client (`client.ts`, 142 lines) provides consistent typed helpers (`apiGet<T>`, `apiPost<T>`, `apiPatch<T>`, `apiDelete`) with centralized auth and error handling. This is clean separation of concerns.

---

### [SOUND] Evidence Parser Factory Pattern

**File**: `/Users/proth/repos/kmflow/src/evidence/parsers/`  
**Agent**: B1 (Architecture Auditor)  
**Description**: The evidence parsing subsystem uses a proper factory pattern (`parsers/factory.py`) with a base class (`parsers/base.py`) and 14 format-specific parser implementations. Each parser handles one evidence format. The factory dispatches based on file extension and MIME type. This follows the Open/Closed principle -- new formats are added by creating new parser classes without modifying existing code.

---

### [SOUND] FastAPI Dependency Injection

**File**: `/Users/proth/repos/kmflow/src/api/deps.py` and `/Users/proth/repos/kmflow/src/core/permissions.py`  
**Agent**: B1 (Architecture Auditor)  
**Description**: The codebase consistently uses FastAPI's `Depends()` for database sessions, authentication, and authorization. Permission checks are implemented as injectable dependencies (`require_permission("simulation:create")`), enabling clean composition. The lifespan pattern in `main.py` properly initializes and tears down connections (PostgreSQL, Neo4j, Redis, Camunda) via `app.state`.

---

### [SOUND] Knowledge Graph Service Abstraction

**File**: `/Users/proth/repos/kmflow/src/semantic/graph.py`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
class KnowledgeGraphService:
    """Service for managing the Neo4j knowledge graph.
    All graph operations are scoped to an engagement_id for data isolation.
    The service uses parameterized Cypher queries to prevent injection."""

    async def _run_query(self, query, parameters):     # read transaction
    async def _run_write_query(self, query, parameters): # write transaction
```
**Description**: The knowledge graph service provides proper read/write transaction separation (`execute_read` vs `execute_write`), parameterized Cypher queries (preventing injection), engagement-scoped data isolation, batch operations (UNWIND for bulk creates), and result set limits (guarding against unbounded scans). The ontology validation loads node labels and relationship types from YAML, following a schema-driven approach. This is well-designed for its purpose.

---

## Module Dependency Analysis

### Dependency Direction (Healthy Patterns)
```
api/routes -> core/models       (presentation -> domain: correct)
api/routes -> core/permissions   (presentation -> auth: correct)
api/routes -> core/audit         (presentation -> cross-cutting: correct)
api/routes -> {service modules}  (presentation -> service: correct)
evidence/pipeline -> semantic/*  (service -> service: acceptable)
evidence/pipeline -> datalake/*  (service -> data: correct)
evidence/pipeline -> rag/*       (service -> service: acceptable)
```

### Dependency Concerns
```
api/routes/simulations.py -> 7 service modules (high fan-out)
evidence/pipeline.py -> 6 packages via deferred imports (hidden coupling)
api/routes/tom.py -> src.core.models (deferred import of TOMDimension already at top-level)
```

### No Circular Dependencies Detected
Core does not import from API layer. No route-to-route imports exist. The deferred imports are used for lazy loading, not cycle breaking (verified by checking that none of the deferred import sources import from the files that defer them).

---

## Scalability Assessment

| Concern | Rating | Notes |
|---------|--------|-------|
| Stateless service design | PARTIAL | In-memory rate limiter and cache break statelessness |
| Database connection pooling | GOOD | `pool_size` + `max_overflow` + `pool_pre_ping` configured |
| Async architecture | AT RISK | Sync simulation engine blocks event loop |
| Session management | GOOD | Cookie-based auth, no server-side session state |
| Horizontal scaling | BLOCKED | Must fix mutable global state before adding workers |
| Data isolation | GOOD | Engagement-scoped queries throughout |
| Background workers | GOOD | Redis-backed monitoring and task mining workers |

---

## Recommendations Priority

| Priority | Finding | Effort |
|----------|---------|--------|
| 1 | Fix async/sync mixing in simulation route | Low (1 line: `asyncio.to_thread()`) |
| 2 | Move rate limiter and cache to Redis | Medium |
| 3 | Extract remaining inline schemas to `src/api/schemas/` | Medium |
| 4 | Decompose evidence pipeline into focused modules | Medium |
| 5 | Remove `_check_engagement_member` duplication | Low |
| 6 | Standardize frontend API_BASE usage | Low |
| 7 | Slim down simulations route with service extraction | High |
| 8 | Add public method to TOMAlignmentEngine for maturity scores | Low |
