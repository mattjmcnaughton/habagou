# Habagou — Developer Experience (DEVEX)

| | |
|---|---|
| Status | **Final v1.0** — approved for implementation |
| Depends on | [TDD](technical/tdd.md) |
| Goal | Run N independent copies of Habagou on one laptop when devenv is available; otherwise prefer already-installed host tools + Compose services; never require a fresh host Nix install; the justfile owns app processes; Docker remains deploy packaging and an optional service/smoke path |

## 1. Requirements

- **N independent instances**: different branches/worktrees (or different agents) running simultaneously, no shared state, no port fights, no coordination step.
- **Docker not required for humans when Postgres/Keycloak already exist**; Compose is the preferred backing-service path when Docker is available and Nix is not. **Do not install Nix on the host solely for Habagou.**
- **Hermetic toolchain when using devenv**: Python, Node, Postgres, just — pinned and identical across machines that already have Nix/devenv (or use `Dockerfile.dev`).
- **Disposable**: destroying a devenv instance is `rm -rf` of one directory; creating one is one command.
- **Same mechanism reused by tests**: the e2e harness provisions instances the same way a developer does for that mode.
- **Narrow devenv scope**: when used, devenv owns the toolchain and the database — nothing else. App processes are always started by justfile targets, so the same `just` commands work regardless of where Postgres comes from.
- **Prefer already-installed tools**: host `uv`/`pnpm`/`just` + Compose (or existing services) before introducing Nix.

## 2. Decision: devenv owns the database (and toolchain), the justfile owns the app

**One instance = one checkout (git worktree).** Each checkout carries its own devenv-managed Postgres cluster, its own data directory, and its own derived HTTP ports. There is no shared database process.

**Division of labor** — devenv provides exactly two things: the pinned toolchain (`devenv shell`) and the Postgres service (`devenv up` starts *only* Postgres). Backend and frontend are never orchestrated by devenv; they run via `just dev` (and friends), which reads `DATABASE_URL` from the environment. This keeps the justfile as the single interface: point `DATABASE_URL` at the devenv socket, at a Compose-managed Postgres, or at anything else, and every `just` target behaves identically.

### Why per-checkout clusters, not one shared Postgres with N databases

The shared-cluster/database-per-instance pattern was considered and rejected for *cross-instance* use:

| Concern | Per-checkout cluster | Shared cluster + N databases |
|---|---|---|
| Independence | Total: own PG version, extensions, config, lifecycle | Weak: shared version/config; restarting or upgrading the cluster hits every instance |
| Coordination | None — no registry of who owns which database | Need naming discipline + cleanup of orphaned databases |
| Port conflicts | None — Postgres listens on a **Unix socket only** (`listen_addresses=''`), no TCP port at all | One port, but it's shared mutable infrastructure |
| Teardown | `rm -rf .devenv/state` | `DROP DATABASE` per instance, cluster lives on |
| Cost | ~40–60 MB RAM per idle cluster | Marginally less RAM |

The RAM saving of a shared cluster is negligible on a modern laptop even at N=10, and it purchases coordination burden. The database-per-X pattern is still used — but *inside* an instance, for test isolation (§5 of VERIFICATION.md): each integration/e2e test gets its own database via `CREATE DATABASE ... TEMPLATE ...` within that instance's cluster.

### Why devenv (Nix) rather than hand-rolled `initdb` scripts

- `devenv` pins Python, uv, Node, pnpm, just, and the Postgres **binary** version in one `devenv.nix` — the toolchain drift problem disappears for humans, agents, and CI alike.
- `services.postgres.enable = true` gives a per-project cluster in `$DEVENV_STATE/postgres` with lifecycle management for free.
- `devenv up` (process-compose under the hood) manages the Postgres service lifecycle — and only that.
- Fallback: everything devenv does is also expressible as `initdb`/`pg_ctl` in a justfile; if Nix is ever unacceptable, only `devenv.nix` is replaced. The app itself never knows — it only reads `DATABASE_URL`.

## 3. Instance anatomy

```
~/code/habagou            # worktree A (instance "habagou")
~/code/habagou-featx      # worktree B (instance "habagou-featx")
```

Each checkout derives an **instance identity** and from it, all mutable resources:

| Resource | Derivation |
|---|---|
| Instance name | basename of checkout dir (override: `HABAGOU_INSTANCE`) |
| Postgres | Unix socket at `$DEVENV_STATE/postgres/`, database `habagou` — no TCP |
| Backend port | `8000 + (stable_hash(instance) % 500)` (override: `HABAGOU_PORT`) |
| Frontend port | backend port + 3000 (override: `VITE_PORT`) |
| DATABASE_URL | `postgresql+asyncpg://habagou@/habagou?host=$DEVENV_STATE/postgres` |

Rules:

- Ports are **derived, deterministic, and printed** — `just info` shows the instance name, ports, socket path, and DATABASE_URL. No guessing, no scanning.
- The stable hash makes collisions across worktrees unlikely; when they happen (or when you want fixed ports), the env override wins. `.env` is per-checkout and gitignored.
- Vite's dev proxy targets the derived backend port (read from env at config time), so the FE↔BE pairing within an instance is automatic.
- asyncpg connects over the Unix socket via the `?host=<socket-dir>` URL form — the DB is unreachable from outside the machine and from other instances by construction.

## 4. Daily workflow

**Prefer already-installed tools.** Do not install Nix solely for Habagou.

Host tools + Compose services (when Docker is available and Nix is not):

```sh
uv sync
cd src/habagou/web/frontend && pnpm install --frozen-lockfile && cd -
uv run python scripts/dev_env.py render-keycloak-realm
just compose-db-up          # Compose Postgres on localhost:5432
docker compose up -d keycloak
export DATABASE_URL=postgresql+asyncpg://habagou:habagou@localhost:5432/habagou
export OIDC_PROVIDER=keycloak
export OIDC_ISSUER=http://127.0.0.1:18080/realms/habagou
export OIDC_CLIENT_ID=habagou
export OIDC_CLIENT_SECRET=habagou-dev-secret
export SESSION_SECRET_KEY=habagou-dev-session-secret
just bootstrap && just dev
```

When Nix/devenv is already present (multi-worktree isolation):

```sh
# new instance
git worktree add ../habagou-featx featx
cd ../habagou-featx
devenv up -d         # postgres + keycloak
devenv shell         # pinned uv/node/pnpm/just toolchain
```

Inside that shell:

```sh
just bootstrap       # migrate -> corpus import (cached) -> seed
just dev             # backend + frontend, natively
just info            # where is everything?
```

```sh
# throw it away
git worktree remove ../habagou-featx   # code
# state died with the directory (.devenv/state is inside it)
```

Environments that already ship Nix in an image (not a host install):

```sh
just dev-shell-docker    # builds Dockerfile.dev, then opens devenv shell
```

Inside the container shell:

```sh
devenv up -d             # inside the container
just bootstrap           # inside the container: migrate/import/seed
just dev                 # inside the container: backend + frontend
```

And the full prod-like stack (built image + db) — **smoke only**, not the
everyday native app loop:

```sh
just compose-up             # wraps docker compose up --build
just compose-smoke          # CI-style probes against that stack
```

Details that make this pleasant:

- **Corpus import caching**: the ~25 MB `hanzi-writer-data` download is cached in a shared, content-addressed location (`$XDG_CACHE_HOME/habagou/`), so instance #2..N import from disk in seconds. Import into Postgres itself is idempotent and fast (bulk upsert).
- **`just bootstrap`** is the one idempotent entry point for `migrate → import → seed`, identical against a devenv socket, a Compose Postgres, CI's service container, or staging. The import and seed commands are placeholders until HAB-012 and HAB-013 add the real corpus and pack data.
- **`just dev`** runs backend + frontend natively (separate `-be`/`-fe` variants per template convention) against whatever `DATABASE_URL` points at.
- **CI parity**: CI runs plain uv/pnpm with a Postgres service container (DEVEX DX-2), but through the same justfile targets — the justfile is the single interface everywhere.

## 5. Relationship to Docker Compose and host tools

**Do not install Nix just to work on Habagou.** Prefer tools and services already
on the machine. Compose is both a **backing-service** option for native apps and
the **production-image smoke** harness:

| Mode | Database / auth | App processes | Use |
|---|---|---|---|
| Host tools + Compose services | Compose Postgres (+ Keycloak) | native, `just dev` | preferred when Docker/host tools exist and Nix does not |
| Host tools + existing services | your Postgres / Keycloak | native, `just dev` | when you already run those services |
| devenv (optional) | devenv per-checkout cluster, Unix socket | native, `just dev` | only if Nix/devenv is already present; N worktree instances |
| Docker dev shell | devenv inside `Dockerfile.dev` | container shell, `just dev` | environments that already ship Nix in the image |
| Full Compose | Compose Postgres + Keycloak | Compose (built backend image) | local / CI prod-image smoke (`just compose-up` / `compose-smoke`) |

Nothing in the devenv setup leaks into the image; the app only ever reads `DATABASE_URL`.

## 6. Open questions

| # | Question | Default |
|---|---|---|
| DX-1 | Is Nix/devenv acceptable tooling for everyone touching this repo? | Only when already present; **do not install Nix solely for Habagou**. Prefer host tools + Compose/existing services otherwise |
| DX-2 | Should CI run inside devenv (slower cold start, perfect parity) or plain uv/pnpm + service container (faster, near-parity)? | Plain toolchain in CI for v1; revisit if drift bites |
