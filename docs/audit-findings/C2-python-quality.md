# C2: Python Code Quality Audit — Agent Python Layer

**Agent**: C2 (Python Code Quality Auditor)
**Scope**: All Python files under `agent/python/kmflow_agent/` and `agent/python/tests/`
**Date**: 2026-02-28
**Auditor**: Code Quality Review — READ ONLY

---

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total Python files | 29 |
| Total lines of code | ~2,500 |
| Broad exception catches (`except Exception`) | 12 |
| Bare excepts (`except:`) | 0 |
| `: Any` type annotations | 3 |
| `datetime.utcnow()` (deprecated) | 1 |
| f-string in logger calls | 0 |
| TODO/FIXME/HACK comments | 0 |
| Stub/placeholder implementations | 1 (VLMClassifier) |
| Files without `from __future__ import annotations` | 0 |

---

## Code Quality Score: 7.5 / 10

**Justification**: The codebase demonstrates strong structural discipline — consistent module organization, `from __future__ import annotations` universally applied, appropriate use of `asyncio.to_thread()` for SQLite I/O, and security-conscious patterns (keychain-backed key storage, owner-only socket permissions). The primary quality gaps are: one deprecated API call that introduces timezone bugs, a documented stub class integrated into the live classification path, multiple broad exception handlers that suppress context, a repeated PII pattern definition violating DRY, and a non-generic type annotation in the `L2Filter.filter_event` signature. None of these are showstoppers, but several require remediation before the agent is field-deployed.

---

## Critical Issues (MUST fix before deploy)

### [HIGH] DATETIME: `datetime.utcnow()` — deprecated, timezone-naive
**File**: `agent/python/kmflow_agent/vce/trigger_engine.py:61`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
now = datetime.utcnow()
cutoff = now - timedelta(minutes=_EXCEPTION_WINDOW_MINUTES)

history = self._error_history[app_name]
history.append(now)
```
**Description**: `datetime.utcnow()` is deprecated in Python 3.12 and returns a naive datetime with no timezone information. The appended values in `_error_history` are timezone-naive datetimes. If any calling code supplies timezone-aware datetimes, comparisons will raise `TypeError`. The rest of the codebase uses `datetime.now(UTC)` (e.g., `buffer/manager.py:156`), making this an inconsistency.
**Risk**: Subtle silent correctness bug — the exception-window cutoff calculation is always correct by accident when comparing two naive UTC datetimes, but will throw `TypeError` the moment any aware datetime is mixed in. Deprecation warnings will appear in Python 3.12 stderr and will become errors in a future Python release.
**Recommendation**: Replace with `datetime.now(UTC)` (import `UTC` from `datetime`, as already done in `buffer/manager.py:16`).

```python
# Fix
from datetime import UTC, datetime
now = datetime.now(UTC)
```

---

### [HIGH] DRY VIOLATION: PII patterns duplicated across two files
**File**: `agent/python/kmflow_agent/vce/redactor.py:13` and `agent/python/kmflow_agent/pii/l2_filter.py:12`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:

`redactor.py:13-23`:
```python
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL", re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")),
    ("PHONE", re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:4\d{3}|5[1-5]\d{2}|6011|35\d{2})[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")),
    ("AMEX", re.compile(r"\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b")),
```

`l2_filter.py:12-20` (identical 5-pattern subset):
```python
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL", re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")),
    ("PHONE", re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:4\d{3}|5[1-5]\d{2}|6011|35\d{2})[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")),
    ("AMEX", re.compile(r"\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b")),
```

**Description**: The 5 core PII patterns are defined identically in two modules. `redactor.py` itself acknowledges this at line 11 with the comment "kept in sync manually." Manual synchronization between duplicated definitions is an operational fragility: a pattern added to one file will silently not apply in the other. This is a textbook DRY violation.
**Risk**: A future pattern update (e.g., adding IBAN or NPI) applied to only one module will leave one code path unprotected, causing PII to leak into either the event buffer (via `l2_filter`) or the VCE upload payload (via `redactor`).
**Recommendation**: Define `BASE_PATTERNS` in `pii/l2_filter.py` and import + extend in `redactor.py`. `redactor.py` adds NAME and ADDRESS on top of the base set.

```python
# pii/l2_filter.py — export the base patterns
BASE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ...
]

# redactor.py — import and extend
from kmflow_agent.pii.l2_filter import BASE_PATTERNS
_PATTERNS: list[tuple[str, re.Pattern[str]]] = BASE_PATTERNS + [
    ("NAME", re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")),
    ("ADDRESS", re.compile(r"...")),
]
```

---

## High Issues (Should fix before deploy)

### [HIGH] STUB IN LIVE PATH: VLMClassifier is a non-functional stub integrated into production logic
**File**: `agent/python/kmflow_agent/vce/classifier.py:129-142`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
class VLMClassifier:
    """Placeholder for Phase 2 VLM-based screen state classification.

    Will integrate Florence-2 or Moondream2 for vision-language model
    inference. Returns (OTHER, 0.0) until the model is integrated.
    """

    def classify(self, image_bytes: bytes) -> tuple[str, float]:
        """Return (screen_state_class, confidence).

        Phase 2 stub — always returns (OTHER, 0.0).
        """
        logger.debug("VLMClassifier.classify called (stub — returning OTHER, 0.0)")
        return OTHER, 0.0
```
**Description**: `VLMClassifier` is an explicitly documented stub that always returns `(OTHER, 0.0)`. It is instantiated unconditionally in `HybridClassifier.__init__()` and invoked via `self._vlm.classify(image_bytes)` when image bytes are present. The stub itself is not harmful (it never beats the rule-based classifier's confidence), but it represents unfinished work that is shipped in the live code path with no feature flag or conditional guard.
**Risk**: Cognitive overhead for anyone reading the classifier code, test confusion (tests must account for stub behaviour), and no path to Phase 2 VLM integration without modifying production logic. If a future developer adds a non-zero confidence to the stub while testing, it can silently override correct rule-based classifications.
**Recommendation**: Either (a) remove the VLM path entirely until Phase 2 is implemented, reverting `HybridClassifier` to a thin wrapper around `RuleBasedClassifier`, or (b) guard VLM invocation with a config flag `vlm_enabled: bool = False`.

---

### [HIGH] BROAD EXCEPTION: `except Exception:` without context in `upload/batch_uploader.py`
**File**: `agent/python/kmflow_agent/upload/batch_uploader.py:52`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
while not shutdown_event.is_set():
    try:
        await self._upload_pending()
    except Exception:
        logger.exception("Upload cycle error")
```
**Description**: The broad `except Exception` in the upload loop catches everything from network errors to programming errors (e.g., `AttributeError`, `KeyError`). While `logger.exception` does log the traceback, this pattern masks bugs that should surface differently. If `_upload_pending()` raises a `TypeError` due to a code defect, it will be silently swallowed and retried on the next cycle with no escalation.
**Risk**: Continuous silent retry of a broken state. In a field agent, this could mean events never upload and the buffer grows without operator awareness. Programming errors are indistinguishable from transient network failures in logs.
**Recommendation**: Narrow to specific exception types (`httpx.HTTPError`, `json.JSONDecodeError`), and let programming errors propagate to the outer `asyncio.gather()` handler in `__main__.py`.

---

### [HIGH] BROAD EXCEPTION: `except Exception:` in `_windows.py` credential read (swallows exc silently)
**File**: `agent/python/kmflow_agent/platform/_windows.py:140`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
def get_credential(self, key: str) -> str | None:
    target = f"{_CREDENTIAL_TARGET_PREFIX}{key}"
    try:
        cred_file = self.get_data_dir() / "credentials" / f"{key}.dpapi"
        if cred_file.exists():
            encrypted = cred_file.read_bytes()
            return self._dpapi_unprotect(encrypted)
    except Exception:
        logger.debug("Credential read failed for key=%s", key)
    return None
```
**Description**: The `except Exception` catches all errors — including `MemoryError`, `SystemExit`, and programming bugs — and logs only at `DEBUG` level. A failed credential read is silently converted to `None` return. The caller has no way to distinguish "credential not stored" from "DPAPI failed to decrypt due to a permissions error."
**Risk**: On Windows, if DPAPI decryption fails because the user account changed or the profile was copied, the agent will silently fall back to generating a new key, invalidating all previously encrypted buffer data.
**Recommendation**: Catch `OSError` specifically for file operations, catch `(ValueError, UnicodeDecodeError)` for decryption failures, and log at `WARNING` level (not `DEBUG`) for decryption failures.

---

### [HIGH] BROAD EXCEPTION: `except Exception:` in `_windows.py` DPAPI helpers (4 occurrences)
**File**: `agent/python/kmflow_agent/platform/_windows.py:236` and `:263`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
except (OSError, ValueError, ctypes.ArgumentError):
    pass
except Exception:
    logger.warning("Unexpected error in DPAPI protect", exc_info=True)
return None
```
**Description**: Both `_dpapi_protect` and `_dpapi_unprotect` use a two-level exception handler. The first catches known ctypes errors. The second catches all remaining exceptions. This is an acceptable pattern for protecting against unknown platform exceptions, and `exc_info=True` is correctly used. The occurrences at lines 140 and 188 (`get_credential`, `get_encryption_key`) are more problematic — they catch broadly at a higher level without `exc_info`.
**Risk**: Medium — the DPAPI helpers themselves are appropriately guarded, but callers may shadow errors.
**Recommendation**: Keep the DPAPI helper pattern as-is. Fix callers.

---

### [HIGH] BROAD EXCEPTION: `except Exception:` in `__main__.py` service loop
**File**: `agent/python/kmflow_agent/__main__.py:86`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
try:
    await asyncio.gather(
        server.serve(shutdown_event),
        uploader.run(shutdown_event),
        config.run(shutdown_event),
        health.run(shutdown_event),
    )
except Exception:
    logger.exception("Service error")
finally:
    await http_client.aclose()
    await buffer.close()
```
**Description**: The top-level service exception handler is acceptable in principle (a crash handler at the entry point), but catching `Exception` here means `asyncio.CancelledError` (which extends `BaseException` in Python 3.8+) is not caught — this is actually correct. The concern is that a single service failure cancels all services via `asyncio.gather()`, and the broad catch logs and exits without distinguishing which service failed or why.
**Risk**: Low for the catch pattern at this level (top-level handler is standard practice). The real risk is that `asyncio.gather()` by default cancels all other coroutines when one raises, making the agent a single-point-of-failure if any service throws unexpectedly.
**Recommendation**: Consider `asyncio.gather(..., return_exceptions=True)` with per-service restart logic, or at minimum structured logging that identifies which service failed.

---

## Medium Issues (Consider fixing)

### [MEDIUM] TYPE ANNOTATION: `config: dict` lacks generic parameter in `TriggerEngine`
**File**: `agent/python/kmflow_agent/vce/trigger_engine.py:114`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
def check_taxonomy_boundary(
    self,
    from_app: str,
    to_app: str,
    config: dict,
) -> bool:
```
**Description**: `config: dict` is not a fully qualified type annotation. Per KMFlow coding standards and PEP 585, this should be `dict[str, Any]` to match the rest of the codebase. The unparameterized `dict` type is a weaker type hint that provides less information to type checkers and editors.
**Risk**: Low — mypy treats `dict` and `dict[Any, Any]` equivalently in practice. Cosmetic but inconsistent with project standards.
**Recommendation**: Change to `config: dict[str, Any]` and add `from typing import Any` to the imports.

---

### [MEDIUM] TYPE ANNOTATION: `filter_event` uses unparameterized `dict` return type
**File**: `agent/python/kmflow_agent/pii/l2_filter.py:42`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
def filter_event(self, event: dict) -> dict:
    """Apply L2 PII filtering to an event dict."""
    filtered = dict(event)
```
**Description**: Both the parameter and return type use bare `dict` without type parameters. The rest of the codebase uses `dict[str, Any]` for event payloads consistently (e.g., `buffer/manager.py:151`).
**Risk**: Minor — inconsistency with coding standards.
**Recommendation**: Change to `def filter_event(self, event: dict[str, Any]) -> dict[str, Any]`.

---

### [MEDIUM] TYPE ANNOTATION: `to_dict()` return type is unparameterized `dict`
**File**: `agent/python/kmflow_agent/vce/record.py:33`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
def to_dict(self) -> dict:
    """Serialise to a dict suitable for JSON upload."""
    return {
        "timestamp": self.timestamp.isoformat(),
        ...
    }
```
**Description**: The return type `dict` lacks type parameters. Should be `dict[str, Any]` to be consistent with project standards and provide meaningful type information.
**Risk**: Minor — type checking and editor support are marginally reduced.
**Recommendation**: Change to `-> dict[str, Any]` and import `Any` from `typing`.

---

### [MEDIUM] TYPE ANNOTATION: `client_handler: Any` in abstract base and implementations
**Files**: `agent/python/kmflow_agent/platform/_base.py:37`, `_macos.py:36`, `_windows.py:48`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
async def create_ipc_server(
    self,
    client_handler: Any,
    shutdown_event: asyncio.Event,
) -> None:
```
**Description**: `client_handler` is typed as `Any` in the abstract interface and both implementations. The actual type is a coroutine callable with the signature `(asyncio.StreamReader, asyncio.StreamWriter) -> None`. This can be expressed precisely using `Callable`.
**Risk**: Low — `Any` is acceptable for complex callable types, but a precise `Callable` type would catch interface mismatches at type-check time.
**Recommendation**: Replace with:
```python
from collections.abc import Callable, Coroutine
ClientHandler = Callable[
    [asyncio.StreamReader, asyncio.StreamWriter],
    Coroutine[None, None, None]
]
```

---

### [MEDIUM] DEFENSIVE PROGRAMMING: `assert` used for null checks in production SQLite path
**File**: `agent/python/kmflow_agent/buffer/manager.py:158`, `:178`, `:200`, `:214`, `:225`, `:235`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
def _db_write_event(self, event: dict[str, Any]) -> str:
    """Synchronous DB write — called via asyncio.to_thread."""
    event_id = str(uuid.uuid4())
    payload = json.dumps(event).encode("utf-8")
    encrypted = encrypt_payload(payload, self._encryption_key)
    now = datetime.now(UTC).isoformat()

    assert self._conn is not None
    self._conn.execute(...)
```
**Description**: `assert` statements are disabled when Python runs with the `-O` (optimize) flag (`python -O`). In optimized mode, `assert self._conn is not None` is a no-op, and the subsequent `self._conn.execute()` will raise `AttributeError: 'NoneType' object has no attribute 'execute'` — a less informative error than a guarded check. This appears six times throughout the class.
**Risk**: If the agent is ever launched with `-O` optimization (which some deployment scripts do for performance), the safety guards are silently removed, leading to cryptic runtime errors instead of clear diagnostic messages.
**Recommendation**: Replace asserts with explicit runtime guards:
```python
if self._conn is None:
    raise RuntimeError("BufferManager: database connection is not open")
```

---

### [MEDIUM] NARROW EXCEPTION MISSING: `ipc/socket_server.py` broad catch in `_handle_client`
**File**: `agent/python/kmflow_agent/ipc/socket_server.py:123`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
except asyncio.CancelledError:
    pass
except Exception:
    logger.exception("Client handler error")
finally:
    writer.close()
    logger.info("Swift client disconnected")
```
**Description**: The client handler correctly separates `CancelledError` from the general `Exception` catch (good pattern). The broad `except Exception` is appropriate here since this is a network handler where any error should not crash the server. However, the handler swallows the error and continues — it should still close the writer cleanly, which it does in `finally`. This is borderline acceptable.
**Risk**: Low — the pattern is defensively appropriate for a socket handler. Logged via `logger.exception` which includes traceback.
**Recommendation**: Accept this pattern for the socket handler. Add a counter increment for monitoring error rates.

---

### [MEDIUM] UNUSED VARIABLE: `target` computed but not used in `get_credential` and `delete_credential`
**File**: `agent/python/kmflow_agent/platform/_windows.py:132` and `:145`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
def get_credential(self, key: str) -> str | None:
    target = f"{_CREDENTIAL_TARGET_PREFIX}{key}"
    try:
        # cmdkey /list doesn't expose passwords, so we use DPAPI file fallback
        # For a real implementation, use ctypes to call CredRead from advapi32.dll
        cred_file = self.get_data_dir() / "credentials" / f"{key}.dpapi"
```
And:
```python
def delete_credential(self, key: str) -> None:
    target = f"{_CREDENTIAL_TARGET_PREFIX}{key}"
    try:
        subprocess.run(
            ["cmdkey", f"/delete:{target}"],
```
**Description**: In `get_credential`, `target` is assigned but never used — the function falls back to the DPAPI file path entirely. In `delete_credential`, `target` IS used in the `cmdkey` subprocess call. The `get_credential` dead assignment is misleading — it suggests credential retrieval uses `cmdkey` when it does not.
**Risk**: Readability issue — misleads developers reading the code into thinking Windows Credential Manager is consulted for reads. The comment on line 134-135 explains why, but the unused variable still creates confusion.
**Recommendation**: Remove the `target` assignment from `get_credential` and add a comment explaining that reads go through the DPAPI file fallback.

---

## Low Issues (Informational)

### [LOW] DOCSTRING COVERAGE: Some public methods lack docstrings
**Files**: `agent/python/kmflow_agent/buffer/manager.py`, `agent/python/kmflow_agent/pii/l2_filter.py`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
# buffer/manager.py - public method without docstring:
async def prune_uploaded(self) -> int:
    """Delete uploaded events from the buffer. Returns count deleted."""
    return await asyncio.to_thread(self._db_prune_uploaded)
```
Most public methods do have docstrings (adequate coverage). Missing: `L2Filter.scrub`, `L2Filter.contains_pii` — these two are public methods exposed by the class but have no docstrings. Internal helpers are appropriately without docstrings.
**Risk**: Very low — no runtime impact.
**Recommendation**: Add one-line docstrings to `L2Filter.scrub` and `L2Filter.contains_pii`.

---

### [LOW] MAGIC NUMBER: Poll interval `0.5` used in three separate server loops
**Files**: `agent/python/kmflow_agent/ipc/socket_server.py:92`, `platform/_macos.py:57`, `platform/_windows.py:109`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
# socket_server.py
while not shutdown_event.is_set():
    await asyncio.sleep(0.5)

# _macos.py
while not shutdown_event.is_set():
    await asyncio.sleep(0.5)

# _windows.py
while not shutdown_event.is_set():
    await asyncio.sleep(0.5)
```
**Description**: The `0.5` second shutdown poll interval is hardcoded in three places. While consistent by coincidence, there is no named constant tying them together. A change to shutdown responsiveness would require modifying three files.
**Risk**: Very low — cosmetic.
**Recommendation**: Define `_SHUTDOWN_POLL_INTERVAL_SECONDS = 0.5` as a module-level constant (or in a shared `constants.py`) and reference it in all three locations.

---

### [LOW] INIT FILES: `__init__.py` files missing `__all__` exports
**Files**: `agent/python/kmflow_agent/buffer/__init__.py`, `agent/python/kmflow_agent/vce/__init__.py`, multiple subpackages
**Agent**: C2 (Python Code Quality Auditor)
**Description**: Only `agent/python/kmflow_agent/platform/__init__.py` defines `__all__`. Other subpackage `__init__.py` files are empty (1 line). For a library-style module, explicit `__all__` declarations clarify the public API and prevent accidental wildcard imports.
**Risk**: Very low — only affects `from module import *` usage which is not present in this codebase.
**Recommendation**: Low priority; consider adding `__all__` to `platform/__init__.py` equivalents in other subpackages when those modules stabilize.

---

### [LOW] BROAD EXCEPTION: `except Exception` in `platform/_windows.py:188` (key generation)
**File**: `agent/python/kmflow_agent/platform/_windows.py:188`
**Agent**: C2 (Python Code Quality Auditor)
**Evidence**:
```python
if key_file.exists():
    try:
        encrypted = key_file.read_bytes()
        decrypted = self._dpapi_unprotect(encrypted)
        if decrypted:
            return base64.b64decode(decrypted)[:32]
    except Exception:
        logger.warning("Failed to decrypt buffer key, generating new one")
```
**Description**: Catches all exceptions when decrypting the existing buffer key. If decryption fails for any reason (corrupted file, wrong DPAPI scope, etc.), a new key is silently generated, invalidating all previously encrypted buffer events. The `WARNING` log level is appropriate, but the exception type and original error message are lost.
**Risk**: Operational — a DPAPI scope change (e.g., user re-enrollment) would silently discard buffered events without explanation.
**Recommendation**: Log `exc_info=True` on the warning so the original exception is visible in logs.

---

## Acceptance Criteria Verification

| Criteria | Status | Details |
|----------|--------|---------|
| NO TODO COMMENTS | PASS | No TODO/FIXME/HACK markers found |
| NO PLACEHOLDERS | FAIL | VLMClassifier is an explicit stub in the live classification path |
| NO HARDCODED SECRETS | PASS | No credentials, API keys, or secrets in source |
| PROPER ERROR HANDLING | PARTIAL | 12 broad exception catches; 4 notable instances in critical paths |
| NO ANY TYPES | PARTIAL | 3 `Any` annotations (client_handler callbacks — partially justified) |
| TYPE HINTS | PARTIAL | 3 functions use unparameterized `dict`; `config: dict` missing parameter |

---

## Positive Highlights

1. **Universal `from __future__ import annotations`**: All 19 source files in `kmflow_agent/` include this — consistent and correct for Python 3.12+ compatibility.

2. **`asyncio.to_thread()` for SQLite**: Synchronous SQLite operations are correctly offloaded via `asyncio.to_thread()` in `BufferManager`, avoiding event loop blocking. The pattern is used consistently across all six DB methods.

3. **Keychain-first credential storage**: Both `auth.py` and `buffer/manager.py` implement a proper fallback chain: env var → Keychain → legacy file (with migration) → generate new. Security-conscious and well-structured.

4. **Explicit memory cleanup of image bytes**: In `ipc/socket_server.py:199-202`, image bytes are explicitly `del`'d and `gc.collect()` is called after OCR. The privacy-by-design pattern is clearly documented in the module docstring and implemented correctly.

5. **No bare `except:` clauses**: Zero instances of bare `except:` found. All exception handlers at minimum catch `Exception`, and most catch specific exception types.

6. **No f-strings in logging calls**: All logging uses `%s` lazy formatting throughout the codebase — correct practice that avoids unnecessary string evaluation when the log level is filtered.

7. **Proper shutdown signal handling**: `__main__.py` uses `loop.add_signal_handler()` for POSIX signals, which integrates cleanly with asyncio's event loop and avoids the race conditions of naive `signal.signal()` usage in async code.

8. **`StrEnum` for event types**: `DesktopEventType` in `ipc/protocol.py` correctly uses `StrEnum` per project coding standards.

9. **Test fixtures are well-structured**: `conftest.py` provides isolated `BufferManager` fixtures with temp paths and test encryption keys, preventing test-to-test contamination.

---

## File-by-File Summary

| File | Lines | Key Issues |
|------|-------|-----------|
| `buffer/manager.py` | 259 | 6x `assert` guards disabled by `-O`; `from typing import Any` used appropriately |
| `buffer/encryption.py` | 36 | Clean — no issues |
| `ipc/socket_server.py` | 244 | 1x broad exception in `_handle_client` (acceptable); proper memory cleanup |
| `ipc/protocol.py` | 57 | `Any` in `event_data` type — acceptable for IPC envelope |
| `platform/_base.py` | 84 | `client_handler: Any` — imprecise callable type |
| `platform/_macos.py` | 161 | Clean; mirrors auth.py keychain pattern (some duplication with auth.py) |
| `platform/_windows.py` | 265 | 4x broad exception catches; unused `target` variable in `get_credential` |
| `platform/__init__.py` | 41 | Well-structured; `__all__` defined; `lru_cache` for singleton |
| `auth.py` | 145 | Clean; keychain fallback chain is well-implemented |
| `config/manager.py` | 128 | Clean; `dict[str, Any]` used correctly throughout |
| `health/reporter.py` | 129 | Clean; `psutil` usage correct; specific `httpx.HTTPError` catch |
| `upload/batch_uploader.py` | 147 | 1x broad exception in upload loop (should narrow) |
| `pii/l2_filter.py` | 55 | DRY violation with `redactor.py`; bare `dict` annotations |
| `vce/classifier.py` | 190 | `VLMClassifier` stub in live path |
| `vce/ocr.py` | 135 | 4x broad exceptions (acceptable for optional dependency loading) |
| `vce/record.py` | 50 | `to_dict() -> dict` unparameterized |
| `vce/redactor.py` | 57 | DRY violation with `l2_filter.py` |
| `vce/trigger_engine.py` | 165 | `datetime.utcnow()` deprecated; `config: dict` unparameterized |
| `__main__.py` | 95 | Top-level broad exception (acceptable); `asyncio.gather()` single-point-of-failure risk |

---

## Priority Fix Order

1. **`trigger_engine.py:61`** — `datetime.utcnow()` → `datetime.now(UTC)` (trivial, prevents future TypeError)
2. **`pii/l2_filter.py` + `vce/redactor.py`** — Extract shared `BASE_PATTERNS`, eliminate DRY violation
3. **`vce/classifier.py:129`** — Remove or gate VLMClassifier with config flag
4. **`buffer/manager.py` asserts** — Replace 6x `assert` with proper runtime guards
5. **`upload/batch_uploader.py:52`** — Narrow `except Exception` to specific network errors
6. **`platform/_windows.py:140`** — Narrow credential read exception, add `exc_info=True`
7. **Bare `dict` annotations** — Parameterize 3 instances: `filter_event`, `to_dict`, `config: dict`
