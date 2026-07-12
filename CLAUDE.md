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
  models.py                 # SQLAlchemy models
  repositories.py           # Data access layer
tests/
  unit/                     # Unit tests
  integration/              # Integration tests
  e2e/                      # End-to-end tests
```

## Local Development: devenv vs Docker Compose

- **Default = devenv.** Day-to-day work, bootstrap, `just dev`, and local e2e
  (`just test-e2e` / `just e2e` without `BASE_URL`) use devenv for Postgres +
  Keycloak. Typical loop: `devenv up -d` → `devenv shell` → `just bootstrap` →
  `just dev`. See `docs/devex.md` and `docs/development.md`.
- **Docker Compose is not the daily loop.** Use it only for production-image
  smoke: `just compose-up` / `just compose-smoke` (and the CI `compose-smoke`
  job). That path builds the real app image with Compose Postgres + Keycloak.
- Do **not** start Compose for ordinary development or default local e2e.
  Optional escape hatches (`just compose-db-up`, pointing `just e2e BASE_URL=…`
  at a Compose stack) exist, but devenv is the supported default.
- Agents without host Nix: `just dev-shell-docker` (still devenv inside
  `Dockerfile.dev`), not Compose.

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
- `docs/devex.md` — devenv primary loop vs Compose smoke role
- `docs/api.md` — API endpoint reference
