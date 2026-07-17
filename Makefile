.DEFAULT_GOAL := help

VENV ?= .venv
PYTHON_BOOTSTRAP ?= python3.11
PYTHON ?= $(VENV)/bin/python
PIP ?= $(PYTHON) -m pip
PNPM ?= pnpm
PROOFSTACK ?= $(VENV)/bin/proofstack
DEMO_OUTPUT ?= .proofstack/demo-evidence-$(shell date -u +%Y%m%d-%H%M%S)
PROOFSTACK_ENV ?= development

.PHONY: help bootstrap install dev dev-api dev-worker dev-web lint format format-check \
	typecheck test test-python test-web test-integration test-security e2e build smoke \
	acceptance clean clean-check db-upgrade db-downgrade db-reset demo doctor

help: ## Show available project commands.
	@awk 'BEGIN {FS = ":.*## "; printf "ProofStack development commands\n\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

$(VENV)/bin/python:
	$(PYTHON_BOOTSTRAP) -m venv $(VENV)

bootstrap: $(VENV)/bin/python ## Create the local environment and install all dependencies.
	$(PYTHON) -m ensurepip --upgrade
	$(PIP) install --upgrade pip
	$(PIP) install --editable '.[dev]'
	@if ! command -v $(PNPM) >/dev/null 2>&1; then corepack enable; fi
	$(PNPM) install --frozen-lockfile

install: bootstrap ## Install Python and frontend workspaces for development.

dev: ## Start the lightweight API and web development servers.
	$(MAKE) --jobs=2 dev-api dev-web

dev-api: ## Start FastAPI with reload on port 8000.
	PROOFSTACK_ENV=development PROOFSTACK_TASK_BACKEND=inline $(PYTHON) -m uvicorn proofstack_api.main:app --host 127.0.0.1 --port 8000 --reload

dev-worker: ## Start the Redis Queue worker for rq task mode.
	PROOFSTACK_TASK_BACKEND=rq $(PROOFSTACK)-worker

dev-web: ## Start Vite on port 5173.
	$(PNPM) dev

lint: ## Run Python and frontend lint checks.
	$(PYTHON) -m ruff check .
	$(PNPM) lint

format: ## Format Python and frontend source.
	$(PYTHON) -m ruff format .
	$(PNPM) format

format-check: ## Check formatting without changing files.
	$(PYTHON) -m ruff format --check .
	$(PNPM) format:check

typecheck: ## Run strict Python and TypeScript checks.
	$(PYTHON) -m mypy apps packages scripts
	$(PNPM) typecheck

test: test-python test-web ## Run all non-browser automated tests.

test-python: ## Run all Python tests with branch coverage.
	$(PYTHON) -m pytest --cov --cov-report=term-missing --cov-report=xml

test-web: ## Run frontend component tests.
	$(PNPM) test

test-integration: ## Run backend integration and contract tests.
	$(PYTHON) -m pytest tests/integration tests/contract

test-security: ## Run security boundary tests.
	$(PYTHON) -m pytest tests/security

e2e: ## Run the three offline Playwright workflows.
	$(PNPM) e2e

build: ## Build a Python wheel and the production web application.
	$(PIP) wheel --no-deps --no-build-isolation --wheel-dir build .
	$(PNPM) build

smoke: ## Exercise the live API, Demo pipeline, CLI, and Evidence download.
	scripts/smoke_test.sh

acceptance: ## Run the ordered full local acceptance gate and final cleanup.
	scripts/acceptance.sh

clean: ## Remove generated environments, caches, databases, reports, and build output.
	scripts/clean.sh

clean-check: ## Fail if generated repository artifacts remain.
	python3 scripts/clean_check.py

db-upgrade: ## Apply all Alembic migrations.
	$(PYTHON) -m alembic upgrade head

db-downgrade: ## Revert one Alembic revision.
	$(PYTHON) -m alembic downgrade -1

db-reset: ## Delete only the local development SQLite database and recreate the schema.
	@test "$(PROOFSTACK_ENV)" = "development" || (echo "db-reset requires PROOFSTACK_ENV=development" >&2; exit 2)
	@test "$(CONFIRM)" = "YES" || (echo "Run make db-reset CONFIRM=YES to confirm local data deletion" >&2; exit 2)
	$(PYTHON) -c 'from pathlib import Path; path = Path("proofstack.db").resolve(); expected = (Path.cwd() / "proofstack.db").resolve(); assert path == expected; path.unlink(missing_ok=True)'
	$(MAKE) db-upgrade

demo: ## Analyze the checked-in Demo and write a fresh Evidence Bundle.
	PROOFSTACK_DEMO_MODE=true $(PROOFSTACK) demo --output $(DEMO_OUTPUT)

doctor: ## Inspect optional and required local tools without changing the machine.
	$(PROOFSTACK) doctor
