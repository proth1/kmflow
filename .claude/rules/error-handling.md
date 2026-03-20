# Error Handling Standards (MANDATORY)

## Broad Exception Catches

`except Exception` is PROHIBITED without an explicit justification comment:

```python
# WRONG
except Exception:
    logger.error("Something failed")

# CORRECT - specific exception
except Neo4jError as exc:
    logger.error("Neo4j write failed: %s", exc, exc_info=True)

# CORRECT - justified broad catch (rare, top-level boundaries only)
except Exception:  # Intentionally broad: top-level error boundary for worker loop
    logger.exception("Unhandled error in worker iteration")
```

## Specific Exception Types

Use the most specific exception type available:

| Library | Exception | Import |
|---------|-----------|--------|
| Neo4j | `Neo4jError` | `from neo4j.exceptions import Neo4jError` |
| SQLAlchemy | `SQLAlchemyError` | `from sqlalchemy.exc import SQLAlchemyError` |
| httpx | `HTTPError` | `from httpx import HTTPError` |
| JSON | `JSONDecodeError` | `import json` (or `from json import JSONDecodeError`) |
| Pydantic | `ValidationError` | `from pydantic import ValidationError` |
| Redis | `RedisError` | `from redis.exceptions import RedisError` |
| I/O | `OSError` | built-in |

## Logging in Exception Handlers

All exception handlers MUST log the error:
- `logger.exception("message")` — for unexpected errors (includes traceback)
- `logger.warning("message", exc_info=True)` — for expected/recoverable errors
- `logger.error("message: %s", exc)` — for errors where traceback is noise

Never silently swallow exceptions:
```python
# WRONG
except SomeError:
    pass

# CORRECT
except SomeError:
    logger.debug("Expected error during optional operation, continuing")
```

## Stubs and Not-Implemented Features

Stubs MUST raise `NotImplementedError` — never return fake success data:

```python
# WRONG
async def export_to_pdf(engagement_id: UUID) -> dict:
    return {"status": "success", "url": ""}  # Stub

# CORRECT
async def export_to_pdf(engagement_id: UUID) -> dict:
    raise NotImplementedError("PDF export not yet implemented (KMFLOW-XXX)")
```
