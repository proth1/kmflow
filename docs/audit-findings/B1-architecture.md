# B1: Architecture Audit Findings

**Agent**: B1 (Architecture Auditor)
**Date**: 2026-02-20
**Scope**: Module boundaries, god files, coupling analysis, async patterns, scalability concerns

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 3 |
| MEDIUM | 6 |
| LOW | 3 |
| SOUND | 4 |

---

## Findings

### [HIGH] GOD-FILE: `src/core/models.py` is 1717 lines with 76 classes

**File**: `src/core/models.py:1-1717`
**Agent**: B1 (Architecture Auditor)
**Evidence**:
```python
# 76 classes in a single file:
# 24 enum classes (EngagementStatus, EvidenceCategory, ValidationStatus, ...)
# 52 ORM model classes (Engagement, EvidenceItem, User, SimulationScenario, ...)
```
**Description**: This file contains every SQLAlchemy ORM model and enum for the entire platform — 76 classes spanning engagement management, evidence processing, simulation, monitoring, governance, conformance, copilot, and data catalog. A developer modifying any domain touches the same file, increasing merge conflict risk and cognitive load.
**Risk**: High merge conflict frequency as teams scale. Violates Single Responsibility Principle. A change to simulation enums forces re-parsing of unrelated governance models in IDEs and tools.
**Recommendation**: Split into domain-specific model modules: `src/core/models/engagement.py`, `src/core/models/evidence.py`, `src/core/models/simulation.py`, `src/core/models/monitoring.py`, `src/core/models/governance.py`, `src/core/models/conformance.py`. Keep a `src/core/models/__init__.py` that re-exports all symbols for backward compatibility.

---

### [HIGH] GOD-FILE: `src/api/routes/simulations.py` is 1309 lines with 27 Pydantic schemas and business logic

**File**: `src/api/routes/simulations.py:1-1309`
**Agent**: B1 (Architecture Auditor)
**Evidence**:
```python
# 27 Pydantic schemas defined inline (lines 86-1221)
# In-memory rate limiter (lines 49-80)
# Direct ORM queries, service instantiation, and response mapping in handlers
# Deferred imports to 6 different service modules
```
**Description**: This route file combines API schemas (27 Pydantic models), an in-memory rate limiter, ORM query logic, and response serialization. It acts as a combined controller+service+schema layer. Other large route files exhibit the same pattern: `tom.py` (732 lines, 17 schemas), `monitoring.py` (602 lines, 12 schemas), `governance.py` (546 lines, 11 schemas), `pov.py` (528 lines, 12 schemas).
**Risk**: Violates Single Responsibility. Schemas cannot be imported by other modules (e.g., for client SDK generation) without pulling in route dependencies. Business logic is untestable without spinning up FastAPI.
**Recommendation**: Extract Pydantic schemas to `src/api/schemas/simulations.py`. Move business logic to service classes (e.g., `src/simulation/service.py`). Route handlers should only do: parse request, call service, return response.

---

### [HIGH] LAYERING-VIOLATION: `src/core/` modules depend on FastAPI framework

**File**: `src/core/auth.py:20`, `src/core/permissions.py:13`, `src/core/rate_limiter.py:12`
**Agent**: B1 (Architecture Auditor)
**Evidence**:
```python
# src/core/auth.py:20
from fastapi import Depends, HTTPException, Request, status

# src/core/permissions.py:13
from fastapi import Depends, HTTPException, Request, status

# src/core/rate_limiter.py:12
from fastapi import Depends, HTTPException, Request, status
```
**Description**: The `src/core/` package is the domain/business logic layer, yet three modules directly depend on FastAPI's `Depends`, `HTTPException`, `Request`, and `status`. This couples core business logic to the web framework. Additionally, `src/evidence/pipeline.py:20` imports `HTTPException` from FastAPI, meaning the evidence processing pipeline (a domain service) cannot run outside a FastAPI context.
**Risk**: Core business logic cannot be reused from CLI tools, background workers, or test harnesses without importing FastAPI. The evidence pipeline raising `HTTPException` (HTTP 413, 415) means domain validation is expressed as HTTP semantics — mixing transport with domain concerns.
**Recommendation**: For `core/auth.py` and `core/permissions.py`, extract pure business logic (token validation, permission checking) into framework-agnostic functions, with thin FastAPI `Depends` wrappers in `src/api/deps.py`. For `evidence/pipeline.py`, raise domain-specific exceptions (e.g., `FileTooLargeError`, `UnsupportedFileTypeError`) and translate to `HTTPException` at the route layer.

---

### [MEDIUM] GLOBAL-MUTABLE-STATE: In-memory rate limiter in `simulations.py`

**File**: `src/api/routes/simulations.py:56`
**Agent**: B1 (Architecture Auditor)
**Evidence**:
```python
_LLM_RATE_LIMIT = 5
_LLM_RATE_WINDOW = 60  # seconds
_LLM_MAX_TRACKED_USERS = 10_000
_llm_request_log: dict[str, list[float]] = defaultdict(list)
```
**Description**: Module-level mutable `defaultdict` tracks per-user LLM request timestamps. While the code includes a comment acknowledging the multi-worker limitation, this state is not shared across uvicorn workers. The file already has a proper Redis-based rate limiter in `src/core/rate_limiter.py` used by the copilot endpoint.
**Risk**: In multi-worker deployments, the effective rate limit multiplies by worker count (N workers = N * 5 = potentially 20+ requests/min). The `_LLM_MAX_TRACKED_USERS` eviction is also racy under concurrent requests. This is inconsistent with the Redis-based approach used elsewhere.
**Recommendation**: Replace with the existing Redis-based rate limiter pattern from `src/core/rate_limiter.py`, or factor the in-memory limiter into a shared utility with clear documentation about its single-process limitation.

---

### [MEDIUM] EXCESSIVE-DEFERRED-IMPORTS: 67 deferred imports across 14 files indicate coupling pressure

**File**: `src/evidence/pipeline.py` (14 deferred imports), `src/api/routes/simulations.py` (8), `src/api/routes/tom.py` (8), `src/mcp/server.py` (6), and 10 other files
**Agent**: B1 (Architecture Auditor)
**Evidence**:
```python
# src/evidence/pipeline.py:267 (inside async function body)
from src.semantic.entity_extraction import extract_entities, resolve_entities

# src/evidence/pipeline.py:534-538 (inside async function body)
from src.semantic.bridges.communication_deviation import CommunicationDeviationBridge
from src.semantic.bridges.evidence_policy import EvidencePolicyBridge
from src.semantic.bridges.process_evidence import ProcessEvidenceBridge
from src.semantic.bridges.process_tom import ProcessTOMBridge
from src.semantic.graph import KnowledgeGraphService
```
**Description**: 67 imports are deferred into function bodies rather than placed at module level. While deferred imports are a valid technique to avoid circular dependencies or defer heavy module loading, the volume here (14 in `pipeline.py` alone) suggests the dependency graph is tangled enough that top-level imports would cause circular import errors. The `evidence/pipeline.py` file imports from `semantic`, `rag`, `datalake`, and `core` — all inside function bodies.
**Risk**: Hides the true dependency graph from static analysis tools, IDE navigation, and import-time error detection. Makes it easy to introduce circular dependencies without noticing. Deferred imports also prevent IDE autocompletion until the function is entered.
**Recommendation**: Audit which deferred imports are protecting against circular imports vs. just deferring heavy loads. For circular import cases, consider introducing interface protocols or restructuring module boundaries. For heavy-load cases, document the reason with a comment.

---

### [MEDIUM] MISSING-SERVICE-LAYER: Route handlers directly instantiate services and execute business logic

**File**: `src/api/routes/simulations.py:495-500`, `src/api/routes/regulatory.py:396-398`, `src/api/routes/tom.py:535-537`
**Agent**: B1 (Architecture Auditor)
**Evidence**:
```python
# src/api/routes/simulations.py:495-500
from src.semantic.graph import KnowledgeGraphService
from src.simulation.coverage import EvidenceCoverageService
driver = request.app.state.neo4j_driver
graph_service = KnowledgeGraphService(driver)
coverage_service = EvidenceCoverageService(graph_service)
coverage = await coverage_service.compute_coverage(...)
```
**Description**: Route handlers manually construct service objects by pulling drivers from `app.state`, then compose service chains. This pattern is repeated 15+ times across `simulations.py`, `regulatory.py`, `tom.py`, `copilot.py`, and `graph.py`. There is no dependency injection for Neo4j-backed services — only the DB session uses FastAPI's `Depends` (via `get_session`).
**Risk**: Each route handler duplicates service construction logic. Testing requires mocking `request.app.state` internals. If the `KnowledgeGraphService` constructor changes, every route handler must be updated.
**Recommendation**: Create FastAPI dependencies for common services (e.g., `get_graph_service`, `get_coverage_service`) in `src/api/deps.py`. Use `Depends()` to inject them, matching the existing pattern for database sessions.

---

### [MEDIUM] SCHEMA-COUPLING: 150+ Pydantic schemas co-located in route files

**File**: All files under `src/api/routes/` (27 in simulations.py, 17 in tom.py, 12 in monitoring.py, etc.)
**Agent**: B1 (Architecture Auditor)
**Evidence**:
```python
# src/api/routes/simulations.py has 27 schemas (BaseModel subclasses)
# src/api/routes/tom.py has 17 schemas
# src/api/routes/monitoring.py has 12 schemas
# src/api/routes/governance.py has 11 schemas
# src/api/routes/pov.py has 12 schemas
# Total: ~150+ Pydantic schemas across route files
```
**Description**: API request/response schemas are defined inline within route files rather than in a dedicated schemas package. This means schemas cannot be imported independently for client SDK generation, documentation tools, or cross-module reuse without importing the entire route module (and its FastAPI dependencies).
**Risk**: Prevents schema reuse across modules. Makes OpenAPI schema generation tightly coupled to route registration. Frontend `api.ts` (1694 lines) duplicates all these types in TypeScript, with no automated synchronization mechanism.
**Recommendation**: Move schemas to `src/api/schemas/{domain}.py` modules. Consider using a code generation tool (e.g., `openapi-typescript-codegen`) to auto-generate the frontend TypeScript types from the OpenAPI spec.

---

### [MEDIUM] FRONTEND-MONOLITH: `frontend/src/lib/api.ts` is 1694 lines with 82 functions and 98 types

**File**: `frontend/src/lib/api.ts:1-1694`
**Agent**: B1 (Architecture Auditor)
**Evidence**:
```typescript
// Line 7-9: The file acknowledges its own problem
// TODO: Split into domain modules when this file exceeds 1500 lines.
// Suggested modules: api/evidence.ts, api/governance.ts, api/monitoring.ts,
// api/reports.ts, api/admin.ts

// 82 exported functions, 98 exported interfaces/types
```
**Description**: All API client functions and type definitions for the entire platform are in a single file. The file already exceeds the 1500-line threshold mentioned in its own TODO comment. Every page component imports from this single file. The simulations page (`frontend/src/app/simulations/page.tsx`, 1247 lines) imports 19 items from it.
**Risk**: Large bundle impact — every page that imports any API function pulls the entire module into scope (unless tree-shaking is perfectly effective). High merge conflict probability. Violates the module boundary conventions from the backend.
**Recommendation**: Follow the file's own TODO: split into `frontend/src/lib/api/evidence.ts`, `frontend/src/lib/api/governance.ts`, etc., with a barrel `index.ts` for backward compatibility. Consider generating types from the OpenAPI spec.

---

### [MEDIUM] FRONTEND-GOD-COMPONENT: `frontend/src/app/simulations/page.tsx` is 1247 lines

**File**: `frontend/src/app/simulations/page.tsx:1-1247`
**Agent**: B1 (Architecture Auditor)
**Evidence**:
```typescript
// Single page component with:
// - 19 imports from api.ts
// - Multiple useState/useEffect hooks
// - Inline data fetching, transformation, and rendering
// - No extracted sub-components or custom hooks
```
**Description**: The simulations page is a monolithic component that handles scenario creation, running simulations, viewing results, managing modifications, evidence coverage, financial analysis, suggestions, and epistemic planning — all in a single file. This mirrors the backend's `simulations.py` monolith.
**Risk**: Difficult to test individual features. Re-renders the entire page on any state change. Cannot code-split individual features within the page.
**Recommendation**: Extract into sub-components: `ScenarioList`, `ScenarioDetail`, `CoveragePanel`, `FinancialAnalysis`, `EpistemicPlanner`. Extract data-fetching into custom hooks: `useScenarios`, `useCoverage`, etc.

---

### [LOW] ASYNC-SYNC-MIX: Sync file I/O inside async methods in storage backends

**File**: `src/datalake/backend.py:160-175`, `src/datalake/backend.py:293-319`
**Agent**: B1 (Architecture Auditor)
**Evidence**:
```python
# src/datalake/backend.py:160 (LocalFilesystemBackend)
async def write(self, engagement_id: str, file_name: str, content: bytes, ...) -> StorageMetadata:
    ...
    with open(file_path, "wb") as f:  # line 174 - SYNC I/O in async method
        f.write(content)

# src/datalake/backend.py:293 (DeltaLakeBackend)
async def write(self, engagement_id: str, file_name: str, content: bytes, ...) -> StorageMetadata:
    ...
    with open(file_path, "wb") as f:  # line 318 - SYNC I/O in async method
        f.write(content)
```
**Description**: Both storage backend implementations define `async def write()` but use synchronous `open()` for file I/O. The evidence pipeline (`src/evidence/pipeline.py:203`) correctly uses `aiofiles.open()` for its file writes, showing the team is aware of the pattern but it was not applied consistently.
**Risk**: Sync file I/O blocks the event loop. For small files this is negligible, but large evidence files (the platform handles video, audio, structured data) could cause request latency spikes for other concurrent requests.
**Recommendation**: Use `aiofiles.open()` (already a project dependency) or `asyncio.to_thread(open(...).write, content)` for file writes in async methods.

---

### [LOW] NO-DEPENDENCY-INJECTION: Neo4j driver accessed via `request.app.state` pattern

**File**: `src/api/routes/simulations.py:498`, `src/api/routes/regulatory.py:396`, `src/api/routes/tom.py:535`, and 12 other locations
**Agent**: B1 (Architecture Auditor)
**Evidence**:
```python
# Repeated pattern across route files:
driver = request.app.state.neo4j_driver
graph_service = KnowledgeGraphService(driver)
engine = TOMAlignmentEngine(graph_service)
```
**Description**: The Neo4j driver, Redis client, and other infrastructure dependencies are accessed via `request.app.state` rather than FastAPI's dependency injection system. The database session correctly uses `Depends(get_session)`, but this pattern was not extended to other infrastructure clients.
**Risk**: Testing requires complex mocking of `request.app.state`. No type safety on `app.state` attributes (they are `Any`). Service construction is duplicated across handlers.
**Recommendation**: Create typed dependencies: `async def get_neo4j_driver(request: Request) -> AsyncDriver`, `async def get_graph_service(driver=Depends(get_neo4j_driver)) -> KnowledgeGraphService`, etc.

---

### [LOW] INCONSISTENT-SCHEMAS: Route handlers return `dict[str, Any]` despite declaring `response_model`

**File**: `src/api/routes/simulations.py:265-286`, and most other route files
**Agent**: B1 (Architecture Auditor)
**Evidence**:
```python
@router.post("/scenarios", response_model=ScenarioResponse, status_code=status.HTTP_201_CREATED)
async def create_scenario(...) -> dict[str, Any]:  # Returns raw dict, not ScenarioResponse
    ...
    return _scenario_to_response(scenario)  # Manual dict construction
```
**Description**: Route handlers declare `response_model=SomeSchema` but return `dict[str, Any]` rather than the schema instance. FastAPI will validate the dict against the schema at runtime, but this means: (1) no IDE type checking on the return value, (2) manual dict-building functions (`_scenario_to_response`, `_result_to_response`) that duplicate schema field lists, and (3) divergence risk between the dict keys and schema fields.
**Risk**: If a schema field is renamed, the manual dict builder will silently produce a response missing that field (caught only at runtime by Pydantic validation). No compile-time safety.
**Recommendation**: Return Pydantic model instances directly (e.g., `return ScenarioResponse.model_validate(scenario)`) or use `from_attributes=True` on schemas with `model_config`.

---

## Architecture Health: SOUND Areas

### [SOUND] LAYERING-DIRECTION: No upward dependency violations

Core (`src/core/`) is not imported by `src/api/` in the wrong direction. No route file imports from another route file. No business logic module imports from `src/api/routes/`. The dependency arrow flows: `api/routes -> core -> database`, `api/routes -> {domain modules} -> core`, which is correct.

### [SOUND] MODULE-ORGANIZATION: 17 well-named domain packages

The `src/` directory contains 17 clearly bounded domain packages: `agents`, `api`, `conformance`, `core`, `data`, `datalake`, `evidence`, `governance`, `integrations`, `mcp`, `monitoring`, `patterns`, `pov`, `rag`, `semantic`, `simulation`, `tom`. Each maps to a distinct bounded context from the PRD.

### [SOUND] NO-CIRCULAR-IMPORTS: Deferred imports prevent circular dependency failures

Despite the heavy coupling between `evidence`, `semantic`, `datalake`, and `core`, the codebase has no circular import failures at runtime. The deferred import pattern (while a smell at scale) successfully prevents import-time errors.

### [SOUND] NO-GLOBAL-MUTABLE-STATE (except one): Clean module-level declarations

Aside from the `_llm_request_log` defaultdict in `simulations.py`, the codebase has no module-level mutable state (no global dicts, lists, or sets). Configuration is accessed via `get_settings()` which returns an immutable Pydantic `Settings` object.

---

## Overall Architecture Risk Score

**MEDIUM** — The architecture follows sound layering principles and has clean module boundaries at the package level. However, several files have grown beyond maintainable size (models.py, simulations.py, api.ts), the core layer is coupled to FastAPI, and the absence of a consistent service layer and schema separation will make the codebase increasingly difficult to maintain as the team grows. None of these are blocking issues today, but they represent architectural debt that compounds over time.

### Priority Remediation Order

1. **Extract core/auth FastAPI coupling** (HIGH) — blocks reuse in CLI/workers
2. **Split models.py** (HIGH) — reduces merge conflicts, improves IDE performance
3. **Extract Pydantic schemas from routes** (MEDIUM) — enables client SDK generation
4. **Add FastAPI dependencies for Neo4j/services** (LOW) — improves testability
5. **Split frontend api.ts** (MEDIUM) — the file already identifies this need
