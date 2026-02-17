.PHONY: help install dev up down logs health test lint migrate setup-neo4j clean

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup ────────────────────────────────────────────────────────

install: ## Install backend dependencies
	pip install -e ".[dev]"

dev: ## Install all dependencies (backend + frontend)
	pip install -e ".[dev]"
	cd frontend && npm install

# ── Docker ───────────────────────────────────────────────────────

up: ## Start all services with Docker Compose
	docker compose up -d

down: ## Stop all services
	docker compose down

logs: ## Tail logs for all services
	docker compose logs -f

health: ## Check health of all services
	@echo "Backend health:"
	@curl -s http://localhost:8000/health | python -m json.tool 2>/dev/null || echo "Backend not reachable"
	@echo ""

# ── Database ─────────────────────────────────────────────────────

migrate: ## Run Alembic migrations
	alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create MSG="description")
	alembic revision --autogenerate -m "$(MSG)"

setup-neo4j: ## Initialize Neo4j constraints and indexes
	python -m scripts.setup_neo4j

db-services: ## Start only database services (postgres, neo4j, redis)
	docker compose up -d postgres neo4j redis

# ── Development ──────────────────────────────────────────────────

backend: ## Run FastAPI backend (development mode)
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

frontend: ## Run Next.js frontend (development mode)
	cd frontend && npm run dev

# ── Testing ──────────────────────────────────────────────────────

test: ## Run all backend tests
	pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage report
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing

test-frontend: ## Run frontend tests
	cd frontend && npm test

# ── Linting ──────────────────────────────────────────────────────

lint: ## Run linting (ruff)
	ruff check src/ tests/

lint-fix: ## Fix linting issues automatically
	ruff check --fix src/ tests/

format: ## Format code (ruff)
	ruff format src/ tests/

typecheck: ## Run type checking (mypy)
	mypy src/

# ── Cleanup ──────────────────────────────────────────────────────

clean: ## Remove build artifacts and caches
	rm -rf __pycache__ .pytest_cache .mypy_cache htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
