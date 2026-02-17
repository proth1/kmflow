# KMFlow

AI-powered Process Intelligence platform that transforms diverse consulting evidence into confidence-scored process views, automated TOM alignment, and evidence-backed gap analysis.

## Architecture

```
Frontend (Next.js 14+, Port 3000)
  -> API Gateway (FastAPI, Port 8000)
    -> Processing Services
      -> Data Layer (PostgreSQL+pgvector, Neo4j, Redis)
```

**Tech Stack**: Python 3.12+, FastAPI, Next.js 14+ (React 18), Neo4j 5.x, PostgreSQL 15 (pgvector), Redis 7

See [docs/architecture.md](docs/architecture.md) for detailed architecture diagrams.

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose

### Infrastructure

```bash
docker compose up -d postgres neo4j redis
```

### Backend

```bash
pip install -e ".[dev]"
uvicorn src.api.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend && npm install && npm run dev
```

### Run Tests

```bash
# Backend
pytest tests/ --cov --cov-report=term-missing

# Frontend
cd frontend && npm test

# E2E
cd frontend && npm run test:e2e
```

## API

Base URL: `http://localhost:8000`

| Group | Prefix | Description |
|-------|--------|-------------|
| Health | `/health` | Service health check |
| Auth | `/api/v1/auth` | JWT authentication |
| Engagements | `/api/v1/engagements` | Engagement CRUD |
| Evidence | `/api/v1/evidence` | Evidence ingestion |
| POV | `/api/v1/pov` | Process point-of-view generation |
| TOM | `/api/v1/tom` | Target Operating Model alignment |
| Conformance | `/api/v1/conformance` | BPMN conformance checking |
| Copilot | `/api/v1/copilot` | RAG-powered evidence Q&A |
| Dashboard | `/api/v1/dashboard` | Engagement dashboards |
| Monitoring | `/api/v1/monitoring` | Continuous monitoring |
| Admin | `/api/v1/admin` | Platform administration |

Interactive docs: `http://localhost:8000/docs` | ReDoc: `http://localhost:8000/redoc`

## Project Structure

```
src/
  api/           # FastAPI routes and middleware
  core/          # Models, auth, config, encryption
  evidence/      # Evidence ingestion and processing
  semantic/      # Knowledge graph engine
  pov/           # LCD algorithm and POV generator
  tom/           # TOM alignment and gap analysis
  rag/           # RAG copilot (hybrid retrieval)
  conformance/   # BPMN conformance checking
  mcp/           # Model Context Protocol server
  monitoring/    # Continuous monitoring workers
frontend/
  src/app/       # Next.js pages
  e2e/           # Playwright E2E tests
docs/
  prd/           # Product requirements
  presentations/ # Stakeholder presentations
```

## Development

```bash
# Lint
ruff check src/ tests/
ruff format src/ tests/

# Type check
mypy src/ --ignore-missing-imports

# Pre-commit hooks
pre-commit install
```

## Docker (Production)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## License

Proprietary. All rights reserved.
