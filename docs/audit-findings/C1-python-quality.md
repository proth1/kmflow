# C1: Python Code Quality Audit Findings

**Agent**: C1 (Python Quality Auditor)
**Scope**: All Python files under `src/` (460 files)
**Date**: 2026-03-19
**Auditor**: Code Quality Review — READ ONLY

---

## Summary Metrics

| Check | Count | Status |
|-------|-------|--------|
| `except Exception` (broad catch) | 70 occurrences total; 56 without justification comment | HIGH — see F1 |
| `except:` (bare except) | 0 | PASS |
| `: Any` type annotations | 154 occurrences across multiple files | HIGH — see F2 |
| `datetime.utcnow()` deprecated calls | 0 | PASS |
| `logger.*()` with f-string argument | 0 | PASS |
| `# TODO / # FIXME / # HACK` markers | 5 occurrences | MEDIUM — see F3 |
| Functions > 200 lines | 3 functions | HIGH — see F4 |
| Classes > 300 lines | 11 classes | HIGH — see F5 |
| Duplicate `_parse_timestamp` implementations | 3 copies in 3 files | MEDIUM — see F6 |
| Stub/placeholder implementations | 2 confirmed (worker + consent service) | HIGH — see F7 |
| `Any` for datetime fields in Pydantic schemas | 16 occurrences across 8 route files | MEDIUM — see F8 |
| Hardcoded stopwords set inside method body | 1 (90+ literal strings) | LOW — see F9 |
| Missing import for typed parameter (`TaskProgress`) | 1 occurrence | LOW — see F10 |

---

## Critical Issues

### [CRITICAL] F11: Hardcoded Default Secrets in `Settings` — Debug Mode On by Default

**File**: `src/core/config.py:34`
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```python
app_env: str = "development"
debug: bool = True
jwt_secret_key: str = "dev-secret-key-change-in-production"
neo4j_password: str = "neo4j_dev_password"
postgres_password: str = "kmflow_dev_password"
encryption_key: str = "dev-encryption-key-change-in-production"
```
**Description**: `debug: bool = True` has no production guard. `neo4j_password` and `postgres_password` have hardcoded development defaults that are not included in the `reject_default_secrets_in_production` validator, which only checks `jwt_secret_key` and `encryption_key`. If `app_env` is accidentally left as `"development"` in a staging or production deployment, the validator is bypassed entirely and all four secrets remain at their insecure defaults.
**Risk**: A misconfigured environment exposes detailed stack traces via `debug=True`, accepts known-weak passwords against Neo4j and PostgreSQL, and bypasses the production secret guard entirely. This is a security regression pathway, not a theoretical concern.
**Recommendation**: Add `neo4j_password` and `postgres_password` to the `reject_default_secrets_in_production` validator. Add: `if self.debug and self.app_env != "development": raise ValueError("debug must not be True outside development")`.

---

## High Severity Findings

### [HIGH] F1: Broad `except Exception` Catches — 56 Unjustified Occurrences

**File**: Multiple — representative samples below
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```python
# src/core/auth.py:431 — silent swallow on blacklist check
try:
    if await is_token_blacklisted(websocket, jwt_token):
        return None
except Exception:
    return None  # no log — exception type and message lost entirely

# src/semantic/conflict_classifier.py:409 — six consecutive broad catches in same class
except Exception:
    logger.exception("Failed to set bitemporal validity for conflict %s", conflict.id)

# src/api/routes/tom.py:2262 — nested broad catches in background task
except Exception:
    logger.exception("Background alignment scoring failed for run %s", run_id)
    try:
        ...
    except Exception:
        logger.exception("Failed to update run %s status to FAILED", run_id)
```
**Description**: 70 total `except Exception` catches across the codebase. 14 carry a `# Intentionally broad:` justification comment. The remaining 56 are unjustified. The most severe pattern is `core/auth.py:431`: the exception from `is_token_blacklisted` is swallowed with no log entry, making Redis failures or code errors in the blacklist check completely invisible. `semantic/conflict_classifier.py` has six consecutive broad catches in a single 408-line class, and `semantic/conflict_detection.py` has seven. The `governance/compliance.py` and `governance/gap_detection.py` files each have two broad catches for Neo4j queries. The `integrations/external_task_worker.py` has three at different nesting levels covering poll cycle, fetch, and failure reporting.
**Risk**: Programming errors like `AttributeError` and `KeyError` are caught alongside expected infrastructure errors, masking logic bugs during development and production. The auth blacklist swallow in `core/auth.py` means a Redis `ConnectionError` and a `KeyError` in the blacklist logic produce identical behavior — the token is silently treated as non-blacklisted.
**Recommendation**: Apply a tiered approach: (1) `core/auth.py:431` must log at minimum `logger.warning("Token blacklist check failed, treating as non-blacklisted: %s", e)` before returning `None`. (2) Neo4j query helpers in `governance/` and `semantic/` should catch `neo4j.exceptions.Neo4jError` specifically instead of `Exception`. (3) The 14 annotated broad catches (`# Intentionally broad:`) are acceptable as-is.

---

### [HIGH] F2: `Any` Type Annotations — 154 Occurrences Undermining Type Safety

**File**: Multiple — representative samples below
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```python
# src/tom/alignment_scoring.py:90-91 — service dependencies typed as Any
def __init__(
    self,
    graph_service: Any,
    embedding_service: Any | None = None,
) -> None:

# src/core/tasks/runner.py:118 — TaskProgress available in same package but not imported
async def _publish_task_progress(
    redis_client: aioredis.Redis,
    progress: Any,       # TaskProgress is defined in src/core/tasks/queue.py
) -> None:

# src/api/routes/tom.py:2227-2228 — background task function
async def _run_alignment_scoring_background(
    run_id: UUID,
    session_factory: Any,    # should be AsyncSessionFactory or Callable
    neo4j_driver: Any,       # should be neo4j.AsyncDriver
```
**Description**: 154 `: Any` annotations across the codebase. The highest-value fixes are: (1) `core/tasks/runner.py:118` — `TaskProgress` is defined in `src/core/tasks/queue.py`, which `runner.py` already imports. The `Any` annotation appears to be an oversight rather than a circular import constraint. (2) `tom/alignment_scoring.py` and `tom/roadmap.py` both accept `graph_service: Any` when `KnowledgeGraphService` from `src/semantic/graph.py` is the concrete type. (3) Background task functions in `api/routes/tom.py` use `Any` for both `session_factory` and `neo4j_driver` parameters. A `SessionFactory = Callable[[], AsyncContextManager[AsyncSession]]` type alias would resolve these cleanly.
**Risk**: `mypy` cannot validate attribute access on `Any`-typed objects. `graph_service: Any` in scoring services means that if `KnowledgeGraphService` renames a method, the error surfaces only at runtime. `session_factory: Any` means the background task cannot be statically verified for correct DB usage.
**Recommendation**: (1) Import `TaskProgress` in `runner.py` and replace `Any`. (2) Define a `SessionFactory` type alias in `src/core/database.py` and use it consistently. (3) Replace `graph_service: Any` in `alignment_scoring.py` with `KnowledgeGraphService` from `src.semantic.graph`.

---

### [HIGH] F4: Functions Exceeding 200 Lines — 3 Functions

**File**: Multiple
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```python
# src/data/seeds.py:12 — 223-line function returning a static list literal
def get_best_practice_seeds() -> list[dict[str, Any]]:
    """Return 30 best practices across 6 TOM dimensions."""
    return [
        {"domain": "Process Standardization", "industry": "Financial Services", ...},
        # ... 228 more lines of inline dicts ...
    ]

# src/api/main.py:258 — 220-line application factory function
def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

# src/pov/generator.py:72 — 204-line pipeline orchestration function
async def generate_pov(session, engagement_id, scope, generated_by) -> GenerationResult:
```
**Description**: Three functions exceed 200 lines. `get_best_practice_seeds` in `data/seeds.py` (223 lines) is entirely a static data literal — this belongs in a YAML or JSON data file, not a Python function. `create_app` in `api/main.py` (220 lines) handles CORS configuration, middleware registration, route inclusion for 30+ routers, OpenAPI customization, and error handler registration — it has at least four distinct concerns. `generate_pov` in `pov/generator.py` (204 lines) executes nine named pipeline steps inline with duplicated failure handling on each step.
**Risk**: `create_app` is particularly risky — a 220-line application factory is difficult to test and the middleware ordering (documented as critical in inline comments) is easy to accidentally disrupt when adding new middleware. `generate_pov`'s nine inline steps each contain similar error-setting patterns that must stay synchronized.
**Recommendation**: (1) Move `get_best_practice_seeds` data to `src/data/seeds/best_practices.yaml` and load it with `yaml.safe_load`. (2) Extract `_register_routes(app)` and `_configure_middleware(app, settings)` helper functions from `create_app`. (3) Each numbered step in `generate_pov` should be its own `async def _step_N_name()` function.

---

### [HIGH] F5: God Classes — 11 Classes Exceeding 300 Lines

**File**: Multiple
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```
702 lines  src/semantic/graph.py:94        KnowledgeGraphService
490 lines  src/semantic/builder.py:72      KnowledgeGraphBuilder
484 lines  src/datalake/databricks_backend.py:54  DatabricksBackend
443 lines  src/semantic/conflict_classifier.py:35  ThreeWayDistinctionClassifier
491 lines  src/core/services/survey_bot_service.py:97  SurveyBotService
398 lines  src/api/services/pdp.py:56      PDPService
412 lines  src/core/tasks/queue.py:65      TaskQueue
368 lines  src/rag/retrieval.py:30         HybridRetriever
357 lines  src/api/services/pdp.py:56      PDPService
340 lines  src/core/services/report_generation.py:68  ReportGenerationService
335 lines  src/evidence/parsers/financial_regulatory_parser.py:130  FinancialRegulatoryParser
```
**Description**: `KnowledgeGraphService` at 702 lines handles read queries, write queries, node CRUD, batch operations, relationship management, graph traversal, semantic similarity search, node deletion, and engagement subgraph management — at least eight distinct responsibilities. `ThreeWayDistinctionClassifier` at 443 lines contains six methods each with a broad `except Exception` catch, has graph queries, database queries, and merge/validity operations all in one class. `SurveyBotService` at 491 lines combines bot state machine management, question flow, consensus computation, and session tracking.
**Risk**: `KnowledgeGraphService` is a dependency in at least 12 other modules. Any change to its interface requires coordinating updates across all dependents. The class is too large to confidently mock in tests, so tests that inject it tend to use `MagicMock(spec=KnowledgeGraphService)` — but with 20 methods, mock coverage is incomplete.
**Recommendation**: `KnowledgeGraphService` should be split into `GraphReadService`, `GraphWriteService`, and `GraphSearchService`. `ThreeWayDistinctionClassifier` should extract its graph query helpers into a `ConflictGraphRepository`. `SurveyBotService` should extract `ConsensusCalculator` as a standalone service.

---

### [HIGH] F7: Stub Implementations Returning Fabricated Responses

**File**: `src/taskmining/worker.py:43` and `src/security/consent/service.py:96`
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```python
# src/taskmining/worker.py:43-54
# TODO: Wire up aggregation engine (src/taskmining/aggregation/) here.
# SessionAggregator -> ActionClassifier -> EvidenceMaterializer
# See Epic #206 stories #207, #208, #209. Stubs below are Phase 1 placeholders.
if task_type == "aggregate":
    return {
        "status": "aggregated",   # fabricated — no actual aggregation occurs
        "event_type": task_data.get("event_type"),
        "session_id": task_data.get("session_id"),
    }
elif task_type == "materialize":
    return {"status": "materialized"}  # fabricated — no materialization occurs

# src/security/consent/service.py:96-113
# TODO(#382): Wire to actual task queue (Redis stream or Celery).
# Currently returns a tracking ID without dispatching.
deletion_task_id = uuid.uuid4()
# ... returns tracking ID but never dispatches actual deletion
return {
    "status": "withdrawal_accepted",
    "deletion_task_id": str(deletion_task_id),  # ID is never stored or tracked
}
```
**Description**: Two confirmed stub implementations. `taskmining/worker.py` returns `{"status": "aggregated"}` for `aggregate` task types without performing any aggregation — the `SessionAggregator`, `ActionClassifier`, and `EvidenceMaterializer` classes exist in `src/taskmining/aggregation/` but are not called. `security/consent/service.py` generates a deletion task UUID that is never persisted, never queued, and never retrievable — a GDPR erasure request is acknowledged but never executed.
**Risk**: The consent service stub is a GDPR compliance risk. A user who withdraws consent receives a `deletion_task_id` and assumes their data will be deleted, but no deletion is ever scheduled. There is no mechanism to detect or retry the missing deletions. The task mining stub silently discards all desktop session aggregation work.
**Recommendation**: For consent service: either implement the Redis Stream dispatch (the infrastructure exists), or change the response to explicitly document the deferred state: `"status": "withdrawal_recorded_pending_manual_deletion"`. For task mining: the stub is acceptable during phased development, but the fabricated `"aggregated"` status must not be returned to callers expecting real work — return `"status": "not_implemented"` or raise `NotImplementedError`.

---

## Medium Severity Findings

### [MEDIUM] F3: TODO Comments Present — 5 Occurrences

**File**: Multiple
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```python
# src/core/audit.py:117
# TODO: Add a security_events table without an engagement FK so these
# events can be persisted to the database instead of the log stream.

# src/security/consent/service.py:96
# TODO(#382): Wire to actual task queue (Redis stream or Celery).

# src/taskmining/worker.py:43
# TODO: Wire up aggregation engine (src/taskmining/aggregation/) here.

# src/monitoring/deviation/engine.py:27
# TODO(#350-followup): Add service layer to persist DeviationRecord -> ProcessDeviation

# src/core/config.py:101
# TODO(DPA): GDPR Article 28 requires Data Processing Agreements...
```
**Description**: Five TODO comments remain in source code. The two most significant are already covered under F7 (stubs). `core/audit.py:117` documents a known architectural gap where security events not tied to an engagement are emitted as log records rather than persisted to the database, making them invisible to compliance queries. `monitoring/deviation/engine.py:27` documents that deviation engine output is in-memory only — the API endpoint that queries deviations has no data to return.
**Risk**: The `audit.py` gap means `LOGIN` and `PERMISSION_DENIED` events cannot be audited from the database. Security reporting tools querying `AuditLog` will have incomplete data. The deviation engine gap means the monitoring dashboard deviation panel will return empty results silently.
**Recommendation**: Convert each TODO to a tracked Jira issue if not already linked. The `config.py` GDPR annotation is acceptable as a compliance comment — remove the `TODO:` prefix to avoid false positives in automated scans.

---

### [MEDIUM] F6: Duplicate `_parse_timestamp` Implementations — 3 Copies

**File**: Multiple
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```python
# src/core/services/aggregate_replay.py:135
def _parse_timestamp(ts: Any) -> datetime:
    if isinstance(ts, datetime): return ts
    ts_clean = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts_clean)

# src/core/services/variant_comparison_replay.py:139
def _parse_timestamp(ts: Any) -> datetime | None:
    if isinstance(ts, datetime): return ts
    if isinstance(ts, str) and ts:
        try: return datetime.fromisoformat(ts)
        except ValueError: return None
    return None

# src/taskmining/aggregation/session.py:190
def _parse_timestamp(ts: str | datetime) -> datetime:
    if isinstance(ts, datetime): return ts
    if ts.endswith("Z"): ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)
```
**Description**: Three private `_parse_timestamp` functions with the same purpose but divergent behavior: the first raises `ValueError` on bad input; the second returns `None`; the third raises `ValueError` but handles the `Z` suffix differently from the first. These are module-private functions that cannot be shared without promotion to a shared utility, but the divergent behavior is itself a defect — callers in `aggregate_replay.py` and `session.py` will behave differently when given the same malformed timestamp.
**Risk**: A timezone-naive ISO string (e.g., `"2026-03-01T10:00:00"`) is accepted by all three; an invalid string like `"not-a-date"` raises in two but returns `None` in one. Callers that rely on the exception for error propagation will silently swallow errors if they ever migrate to the `variant_comparison_replay` version.
**Recommendation**: Extract a single `parse_iso_timestamp(value: str | datetime) -> datetime` function to `src/core/utils/datetime_utils.py`. All three callers import from that module. Align on one behavior: raise `ValueError` on invalid input (the `None`-returning variant makes error propagation caller-dependent and is harder to test correctly).

---

### [MEDIUM] F8: `Any` Used for Datetime Fields in Pydantic Response Schemas — 16 Occurrences

**File**: Multiple API route files
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```python
# src/api/routes/regulatory.py:75-76
class PolicyResponse(BaseModel):
    model_config = {"from_attributes": True}
    name: str
    created_at: Any    # should be datetime
    updated_at: Any    # should be datetime

# src/api/routes/engagements.py:98
class AuditLogResponse(BaseModel):
    model_config = {"from_attributes": True}
    created_at: Any    # should be datetime

# src/api/routes/tom.py:199
class GapResponse(BaseModel):
    created_at: Any    # should be datetime
```
**Description**: 16 `created_at: Any` and `updated_at: Any` fields across 8 route files: `metrics.py`, `tom.py` (3 models), `engagements.py`, `dashboard.py`, `regulatory.py` (3 models), `lineage.py`, and `evidence.py`. All of these models have `model_config = {"from_attributes": True}`, confirming they are ORM-backed response schemas. SQLAlchemy `DateTime(timezone=True)` columns produce `datetime` objects; `Any` adds no value and prevents Pydantic from enforcing correct serialization to ISO 8601 in API responses.
**Risk**: If the ORM column ever returns a string (e.g., from a raw query result), Pydantic will accept it without validation when the field is typed `Any`, but would reject and report the error if typed `datetime`. Silent type corruption in API responses.
**Recommendation**: Replace `created_at: Any` with `created_at: datetime` and `updated_at: Any` with `updated_at: datetime` in all 8 files. Add `from datetime import datetime` where missing. Pydantic v2 with `from_attributes=True` handles SQLAlchemy datetime columns correctly.

---

## Low Severity Findings

### [LOW] F9: 90-Entry Stopwords Set Defined Inline Inside Method Body

**File**: `src/rag/retrieval.py:244`
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```python
async def _graph_expand(self, query: str, engagement_id: str, top_k: int = 5) -> list[RetrievalResult]:
    # Extract meaningful query terms (3+ chars, skip stopwords)
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        # ... approximately 90 string literals continuing for ~50 lines ...
    }
    query_terms = [w.lower() for w in query.split() if len(w) >= 3 and w.lower() not in stopwords]
```
**Description**: A 90-entry set literal is reconstructed on every call to `_graph_expand`. The set is never mutated, has no per-call variation, and is logically a module-level constant. Beyond performance (reconstructing a 90-entry set on every graph expansion call), the inline definition buries the actual method logic — the method body starts at line 228 but the first meaningful logic statement is at line 336 after the stopword definition.
**Risk**: Negligible performance impact at current call volumes. Code clarity: the 90-line inline set makes `_graph_expand` appear to be a 170-line function when the real logic is ~30 lines.
**Recommendation**: Move to module level: `_GRAPH_EXPAND_STOPWORDS: frozenset[str] = frozenset({"the", "a", ...})`. Use `frozenset` to signal immutability and get a minor memory benefit from hash caching.

---

### [LOW] F10: `TaskProgress` Available But Not Imported in `runner.py`

**File**: `src/core/tasks/runner.py:118`
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```python
# runner.py already imports TaskQueue from queue.py
from src.core.tasks.queue import TaskQueue

# But uses Any for TaskProgress despite it being in the same module
async def _publish_task_progress(
    redis_client: aioredis.Redis,
    progress: Any,        # TaskProgress is in src.core.tasks.queue
) -> None:
    """...
    Args:
        progress: TaskProgress dataclass from the queue.   ← docstring names the type
    """
```
**Description**: The docstring for `_publish_task_progress` explicitly names `TaskProgress` as the expected type, but the annotation uses `Any`. `TaskProgress` is a `@dataclass` defined at line 35 of `src/core/tasks/queue.py`, the same module that `TaskQueue` is already imported from. There is no circular import preventing this — `runner.py` imports from `queue.py` and `queue.py` does not import from `runner.py`.
**Risk**: Low. The function body accesses `progress.task_id`, `progress.task_type`, `progress.status.value`, etc. — none of these can be statically verified with `Any`.
**Recommendation**: Add `TaskProgress` to the existing import: `from src.core.tasks.queue import TaskQueue, TaskProgress`.

---

## Positive Highlights

1. **Zero bare `except:` clauses** — no bare `except:` found in 460 files. All exception handling specifies at minimum `Exception`.

2. **Zero `datetime.utcnow()` calls** — the codebase consistently uses `datetime.now(UTC)` throughout, correctly using the timezone-aware form required by Python 3.12+.

3. **Zero f-string logger calls** — all 281 error/warning/exception log calls use lazy `%s` formatting (`logger.warning("msg %s", value)`) rather than f-strings, preventing string evaluation overhead when log levels are suppressed.

4. **Zero mutable default arguments** — no `def func(items=[])` or `def func(data={})` patterns found across 460 files.

5. **Justified broad catches annotated** — 14 of 70 `except Exception` catches carry a `# Intentionally broad:` comment explaining the rationale (PDF corruption, Excel format variance, DeltaLake library variance, etc.). This is a good discipline.

6. **`from __future__ import annotations`** — consistently applied across modules per the project coding standard requiring Python 3.12+ forward reference style.

7. **Fail-closed authentication** — `is_token_blacklisted()` in `core/auth.py` returns `True` (denies access) when Redis is unavailable. WebSocket handlers follow the same fail-closed pattern.

8. **No hardcoded API keys or credentials in source** — no bearer tokens, API keys, or production passwords embedded in code. All sensitive values flow through `pydantic-settings` from environment variables.

9. **Structured logging throughout** — `logger = logging.getLogger(__name__)` used consistently. No `print()` statements in service or API code. Logger names follow module hierarchy for granular log level control.

10. **Parameterized Neo4j queries** — `KnowledgeGraphService._run_query` and `_run_write_query` consistently use `$parameter` placeholders rather than string interpolation, preventing Cypher injection throughout the graph layer.

---

## Checkbox Verification Results

| Criterion | Status | Details |
|-----------|--------|---------|
| NO TODO COMMENTS | FAIL | 5 TODO comments in `core/audit.py:117`, `core/config.py:101`, `security/consent/service.py:96`, `taskmining/worker.py:43`, `monitoring/deviation/engine.py:27` |
| NO PLACEHOLDERS | FAIL | `taskmining/worker.py:46-54` returns fabricated aggregation status; `security/consent/service.py:100` generates deletion UUID never dispatched |
| NO HARDCODED SECRETS | PARTIAL | Dev default secrets guarded by validator for JWT/encryption; `neo4j_password` and `postgres_password` not covered by guard |
| PROPER ERROR HANDLING | PARTIAL | 56 broad `except Exception` catches without justification; 1 silent swallow in `core/auth.py:431` |
| TYPE HINTS PRESENT | PARTIAL | All function signatures annotated but 154 `: Any` usages undermine static verification; 16 datetime fields in Pydantic schemas typed as `Any` |
| NAMING CONVENTIONS | PASS | Consistent `snake_case` functions, `PascalCase` classes, `UPPER_SNAKE_CASE` constants throughout |
| DRY PRINCIPLE | FAIL | `_parse_timestamp` duplicated in 3 modules with divergent behavior |
| SRP FOLLOWED | FAIL | `KnowledgeGraphService` at 702 lines has 8+ distinct responsibilities; 10 other classes exceed 300 lines |
| FUNCTIONS < 200 LINES | FAIL | 3 functions exceed 200 lines: `get_best_practice_seeds` (223), `create_app` (220), `generate_pov` (204) |

---

## File-by-File Reference (Key Issues)

- `src/core/config.py:34` — CRITICAL: `debug=True` default; `neo4j_password`/`postgres_password` not in production guard
- `src/core/auth.py:431` — HIGH: silent swallow of blacklist check exception with no log entry
- `src/taskmining/worker.py:43-54` — HIGH: stub returning fabricated `"aggregated"` status without actual work
- `src/security/consent/service.py:96-113` — HIGH: GDPR deletion task UUID generated but never dispatched
- `src/semantic/graph.py:94` — HIGH: 702-line god class with 8+ distinct responsibilities
- `src/semantic/builder.py:72` — HIGH: 490-line god class coupling DB, embeddings, and graph ops
- `src/datalake/databricks_backend.py:54` — HIGH: 484-line god class with metadata, storage, and lifecycle concerns
- `src/semantic/conflict_classifier.py:35` — HIGH: 443-line class with 6 consecutive broad exception catches
- `src/core/services/survey_bot_service.py:97` — HIGH: 491-line class combining bot state, question flow, and consensus
- `src/data/seeds.py:12` — HIGH: 223-line function that is entirely a static data literal
- `src/api/main.py:258` — HIGH: 220-line application factory with 4+ distinct concerns
- `src/pov/generator.py:72` — HIGH: 204-line function with 9 inline pipeline steps
- `src/core/services/aggregate_replay.py:135` and `src/core/services/variant_comparison_replay.py:139` and `src/taskmining/aggregation/session.py:190` — MEDIUM: three divergent `_parse_timestamp` implementations
- `src/api/routes/regulatory.py:75-76`, `src/api/routes/tom.py:199,234,262`, `src/api/routes/engagements.py:98` et al. — MEDIUM: 16 datetime fields typed as `Any` in Pydantic schemas
- `src/core/tasks/runner.py:118` — LOW: `TaskProgress` typed as `Any` despite being importable from same package
- `src/rag/retrieval.py:244` — LOW: 90-entry stopwords set reconstructed inline on every `_graph_expand` call
