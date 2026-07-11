# Habagou 哈巴狗

Learn to write Chinese characters by tracing them, stroke by stroke.

Habagou is a full-stack web app for practicing Hanzi handwriting. Characters are organized into themed **packs** (Greetings, Numbers, Family, Food & Drink). Each pack offers three activities:

- **Trace** — write each character stroke by stroke with guided feedback and hints.
- **Match** — a timed matching game pairing characters with their pinyin and meaning.
- **Sentence** — trace every character of short sentences, reinforcing characters in context.

Progress is tracked per user. v1 ships without authentication — everyone acts as a shared **guest user** — but the data model is user-centric from day one so real accounts can be added without a migration rewrite. AI-assisted pack generation is on the v2 roadmap; v1 packs are curated and seeded.

## Stack

| Layer | Technology |
| ----- | ---------- |
| Backend | Python 3.12, FastAPI, uvicorn, structlog, pydantic-settings |
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

The primary human dev environment is [devenv](https://devenv.sh/) — it pins the entire toolchain (Python, uv, Node, pnpm, just, Postgres) and gives every checkout its own isolated Postgres over a Unix socket, so you can run any number of independent instances (e.g. one per git worktree) with no port coordination. Install Nix/devenv before this step; agents use the checked-in `Dockerfile.dev`, which installs Nix and devenv inside the image rather than on the host. See [docs/devex.md](docs/devex.md).

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

Agent/container path:

```sh
just dev-shell-docker   # builds Dockerfile.dev, then enters devenv shell
```

Prefer Docker for the database? Same targets, different `DATABASE_URL`:

```sh
just compose-db-up
export DATABASE_URL=postgresql+asyncpg://habagou:habagou@localhost:5432/habagou
just bootstrap && just dev
```

### Manual setup (no devenv, no Docker)

Prerequisites: [uv](https://docs.astral.sh/uv/), [just](https://just.systems/), Node 22 + pnpm, a Postgres 16 you provide.

```sh
# 1. Install dependencies
uv sync
cd src/habagou/web/frontend && pnpm install && cd -

# 2. Configure environment
cp .env.example .env       # set DATABASE_URL

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
| `just dev-shell-docker` | Docker-based devenv shell for agents |
| `just compose-db-up` | Compose Postgres for native app development |
| `just compose-up` | Full prod-like stack via Docker Compose |
| `just gate` | Fast pre-push check (fmt + lint + typecheck + unit tests) |
| `just gate-expensive` | gate + integration + e2e tests |
| `just info` | Show this instance's ports and database |
| `just e2e BASE_URL=…` | Full e2e suite against staging |
| `just smoke BASE_URL=…` | Read-only smoke against production |
| `uv run python scripts/check_invariants.py --dsn "$DATABASE_URL"` | Production data invariant check |

## Deployment

Production runs on [Fly.io](https://fly.io/) with Postgres on [Neon](https://neon.tech/) (Neon project **`habagou`**). The production image is a single container: FastAPI serves the built frontend and `/api/v1`. Migrations, corpus import, and seeding run once per deploy via Fly's `release_command` (not on every app-machine boot).

Successful CI on `main` runs semantic-release; when a release is published, GitHub Actions pushes `ghcr.io/mattjmcnaughton/habagou` (for artifact retention) and runs `flyctl deploy --remote-only` so Fly builds from the release tag. See [docs/deploy.md](docs/deploy.md) for one-time cutover (Neon, `fly secrets`, custom domain + DNS) and ongoing CD.

Locally, `docker compose up` still builds the same image alongside Postgres and bootstraps on container start — useful for a prod-like smoke without Fly.

## Documentation

- [Product Requirements (PRD)](docs/product/prd.md)
- [Technical Design (TDD)](docs/technical/tdd.md)
- [Ticket breakdown](docs/tickets.md)
- [Deploy runbook](docs/deploy.md) — Fly.io cutover, secrets, DNS/certs, CD
- [Developer experience](docs/devex.md) — running N local instances, devenv
- [Verification & validation](docs/verification.md) — workflow catalog, testing strategy, prod instrumentation

## License

Habagou application code is MIT licensed. Stroke data is derived from [hanzi-writer-data](https://github.com/chanind/hanzi-writer-data), whose glyph outlines originate from [Make Me a Hanzi](https://github.com/skishore/makemeahanzi) and are distributed under the Arphic Public License. See [ATTRIBUTION.md](ATTRIBUTION.md) and [LICENSE-ARPHIC](LICENSE-ARPHIC).
