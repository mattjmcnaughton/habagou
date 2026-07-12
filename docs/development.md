# Development

## Prefer what is already installed

**Do not install Nix just to work on Habagou.** Use the first option that
matches what you already have:

1. Host `uv` / `just` / Node 22 / `pnpm`, plus Postgres (and Keycloak when you
   need auth) — either already running, or via Docker Compose.
2. devenv — only if Nix/devenv is already on the machine (or provided by the
   cloud-agent / `Dockerfile.dev` environment).
3. Full Compose (`just compose-up` / `just compose-smoke`) — production-image
   smoke, not the everyday app loop.

## Prerequisites

Pick the set that matches your path:

- **Host toolchain path:** Python 3.12+, [uv](https://docs.astral.sh/uv/),
  [just](https://just.systems/), Node 22 + [pnpm](https://pnpm.io/), and either
  your own Postgres 16 (+ Keycloak for auth) or [Docker](https://www.docker.com/)
  for Compose-managed services
- **devenv path (optional):** Nix + [devenv](https://devenv.sh/) already
  installed — do not add them solely for this repo
- **Prod-image smoke:** Docker (for `just compose-smoke` / `just compose-up`)

## Setup without Nix (preferred when Nix is not already present)

```sh
# Toolchain
uv sync
cd src/habagou/web/frontend && pnpm install --frozen-lockfile && cd -

# Backing services via Compose (if you do not already have Postgres/Keycloak)
uv run python scripts/dev_env.py render-keycloak-realm
just compose-db-up
docker compose up -d keycloak
export DATABASE_URL=postgresql+asyncpg://habagou:habagou@localhost:5432/habagou
# Point OIDC at Compose Keycloak on the published host port (18080 by default):
export OIDC_PROVIDER=keycloak
export OIDC_ISSUER=http://127.0.0.1:18080/realms/habagou
export OIDC_CLIENT_ID=habagou
export OIDC_CLIENT_SECRET=habagou-dev-secret
export SESSION_SECRET_KEY=habagou-dev-session-secret

just bootstrap
just info
just dev
```

If you already have Postgres (and Keycloak when needed), skip Compose and set
`DATABASE_URL` / OIDC env yourself — see `.env.example`.

## Setup with devenv (only if already installed)

```sh
devenv up -d          # Postgres + Keycloak for this checkout
devenv shell          # pinned toolchain
just bootstrap        # migrate → import → seed
just info             # ports, DATABASE_URL, Keycloak issuer
just dev
```

## Frontend Scaffolding

The frontend is scaffolded separately using the `frontend-react` Copier template:

```sh
copier copy --trust path/to/templates/frontend-react src/habagou/web/frontend
```

## Database

The app only reads `DATABASE_URL`. Point it at:

- Compose Postgres (`just compose-db-up`) when using Docker for services
- The devenv Unix-socket URL when using an existing devenv checkout
- Any other Postgres 16 you already run

`just bootstrap` runs migrate → import → seed against whatever `DATABASE_URL`
is set.

## Running Locally

```sh
just bootstrap
just dev

# Or start separately
just dev-be   # Backend at the port shown by just info
just dev-fe   # Frontend dev server
```

Run `just info` for this checkout's exact backend/frontend/Keycloak URLs when
using the devenv-derived env. Interactive docs are available at `/docs` on the
backend URL.

Local auth uses the Keycloak realm rendered from
`docker/keycloak/habagou-realm.template.json` into
`.devenv/state/keycloak/habagou-realm.json`. `scripts/dev_env.py
render-keycloak-realm`, `devenv shell`, and `just bootstrap` can render this
file. If Keycloak was started before the file existed, restart Keycloak after
rendering. The seeded local login is `dev` / `dev`.

Auth-related env values can come from `scripts/dev_env.py` (devenv path) or
from explicit exports / `.env` (host + Compose path): `SESSION_SECRET_KEY`,
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
if the Keycloak issuer is not reachable; start Keycloak first (Compose or
devenv). Prefer the same service path you used for development — do not install
Nix solely to run e2e.

## Docker Compose

Two roles:

**Backing services for native app development** (when Docker is available and
Nix is not):

```sh
uv run python scripts/dev_env.py render-keycloak-realm
just compose-db-up
docker compose up -d keycloak
```

**Production-image smoke** (local stand-in for the built image; also CI
`compose-smoke`):

```sh
just compose-up       # build + run app image with Compose Postgres + Keycloak
just compose-smoke    # up, health/SPA/auth probes, restart check, tear down
```

`just compose-up` renders the dev Keycloak realm and starts app, Postgres, and
Keycloak. `just compose-smoke` verifies health, the SPA shell, the anonymous
session probe, and that data APIs return 401 without a session.

To build the image alone (without Compose orchestration):

```sh
docker build -t habagou .
```

Release images are published by GitHub Actions after successful CI on `main`
when semantic-release creates a new release. The workflow pushes
`ghcr.io/mattjmcnaughton/habagou` with full semver, major/minor, and `latest`
tags, and (in parallel) deploys to Fly.io via `flyctl deploy --remote-only`
so Fly builds from the release tag. See [deploy.md](deploy.md) for
production cutover, secrets, DNS/certs, and how CD works.
