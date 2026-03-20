# Engagement Access Control Pattern (MANDATORY)

KMFlow is multi-tenant. Every endpoint that accesses engagement-scoped data MUST verify the current user is a member of the engagement.

## Two Patterns

### 1. Path Parameter Pattern — `require_engagement_access`

Use when `engagement_id` is in the URL path:

```python
from src.api.deps import require_engagement_access

@router.get("/engagements/{engagement_id}/items", response_model=list[ItemResponse])
async def list_items(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    _access: None = Depends(require_engagement_access),  # Validates membership
) -> dict[str, Any]:
    ...
```

### 2. Entity Fetch Pattern — `verify_engagement_member`

Use when `engagement_id` comes from the fetched entity (not the URL):

```python
from src.core.auth import verify_engagement_member

@router.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    item = await _get_item_or_404(session, item_id)
    # MUST verify AFTER fetch — the engagement_id comes from the entity
    await verify_engagement_member(session, current_user, item.engagement_id)
    return item
```

## Checklist for New Routes

Before merging any new route:

- [ ] Does the route access engagement-scoped data?
- [ ] If yes, is engagement membership verified?
- [ ] Is verification done AFTER entity fetch (not before)?
- [ ] For DELETE/PUT/PATCH: is the user's role sufficient? (not just membership)
- [ ] For cookie-auth mutation endpoints: is CSRF middleware active?

## Common Mistakes

1. **Checking membership before fetch**: The entity might belong to a different engagement than the URL suggests. Always fetch first, then verify.

2. **Missing check on nested resources**: If fetching a sub-resource (e.g., evidence attachment), verify the parent resource's engagement membership.

3. **Admin bypass without audit**: Platform admins can access any engagement, but the access MUST be logged via the audit middleware.

## Never Skip Access Checks

Even if a route "only reads public data," if the data is scoped to an engagement, enforce the check. Data classification can change, and the check is cheap.
