# Audit Lessons Learned

Structured record of recurring audit findings, their root causes, and the guardrails added to prevent recurrence. Referenced by the `code-audit` command agents.

## Finding Categories

### 1. Missing `response_model` on Route Decorators

| Field | Value |
|-------|-------|
| **Category** | API Compliance (B3) |
| **Root Cause** | No enforcement — routes were added without response_model and passed review |
| **Recurrence** | 84 endpoints across 5 audit cycles |
| **Guardrail Added** | `.claude/rules/fastapi-routes.md` — mandatory response_model rule |
| **Date** | 2026-03-20 |

### 2. Broad `except Exception` Without Justification

| Field | Value |
|-------|-------|
| **Category** | Python Quality (C1) |
| **Root Cause** | Defensive coding habit — catch-all used instead of specific exception types |
| **Recurrence** | 38 instances across 3 audit cycles |
| **Guardrail Added** | `.claude/rules/error-handling.md` — specific exception types required |
| **Date** | 2026-03-20 |

### 3. `: Any` Type Annotations

| Field | Value |
|-------|-------|
| **Category** | Python Quality (C1) |
| **Root Cause** | Convenience during rapid prototyping — concrete types deferred and never revisited |
| **Recurrence** | 148 instances across 3 audit cycles |
| **Guardrail Added** | `.claude/rules/type-safety.md` — justification comment required for `: Any` |
| **Date** | 2026-03-20 |

### 4. Missing Engagement Access Checks (IDOR)

| Field | Value |
|-------|-------|
| **Category** | Authorization (A1) |
| **Root Cause** | New routes added without following the multi-tenant access pattern |
| **Recurrence** | 12 instances across 4 audit cycles |
| **Guardrail Added** | `.claude/rules/engagement-access.md` — canonical pattern with checklist |
| **Date** | 2026-03-20 |

### 5. Unbounded Database Queries

| Field | Value |
|-------|-------|
| **Category** | Performance (C3) / Data Integrity (B2) |
| **Root Cause** | List endpoints added without pagination or with inconsistent limits |
| **Recurrence** | 15 instances across 2 audit cycles |
| **Guardrail Added** | `.claude/rules/fastapi-routes.md` — mandatory `le=1000` pagination ceiling |
| **Date** | 2026-03-20 |

### 6. Bare `MagicMock()` Without `spec=`

| Field | Value |
|-------|-------|
| **Category** | Test Quality (D1) |
| **Root Cause** | Quick test setup without enforcing type safety on mocks |
| **Recurrence** | 27 instances across 2 audit cycles |
| **Guardrail Added** | `.claude/rules/type-safety.md` — `spec=ConcreteClass` required |
| **Date** | 2026-03-20 |

### 7. `asyncio.sleep()` in Test Assertions

| Field | Value |
|-------|-------|
| **Category** | Test Quality (D1) |
| **Root Cause** | Timing-based synchronization instead of event-based |
| **Recurrence** | 27 instances in 1 audit cycle |
| **Guardrail Added** | `.claude/rules/type-safety.md` — event-based synchronization required |
| **Date** | 2026-03-20 |

### 8. Stubs Returning Fake Success

| Field | Value |
|-------|-------|
| **Category** | Python Quality (C1) |
| **Root Cause** | Placeholder implementations that return `{"status": "success"}` instead of raising |
| **Recurrence** | 8 instances across 2 audit cycles |
| **Guardrail Added** | `.claude/rules/error-handling.md` — stubs must raise `NotImplementedError` |
| **Date** | 2026-03-20 |

### 9. In-Memory Fallbacks in Production

| Field | Value |
|-------|-------|
| **Category** | Security (A2) |
| **Root Cause** | `or "memory://"` fallback on rate limiter bypasses Redis in production |
| **Recurrence** | 1 CRITICAL finding, 2 audit cycles |
| **Guardrail Added** | Batch 1 fix — fail loudly if Redis unavailable in production |
| **Date** | 2026-03-20 |

### 10. Missing CSRF on Cookie-Auth Mutations

| Field | Value |
|-------|-------|
| **Category** | Security (A1) |
| **Root Cause** | Cookie auth added (Issue #156) without corresponding CSRF middleware |
| **Recurrence** | 1 HIGH finding, first occurrence |
| **Guardrail Added** | CSRF middleware + `.claude/rules/engagement-access.md` CSRF checklist item |
| **Date** | 2026-03-20 |
