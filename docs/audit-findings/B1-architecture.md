# B1: Architecture Audit Findings (Cycle 7)

**Agent**: B1 (Architecture Auditor)  
**Date**: 2026-03-20  
**Prior Audits**: 2026-02-20, 2026-02-26, 2026-03-19 (Re-Audit #2), 2026-03-19 (Re-Audit #3), 2026-03-20 (Re-Audit #4)  
**Scope**: Module boundaries, god files, coupling analysis, async patterns, layering violations, scalability  

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 1 |
| MEDIUM | 5 |
| LOW | 3 |
| SOUND | 10 |

**Overall Architecture Risk Score**: MEDIUM (unchanged from prior cycle)  
**Design Pattern Compliance**: 8.5/10  
**SOLID Compliance**: 8/10  

### Prior-Audit Remediation Status

| Prior Finding | Status | Notes |
|---------------|--------|-------|
| CRITICAL: Sync simulation engine blocking event loop | **RESOLVED** | Wrapped in `asyncio.to_thread()` (simulations.py:216) |
| HIGH: GOD-FILE `src/core/models.py` (1717 lines) | **RESOLVED** | Split into 33 domain modules under `src/core/models/` |
| HIGH: Schemas defined inline in 6 route files (104 schemas) | **RESOLVED** | All 6 files now import from `src/api/schemas/` |
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
# tom.py: 1762 lines, 36 route handlers spanning 8 sub-domains:
# 88 direct session operations (execute/add/delete/commit/refresh/flush)
async def create_tom(                    # line ~139 - TOM CRUD
async def create_gap(                    # line ~426 - Gap analysis
async def create_best_practice(          # line ~595 - Best practices
async def create_benchmark(              # line ~674 - Benchmarks
async def generate_roadmap(              # line ~1214 - Roadmaps
async def compute_maturity_scores(       # line ~1408 - Maturity
async def trigger_alignment_scoring(     # line ~1595 - Alignment runs
async def _run_alignment_scoring_async(  # line ~1713 - Background task

# pov.py: 1537 lines, 31 route handlers, 39 direct session operations
```
**Description**: tom.py is the largest file in the codebase at 1762 lines (unchanged since last audit) with 36 async route handlers and 88 direct `session.execute/add/commit` calls -- making it a fat controller with no service layer extraction. pov.py follows the same pattern at 1537 lines with 31 handlers and 39 session calls. Both files violate Single Responsibility: route handlers perform SQL queries, business logic, and response transformation inline.  
**Risk**: Merge conflicts when multiple developers work on TOM-adjacent features. A syntax error anywhere disables the entire TOM subsystem (all 36 endpoints). Untestable business logic embedded in route handlers. 88 session calls in one file means database interaction patterns cannot be unit-tested without spinning up a full HTTP test client.  
**Recommendation**: Extract service classes: `tom/service.py` (business logic + DB ops), split routes into `tom/core.py`, `tom/gaps.py`, `tom/benchmarks.py`, `tom/roadmaps.py`, `tom/maturity.py`, `tom/alignment.py`. Tagged `FUTURE(audit-B1-001)` and `FUTURE(audit-B1-002)`.

---

### [MEDIUM] LAYERING-VIOLATION: core/ imports from semantic/ and api/ (upward dependencies)

**File**: `/Users/proth/repos/kmflow/src/core/regulatory.py:19`, `/Users/proth/repos/kmflow/src/core/retention.py:59`, `/Users/proth/repos/kmflow/src/core/services/reviewer_actions_service.py:19`, `/Users/proth/repos/kmflow/src/core/auth.py:254`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# core/regulatory.py:19 (top-level import from semantic/)
from src.semantic.graph import KnowledgeGraphService

# core/services/reviewer_actions_service.py:19 (top-level)
from src.semantic.graph import KnowledgeGraphService

# core/retention.py:59 (deferred)
    from src.semantic.graph import KnowledgeGraphService

# core/auth.py:254 (deferred)
    from src.api.middleware.csrf import generate_csrf_token
```
**Description**: The `core/` package is the foundation layer -- models, config, database, auth. It should not depend on higher-level packages. Three files in `core/` import from `src.semantic.graph`, and `core/auth.py` imports from `src.api.middleware.csrf`. The deferred imports in retention.py and auth.py may have been used to avoid import-time errors, which is itself a symptom of incorrect layering.  
**Risk**: `core/regulatory.py` and `core/services/reviewer_actions_service.py` are business services misplaced in the core layer. This creates circular dependency potential and prevents `core/` from being a standalone, dependency-free foundation.  
**Recommendation**: Move `core/regulatory.py` to `src/governance/regulatory.py` or `src/regulatory/engine.py`. Move `core/services/reviewer_actions_service.py` to `src/api/services/`. Extract `generate_csrf_token` to a `src/core/csrf.py` utility (pure HMAC function with no API-layer dependencies).

---

### [MEDIUM] DEFERRED-IMPORTS: 233 deferred imports across 86 files indicate hidden coupling

**File**: Multiple files across `/Users/proth/repos/kmflow/src/`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# 233 deferred imports in 86 files. Notable categories:

# Circular avoidance (19 occurrences in tom.py alone):
    from src.core.config import get_settings        # tom.py deferred
    from src.rag.embeddings import EmbeddingService  # tom.py deferred

# Heavy-init avoidance (mcp/server.py: 7 deferred):
    from src.core.models import Engagement, EngagementMember, EvidenceItem

# Lazy loading (integrations/base.py: 5 connectors):
    from src.integrations.celonis import CelonisConnector  # justified registry

# Pipeline cross-cutting (evidence/pipeline.py: 13 deferred):
    from src.semantic.graph import KnowledgeGraphService
    from src.evidence.quality import score_evidence
```
**Description**: Over 233 function-scope imports exist across 86 files (up from "30+" documented in last audit -- the actual number is significantly higher). Categories: (a) lazy registry loading in integrations/base.py (5, justified), (b) TYPE_CHECKING guards in model files (56 occurrences in 28 files, correct usage), (c) circular dependency avoidance in route/service files (~100+, concerning), (d) heavy-init avoidance in MCP/worker modules (~20, pragmatic).  
**Risk**: Import-time errors only surface at runtime when specific code paths are hit. Static analysis tools (mypy, ruff) cannot trace the full dependency graph. Category (c) is the concern -- it masks architectural problems that should be solved by restructuring.  
**Recommendation**: Prioritize resolving the circular dependencies that cause categories (b) and (c). The tom.py file alone has 19 deferred imports, reinforcing the case for its decomposition. Accept categories (a) and (d) as justified patterns.

---

### [MEDIUM] PIPELINE-RESPONSIBILITY: Evidence pipeline is 882 lines spanning 5 architectural concerns

**File**: `/Users/proth/repos/kmflow/src/evidence/pipeline.py:1-882`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# Five distinct responsibilities with 13 deferred imports:
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
**Description**: This file imports from 6 packages (`core`, `evidence`, `semantic`, `rag`, `datalake`, `quality`) and uses 13 deferred imports. It mixes storage, parsing, entity extraction, graph building, embedding generation, and semantic bridging into a single module. The prior HTTPException layering violation was fixed.  
**Risk**: Testing any single pipeline stage requires loading the entire 882-line module. Changes to the embedding step risk breaking parsing through shared imports and state.  
**Recommendation**: Extract `evidence/storage.py` (store_file, check_duplicate), `evidence/intelligence.py` (extract, graph, embeddings, bridges). Keep `pipeline.py` as a thin orchestrator calling these modules.

---

### [MEDIUM] LAYERING-VIOLATION: Service module imports from API schema layer

**File**: `/Users/proth/repos/kmflow/src/semantic/confidence.py:17`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# FUTURE(audit-B2-001): Move ConfidenceScore to src/core/models/confidence.py
from src.api.schemas.confidence import ConfidenceScore
```
**Description**: `src/semantic/confidence.py` imports `ConfidenceScore` from `src/api/schemas/confidence`, violating the dependency direction rule. The code has a FUTURE tag acknowledging this. This is the only remaining service-to-API schema dependency.  
**Risk**: Service layer becomes coupled to API schema changes. Cannot refactor schemas without modifying the semantic service.  
**Recommendation**: Move `ConfidenceScore` to `src/core/models/confidence.py` or `src/core/schemas/confidence.py`.

---

### [MEDIUM] MUTABLE-GLOBAL-STATE: In-process caches and rate limiters without multi-worker safety

**File**: `/Users/proth/repos/kmflow/src/api/services/pdp.py:42-48`, `/Users/proth/repos/kmflow/src/mcp/auth.py:27`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# pdp.py:42-48 - Module-level mutable state:
_policy_cache: list[dict[str, Any]] = []
_cache_loaded_at: float = 0.0
_cache_lock = asyncio.Lock()
_recent_latencies: collections.deque[float] = collections.deque(maxlen=100)

# mcp/auth.py:27-28 - Rate limit state:
_FAILED_ATTEMPTS: dict[str, tuple[int, float]] = {}
_MAX_FAILED_ATTEMPTS = 5

# EmbeddingService bypass (5 call sites constructing directly):
# pipeline.py:532, retrieval.py:136, copilot.py:66, tom.py:1738, graph.py:125
```
**Description**: (1) PDP policy cache uses module-level globals with an asyncio.Lock -- correct within a single process but each worker gets its own cache (cache invalidation is per-process). (2) MCP rate limiter stores failed attempts in-process memory, resetting on restart. (3) Five call sites construct `EmbeddingService()` directly instead of using `get_embedding_service()`, potentially loading duplicate models.  
**Risk**: PDP cache is low-risk (5s TTL, auto-refresh). MCP rate limiter provides no protection in multi-worker deployments. Duplicate EmbeddingService instances waste memory.  
**Recommendation**: (1) Accept PDP cache as adequate given short TTL. (2) Move MCP rate limiting to Redis. (3) Replace all 5 direct `EmbeddingService()` calls with `get_embedding_service()`.

---

### [LOW] ROUTE-FILE-PROLIFERATION: 78 route modules registered in main.py

**File**: `/Users/proth/repos/kmflow/src/api/main.py:34-117`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
from src.api.routes import (
    admin, assessment_matrix, assumptions, audit_logs,
    camunda, claim_write_back, cohort, confidence,
    # ... 70+ more imports across 4 import blocks
    websocket,
)
# 78 app.include_router() calls in a 516-line file
```
**Description**: The application registers 78 route modules (up from 77 at last audit). Adding a new route requires modifying main.py in two places (import + include_router). The file is 516 lines, most of which is router registration boilerplate.  
**Risk**: Low -- maintainability concern, not correctness.  
**Recommendation**: Consider route auto-discovery or grouping related routes into sub-packages.

---

### [LOW] GOD-FILE-RISK: 6 route files between 500-1211 lines (post schema extraction)

**File**: Multiple route files  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
# Route files > 500 lines (schemas properly extracted):
# simulations.py:    1211 lines, 57 session ops (unchanged)
# taskmining.py:     1130 lines, 45 session ops (unchanged)
# governance.py:     1026 lines, 35 session ops (unchanged)
# dashboard.py:       920 lines, 35 session ops (unchanged)
# validation.py:      895 lines, 32 session ops (unchanged)
# monitoring.py:      821 lines, 50 session ops (unchanged)
```
**Description**: Line counts are unchanged since last audit -- no growth but no improvement either. All six files have schemas properly extracted but retain business logic and database operations inline (total 254 session operations across these 6 files).  
**Risk**: Files above 800 lines remain hard to navigate and review. Inline session operations prevent unit testing business logic.  
**Recommendation**: For simulations.py (57 session ops) and monitoring.py (50 session ops), extract service classes as higher priority.

---

### [LOW] ROUTE-TO-ROUTE-IMPORT: intake.py imports limiter from auth.py

**File**: `/Users/proth/repos/kmflow/src/api/routes/intake.py:21`  
**Agent**: B1 (Architecture Auditor)  
**Evidence**:
```python
from src.api.routes.auth import limiter
```
**Description**: `intake.py` imports the `Limiter` instance from `auth.py`. This is the only route-to-route import. Creates an implicit load-order dependency.  
**Risk**: Low -- the limiter is a shared utility, not business logic.  
**Recommendation**: Move `limiter` to `src/api/deps.py` or `src/api/rate_limit.py`.

---

## Sound Architecture Patterns

### [SOUND] Schema Extraction Complete (Remediated)

**File**: `/Users/proth/repos/kmflow/src/api/schemas/`  
**Description**: All previously flagged route files now properly import schemas from `src/api/schemas/`. The schemas directory contains 24 domain-specific schema files. Zero inline Pydantic schemas remain in route files.

---

### [SOUND] Background Task Centralization (Remediated)

**File**: `/Users/proth/repos/kmflow/src/api/background.py`  
**Description**: Shared `track_background_task()` function used by all background task call sites. DRY violation resolved.

---

### [SOUND] Model Domain Package Split

**File**: `/Users/proth/repos/kmflow/src/core/models/`  
**Description**: 33 domain-specific model files totaling ~6100 lines (average 185 lines/file, largest taskmining.py at 506). The barrel `__init__.py` (473 lines) re-exports 170+ symbols. Clean domain-driven decomposition.

---

### [SOUND] Frontend API Client Architecture

**File**: `/Users/proth/repos/kmflow/frontend/src/lib/api/`  
**Description**: 23 domain-specific API modules with a shared `client.ts` providing typed generic helpers. Only 3 frontend files exceed 500 lines (532, 517, 507), all within acceptable bounds.

---

### [SOUND] Async Pattern Compliance

**File**: `/Users/proth/repos/kmflow/src/api/routes/simulations.py:216`  
**Description**: All sync-to-async bridges correctly use `asyncio.to_thread()`. Only 2 `asyncio.run()` calls exist, both in CLI entry points (governance/migration_cli.py, semantic/ontology/validate.py) -- correct usage for script main functions. No sync I/O in async route handlers detected.

---

### [SOUND] Evidence Pipeline Layering (Remediated)

**File**: `/Users/proth/repos/kmflow/src/evidence/pipeline.py`, `/Users/proth/repos/kmflow/src/evidence/exceptions.py`  
**Description**: Pipeline uses `EvidenceValidationError` with `status_hint`. Route handler translates to HTTPException. Proper separation of service-layer from presentation-layer concerns.

---

### [SOUND] Dashboard Redis Cache (Remediated)

**File**: `/Users/proth/repos/kmflow/src/api/routes/dashboard.py`  
**Description**: Dashboard cache uses Redis via `request.app.state.redis_client` with `SETEX` for TTL. Graceful fallback on Redis errors. Supports multi-worker horizontal scaling.

---

### [SOUND] Shared Authorization

**File**: `/Users/proth/repos/kmflow/src/core/permissions.py`  
**Description**: All route files use `verify_engagement_member` from `src/core/permissions`. Single authorization code path. No duplicated auth logic.

---

### [SOUND] No Circular Dependencies in Module Imports

**Description**: Despite 233 deferred imports, no actual circular import errors exist at runtime. `TYPE_CHECKING` guards (56 occurrences in 28 model files) correctly handle forward references. The deferred imports indicate coupling complexity but not broken imports.

---

### [SOUND] Evidence Parser Factory Pattern

**File**: `/Users/proth/repos/kmflow/src/evidence/parsers/`  
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
core/regulatory.py          -> semantic/graph (core importing from service layer)
core/services/reviewer_*    -> semantic/graph (core importing from service layer)
core/retention.py           -> semantic/graph (core importing from service layer, deferred)
core/auth.py                -> api/middleware/csrf (core importing from api layer, deferred)
semantic/confidence.py      -> api/schemas/confidence (service importing from api layer)
api/routes/intake.py        -> api/routes/auth.limiter (route-to-route)
evidence/pipeline.py        -> 6 packages via 13 deferred imports (hidden coupling)
mcp/server.py               -> 7 deferred imports per tool handler (lazy loading)
api/main.py                 -> 78 route modules (import surface)
```

### Fat Controller Analysis (session operations in route files)
```
tom.py:          88 session ops in 1762 lines  (worst offender)
simulations.py:  57 session ops in 1211 lines
monitoring.py:   50 session ops in  821 lines
taskmining.py:   45 session ops in 1130 lines
pov.py:          39 session ops in 1537 lines
regulatory.py:   39 session ops in  553 lines
governance.py:   35 session ops in 1026 lines
dashboard.py:    35 session ops in  920 lines
validation.py:   32 session ops in  895 lines
Total:          807 session ops across 58 route files
```

---

## God File Summary (>500 lines)

### Python files under src/ exceeding 500 lines:

| File | Lines | Session Ops | Status | Change Since Last Audit |
|------|-------|-------------|--------|------------------------|
| `api/routes/tom.py` | 1762 | 88 | **GOD FILE** - needs sub-router + service split | unchanged |
| `api/routes/pov.py` | 1537 | 39 | **GOD FILE** - needs sub-router + service split | unchanged |
| `api/routes/simulations.py` | 1211 | 57 | Large (schemas extracted) | unchanged |
| `api/routes/taskmining.py` | 1130 | 45 | Large (schemas extracted) | unchanged |
| `api/routes/governance.py` | 1026 | 35 | Improved (schemas extracted) | unchanged |
| `semantic/conflict_detection.py` | 944 | 0 | Acceptable (algorithm) | unchanged |
| `api/routes/dashboard.py` | 920 | 35 | Improved (schemas extracted) | unchanged |
| `api/routes/validation.py` | 895 | 32 | Improved (schemas extracted) | unchanged |
| `evidence/pipeline.py` | 882 | -- | Needs responsibility split | unchanged |
| `semantic/graph.py` | 822 | 0 | Acceptable (service) | unchanged |
| `api/routes/monitoring.py` | 821 | 50 | Improved (schemas extracted) | unchanged |
| `semantic/entity_extraction.py` | 800 | 0 | Acceptable (algorithm) | unchanged |
| `pov/contradiction.py` | 735 | 0 | Acceptable (algorithm) | unchanged |
| `taskmining/graph_ingest.py` | 645 | 0 | Acceptable | unchanged |
| `api/routes/evidence.py` | 633 | 17 | Borderline | unchanged |
| `monitoring/alerting/engine.py` | 613 | 0 | Acceptable | unchanged |
| `api/routes/gdpr.py` | 577 | 19 | Borderline | unchanged |
| `integrations/celonis_ems.py` | 565 | 0 | Acceptable | unchanged |
| `semantic/builder.py` | 563 | 0 | Acceptable | unchanged |
| `api/routes/regulatory.py` | 553 | 39 | High session density (7.1/100 lines) | unchanged |
| `api/schemas/tom.py` | 539 | 0 | Acceptable (schema-only) | unchanged |
| `core/auth.py` | 533 | 0 | Borderline + layering concern | +21 lines |
| `api/main.py` | 516 | 0 | Borderline (78 routers) | unchanged |
| `core/models/taskmining.py` | 506 | 0 | Acceptable | unchanged |

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
| PDP policy cache | ACCEPTABLE | 5s TTL per-process, auto-refresh, lock-protected |

---

## Recommendations Priority

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| 1 | Split tom.py into sub-routers + extract service class | Medium | Eliminates largest god file (1762 lines, 88 session ops) |
| 2 | Split pov.py into sub-routers + extract service class | Medium | Eliminates second god file (1537 lines, 39 session ops) |
| 3 | Move core/regulatory.py and core/services/reviewer_actions_service.py out of core/ | Low | Fixes core-layer upward dependencies |
| 4 | Decompose evidence pipeline into focused modules | Medium | Reduces coupling and improves testability |
| 5 | Move ConfidenceScore to core layer | Low | Fixes service-to-API layering violation |
| 6 | Extract generate_csrf_token to core/csrf.py | Low | Fixes core-to-API dependency in auth.py |
| 7 | Replace 5 direct EmbeddingService() calls with get_embedding_service() | Low | Prevents duplicate model loading |
| 8 | Move limiter to shared module | Low | Removes route-to-route import |
| 9 | Move MCP rate limiting to Redis | Low | Multi-worker support |
| 10 | Add background task shutdown drain to lifespan | Low | Clean shutdown |
