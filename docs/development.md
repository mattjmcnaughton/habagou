# Development

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [just](https://just.systems/)
- [Docker](https://www.docker.com/) (optional: Compose database and production-like stack)
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
# Start Postgres through Compose
just compose-db-up

# Run migrations
uv run alembic upgrade head
```

## Running Locally

```sh
# Start Postgres and Keycloak through devenv, then start both dev servers
devenv up -d
just bootstrap
just dev

# Or start separately
just dev-be   # Backend at the port shown by just info
just dev-fe   # Frontend dev server
```

Run `just info` for this checkout's exact backend/frontend/Keycloak URLs.
Interactive docs are available at `/docs` on the backend URL.

Local auth uses the Keycloak realm rendered from
`docker/keycloak/habagou-realm.template.json` into
`.devenv/state/keycloak/habagou-realm.json`. `devenv shell` and `just
bootstrap` render this file. If Keycloak was started before the file existed,
restart the Keycloak service after entering the shell. The seeded local login is
`dev` / `dev`.

Auth-related env values are derived by `scripts/dev_env.py`: `SESSION_SECRET_KEY`,
`OIDC_PROVIDER=keycloak`, `OIDC_ISSUER`, `OIDC_CLIENT_ID`, and
`OIDC_CLIENT_SECRET`. `SESSION_SECRET_KEY` is required; the app fails fast when
it is unset.

## Using Auth0 or another OIDC provider

Set `OIDC_PROVIDER` to a display name such as `auth0`, set `OIDC_ISSUER` to the
provider's issuer URL, and provide that application's `OIDC_CLIENT_ID` and
`OIDC_CLIENT_SECRET`. The application discovers standard OIDC metadata from the
issuer and continues to identify users by the stable `iss` and `sub` claims.
Register Habagou's `/auth/callback` URL with the provider.

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

Frontend e2e tests drive the real Keycloak form. `just test-e2e-fe` fails fast
if the derived Keycloak issuer is not reachable; start devenv services first.

## Docker

```sh
# Build image
docker build -t habagou .

# Run container
docker run -p 8000:8000 habagou

# Or use the project wrapper
just compose-up
```

`just compose-up` renders the dev Keycloak realm and starts app, Postgres, and
Keycloak. `just compose-smoke` verifies health, the SPA shell, the anonymous
session probe, and that data APIs return 401 without a session.

Release images are published by GitHub Actions after successful CI on `main`
when semantic-release creates a new release. The workflow pushes
`ghcr.io/mattjmcnaughton/habagou` with full semver, major/minor, and `latest`
tags, and (in parallel) deploys to Fly.io via `flyctl deploy --remote-only`
so Fly builds from the release tag. See [deploy.md](deploy.md) for
production cutover, secrets, DNS/certs, and how CD works.
