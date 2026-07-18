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

## Agent pack generation (LLM features)

Agent pack generation drafts a themed practice pack from a topic, grounded
against the stroke corpus (see
[ADR 0010](adrs/0010-agent-pack-generation.md) and the API in
[api.md](api.md#generation)). It is **optional and off by default**: with no
API key set, the rest of the app is unaffected.

**Enable it locally.** Put an [OpenRouter](https://openrouter.ai/) API key in
`.env` (the app reads `.env` on startup):

```sh
OPENROUTER_API_KEY=sk-or-...        # required to enable generation AND practice
GENERATION_MODEL=openai/gpt-5.6-terra  # optional; default shown (via OpenRouter)
GENERATION_RATE_LIMIT_PER_HOUR=10   # optional; per user, 0 or negative disables the cap
PRACTICE_MODEL=openai/gpt-5.6-terra    # optional; conversational practice model
PRACTICE_RATE_LIMIT_PER_HOUR=60     # optional; per user, 0 or negative disables the cap
ADMIN_CHAT_MODELS=anthropic/claude-sonnet-5,minimax/minimax-m3  # optional; extra models admins may pick
ADMIN_EMAIL_DOMAINS=mattjmcnaughton.com  # optional; admin email domains (docs/auth.md)
LOGFIRE_TOKEN=                      # optional; enables API, database, and AI trace export
```

FastAPI requests, SQLAlchemy queries, and Pydantic AI calls are instrumented
with Logfire. The SDK uses
`send_to_logfire="if-token-present"`, so the app boots and generation works
normally when `LOGFIRE_TOKEN` is absent; only remote trace export is disabled.
System metrics are not instrumented. Pydantic AI spans include the full
generation conversation (user messages, replayed history, tool activity, and
model responses) for review in Logfire.

**When it is disabled** (no key), `GET /api/v1/generation/status` returns
`{"enabled": false, "models": null, "default_model": null}`, the frontend
hides the "Create a pack" entry point, and
`POST /api/v1/generation/draft` returns 503. Likewise
`GET /api/v1/practice/status` reports disabled, the Practice screen shows an
unavailable state, and `POST /api/v1/practice/turn` returns 503. Nothing else
changes.

**Develop the chat UIs without a key or any provider.**
`scripts/e2e_backend.py` serves the real API and seeded corpus with
deterministic, network-free generation and practice models (zero provider
calls) — the same stubs the Playwright suite runs against. Start it in place of `just dev-be`, on
the port `just dev-fe` proxies to, with the usual backend env (`DATABASE_URL`,
OIDC, `SESSION_SECRET_KEY`):

```sh
just bootstrap
# stub backend: real API + seeded corpus, fake key, stubbed models, caps disabled
GENERATION_RATE_LIMIT_PER_HOUR=0 PRACTICE_RATE_LIMIT_PER_HOUR=0 \
    uv run uvicorn scripts.e2e_backend:create_stub_app \
    --factory --host 127.0.0.1 --port "${HABAGOU_PORT:-8000}"
```

In another shell run `just dev-fe`; its Vite dev server proxies `/api` to that
backend port, so the "Create a pack" flow works end to end with no OpenRouter
account.

**PR CI makes zero real LLM calls.** The e2e suite drives the stub above, and
the backend test tiers force a `TestModel`/`FunctionModel` via `Agent.override`.
The real-provider contract tests (one per agent feature, in
`tests/external/`) are marked `@pytest.mark.external` and run only via
`just test-external`, never in `just gate` or the PR suite.

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
