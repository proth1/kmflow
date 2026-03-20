# B1: Architecture Audit Findings (Re-Audit #4)

**Agent**: B1 (Architecture Auditor)  
**Date**: 2026-03-20  
**Prior Audits**: 2026-02-20, 2026-02-26, 2026-03-19 (Re-Audit #2), 2026-03-19 (Re-Audit #3)  
**Scope**: Module boundaries, god files, coupling analysis, async patterns, scalability concerns  

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 1 |
| MEDIUM | 4 |
| LOW | 3 |
| SOUND | 10 |

**Overall Architecture Risk Score**: MEDIUM (improved from prior — schema coupling resolved)  
**Design Pattern Compliance**: 8.5/10  
**SOLID Compliance**: 8.5/10  

### Prior-Audit Remediation Status

| Prior Finding | Status | Notes |
|---------------|--------|-------|
| CRITICAL: Sync simulation engine blocking event loop | **RESOLVED** | Wrapped in `asyncio.to_thread()` (simulations.py:216) |
| HIGH: GOD-FILE `src/core/models.py` (1717 lines) | **RESOLVED** | Split into 33 domain modules under `src/core/models/` |
| HIGH: `src/api/routes/simulations.py` (1309 lines) | **RESOLVED** | Schemas extracted; route file now 1211 lines |
| HIGH: Schemas defined inline in 6 route files (104 schemas) | **RESOLVED** | All 6 files now import from `src/api/schemas/` (governance, validation, dashboard, monitoring, regulatory, pipeline_quality) |
| HIGH: Encapsulation violation `engine._assess_dimension_maturity` | **RESOLVED** | No longer present |
| MEDIUM: In-memory rate limiter in simulations.py | **RESOLVED** | Replaced with Redis sliding-window |
| MEDIUM: Inconsistent API_BASE in frontend | **RESOLVED** | All files import from `@/lib/api/client` |
| MEDIUM: Evidence pipeline imports HTTPException | **RESOLVED** | Now uses `EvidenceValidationError` domain exception |
| MEDIUM: Dashboard in-memory cache | **RESOLVED** | Now Redis-backed via `request.app.state.redis_client` |
| MEDIUM: Background task duplication (3 separate sets) | **RESOLVED** | Centralized to `src/api/background.py:track_background_task()` |
| LOW: `_check_engagement_member` duplication in tom.py | **RESOLVED** | Replaced with shared `verify_engagement_member` from `src/core/permissions` |

---

## Findings

### [HIGH] GOD-FILE: Route files tom.py (1762 lines) and pov.py (1537 lines) remain oversized

**File**: `/Users/proth/repos/kmflow/src/api/routes/tom.py:1-1762`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# tom.py: 1762 lines, 35+ route handlers spanning 8 sub-domains:
async def create_tom(                    # line ~139 - TOM CRUD
async def create_gap(                    # line ~426 - Gap analysis
async def create_best_practice(          # line ~595 - Best practices
async def create_benchmark(              # line ~674 - Benchmarks
async def generate_roadmap(              # line ~1202 - Roadmaps
async def compute_maturity_scores(       # line ~1396 - Maturity
async def trigger_alignment_scoring(     # line ~1583 - Alignment runs
async def _run_alignment_scoring_async(  # line ~1702 - Background task
```
**Description**: tom.py is 1762 lines (up from 1751 at last audit) with 35+ async route handlers covering TOMs, gap analysis, best practices, benchmarks, roadmaps, maturity scoring, conformance, and alignment runs. Schemas have been properly extracted to `src/api/schemas/tom.py` (539 lines). pov.py follows the same pattern at 1537 lines (up from 1496). Both files continue to grow.  
**Risk**: Merge conflicts when multiple developers work on TOM-adjacent features. A syntax error anywhere in the file disables the entire TOM subsystem (all 35 endpoints). High cognitive load for reviewers.  
**Recommendation**: Split into sub-routers: `tom/core.py` (CRUD), `tom/gaps.py`, `tom/benchmarks.py`, `tom/roadmaps.py`, `tom/maturity.py`, `tom/alignment.py`. Same for pov.py. This is tagged `FUTURE(audit-B1-001)` and `FUTURE(audit-B1-002)` in the source.

---

### [MEDIUM] DEFERRED-IMPORTS: 30+ deferred imports indicate hidden coupling in service modules

**File**: Multiple files across `/Users/proth/repos/kmflow/src/`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# src/taskmining/graph_ingest.py:398 - deferred to avoid circular:
    from src.taskmining.correlation.role_association import ROLE_AGGREGATE_PREFIX

# src/integrations/base.py:120-124 - lazy connector loading:
    from src.integrations.celonis import CelonisConnector
    from src.integrations.salesforce import SalesforceConnector
    from src.integrations.sap import SAPConnector
    from src.integrations.servicenow import ServiceNowConnector
    from src.integrations.soroco import SorocoConnector

# src/tom/rationale_generator.py:154,275 - deferred settings/LLM:
            from src.core.config import get_settings
        from src.core.llm import get_llm_provider
```
**Description**: Over 30 imports are deferred to function-level scope. Some are justified: `integrations/base.py` lazily loads connectors (registry pattern), `core/models/*.py` uses `TYPE_CHECKING` guards for relationship typing. Others (e.g., `graph_ingest.py`, `rationale_generator.py`, `erasure_worker.py`) suggest circular dependency or heavy-init avoidance.  
**Risk**: Import-time errors surface only at runtime when specific code paths are hit. Static analysis tools cannot trace the full dependency graph.  
**Recommendation**: Categorize each deferred import as (a) lazy-loading optional dependency, (b) circular dependency avoidance, (c) unnecessary. Move category (c) to top level. For (b), consider restructuring modules to break the cycle.

---

### [MEDIUM] PIPELINE-RESPONSIBILITY: Evidence pipeline is 882 lines spanning 5 architectural concerns

**File**: `/Users/proth/repos/kmflow/src/evidence/pipeline.py:1-882`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# Five distinct responsibilities in one file:
async def check_duplicate(...)           # line ~150 - Storage concern
async def store_file(...)                # line ~171 - Storage concern
async def process_evidence(...)          # line ~231 - Parse orchestration
async def extract_fragment_entities(...) # line ~280 - NLP/semantic
async def build_fragment_graph(...)      # line ~358 - Knowledge graph
async def generate_fragment_embeddings(...)  # line ~501 - RAG
async def run_semantic_bridges(...)      # line ~555 - Semantic linking
async def run_intelligence_pipeline(...) # line ~616 - Orchestrator
async def ingest_evidence(...)           # line ~702 - Master orchestrator
```
**Description**: This file orchestrates the entire evidence lifecycle. It imports from 6 packages (`core`, `evidence`, `semantic`, `rag`, `datalake`, `quality`). The prior layering violation (HTTPException) was resolved. However, it still mixes storage, parsing, entity extraction, graph building, embedding generation, and semantic bridging.  
**Risk**: Testing any single pipeline stage requires loading the entire 882-line module. Changes to embedding step risk breaking parsing through shared state.  
**Recommendation**: Extract `evidence/storage.py` (store_file, check_duplicate), `evidence/intelligence.py` (extract, graph, embeddings, bridges). Keep `pipeline.py` as a thin orchestrator.

---

### [MEDIUM] LAYERING-VIOLATION: Service module imports from API schema layer

**File**: `/Users/proth/repos/kmflow/src/semantic/confidence.py:17`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# FUTURE(audit-B2-001): Move ConfidenceScore to src/core/models/confidence.py
from src.api.schemas.confidence import ConfidenceScore
```
**Description**: `src/semantic/confidence.py` (a service-layer module) imports `ConfidenceScore` from `src/api/schemas/confidence`, violating the dependency direction rule (service layer should not depend on API layer). The code has a FUTURE tag acknowledging this. This is the only remaining service-to-API dependency outside of `src/api/` itself.  
**Risk**: Service layer becomes coupled to API schema changes. The schema cannot be refactored without also modifying the semantic service. Other service modules requiring `ConfidenceScore` would propagate the violation.  
**Recommendation**: Move `ConfidenceScore` to `src/core/models/confidence.py` or `src/core/schemas/confidence.py` (a shared schema location). Import from there in both `semantic/` and `api/schemas/`.

---

### [MEDIUM] MUTABLE-GLOBAL-STATE: Embedding service singleton dict and MCP rate limiter without thread safety

**File**: `/Users/proth/repos/kmflow/src/rag/embeddings.py:24`, `/Users/proth/repos/kmflow/src/mcp/auth.py:27`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# rag/embeddings.py:24 - Singleton dict:
_instances: dict[tuple[str, int], EmbeddingService] = {}
def get_embedding_service(...) -> EmbeddingService:
    key = (model_name, dimension)
    if key not in _instances:
        _instances[key] = EmbeddingService(...)
    return _instances[key]

# mcp/auth.py:27 - Rate limit state:
_FAILED_ATTEMPTS: dict[str, tuple[int, float]] = {}
```
**Description**: Two module-level mutable dicts serve as shared state. The embedding singleton uses a check-then-set pattern (TOCTOU). The MCP rate limiter stores failed attempt counts in-process memory, which resets on restart and doesn't work across multiple workers. Additionally, 5 call sites still bypass `get_embedding_service()` by constructing `EmbeddingService()` directly (pipeline.py:532, retrieval.py:136, copilot.py:66, tom.py:1738, graph.py:125).  
**Risk**: Low in practice for embedding dict (GIL protects dict ops). MCP rate limiter provides no protection in multi-worker deployments.  
**Recommendation**: (1) Use `functools.lru_cache` for the embedding singleton. (2) Move MCP rate limiting to Redis. (3) Replace all `EmbeddingService()` direct calls with `get_embedding_service()`.

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
# 77 app.include_router() calls
```
**Description**: The application registers 77 route modules. Adding a new route requires modifying main.py in two places (import + include_router).  
**Risk**: Low -- maintainability concern, not correctness.  
**Recommendation**: Consider route auto-discovery or grouping related routes into sub-packages (e.g., `tom/` sub-package would collapse 1 god-file into several focused modules with a single `include_router` call).

---

### [LOW] GOD-FILE-RISK: 6 route files between 500-1211 lines (post schema extraction)

**File**: Multiple route files  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# Route files > 500 lines (schemas now properly extracted):
# simulations.py:    1211 lines (schemas extracted)
# taskmining.py:     1130 lines (schemas extracted)
# governance.py:     1026 lines (schemas extracted - down from 1259)
# dashboard.py:       920 lines (schemas extracted - down from 1079)
# validation.py:      895 lines (schemas extracted - down from 1099)
# monitoring.py:      821 lines (schemas extracted - down from 1008)
# evidence.py:        633 lines
# regulatory.py:      553 lines (schemas extracted - down from 688)
```
**Description**: Schema extraction reduced all 6 previously flagged files by 130-275 lines each. Governance dropped from 1259 to 1026, dashboard from 1079 to 920, validation from 1099 to 895, monitoring from 1008 to 821, regulatory from 688 to 553. Despite this improvement, simulations.py (1211) and taskmining.py (1130) remain large due to route logic volume, not inline schemas.  
**Risk**: Files above 800 lines remain hard to navigate and review.  
**Recommendation**: For simulations.py and taskmining.py, consider sub-router decomposition similar to what's recommended for tom.py.

---

### [LOW] ROUTE-TO-ROUTE-IMPORT: intake.py imports limiter from auth.py

**File**: `/Users/proth/repos/kmflow/src/api/routes/intake.py:21`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
from src.api.routes.auth import limiter
```
**Description**: `intake.py` imports the `Limiter` instance from `auth.py` (line 65). This creates a horizontal dependency between route modules, which are expected to be independent. Other than this single case, no route-to-route imports exist.  
**Risk**: Low -- the limiter is a shared utility, not business logic. However, it creates an implicit load-order dependency.  
**Recommendation**: Move `limiter` to a shared module like `src/api/rate_limit.py` or `src/api/deps.py`.

---

## Sound Architecture Patterns

### [SOUND] Schema Extraction Complete (Remediated)

**File**: `/Users/proth/repos/kmflow/src/api/schemas/`  
**Agent**: B1 (Architecture Auditor)  
**Description**: All 6 previously flagged route files (governance, validation, dashboard, monitoring, regulatory, pipeline_quality) now properly import schemas from `src/api/schemas/`. The schemas directory contains 24 domain-specific schema files. Zero inline Pydantic schemas remain in any route file. This fully resolves the prior HIGH finding.

---

### [SOUND] Background Task Centralization (Remediated)

**File**: `/Users/proth/repos/kmflow/src/api/background.py`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
_background_tasks: set[asyncio.Task[None]] = set()

def track_background_task(task: asyncio.Task[None]) -> None:
    """Track a background task to prevent GC. Removes itself when done."""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
```
**Description**: The prior MEDIUM finding (3 duplicate `_background_tasks` sets in tom.py, validation.py, scenario_simulation.py) is resolved. A shared `track_background_task()` function in `src/api/background.py` is now used by all 3 call sites. Note: shutdown draining is still not implemented, but the DRY violation is resolved.

---

### [SOUND] Model Domain Package Split

**File**: `/Users/proth/repos/kmflow/src/core/models/`  
**Agent**: B1 (Architecture Auditor)  
**Description**: 33 domain-specific model files totaling ~6100 lines (average 185 lines/file, largest taskmining.py at 506). The barrel `__init__.py` (473 lines) re-exports 170+ symbols. Clean domain-driven decomposition.

---

### [SOUND] Frontend API Client Architecture

**File**: `/Users/proth/repos/kmflow/frontend/src/lib/api/`  
**Agent**: B1 (Architecture Auditor)  
**Description**: 23 domain-specific API modules with a shared `client.ts` providing typed generic helpers. All frontend files import from the shared client. The largest TypeScript files (532, 517, 507 lines) are within acceptable bounds. Only 3 frontend files exceed 500 lines.

---

### [SOUND] Async Pattern Compliance

**File**: `/Users/proth/repos/kmflow/src/api/routes/simulations.py:216`  
**Agent**: B1 (Architecture Auditor)  
**Description**: All sync-to-async bridges correctly use `asyncio.to_thread()`. No `time.sleep` or blocking `requests` calls exist in `src/`. No sync I/O in async functions detected.

---

### [SOUND] Evidence Pipeline Layering (Remediated)

**File**: `/Users/proth/repos/kmflow/src/evidence/pipeline.py` and `/Users/proth/repos/kmflow/src/evidence/exceptions.py`  
**Agent**: B1 (Architecture Auditor)  
**Description**: Pipeline uses `EvidenceValidationError` with `status_hint`. Route handler translates to HTTPException. Proper separation of service-layer from presentation-layer concerns.

---

### [SOUND] Dashboard Redis Cache (Remediated)

**File**: `/Users/proth/repos/kmflow/src/api/routes/dashboard.py`  
**Agent**: B1 (Architecture Auditor)  
**Description**: Dashboard cache uses Redis via `request.app.state.redis_client` with `SETEX` for TTL. Graceful fallback on Redis errors. Supports multi-worker horizontal scaling.

---

### [SOUND] Shared Authorization

**File**: `/Users/proth/repos/kmflow/src/core/permissions.py`  
**Agent**: B1 (Architecture Auditor)  
**Description**: All route files use `verify_engagement_member` from `src/core/permissions`. Single authorization code path. No duplicated auth logic.

---

### [SOUND] No Circular Dependencies in Core Layer

**File**: `/Users/proth/repos/kmflow/src/core/`  
**Agent**: B1 (Architecture Auditor)  
**Description**: `src/core/` does not import from `src/api/`. Only one route-to-route import exists (intake -> auth.limiter). Dependency direction is consistently downward. TYPE_CHECKING guards in model files handle forward references correctly.

---

### [SOUND] Evidence Parser Factory Pattern

**File**: `/Users/proth/repos/kmflow/src/evidence/parsers/`  
**Agent**: B1 (Architecture Auditor)  
**Description**: 15+ format-specific parsers follow Open/Closed principle via base class and factory dispatch. New formats added without modifying existing parsers.

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
semantic/confidence.py  -> api/schemas/confidence (layering violation, FUTURE tagged)
api/routes/intake.py    -> api/routes/auth.limiter (route-to-route, minor)
evidence/pipeline.py    -> 6 packages via deferred imports (hidden coupling)
mcp/server.py           -> 6 deferred imports per tool handler (lazy loading)
api/main.py             -> 77 route modules (import surface)
```

### Cross-Cutting Concerns
```
Service modules: 1 violation (semantic/confidence.py -> api/schemas)
Core layer: 0 violations (core/ never imports from api/)
```

---

## God File Summary (>500 lines)

### Python files under src/ exceeding 500 lines:

| File | Lines | Status | Change Since Last Audit |
|------|-------|--------|------------------------|
| `api/routes/tom.py` | 1762 | **GOD FILE** - needs sub-router split | +11 lines |
| `api/routes/pov.py` | 1537 | **GOD FILE** - needs sub-router split | +41 lines |
| `api/routes/simulations.py` | 1211 | Large (schemas extracted) | +34 lines |
| `api/routes/taskmining.py` | 1130 | Large (schemas extracted) | +62 lines |
| `api/routes/governance.py` | 1026 | Improved (schemas extracted) | -233 lines |
| `semantic/conflict_detection.py` | 944 | Acceptable (algorithm) | +1 line |
| `api/routes/dashboard.py` | 920 | Improved (schemas extracted) | -159 lines |
| `api/routes/validation.py` | 895 | Improved (schemas extracted) | -204 lines |
| `evidence/pipeline.py` | 882 | Needs responsibility split | +12 lines |
| `api/routes/monitoring.py` | 821 | Improved (schemas extracted) | -187 lines |
| `semantic/graph.py` | 822 | Acceptable (service) | -- |
| `semantic/entity_extraction.py` | 800 | Acceptable (algorithm) | -- |
| `pov/contradiction.py` | 735 | Acceptable (algorithm) | -- |
| `taskmining/graph_ingest.py` | 645 | Acceptable | -- |
| `api/routes/evidence.py` | 633 | Borderline | -- |
| `monitoring/alerting/engine.py` | 613 | Acceptable | -- |
| `integrations/celonis_ems.py` | 565 | Acceptable | -- |
| `semantic/builder.py` | 563 | Acceptable | -- |
| `api/routes/regulatory.py` | 553 | Improved (schemas extracted) | -135 lines |
| `api/schemas/tom.py` | 539 | Acceptable (schema-only) | -- |
| `api/routes/gdpr.py` | 526 | Borderline | -- |
| `api/main.py` | 516 | Borderline (77 routers) | -- |
| `core/auth.py` | 512 | Borderline | -- |
| `core/models/taskmining.py` | 506 | Acceptable | -- |

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
| Stateless service design | GOOD | Dashboard cache on Redis, no in-memory session state |
| Database connection pooling | GOOD | `pool_size` + `max_overflow` + `pool_pre_ping` configured |
| Async architecture | GOOD | All sync calls properly wrapped in `asyncio.to_thread()` |
| Session management | GOOD | Cookie-based auth, no server-side session state |
| Horizontal scaling | GOOD | Redis-backed caching and rate limiting throughout |
| Data isolation | GOOD | Engagement-scoped queries + RLS throughout |
| Background workers | GOOD | Redis-backed monitoring, POV generation, task mining |
| Background task shutdown | AT RISK | Centralized `_background_tasks` set not drained on shutdown |
| MCP rate limiting | AT RISK | In-process dict resets on restart, no multi-worker support |

---

## Recommendations Priority

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| 1 | Split tom.py (1762 lines) into sub-routers | Medium | Eliminates largest god file |
| 2 | Split pov.py (1537 lines) into sub-routers | Medium | Eliminates second god file |
| 3 | Decompose evidence pipeline into focused modules | Medium | Reduces coupling and improves testability |
| 4 | Move ConfidenceScore to core layer | Low | Fixes layering violation |
| 5 | Use `get_embedding_service()` factory at all 5 bypass sites | Low | Prevents duplicate model loading |
| 6 | Move limiter to shared module | Low | Removes route-to-route import |
| 7 | Add background task shutdown drain to lifespan | Low | Clean shutdown |
| 8 | Move MCP rate limiting to Redis | Low | Multi-worker support |
| 9 | Audit and rationalize deferred imports | Low | Improves static analysis accuracy |
