# Type Safety Standards (MANDATORY)

## Prohibit Bare `: Any`

`: Any` is PROHIBITED without an explicit justification comment:

```python
# WRONG
def process(data: Any) -> Any:
    ...

# CORRECT - concrete type
def process(data: dict[str, str]) -> ProcessResult:
    ...

# CORRECT - justified (rare)
def process(data: Any) -> Any:  # type: Any because: receives arbitrary JSON from external API
    ...
```

## Mock Specifications

All mocks in tests MUST use `spec=ConcreteClass`:

```python
# WRONG - untyped mock allows any attribute access
mock_user = MagicMock()

# CORRECT - type-safe mock
mock_user = MagicMock(spec=User)
```

This catches attribute typos at test time rather than silently passing.

## Named Constants for Sleep/Timeout Values

Never use bare numbers in `asyncio.sleep()` or timeout parameters:

```python
# WRONG
await asyncio.sleep(5)

# CORRECT
RETRY_DELAY_SECONDS = 5
await asyncio.sleep(RETRY_DELAY_SECONDS)
```

## Test Assertions

Never use `asyncio.sleep(N)` as a test synchronization mechanism:

```python
# WRONG - flaky, timing-dependent
await some_async_operation()
await asyncio.sleep(2)
assert result.done

# CORRECT - event-based synchronization
await wait_for_condition(lambda: result.done, timeout=5.0)
```

## Route Handler Return Types

Route handlers MUST NOT use `-> Any`. Use the declared response model type or `dict[str, Any]`:

```python
# WRONG
async def get_items(...) -> Any:

# CORRECT
async def get_items(...) -> dict[str, Any]:
```
