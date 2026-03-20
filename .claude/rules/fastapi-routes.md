# FastAPI Route Development Guardrails (MANDATORY)

Every route in `src/api/routes/` MUST follow these rules. Violations will be flagged by the code audit agent.

## Response Model

Every route decorator MUST declare `response_model=`:
```python
# CORRECT
@router.get("/items/{item_id}", response_model=ItemResponse)

# WRONG - missing response_model
@router.get("/items/{item_id}")
```

## Status Codes

Every POST endpoint MUST declare an explicit `status_code`:
- `201` — resource created (e.g., POST that creates a new entity)
- `200` — action performed (e.g., POST that triggers a workflow)
- `202` — accepted for async processing (e.g., POST that queues a job)

```python
@router.post("/items", response_model=ItemResponse, status_code=201)
```

## Engagement Access Control

Every ID-based lookup MUST verify engagement membership AFTER fetching the entity:
```python
@router.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    item = await _get_item_or_404(session, item_id)
    await verify_engagement_member(session, current_user, item.engagement_id)
    return item
```

Use `require_engagement_access` (path param dependency) for routes where `engagement_id` is in the URL path. Use `verify_engagement_member` (manual call) for routes where `engagement_id` comes from the fetched entity.

## Pagination

All list endpoints MUST use `limit` with `le=1000` and `offset`:
```python
@router.get("/items", response_model=list[ItemResponse])
async def list_items(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    ...
```

Never return unbounded query results. Every `select()` MUST have `.limit()`.

## File Size

Route files MUST NOT exceed 500 lines. When approaching this limit, split into sub-packages:
```
src/api/routes/evidence/
    __init__.py       # re-exports router
    upload.py         # upload-related endpoints
    search.py         # search/list endpoints
    management.py     # CRUD operations
```

## Handler Size

Route handlers MUST NOT exceed 20 lines of logic. Delegate to service layer:
```python
# CORRECT - thin handler
@router.post("/items", response_model=ItemResponse, status_code=201)
async def create_item(payload: CreateItemRequest, ...) -> dict[str, Any]:
    return await item_service.create(session, payload, current_user)

# WRONG - fat handler with inline business logic
@router.post("/items")
async def create_item(payload: CreateItemRequest, ...) -> Any:
    # 50 lines of validation, DB queries, side effects...
```

## CSRF

All mutation endpoints (POST/PUT/PATCH/DELETE) that accept cookie authentication MUST be protected by the CSRF middleware. The middleware is registered globally — do not bypass it.
