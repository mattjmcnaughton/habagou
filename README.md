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
  controllers/         # Request orchestration
  services/            # Business logic
  repositories/        # Data access (SQLAlchemy)
  models/              # SQLAlchemy models
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

The primary dev environment is [devenv](https://devenv.sh/) — it pins the entire toolchain (Python, uv, Node, pnpm, just, Postgres) and gives every checkout its own isolated Postgres over a Unix socket, so you can run any number of independent instances (e.g. one per git worktree) with no Docker and no port coordination. See [docs/devex.md](docs/devex.md).

```sh
devenv up -d       # postgres for this checkout (devenv owns only the database)
just bootstrap     # migrate + corpus import + seed (idempotent)
just dev           # backend + frontend
just info          # this instance's ports, socket path, DATABASE_URL
```

Prefer Docker for the database? Same targets, different `DATABASE_URL`:

```sh
docker compose up -d db
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

Backend runs at `http://localhost:8000`, frontend dev server at `http://localhost:5173` (proxies `/api` to the backend). The API is versioned under `/api/v1`; the contract is checked in at `docs/api/openapi-v1.json` (see TDD §4.1).

## Common commands

| Command | Purpose |
| ------- | ------- |
| `just dev` | Backend + frontend dev servers |
| `just gate` | Fast pre-push check (fmt + lint + typecheck + unit tests) |
| `just gate-expensive` | gate + integration + e2e tests |
| `just info` | Show this instance's ports and database |
| `just e2e BASE_URL=…` | Full e2e suite against staging |
| `just smoke BASE_URL=…` | Read-only smoke against production |
| `just compose-up` | Full prod-like stack via Docker Compose |

## Deployment

`docker compose up` builds a single image containing the FastAPI backend serving the built frontend, alongside Postgres. Migrations, corpus import, and seeding run idempotently on startup. Kubernetes is the post-v1 target; nothing in the design blocks it (12-factor config, stateless app image, standard Postgres).

## Documentation

- [Product Requirements (PRD)](docs/product/prd.md)
- [Technical Design (TDD)](docs/technical/tdd.md)
- [Ticket breakdown](docs/tickets.md)
- [Developer experience](docs/devex.md) — running N local instances, devenv
- [Verification & validation](docs/verification.md) — workflow catalog, testing strategy, prod instrumentation

## License

Stroke data is derived from [hanzi-writer-data](https://github.com/chanind/hanzi-writer-data) (data originally from [Make Me a Hanzi](https://github.com/skishore/makemeahanzi), Arphic Public License). See `docs/technical/tdd.md` § Licensing.
