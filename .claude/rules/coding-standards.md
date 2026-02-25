# KMFlow Coding Standards

## Python (Backend)

### General
- Python 3.12+ with `from __future__ import annotations`
- Type hints on all function signatures (params and return)
- Use `Mapped[T]` and `mapped_column()` for SQLAlchemy models (2.x style)
- Use `StrEnum` for enum types (not plain `str` enums)
- No `# type: ignore` without an explanatory comment
- Prefer `pathlib.Path` over `os.path`

### FastAPI
- Thin route handlers: business logic belongs in service modules
- Use `Depends()` for dependency injection (db sessions, auth, settings)
- Pydantic models for all request/response schemas (in `src/api/schemas/`)
- Return `dict[str, Any]` from routes, not raw model instances
- Error responses: `HTTPException(status_code=N, detail="message")`
- Pagination: `?limit=N&offset=M` pattern with `PaginatedResponse` wrapper

### SQLAlchemy
- UUID primary keys with `default=uuid.uuid4`
- `DateTime(timezone=True)` for all timestamps
- `server_default=func.now()` for `created_at` columns
- Foreign keys with `ondelete="CASCADE"` or `"SET NULL"` (explicit)
- Index names: `ix_{tablename}_{column}`
- Relationships use string references: `relationship("ModelName")`

### Testing
- pytest with `pytest-asyncio` for async tests
- `@pytest.mark.asyncio` on all async test methods
- Mock database sessions via `conftest.py` fixtures
- Test files mirror source structure: `tests/{module}/test_{file}.py`
- Minimum 80% code coverage
- Use `MagicMock(spec=ModelClass)` for type-safe mocks

### Formatting & Linting
- `ruff` for linting and formatting (replaces black + isort + flake8)
- `mypy` for type checking with `--ignore-missing-imports`
- Line length: 120 characters (ruff default)
- Import order: stdlib → third-party → local (ruff handles this)

### Naming Conventions
- `snake_case` for functions, methods, variables, modules
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- Prefix private methods/attributes with `_`
- Prefix test classes with `Test`, test methods with `test_`

## TypeScript/React (Frontend)

### General
- TypeScript strict mode
- Explicit types on function parameters and returns
- No `any` — use `unknown` and narrow, or define proper interfaces
- Prefer `interface` over `type` for object shapes

### Next.js / React
- Functional components only (no class components)
- `use client` directive only when needed (prefer server components)
- Custom hooks for shared stateful logic
- SWR or React Query for data fetching
- Component files: `PascalCase.tsx`

### Testing
- Jest for unit tests
- Playwright for E2E tests
- Test files: `__tests__/{Component}.test.tsx` or `{Component}.test.tsx`

## Git Conventions
- Branch format: `feature/{issue}-{description}` (e.g., `feature/123-add-auth`)
- Commit messages: imperative mood, reference issue number
- PR title: <70 characters, descriptive
- PR body: `Closes #{issue}` + summary + test plan
- Squash merge to main (clean history)
- Never force push to main
