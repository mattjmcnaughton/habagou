# Habagou — Ticket Breakdown

**Status: Final v1.0 — ready to hand off.** Ordered for an implementing agent. Each ticket lists dependencies and acceptance criteria (AC). Reference docs: [PRD](product/prd.md), [TDD](technical/tdd.md), [DEVEX](devex.md), [VERIFICATION](verification.md), [prototype](prototype/Habagou.html) (source of truth for UX/visuals; app logic is in the embedded `text/x-dc` script).

Conventions: every ticket must pass `just gate` before merge. Tests added by feature tickets carry workflow tags per VERIFICATION §4. Tickets marked **[FE]**/**[BE]** touch only one side.

Scope note: **no AI/generation work in v1** (v2 roadmap). Forward-compat obligations: stroke corpus in Postgres, `packs.status`. The `packs.status` obligation is superseded by [ADR 0009](adrs/0009-pack-ownership.md): pack ownership (`Pack.owner_id`), not status, is the forward-compat mechanism Epic 6 built for agent-created (Epic 7) packs.

---

## Epic 0 — Scaffolding & DevEx

### HAB-001 — Scaffold repo from templates
Deps: none.
Run Copier per TDD §1 (`python-web` with postgres, **`enable_otel=true`**, product/technical docs; compose `frontend-react` with `is_composed=true`). Add frontend deps: `hanzi-writer`, `@fontsource/hanken-grotesk`, `@fontsource/noto-sans-sc`. `.env.example`: `DATABASE_URL`, `ADMIN_TOKEN`, `LOG_LEVEL`, `OTEL_EXPORTER_OTLP_ENDPOINT` (optional).
**AC:** `just dev` starts both servers; `just gate` green; `/healthz`, `/readyz` respond; OTel is a no-op when no endpoint configured.

### HAB-002 — devenv environment
Deps: HAB-001.
`devenv.nix` per DEVEX §2–3: pinned Python/uv/Node/pnpm/just/Postgres; `services.postgres` with data in `$DEVENV_STATE`, **Unix socket only** (`listen_addresses=''`); env exports `DATABASE_URL` (socket form) and derived `HABAGOU_PORT`/`VITE_PORT` (stable hash of instance name, env-overridable). `just info` prints instance name, ports, socket path, DATABASE_URL. Vite config reads derived ports.
**AC:** `devenv shell` gives the full toolchain with no host installs; postgres starts with no TCP port; two sibling worktrees compute different ports; overrides respected.

### HAB-003 — Bootstrap & dev targets (dual database modes)
Deps: HAB-002, HAB-012 (seed script; can land with stub bootstrap first).
devenv's `devenv up` starts **Postgres only** (DEVEX §2). Justfile targets: `just bootstrap` (migrate → corpus import → seed, idempotent, DATABASE_URL-driven), `just dev`/`-be`/`-fe` (native app processes), `just compose-up` (full prod-like stack), plus a documented Compose-db mode (`docker compose up -d db` + exported DATABASE_URL + same just targets). Corpus tarball cached in `$XDG_CACHE_HOME/habagou/` (content-addressed) so instances 2..N skip the download.
**AC (the headline devex AC):** from a clean second worktree, `devenv up -d && just bootstrap && just dev` yields a fully working independent app; **two instances run simultaneously**, tracing 你 in both, zero cross-talk, zero manual port/db config; killing one leaves the other untouched. Separately: the Compose-db mode passes the same bootstrap+dev flow with devenv absent.

### HAB-004 — CI pipeline
Deps: HAB-001.
Template GitHub Actions: gate on every PR (plain uv/pnpm toolchain + `postgres:16` service container per DEVEX DX-2); integration job; e2e job on PRs to main; OpenAPI drift check (see HAB-025).
**AC:** CI green on the scaffold; integration job connects to Postgres; schema-drift check demonstrably fails on an uncommitted API change.

---

## Epic 1 — Data layer, corpus & seeding

### HAB-010 — [BE] Database schema & migrations
Deps: HAB-001.
SQLAlchemy models + initial Alembic migration for `users`, `characters`, `packs`, `pack_characters`, `pack_sentences`, `activity_completions` per TDD §3. Indexes: `characters.hanzi` unique, `packs.slug` unique, `users.username` unique, `activity_completions(user_id, pack_id)`.
**AC:** upgrade from empty DB + clean downgrade; integration test round-trips a pack with chars + sentences and a completion event.

### HAB-011 — [BE] Stroke corpus import script
Deps: HAB-010.
`scripts/import_stroke_data.py`: download pinned `hanzi-writer-data` release (via the DEVEX cache), bulk-upsert characters (hanzi, stroke_data jsonb, stroke_count). Idempotent; `--subset <file>` for fixtures/CI.
**AC:** Full import < 2 min, ~9 000+ rows; rerun is a no-op; fixture-subset test (all prototype chars incl. 很, 个, 人, 喝) verifies stroke JSON matches source byte-for-byte.

### HAB-012 — [BE] Seed script: guest user + prototype packs
Deps: HAB-011.
`scripts/seed.py`: (1) upsert guest user (fixed well-known UUID, `username='guest'`, `is_guest=true`); (2) upsert the four prototype packs (appendix); (3) validate every referenced character — pack chars **and sentence chars** — against the corpus; abort listing missing chars. Idempotent. Emits `bootstrap_completed` event fields (chars, packs).
**AC:** Post-seed DB: 1 guest, 4 published packs matching prototype; re-run idempotent; integration test proves the abort path (WF-01 negative case).

### HAB-013 — [BE] Repositories
Deps: HAB-010.
`PackRepository` (list published + counts, get by slug eager-loaded), `CharacterRepository` (strokes by hanzi; bulk-exists returning missing set in one query), `ProgressRepository` (record; per-pack aggregate: completed flags/counts/best duration; delete by user+pack). The guest user is read directly by well-known ID.
**AC:** Integration tests for repositories and guest-user resolution against real Postgres.

### HAB-014 — [BE] Per-test database fixtures
Deps: HAB-012, HAB-002.
pytest session fixture: create `habagou_test_base` once (migrate + fixture-subset import + seed), then per-test `CREATE DATABASE test_<id> TEMPLATE habagou_test_base` / `DROP` on teardown (VERIFICATION §3). Works over the devenv socket locally and the service container in CI. Wire pytest-xdist.
**AC:** Integration suite runs fully parallel with zero flakes across 3 consecutive runs; per-test DB setup < 200 ms after template creation.

---

## Epic 2 — Core API

### HAB-020 — [BE] Current-user dependency & events helper
Deps: HAB-012, HAB-013.
`get_current_user` dependency resolving to the seeded guest (cached); documented as the single v2-auth swap point. `src/habagou/events.py` per VERIFICATION §5: structlog emit + OTel counter/histogram (`habagou_workflow_total`, `habagou_workflow_duration_ms`) with enforced fields (`workflow`, `outcome`, `duration_ms`).
**AC:** Unit tests: dependency returns guest; emitted workflow IDs are validated against `src/habagou/workflows.yml`; events log cleanly without OTel endpoint.

### HAB-021 — [BE] Packs API
Deps: HAB-013, HAB-020.
`GET /api/v1/packs` (published, sorted, counts, current user's per-activity completion flags) and `GET /api/v1/packs/{slug}` (full DTO + completion state). 404 unknown/unpublished. Emits `pack_list_served`/`pack_served`. Routers live under `routers/v1/` per TDD §4.1; all subsequent endpoint tickets follow the same namespace.
**AC:** Contract tests tagged WF-02 against seeded per-test DB; OpenAPI documents DTOs.

### HAB-022 — [BE] Stroke data API
Deps: HAB-011, HAB-013, HAB-020.
`GET /api/v1/characters/{hanzi}/strokes`: corpus JSON verbatim, `Cache-Control: public, max-age=31536000, immutable`; 404 unknown (emit `strokes_missing`); 422 multi-grapheme. Grapheme validation in one tested utility.
**AC:** Tests tagged WF-06: 你 → valid Hanzi Writer JSON (`strokes`+`medians`), cache header; 你好 → 422; unknown → 404 + `strokes_missing` event asserted; local benchmark loop p95 < 50 ms.

### HAB-023 — [BE] Progress API
Deps: HAB-020, HAB-021.
`POST /progress/completions` (`{pack_slug, activity, duration_ms}`), `GET /progress/packs/{slug}`, `DELETE /progress/packs/{slug}`. Emits `activity_completed` / `progress_reset`.
**AC:** Tests tagged WF-07/WF-08: complete → reflected → reset → cleared; invalid activity → 422; completions scoped to current user.

### HAB-024 — [BE] Admin endpoints
Deps: HAB-021.
`ADMIN_TOKEN`-protected (constant-time compare): retire/publish, patch `sort_order`; disabled with clear error when token unset. Emits `admin_action`.
**AC:** Tests tagged WF-09: retired pack vanishes from WF-02 output; 401 on missing/wrong token.

### HAB-025 — [BE] OpenAPI contract artifact
Deps: HAB-021..024.
Export OpenAPI schema to a checked-in, **versioned** artifact (`docs/api/openapi-v1.json`) via `just openapi`; CI fails on drift. Frontend types/MSW handlers generated or validated from it (pick: `openapi-typescript` for types + hand-written MSW asserted against schema). The FE client declares the `/api/v1` base in one module.
**AC:** Editing an endpoint without regenerating fails CI; FE build consumes generated types.

---

## Epic 3 — Frontend

### HAB-030 — [FE] Design system & app shell
Deps: HAB-001, HAB-025.
Tailwind theme with prototype tokens (TDD §6), self-hosted fonts, app shell, TanStack Router routes, API client + Query setup, MSW handlers from the contract artifact.
**AC:** Home shell matches prototype dark theme; router renders in unit test; Biome/tsc clean.

### HAB-031 — [FE] Home & pack screens
Deps: HAB-030.
Home: pack card grid (glyph, title, "N characters · M sentences", accent color, completion badge). Pack screen: character chips, three activity buttons with subtitles, completion checkmarks, reset-progress with confirm (DELETE), back nav.
**AC:** Visual parity with prototype; Vitest+MSW tests tagged WF-02/WF-07/WF-08 incl. badge and reset flows; e2e home→pack.

### HAB-032 — [FE] TraceCanvas component
Deps: HAB-030, HAB-022.
`hanzi-writer` wrapper per TDD §6: quiz mode with prototype options/colors, container-sized, `charDataLoader` via Query (staleTime Infinity), `{onTotal,onStroke,onComplete}`, imperative hint/redo. Pack-screen prefetch of **all pack + sentence characters**. Expose a test hook for scripted stroke input (pointer events along medians) per VERIFICATION §3.
**AC:** Unit tests verify option wiring + callbacks (mocked writer); manual QA mouse + touch; prefetch covers 很 for Greetings.

### HAB-033 — [FE] Trace activity
Deps: HAB-031, HAB-032.
Prototype trace flow: sequential chars, "2 / 5" + percent bar, pinyin/meaning, "Stroke i of N", completion reveal, Next/Finish, done screen, Hint/Redo. Posts completion; invalidates queries.
**AC:** State machine unit-tested; e2e tagged WF-03 completes 一 via scripted input and asserts the completion POST + badge.

### HAB-034 — [FE] Match activity
Deps: HAB-031.
Prototype match: columns, tap-to-pair, wrong-pair shake + 560 ms reset, lock/fade, counter, timer, "Finished in Ns". Seedable shuffle test hook. Posts completion with duration.
**AC:** Reducer unit tests (select/deselect, same-side, correct, wrong-reset, timing); e2e tagged WF-04 full match → badge.

### HAB-035 — [FE] Sentence activity
Deps: HAB-033.
Prototype sentence flow: cell strip (done/active/pending), translation + pinyin, per-char TraceCanvas, Next character/sentence/Finish, done screen. Handles non-pack chars. Posts completion.
**AC:** Advance state machine unit-tested; e2e tagged WF-05 traces 我很好 (proves non-pack 很 end-to-end).

---

## Epic 4 — Hardening & ship

### HAB-040 — Docker production build & entrypoint
Deps: HAB-021, HAB-033.
Multi-stage Dockerfile (pnpm build → backend serving dist); compose entrypoint: migrate → import → seed → uvicorn, idempotent; named volume; a standalone `db` service usable by the Compose-db dev mode (DEVEX §5). `just compose-up` wrapper.
**AC:** Tagged WF-10: clean-checkout `docker compose up` → trace 你 end-to-end; progress survives restart.

### HAB-041 — Observability & error handling pass
Deps: Epics 2–3.
Request logging with resolved user id; consistent API error envelope; FE error boundaries + recoverable states for stroke-fetch/progress failures; verify every workflow in `src/habagou/workflows.yml` emits its VERIFICATION §5.1 event with correct fields (integration-level assertion).
**AC:** DB kill → readyz fails, clean API errors, FE recoverable state; an automated check confirms event coverage per workflow.

### HAB-042 — E2E regression suite & device pass
Deps: Epic 3.
Consolidated Playwright suite covering WF-02..WF-08 as tagged journeys; desktop + mobile (390×844) projects; e2e harness provisions an ephemeral instance via `just bootstrap`. The suite is **BASE_URL-parameterizable**: default = ephemeral local instance; `just e2e BASE_URL=…` runs the same suite (mutations included) against a deployed environment — this is the staging gate (VERIFICATION §5.3), and the suite resets guest progress it creates. Manual touch pass on one real device noted in PR.
**AC:** Suite green in CI on both viewports, parallel against per-test databases, no flakes (3 consecutive runs); the same suite passes against a local `just compose-up` stack via BASE_URL — the stand-in for staging.

### HAB-043 — Docs & licensing
Deps: HAB-040.
README quickstart verified against reality (devenv path primary, Docker as deploy); `LICENSE-ARPHIC` + attribution; `docs/architecture.md` updated; ADRs for TDD D-1..D-5 + DEVEX decision.
**AC:** Fresh agent/dev: clone → `devenv up` → working app using only the README.

---

## Epic 5 — Verification infrastructure

### HAB-050 — Workflow catalog file
Deps: HAB-001.
`src/habagou/workflows.yml`: catalog per VERIFICATION §2 (id, title). Tests use matching workflow tags.
**AC:** Schema-validated in CI; catalog matches VERIFICATION.md table.

### HAB-051 — Traceability report in CI
Deps: HAB-050, HAB-004, first tagged tests (HAB-021).
Workflow tags are reviewed as part of test coverage. There is no separate traceability verification script.
**AC:** Removing the WF-03 e2e tag makes CI fail with a readable gap report; matrix artifact uploaded.

### HAB-052 — Prod smoke suite
Deps: HAB-042.
`just smoke BASE_URL=…`: read-only Playwright subset (healthz/readyz, WF-02 browse, WF-06 stroke fetch) against any live deployment. No mutations — this is the **production** tier; full mutating verification runs against staging via HAB-042's `just e2e BASE_URL=…` (VERIFICATION §5.3).
**AC:** Passes against a local `just compose-up`; fails cleanly (non-zero, readable) against a broken deployment.

### HAB-053 — Data invariant checker
Deps: HAB-012.
`scripts/check_invariants.py --dsn …`: every published pack's chars + sentence chars exist in corpus; guest user exists; completions reference live users/packs. Emits `invariant_check` events; non-zero exit on violation. Wired as a CI post-integration step and documented as post-deploy/cron.
**AC:** Seeded DB passes; deleting 很 from a fixture corpus makes it fail naming the pack and character.

---

## Suggested sequence

HAB-001 → 002 → 004 → 010 → 011 → 012 → 003 → 013 → 014 → 050 → 020 → 021 → 022 → 023 → 024 → 025 → 051 → 030 → 031 → 032 → 033 → 034 → 035 → 040 → 041 → 042 → 052 → 053 → 043

---

## Appendix — Seed data (extracted from prototype)

Guest user: fixed UUID (choose once, hardcode in seed + tests), `username='guest'`, `display_name='Guest'`, `is_guest=true`.

**Greetings** (glyph 你, `#c4633f`): 你 nǐ you · 好 hǎo good · 我 wǒ I, me · 他 tā he, him · 谢 xiè thanks. Sentences: 你好 (nǐ hǎo, Hello) · 我很好 (wǒ hěn hǎo, I am well) · 谢谢你 (xièxie nǐ, Thank you).

**Numbers** (glyph 三, `#3f8a86`): 一 yī one · 二 èr two · 三 sān three · 四 sì four · 五 wǔ five. Sentences: 一二三 (yī èr sān, One two three) · 三个人 (sān ge rén, Three people).

**Family** (glyph 妈, `#5b5fa8`): 妈 mā mom · 爸 bà dad · 哥 gē older brother · 姐 jiě older sister · 弟 dì younger brother. Sentences: 爸爸 (bàba, Dad) · 我哥哥 (wǒ gēge, My older brother).

**Food & drink** (glyph 茶, `#b5852e`): 米 mǐ rice · 饭 fàn meal · 茶 chá tea · 水 shuǐ water · 鱼 yú fish. Sentences: 米饭 (mǐfàn, Cooked rice) · 喝茶 (hē chá, Drink tea).

Sentence-only characters requiring corpus presence: 很, 个, 人, 喝 (plus all pack chars). These must be in every test fixture subset.
