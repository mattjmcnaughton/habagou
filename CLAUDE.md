# CLAUDE.md

Learn to write Chinese characters by tracing them, stroke by stroke.

Python web application using FastAPI, uvicorn, OpenTelemetry, uv, ruff, ty, and pytest. Frontend lives in `src/habagou/web/frontend/`.

## Quick Reference

| Command | Purpose |
| ------- | ------- |
| `just fmt` | Check formatting (backend + frontend) |
| `just fmt-fix` | Fix formatting (backend + frontend) |
| `just lint` | Check linting (backend + frontend) |
| `just lint-fix` | Fix linting (backend + frontend) |
| `just typecheck` | Run type checker (backend + frontend) |
| `just test-unit` | Run unit tests (backend + frontend) |
| `just test-integration` | Run integration tests |
| `just test-e2e` | Run e2e tests |
| `just test-all` | Run all tests |
| `just test-external` | Run tests hitting external services |
| `just gate` | Fast pre-push check (fmt + lint + typecheck + test-unit) |
| `just gate-expensive` | Full check (gate + integration + e2e) |
| `just gate-external` | Everything (gate-expensive + external) |
| `just dev` | Start backend and frontend dev servers |
| `just dev-be` | Start backend dev server only |
| `just dev-fe` | Start frontend dev server only |

All formatting, linting, typecheck, test-unit, and gate targets have `-be` and `-fe` variants (e.g. `just fmt-be`, `just fmt-fe`).

## Project Structure

```
src/habagou/
  app.py                    # FastAPI app factory
  config.py                 # Pydantic-settings based config
  logging.py                # structlog setup
  telemetry.py              # OpenTelemetry setup
  routers/                  # HTTP endpoint definitions
    health.py               # /healthz, /readyz
  services/                 # Business logic
  dtos/                     # Pydantic request/response models
  web/                      # Frontend integration
    serve.py                # Static file serving for production
    frontend/               # Frontend application (scaffolded separately)
  db.py                     # Async engine/session setup
  models/                   # SQLAlchemy models (one module per bounded context)
  repositories/             # Data access layer (one module per bounded context)
tests/
  unit/                     # Unit tests
  integration/              # Integration tests
  e2e/                      # End-to-end tests
```

## Local Development: prefer what is already installed

**Do not install Nix just to work on Habagou.** Prefer the toolchain and
services already available on the machine (or in the agent environment).

Pick the first path that fits:

1. **Host tools you already have** (`uv`, `just`, Node 22, `pnpm`) plus
   Postgres/Keycloak you already run, **or** Docker Compose for those
   services (`just compose-db-up`, and Compose Keycloak when you need auth).
   Then `just bootstrap` → `just dev`. See `docs/development.md`.
2. **devenv** — only if Nix/devenv is *already* present (including cloud-agent
   / `Dockerfile.dev` environments that ship it). Never add a host Nix install
   solely for this repo. Loop: `devenv up -d` → `devenv shell` →
   `just bootstrap` → `just dev`.
3. **Full Compose** (`just compose-up` / `just compose-smoke`) — production-image
   smoke only (and the CI `compose-smoke` job), not the default day-to-day app
   loop.

Same justfile targets work in every mode; the app only reads env such as
`DATABASE_URL`. Details: `docs/devex.md`, `docs/development.md`.

## Key Conventions

- Source code lives in `src/habagou/` (src layout).
- **Layering:** routers -> services -> repositories.
- **DTOs** are Pydantic models for API I/O, always separate from DB models.
- **Frontend** is scaffolded separately into `src/habagou/web/frontend/` using the `frontend-react` template.
- Tests are organized by type in `tests/unit/`, `tests/integration/`, `tests/e2e/`.
- Use `@pytest.mark.external` for tests that hit external services.
- All config is in `pyproject.toml` — no separate config files.
- Backend: `just dev-be`. Frontend: `just dev-fe`. Both: `just dev`.

## More Information

- `docs/architecture.md` — read before adding new modules or changing project structure
- `docs/development.md` — read for environment setup, debugging, or common tasks
- `docs/devex.md` — local modes (host tools, Compose services, optional devenv)
- `docs/api.md` — API endpoint reference
