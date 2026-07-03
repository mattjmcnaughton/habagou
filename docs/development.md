# Development

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [just](https://just.systems/)
- [Docker](https://www.docker.com/) (for dependencies)
- [Node.js](https://nodejs.org/) 20+ and [pnpm](https://pnpm.io/) (for frontend)

## Setup

```sh
# Install backend dependencies
uv sync --dev

# Copy environment file
cp .env.example .env

# Install frontend dependencies (after scaffolding)
cd src/habagou/web/frontend && pnpm install
```

## Frontend Scaffolding

The frontend is scaffolded separately using the `frontend-react` Copier template:

```sh
copier copy --trust path/to/templates/frontend-react src/habagou/web/frontend
```

## Database

```sh
# Start Postgres
docker compose up -d

# Run migrations
uv run alembic upgrade head
```

## Running Locally

```sh
# Start both dev servers
just dev

# Or start separately
just dev-be   # Backend at http://localhost:8000
just dev-fe   # Frontend dev server
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## Common Tasks

```sh
# Format and lint (backend + frontend)
just fmt-fix
just lint-fix

# Backend only
just fmt-fix-be
just lint-fix-be

# Frontend only
just fmt-fix-fe
just lint-fix-fe

# Type check
just typecheck

# Run tests
just test-unit
just test-all

# Full pre-push check
just gate

# Full check including integration and e2e
just gate-expensive
```

## Testing

Tests are organized by type:

- `tests/unit/` — fast, isolated tests
- `tests/integration/` — tests with real dependencies
- `tests/e2e/` — end-to-end tests

Use `@pytest.mark.external` for tests that hit external services. These run via `just test-external`.

## Docker

```sh
# Build image
docker build -t habagou .

# Run container
docker run -p 8000:8000 habagou
```
