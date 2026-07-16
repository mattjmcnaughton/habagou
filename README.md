# Habagou 哈巴狗

Learn to write Chinese characters by tracing them, stroke by stroke.

Habagou is a full-stack web app for practicing Hanzi handwriting. Characters are organized into themed **packs** (Greetings, Numbers, Family, Food & Drink). Each pack offers three activities:

- **Trace** — write each character stroke by stroke with guided feedback and hints.
- **Match** — a timed matching game pairing characters with their pinyin and meaning.
- **Sentence** — trace every character of short sentences, reinforcing characters in context.

Progress is tracked per user. v1 ships without authentication — everyone acts as a shared **guest user** — but the data model is user-centric from day one so real accounts can be added without a migration rewrite. Alongside the curated, seeded packs, learners can generate their own private packs from a topic with a corpus-grounded agent (OpenAI-compatible models via OpenRouter; see [ADR 0010](docs/adrs/0010-agent-pack-generation.md)).

## Stack

| Layer | Technology |
| ----- | ---------- |
| Backend | Python 3.12, FastAPI, uvicorn, pydantic-ai, Logfire, structlog, pydantic-settings |
| Database | PostgreSQL 16, SQLAlchemy 2 (async, asyncpg), Alembic |
| Frontend | React 19, TypeScript, Vite, TanStack Router + Query, Tailwind CSS |
| Handwriting | [Hanzi Writer](https://hanziwriter.org/) + `hanzi-writer-data` stroke corpus |
| Tooling | uv, just, ruff, ty, pytest, Biome, Vitest, Playwright |

The repository layout follows the [`python-web`](https://github.com/mattjmcnaughton/templates) Copier template, with the frontend composed from `frontend-react`.

## Repository structure

```
src/habagou/
  app.py               # FastAPI app factory
  config.py            # pydantic-settings config from env vars
  logging.py           # structlog setup
  db.py                # Async engine/session factory
  routers/             # HTTP endpoints (health, packs, strokes, progress)
  services/            # Business logic
  repositories.py      # Data access (SQLAlchemy)
  models.py            # SQLAlchemy models
  dtos/                # Pydantic request/response models
  web/
    serve.py           # Static file serving in production
    frontend/          # React app (Vite)
alembic/               # Database migrations
scripts/               # Stroke-corpus import, pack + guest-user seeding
tests/                 # unit / integration / e2e
docs/
  product/prd.md       # Product requirements
  technical/tdd.md     # Technical design
  tickets.md           # Implementation breakdown
```

## Getting started

**Do not install Nix just to work on Habagou.** Prefer tools and services you
already have. The justfile is the common interface in every mode — see
[docs/devex.md](docs/devex.md) and [docs/development.md](docs/development.md).

### Host tools + Compose services (no Nix)

If you already have `uv`, `just`, Node 22, and `pnpm` (and Docker for
Postgres/Keycloak):

```sh
uv sync
cd src/habagou/web/frontend && pnpm install --frozen-lockfile && cd -
uv run python scripts/dev_env.py render-keycloak-realm
just compose-db-up
docker compose up -d keycloak
export DATABASE_URL=postgresql+asyncpg://habagou:habagou@localhost:5432/habagou
export OIDC_PROVIDER=keycloak
export OIDC_ISSUER=http://127.0.0.1:18080/realms/habagou
export OIDC_CLIENT_ID=habagou
export OIDC_CLIENT_SECRET=habagou-dev-secret
export SESSION_SECRET_KEY=habagou-dev-session-secret
just bootstrap
just info
just dev
```

### devenv (only if already installed)

[devenv](https://devenv.sh/) pins the toolchain and gives every checkout its
own isolated Postgres over a Unix socket. Use this path only when Nix/devenv is
already present — including cloud-agent / `Dockerfile.dev` environments. Do not
install Nix on the host solely for this repo.

```sh
devenv up -d
devenv shell
```

Inside the devenv shell:

```sh
cd src/habagou/web/frontend && pnpm install --frozen-lockfile && cd -
just bootstrap
just info
just dev
```

Open the frontend URL printed by `just info`. Ports are derived from the checkout name, so they are not always `8000` and `5173`.

Agent environments that already ship Nix use:

```sh
just dev-shell-docker   # builds Dockerfile.dev, then enters devenv shell
```

### Manual setup (own Postgres, no Compose)

Prerequisites: [uv](https://docs.astral.sh/uv/), [just](https://just.systems/), Node 22 + pnpm, a Postgres 16 you provide.

```sh
# 1. Install dependencies
uv sync
cd src/habagou/web/frontend && pnpm install && cd -

# 2. Configure environment
cp .env.example .env       # set DATABASE_URL (and OIDC if using Keycloak/Auth0)

# 3. Point DATABASE_URL at your Postgres

# 4. Run migrations, import stroke corpus, seed guest user + starter packs
uv run alembic upgrade head
uv run python scripts/import_stroke_data.py
uv run python scripts/seed.py

# 5. Run backend + frontend dev servers
just dev
```

By default, backend runs at `http://localhost:8000`, frontend dev server at `http://localhost:5173`, and the frontend proxies `/api` to the backend. Per-checkout dev ports are derived from the checkout name; run `just info` for the exact URLs. The API is versioned under `/api/v1`; the contract is checked in at `docs/api/openapi-v1.json` (see TDD §4.1).

## Common commands

| Command | Purpose |
| ------- | ------- |
| `just bootstrap` | Migrate, import corpus data, and seed |
| `just dev` | Backend + frontend dev servers |
| `just dev-shell-docker` | Docker-based devenv shell when the image already includes Nix |
| `just compose-db-up` | Compose Postgres for native app development (no Nix) |
| `just compose-up` | Prod-image smoke stack |
| `just compose-smoke` | CI-style Compose health/SPA/auth smoke |
| `just gate` | Fast pre-push check (fmt + lint + typecheck + unit tests) |
| `just gate-expensive` | gate + integration + e2e tests |
| `just info` | Show this instance's ports and database |
| `just e2e BASE_URL=…` | Full e2e suite against staging |
| `just smoke BASE_URL=…` | Read-only smoke against production |
| `uv run python scripts/check_invariants.py --dsn "$DATABASE_URL"` | Production data invariant check |

## Deployment

Production runs on [Fly.io](https://fly.io/) with Postgres on [Neon](https://neon.tech/) (Neon project **`habagou`**). The production image is a single container: FastAPI serves the built frontend and `/api/v1`. Migrations, corpus import, and seeding run once per deploy via Fly's `release_command` (not on every app-machine boot).

Successful CI on `main` runs semantic-release; when a release is published, GitHub Actions pushes `ghcr.io/mattjmcnaughton/habagou` (for artifact retention) and runs `flyctl deploy --remote-only` so Fly builds from the release tag. See [docs/deploy.md](docs/deploy.md) for one-time cutover (Neon, `fly secrets`, custom domain + DNS) and ongoing CD.

Locally, `just compose-up` / `just compose-smoke` build the same production
image alongside Postgres and Keycloak for **prod-image smoke** without Fly.
Day-to-day development should use host tools (and Compose only for backing
services if needed) — do not install Nix solely for Habagou.

## Documentation

- [Product Requirements (PRD)](docs/product/prd.md)
- [Technical Design (TDD)](docs/technical/tdd.md)
- [Ticket breakdown](docs/tickets.md)
- [Deploy runbook](docs/deploy.md) — Fly.io cutover, secrets, DNS/certs, CD
- [Authentication](docs/auth.md) — OIDC providers, local sessions, and Auth0 configuration
- [Developer experience](docs/devex.md) — running N local instances, devenv
- [Verification & validation](docs/verification.md) — workflow catalog, testing strategy, prod instrumentation

## License

Habagou application code is MIT licensed. Stroke data is derived from [hanzi-writer-data](https://github.com/chanind/hanzi-writer-data), whose glyph outlines originate from [Make Me a Hanzi](https://github.com/skishore/makemeahanzi) and are distributed under the Arphic Public License. See [ATTRIBUTION.md](ATTRIBUTION.md) and [LICENSE-ARPHIC](LICENSE-ARPHIC).
