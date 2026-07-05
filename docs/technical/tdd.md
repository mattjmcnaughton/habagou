# Habagou — Technical Design Document

| | |
|---|---|
| Status | **Final v1.0** — approved for implementation |
| Depends on | [PRD](../product/prd.md) |
| Last updated | 2026-07-03 |
| Changes from v1 | Removed AI generation (agents module, generation jobs, rate limiting, OpenAI config); replaced anonymous sessions with a users table + shared guest user; deployment confirmed Docker Compose with k8s as follow-on |
| Changes from v2 | Added devex (see [DEVEX](../devex.md)) and verification strategy (see [VERIFICATION](../verification.md)); OTel scaffolded via template flag; testing section superseded by VERIFICATION |

## 1. Overview

Habagou is a single deployable FastAPI service with an embedded React frontend and a Postgres database. The repo is scaffolded from the [`python-web`](https://github.com/mattjmcnaughton/templates) Copier template with `include_database=true`, `database_type=postgres`, composed with `frontend-react` (Tailwind, zustand).

```
Browser (React + Hanzi Writer)
   │  /api/*
   ▼
FastAPI (routers → services → repositories)
   ▼
PostgreSQL (users, packs, characters/stroke corpus, activity completions)
```

### Scaffolding commands

```sh
copier copy --trust templates/templates/python-web habagou
#   project_name=habagou, include_database=true, database_type=postgres,
#   enable_otel=true, include_technical_docs=true, include_product_docs=true
copier copy --trust templates/templates/frontend-react habagou/src/habagou/web/frontend
#   is_composed=true, include_zustand=true
```

Then add `hanzi-writer`, `@fontsource/hanken-grotesk`, `@fontsource/noto-sans-sc` to the frontend `package.json`. No extra backend dependencies beyond the template.

## 2. Key decisions

| # | Decision | Rationale | Alternative rejected |
|---|----------|-----------|----------------------|
| D-1 | **Stroke corpus in Postgres**, served by our API | One source of truth; no runtime third-party dependency; seed-time validation that every pack/sentence character has stroke data; enables v2 generation-time validation; responses immutable-cacheable | Frontend loads from jsDelivr CDN — simpler, but adds an external runtime dependency and no validation hook |
| D-2 | **Hanzi Writer** stays the tracing engine, fed by a custom `charDataLoader` hitting our API | Validated by the prototype; mature quiz API (per-stroke callbacks, hints after 3 misses) | Custom canvas engine — months of work |
| D-3 | **User-centric schema with a seeded guest user**; a `get_current_user` dependency resolves every request to the guest user in v1 | Progress is user-scoped from day one; adding auth later swaps only the resolver, not schemas or API shapes | Anonymous session cookies — would require a progress migration when accounts arrive |
| D-4 | **No AI/generation code in v1** — not even stubs | Smaller surface, faster ship; the only v1 obligation to v2 is the corpus-in-Postgres decision (D-1) and `packs.status` | Building generation scaffolding now — dead code until v2 is actually designed |
| D-5 | **Progress = append-only completion events**, aggregated at read time | Simple writes, natural history/audit; per-activity "completed?" and "best duration" are cheap aggregates at v1 scale | Mutable per-(user,pack,activity) state row — loses history; premature optimization |
| D-6 | **Human local dev = devenv with a per-checkout Postgres over Unix sockets**; agent dev runs that same devenv path inside Docker | N independent instances with zero coordination; hermetic toolchain; see [DEVEX](../devex.md) | Shared local Postgres with database-per-instance; full-stack Docker as the primary human loop — both add coordination or weight |
| D-8 | **URL-path API versioning** (`/api/v1`), additive-only within a version | Explicit compatibility contract for the frontend, the OpenAPI artifact, and any future clients; new major version mounts side-by-side | Header/content-negotiation versioning — harder to see in logs, caches, and curl; unversioned API — silent breakage |
| D-7 | **Workflow-keyed verification**: named workflow catalog with tagged tests, CI traceability matrix, and prod events/metrics sharing the same IDs | One vocabulary from PRD to prod dashboard; see [VERIFICATION](../verification.md) | Untagged test suite + ad-hoc logging — cannot answer "is workflow X proven and working?" mechanically |

## 3. Data model

All tables via SQLAlchemy 2 async models + Alembic migrations.

```
users
  id            PK (uuid)
  username      text UNIQUE      -- 'guest' for the seeded guest user
  display_name  text
  is_guest      bool             -- true only for the well-known guest row
  created_at    timestamptz

characters                       -- stroke corpus (~9 500 rows)
  id            PK
  hanzi         text UNIQUE      -- single grapheme
  stroke_data   jsonb            -- hanzi-writer-data JSON: strokes[], medians[]
  stroke_count  int
  created_at    timestamptz

packs
  id            PK (uuid)
  slug          text UNIQUE      -- 'greetings'
  title         text
  glyph         text             -- representative hanzi for the card
  color         text             -- accent hex, e.g. '#c4633f'
  status        enum('draft','published','retired')
  sort_order    int
  created_at, updated_at

pack_characters
  pack_id       FK packs
  character_id  FK characters
  position      int
  pinyin        text             -- display pinyin with tone marks: 'nǐ'
  meaning       text             -- 'you'
  UNIQUE(pack_id, position)

pack_sentences
  id            PK
  pack_id       FK packs
  position      int
  hanzi         text             -- '我很好'
  pinyin        text             -- 'wǒ hěn hǎo'
  translation   text             -- 'I am well'

activity_completions             -- append-only event log
  id            PK
  user_id       FK users
  pack_id       FK packs
  activity      enum('trace','match','sentence')
  duration_ms   int
  completed_at  timestamptz
  INDEX(user_id, pack_id)
```

Notes:

- **Guest user**: migrations/seed create exactly one row with a fixed, well-known UUID and `username='guest'`. The backend's `get_current_user` FastAPI dependency returns it unconditionally in v1. When auth arrives (v2), only this dependency changes.
- `pinyin`/`meaning` live on the **join table**, not `characters`: a character's gloss is contextual to the pack. The corpus row is purely stroke geometry.
- Sentences store raw hanzi strings; the seed script (and, later, any pack-creation path) resolves each grapheme against `characters` and **fails if any is missing** — Hanzi Writer cannot render a character we lack strokes for. Prototype sentence-only chars (很, 个, 人, 喝) are the canonical test of this rule.
- v2 forward-compat: adding `packs.source` + `packs.provenance` later is an additive migration; nothing in v1 assumes their absence.

## 4. API

### 4.1 Versioning (D-8)

- All endpoints live under a **URL-path version prefix**: `/api/v1/...`. Routers are namespaced accordingly (`routers/v1/`), so a future `/api/v2` mounts side-by-side without touching v1 code.
- **Within a version, changes are additive-only**: new endpoints, new optional request fields, new response fields. Breaking changes — removing/renaming fields, changing types or semantics, changing status codes — require a new major version.
- The exported OpenAPI contract is versioned with the API (`docs/api/openapi-v1.json`); the CI drift check (HAB-025) pins frontend types and MSW mocks to it. The frontend API client hardcodes the `/api/v1` base in exactly one place.
- Deprecation: when `/api/v2` exists, v1 responses gain a `Deprecation` header and a sunset date; v1 is removed only after all first-party clients migrate. (Academic while we own the only client, but the policy costs nothing to state now.)
- Unversioned by design: `/healthz` and `/readyz` (infrastructure probes, not API surface).

### 4.2 Endpoints

All under `/api/v1`, DTOs in `dtos/`, thin routers → services per template layering. The current user is resolved by a `get_current_user` dependency (v1: always guest).

| Method & path | Purpose |
|---|---|
| `GET /packs` | Published packs (id, slug, title, glyph, color, char_count, sentence_count) sorted by `sort_order`; includes the current user's per-activity completion flags |
| `GET /packs/{slug}` | Full pack: characters (hanzi, pinyin, meaning) + sentences (hanzi, pinyin, translation) + completion state |
| `GET /characters/{hanzi}/strokes` | Stroke JSON for one character. `Cache-Control: public, max-age=31536000, immutable`. 404 if not in corpus; 422 for multi-grapheme input |
| `POST /progress/completions` | Body: `{pack_slug, activity, duration_ms}`. Records a completion for the current user |
| `GET /progress/packs/{slug}` | Per-activity: completed flag, completion count, best duration for the current user |
| `DELETE /progress/packs/{slug}` | Reset the current user's progress for a pack (PRD OQ-3) |
| `GET /healthz`, `GET /readyz` | From template (readyz checks DB) |

Admin (token-protected via `ADMIN_TOKEN` header, no UI): `POST /admin/packs/{slug}/retire`, `POST /admin/packs/{slug}/publish`, `PATCH /admin/packs/{slug}` (sort_order).

## 5. Stroke corpus ingestion & seeding

`scripts/import_stroke_data.py`:

1. Download `hanzi-writer-data` at a pinned version (npm tarball or GitHub release).
2. Upsert every character JSON into `characters` (hanzi, stroke_data, stroke_count).
3. Idempotent; `--subset <file>` flag imports only listed characters (for test fixtures and fast CI).

`scripts/seed.py`:

1. Upsert the guest user (fixed UUID).
2. Upsert the four prototype packs with exact prototype content (chars, pinyin, meanings, sentences, glyphs, colors — see [tickets appendix](../tickets.md#appendix--seed-data-extracted-from-prototype)).
3. Validate every character referenced by pack chars **and** sentences against the corpus; abort loudly on any miss.
4. Idempotent (keyed on slugs/positions).

Both run as part of the Docker entrypoint (after `alembic upgrade head`) and are safe to re-run on every boot. Corpus size ~9 500 characters, ~25 MB of JSONB — trivial for Postgres.

## 6. Frontend

Scaffolded from `frontend-react` (Vite, React 19, TS, TanStack Router + Query, Tailwind, Biome, Vitest, Playwright, MSW). Additions: `hanzi-writer`, self-hosted fonts.

Routes:

```
/                     Home — pack grid with completion badges
/packs/$slug          Pack screen — chars + activity buttons + completion state + reset
/packs/$slug/trace    Trace activity
/packs/$slug/match    Match activity
/packs/$slug/sentence Sentence activity
```

Key components:

- `TraceCanvas` — wraps `HanziWriter.create(...).quiz(...)`; props: hanzi, size, callbacks `{onTotal, onStroke, onComplete}`; `charDataLoader` fetches `/api/v1/characters/{hanzi}/strokes` through TanStack Query (staleTime: Infinity + prefetch of all pack characters on pack load, including sentence-only characters). Writer options ported from the prototype: `showCharacter:false, showOutline:true, showHintAfterMisses:3, drawingWidth:size*0.085`, prototype colors.
- `MatchBoard` — port of the prototype match logic (selection, wrong-pair shake with 560 ms reset, matched-lock, timer). Pure client state (useReducer/zustand).
- `SentenceTracer` — cell strip + `TraceCanvas`, prototype cell styling (done/active/pending).
- `ProgressBar`, `PackCard`, `ActivityFooter` (Hint / Redo), `DoneScreen` — direct ports of prototype visuals.

Design tokens (from prototype): bg `#0e0f11`, surface `#1b1f22`, text `#e8ecee`, accent `#5fb89a` / `#7fcfae`, error `#c96a5e`; fonts Hanken Grotesk (UI) + Noto Sans SC (hanzi), self-hosted via `@fontsource`.

Activity completion posts to `/api/v1/progress/completions` from the done screen; pack/home queries invalidate to refresh badges.

## 7. Testing

Superseded by [VERIFICATION.md](../verification.md), which defines the workflow catalog, the layer-by-layer strategy (unit / integration with per-test template databases / e2e / prod smoke / invariant checks), contract single-sourcing from OpenAPI, and the CI traceability gate.

## 8. Deployment & ops

Human local development does not require Docker — see [DEVEX.md](../devex.md) (devenv, per-checkout Postgres, N instances). Agents use a Docker dev image that installs Nix/devenv inside the image, and Docker Compose remains the deployment packaging.

- **Dockerfile** (from template): multi-stage — pnpm build of frontend → uv-installed backend serving `web/frontend/dist` via `serve.py`.
- **docker-compose.yml**: `app` + `db` (postgres:16, named volume). App entrypoint: `alembic upgrade head` → `import_stroke_data.py` → `seed.py` → uvicorn.
- **Config**: 12-factor via env (`DATABASE_URL`, `ADMIN_TOKEN`, `LOG_LEVEL`); `.env.example` enumerates everything. No secrets beyond `ADMIN_TOKEN` in v1.
- **k8s later**: the app is already stateless with env-only config and standard health probes (`/healthz`, `/readyz`); the entrypoint's migrate+seed step becomes an init container/Job. No v1 design change required.
- **Logging & metrics**: structlog JSON (template default) with request logging including resolved user id; workflow events and OTel counters via `events.py` per VERIFICATION §5. OTLP export active only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.
- **CI**: template GitHub Actions — fmt, lint, typecheck (ruff/ty/Biome/tsc), unit on every PR; integration with a Postgres service container; e2e on PRs to main.

## 9. Licensing

`hanzi-writer-data` derives from Make Me a Hanzi (Arphic Public License for the glyph outlines). The APL requires attribution and license propagation for the data — include `LICENSE-ARPHIC` and attribution in the README/about screen. Hanzi Writer itself is MIT.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Hanzi Writer touch quirks on some devices | Prototype already validated core interaction; mobile-viewport e2e; manual device pass before ship |
| Shared guest progress confuses multi-person deployments | Documented limitation (PRD OQ-1); per-pack reset action; real accounts in v2 |
| Corpus/seed drift (pack references a char not imported) | Seed validation aborts loudly; CI runs seed against fixture corpus including sentence-only chars |
| Grapheme handling (single `str` index vs surrogate pairs/combining chars) | Centralize grapheme splitting in one utility, unit-tested; corpus chars are single BMP codepoints in practice, but don't assume |
