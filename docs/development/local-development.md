# Local development

## Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer
- pnpm 9 or newer; the workspace records pnpm 10.18.3
- SQLite, included with Python

Docker, Redis, PostgreSQL, Semgrep, a GitHub token, and an LLM key are optional for local
development.

```bash
cp .env.example .env
make bootstrap
make db-upgrade
make dev
```

The lightweight profile runs the API at `http://localhost:8000`, Vite at
`http://localhost:5173`, SQLite at `./proofstack.db`, and tasks inline. Open
`http://localhost:5173`, choose Demo login, create a project, and start Demo analysis.

Run individual processes when debugging:

```bash
make dev-api
make dev-web
make dev-worker
```

The worker command requires `PROOFSTACK_TASK_BACKEND=redis` and a reachable Redis service.
Do not run both inline and queued execution for the same development test.

## Database changes

Edit SQLAlchemy models, create and review an Alembic revision, then test upgrade and
downgrade. Apply migrations with `make db-upgrade`; step back one revision with
`make db-downgrade`. `make db-reset` is gated by both development mode and an explicit
confirmation because it removes the local SQLite database.

## Configuration

Settings are loaded from `PROOFSTACK_*` environment variables and `.env`. Production rejects
the development secret. Keep API, database, GitHub, and LLM credentials out of terminal
history, source files, test snapshots, and frontend variables. Only `VITE_API_BASE_URL` is
intended for the browser build.

Before handing off a change, run `make format`, `make lint`, `make typecheck`, and the focused
tests. `make acceptance` runs the complete local gate and ends with cleanup.
