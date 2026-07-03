# Habagou — Developer Experience (DEVEX)

| | |
|---|---|
| Status | **Final v1.0** — approved for implementation |
| Depends on | [TDD](technical/tdd.md) |
| Goal | Run N independent copies of Habagou on one laptop; devenv owns the database, the justfile owns everything else; Docker remains the agent shell and deployment packaging |

## 1. Requirements

- **N independent instances**: different branches/worktrees (or different agents) running simultaneously, no shared state, no port fights, no coordination step.
- **Docker not required for humans**: the default loop is Docker-free; agents use a Docker dev image so host Nix installs are optional and explicit.
- **Hermetic toolchain**: Python, Node, Postgres, just — pinned and identical across machines and CI.
- **Disposable**: destroying an instance is `rm -rf` of one directory; creating one is one command.
- **Same mechanism reused by tests**: the e2e harness provisions instances the same way a developer does.
- **Narrow devenv scope**: devenv owns the toolchain and the database — nothing else. App processes are always started by justfile targets, so the same `just` commands work regardless of where Postgres comes from.

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

```sh
# new instance
git worktree add ../habagou-featx featx
cd ../habagou-featx
devenv up -d         # postgres only
just bootstrap       # migrate -> corpus import (cached) -> seed
just dev             # backend + frontend, natively
just info            # where is everything?

# throw it away
git worktree remove ../habagou-featx   # code
# state died with the directory (.devenv/state is inside it)
```

The same app targets against a Docker database instead (no devenv):

```sh
docker compose up -d db     # Compose-managed Postgres on localhost:5432
export DATABASE_URL=postgresql+asyncpg://habagou:habagou@localhost:5432/habagou
just bootstrap && just dev
```

Agents enter the devenv environment through Docker, keeping Nix off the host:

```sh
just dev-shell-docker    # builds Dockerfile.dev, then opens devenv shell
devenv up -d             # inside the container: Postgres only
just dev                 # inside the container: backend + frontend
```

And the full prod-like stack (built image + db):

```sh
just compose-up             # wraps docker compose up --build
```

Details that make this pleasant:

- **Corpus import caching**: the ~25 MB `hanzi-writer-data` download is cached in a shared, content-addressed location (`$XDG_CACHE_HOME/habagou/`), so instance #2..N import from disk in seconds. Import into Postgres itself is idempotent and fast (bulk upsert).
- **`just bootstrap`** is the one idempotent entry point for `migrate → import → seed`, identical against a devenv socket, a Compose Postgres, CI's service container, or staging.
- **`just dev`** runs backend + frontend natively (separate `-be`/`-fe` variants per template convention) against whatever `DATABASE_URL` points at.
- **CI parity**: CI runs plain uv/pnpm with a Postgres service container (DEVEX DX-2), but through the same justfile targets — the justfile is the single interface everywhere.

## 5. Relationship to Docker Compose

Compose is a **supported peer**, not just deploy packaging. Three sanctioned modes, all sharing the justfile:

| Mode | Database | App processes | Use |
|---|---|---|---|
| devenv (default) | devenv per-checkout cluster, Unix socket | native, `just dev` | day-to-day human dev, N instances |
| Docker dev shell | devenv per-checkout cluster, Unix socket | container shell, `just dev` | agent dev without host Nix |
| Compose db + native app | `docker compose up -d db` (TCP :5432) | native, `just dev` | devs who prefer Docker over Nix; one instance at a time unless the port is remapped |
| Full Compose | Compose | Compose (built image) | prod-like verification (WF-10), staging/prod deployment |

Nothing in the devenv setup leaks into the image; the app only ever reads `DATABASE_URL`.

## 6. Open questions

| # | Question | Default |
|---|---|---|
| DX-1 | Is Nix/devenv acceptable tooling for everyone touching this repo? | Yes for the default human path; agents use Docker, and host Nix installs require explicit approval |
| DX-2 | Should CI run inside devenv (slower cold start, perfect parity) or plain uv/pnpm + service container (faster, near-parity)? | Plain toolchain in CI for v1; revisit if drift bites |
