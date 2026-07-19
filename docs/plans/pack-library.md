# Plan — Pre-populated pack library with per-user enablement

**Status: executed** (see execution notes below). Self-contained
implementation plan for an implementing agent. Ordered tickets with
dependencies and acceptance criteria (AC), following the conventions of
[tickets.md](../tickets.md).

> **Execution notes.** Landed as planned, with four deviations. (1) The four
> original starter packs live in their topical categories (basics,
> numbers-time, people-family, food-drink) rather than all in `basics`; the
> LIB-06 distribution was adjusted so each of those categories gained one
> fewer new pack (still exactly 50 new, 54 total). (2) The stroke corpus
> gained a second sha-pinned mirror (the immutable npm registry tarball)
> because sandboxed/CI egress policies can block GitHub tarball downloads;
> `ensure_archive` tries GitHub then npm, and the production `Dockerfile` now
> copies `data/` for the release seed step. (3) The integration-test template
> derives its stroke subset from `data/packs` automatically (union with the
> fixture file) instead of hand-maintaining `stroke_subset.txt`. (4)
> `GET /api/v1/progress/summary`'s `packs_total` now counts *enabled* packs —
> the user's active curriculum — rather than all global packs, as a direct
> consequence of the per-user curriculum (LIB-05).

Branch: `claude/pack-library-prepopulated-hmjysh`. Suggested commit split: one
commit per ticket (LIB-01 … LIB-09), docs folded into each; LIB-06 (the 50
authored packs) is its own commit so content review is isolated from code
review.

## Product intent

1. Grow from 4 curated packs to a **library of ~50+ curated packs**, organized
   by category, that users browse and **enable** individually. Only enabled
   packs appear on the home bench and feed the Learning Path.
2. **Starter packs are auto-enabled** (decision made): a small set of packs
   marked `starter` is on for every user — existing and new, including guests
   — without any per-user writes at signup.
3. **AI pack creation becomes the fallback**, not the front door: the
   "Create a pack" card moves off the home screen into the library (bottom CTA
   and empty-search state). The generation flow itself is unchanged.
4. The **first 50 library packs are authored offline by a Claude subagent**
   (LIB-06) and committed as reviewed data files. The runtime OpenRouter
   generation agent is **not** used for this — library content is static,
   vetted data; runtime AI remains only for user-initiated custom packs.

## Required reading for the implementing agent

- `CLAUDE.md` (gates, layering: routers → services → repositories; DTOs are
  Pydantic, separate from DB models)
- `docs/architecture.md`, `docs/api.md`,
  `docs/adrs/0009-pack-ownership.md` (two-tier ownership),
  `docs/adrs/0008-review-state-as-rebuildable-projection.md`
- Code: `src/habagou/models/packs.py`, `src/habagou/repositories/packs.py`,
  `src/habagou/services/packs.py`, `src/habagou/routers/v1/packs.py`,
  `src/habagou/services/path.py`, `scripts/seed.py`,
  `scripts/import_stroke_data.py`, `scripts/check_invariants.py`, frontend
  `src/habagou/web/frontend/src/routes/packs.index.tsx`,
  `src/routes/packs.$packId.tsx`, `src/lib/api.ts`, `src/mocks/handlers.ts`,
  e2e `tests/e2e/pack-helpers.ts`

## Design decisions (already made — do not relitigate)

- **Enablement is a lazy per-user overlay, not eager rows.** New table
  `user_pack_settings (user_id, pack_id, enabled bool, updated_at)` where
  *absence of a row means "use the default"*, and the default for a global
  pack is `packs.starter`. Effective enablement for a global pack is
  `COALESCE(user_pack_settings.enabled, packs.starter)`; owned packs are
  always enabled and never have rows. This gives starter auto-enablement for
  every existing and future user (guests included) with **no signup hook and
  no backfill migration**. Disabling a starter pack writes `enabled=false`;
  enabling a library pack writes `enabled=true`.
- **Disable is the user action on curated packs; delete stays forbidden**
  (`PackDeletion.FORBIDDEN` unchanged). Disabling is non-destructive:
  `review_states` and `activity_completions` are kept (they cascade only on
  pack delete), so re-enabling resumes progress. *Pending* `path_items` for
  the disabled pack are pruned (completed ones are history and stay).
- **Catalog metadata lives on `Pack` plus a tiny `categories` table.**
  `categories (slug PK, title, sort_order)`; `packs` gains
  `category_slug` (nullable FK, NULL for user packs), `description`
  (nullable), `starter` (bool, server default false). The **existing four
  seed packs are the starter set** — re-seeded with categories,
  descriptions, and `starter=true`, keeping their slugs, so current users
  and current e2e flows see no behavioral change on deploy.
- **`GET /api/v1/packs` (home bench) changes semantics** to owned + 
  effectively-enabled global packs. The per-pack progress aggregate in
  `PackService._summary` is acceptable there (short list). The new
  **`GET /api/v1/library`** returns *all* global packs grouped by category
  with a slim DTO (no progress aggregates — avoid the N+1 across hundreds of
  packs) plus an `enabled` flag.
- **The Learning Path curriculum becomes per-user**:
  `PackRepository.list_global_with_content()` is replaced by an
  enablement-aware query. Ordering stays `sort_order, id` (sort_order now
  orders within a category for the library; the flat ordering the scheduler
  sees remains stable and global).
- **Curated content is data, not Python.** Packs move from the inline
  `SEED_PACKS` tuple to `data/packs/categories.json` +
  `data/packs/<category>/<slug>.json`. `scripts/seed.py` loads these files
  and upserts by slug (already idempotent), so shipping new packs = merging
  JSON + redeploy (bootstrap re-runs seed). A committed corpus index
  (`data/corpus_index.txt`, generated from the pinned hanzi-writer-data
  release) lets a DB-free validation script run in `just gate`/CI.
- **Library authorship is build-time Claude, never runtime OpenRouter.**
  LIB-06 is executed by spawning a general-purpose subagent that writes the
  JSON files and runs the validator until clean; content lands as a reviewable
  diff.
- **Workflow events reuse WF-02 ("Browse library")**: new events
  `library_served` and `pack_enablement_changed` under WF-02. No new
  workflow id.

---

## LIB-01 — [BE] Schema: categories, pack catalog columns, user_pack_settings

Deps: none.

- Alembic migration `0007_pack_library.py`:
  - `categories`: `slug TEXT PK`, `title TEXT NOT NULL`,
    `sort_order INTEGER NOT NULL`.
  - `packs`: add `category_slug TEXT NULL REFERENCES categories(slug)`
    (ON DELETE RESTRICT — deleting a category with packs is a seed-pipeline
    bug), `description TEXT NULL`, `starter BOOLEAN NOT NULL DEFAULT false`.
    Index `ix_packs_category` on `category_slug`.
  - `user_pack_settings`: `user_id UUID FK users.id ON DELETE CASCADE`,
    `pack_id UUID FK packs.id ON DELETE CASCADE`, `enabled BOOLEAN NOT NULL`,
    `updated_at timestamptz NOT NULL`, `PRIMARY KEY (user_id, pack_id)`.
- SQLAlchemy models: `Category` (new module or in `models/packs.py` — packs
  bounded context), `UserPackSetting`, new `Pack` columns + relationships.
- No data backfill in the migration: values arrive via seed (LIB-02); the
  server default `starter=false` is safe because the lazy-overlay semantics
  only take effect once LIB-03 lands, and LIB-02/LIB-03 ship in the same
  release as this migration.

**AC:** upgrade from empty DB and from a 0006 DB + clean downgrade;
integration test round-trips a category, a pack with catalog fields, and a
user setting row; cascade test: deleting a user removes their settings rows,
deleting a pack removes its settings rows.

## LIB-02 — [BE] Curated-content data pipeline (files → seed)

Deps: LIB-01.

- `data/packs/categories.json`: `[{"slug","title","sort_order"}, ...]`.
- `data/packs/<category-slug>/<pack-slug>.json`, schema (one pack per file):

  ```json
  {
    "slug": "greetings",
    "title": "Greetings",
    "glyph": "你",
    "color": "#c4633f",
    "category": "basics",
    "description": "Say hello, introduce yourself, and thank people.",
    "starter": true,
    "sort_order": 1,
    "characters": [{"hanzi": "你", "pinyin": "nǐ", "meaning": "you"}],
    "sentences": [{"hanzi": "你好", "pinyin": "nǐ hǎo", "translation": "Hello"}]
  }
  ```

- Port the four existing `SEED_PACKS` into files **keeping their slugs**
  (`greetings`, `numbers`, `family`, `food-drink`), all with
  `starter=true`, under sensible categories. Delete the inline tuple;
  `scripts/seed.py` gains a loader (`load_seed_packs()` returning the same
  `SeedPack` dataclasses + `SeedCategory`) and upserts categories before
  packs. `upsert_pack` additionally writes `category_slug`, `description`,
  `starter`. Seeding never deletes packs absent from the files (removal is a
  deliberate manual operation, keeps user progress safe).
- `scripts/import_stroke_data.py`: add `--write-index data/corpus_index.txt`
  emitting the sorted hanzi of the full pinned corpus (one per line,
  generated from the cached tarball without a DB); commit the generated file.
- `scripts/validate_pack_data.py` (no DB, runs in `just gate` and CI): every
  pack file parses against the schema (pydantic model); slugs unique;
  `category` exists in `categories.json`; `(category, sort_order)` and glyph
  colors sane (`#rrggbb`); every member hanzi **and every sentence glyph** is
  in `data/corpus_index.txt`; pack glyph is one of its member hanzi; 4–10
  characters and 2–5 sentences per pack; sentences only use corpus glyphs.
  Wire into the `gate` just target.

**AC:** `just bootstrap` from empty DB seeds categories + the four packs with
`starter=true` and categories set; re-run idempotent (`seed_database` result
unchanged); validator passes on the committed data and demonstrably fails on
a fixture pack referencing a non-corpus glyph, a duplicate slug, and an
unknown category; `bootstrap_completed` event now also reports
`categories` count.

## LIB-03 — [BE] Enablement-aware repositories & services

Deps: LIB-01.

- `PackRepository`:
  - `list_visible(user_id)` → renamed intent: **bench query**. Global packs
    join `LEFT JOIN user_pack_settings` and filter
    `COALESCE(ups.enabled, packs.starter) IS TRUE`; owned packs unchanged.
  - New `list_library(user_id)`: all global packs (+counts) with the
    computed `enabled` bool and catalog fields, ordered by category
    sort_order, then pack sort_order. Single query, no progress aggregates.
  - `list_global_with_content()` → `list_enabled_with_content(user_id)`:
    same eager-loading, adds the enablement predicate above (used by the
    path service, LIB-05).
  - `get_visible` unchanged (a disabled global pack stays *viewable* by
    direct link — the library links to it).
- New `UserPackSettingRepository` (or methods on `PackRepository`):
  `upsert(user_id, pack_id, enabled)`.
- `PackService`:
  - `set_enabled(pack_id, user, enabled) -> PackEnablement` enum
    (`NOT_FOUND` — not visible; `OWNED` — owned packs can't be toggled;
    `UPDATED`). On `enabled=False`, prune pending path items (LIB-05 exposes
    the repository method; wire the call here in the same transaction).
  - `list_library(user) -> LibraryDTO` grouping packs under ordered
    categories.
- `PackSummaryDTO` gains `enabled: bool` (always true on the bench, but the
  detail view reuses the DTO and needs the real value) and
  `starter: bool`; `PackDetailDTO` inherits. New `LibraryDTO`,
  `LibraryCategoryDTO`, `LibraryPackDTO` (id, title, glyph, color,
  description, char_count, sentence_count, starter, enabled) in
  `dtos/packs.py`.

**AC:** integration tests: user with no settings rows sees exactly starter +
owned packs on the bench; enabling a non-starter library pack adds it;
disabling a starter pack removes it; another user's settings don't leak;
library listing returns every global pack exactly once, grouped and ordered,
with correct `enabled` flags, in one repository call (assert query count if
harness allows); owned packs never appear in the library.

## LIB-04 — [BE] Library & enablement API

Deps: LIB-03.

- `GET /api/v1/library` → `LibraryDTO`; emits `library_served` (WF-02,
  fields: `pack_count`, `category_count`, `user_id`).
- `PUT /api/v1/packs/{pack_id}/enabled`, body `{"enabled": bool}` →
  204; 404 when not visible; 409 when the pack is owned (owned packs are
  always enabled). Idempotent. Emits `pack_enablement_changed` (WF-02,
  fields: `pack_id`, `enabled`, `user_id`).
- `just openapi-export` to regenerate `docs/api/openapi-v1.json` and
  `src/lib/api-types.ts`; document both endpoints in `docs/api.md`.

**AC:** contract tests tagged WF-02: enable → bench includes pack; disable →
bench excludes it, detail still 200; enable an owned pack → 409; unknown or
other-user pack → 404; `just openapi-check` green.

## LIB-05 — [BE] Learning Path honors enablement

Deps: LIB-03.

- `services/path.py`: build the curriculum from
  `list_enabled_with_content(user_id)`. An empty enabled set yields an empty
  batch (no crash) — the frontend path view already tolerates an empty queue;
  verify and add a test.
- `PathRepository.delete_pending_for_pack(user_id, pack_id)`: delete path
  items for that pack not yet completed; renumber is unnecessary (positions
  keep gaps; queue ordering is by position). Called from
  `PackService.set_enabled(..., enabled=False)` in the same transaction.
- Review states are left untouched on disable (rebuildable projection, ADR
  0008); the scheduler naturally stops surfacing units of packs not in the
  curriculum.

**AC:** integration tests: user's queue only ever contains enabled packs'
items; disabling removes that pack's pending items but keeps completed ones
and keeps review_states rows; re-enabling resumes scheduling (units the user
completed are not re-introduced as `new`); two users with different
enablement sets get different queues from the same global catalog.

## LIB-06 — [Content] Author the first 50 library packs (subagent task)

Deps: LIB-02 (schema + validator must exist first).

**Execution note: this ticket is performed by spawning a general-purpose
Claude subagent** (e.g. the Agent tool / Task subagent), *not* by the app's
runtime OpenRouter generation agent and not by hand. The subagent writes the
JSON files and iterates against `scripts/validate_pack_data.py` until clean;
the diff is then human-reviewed like any content PR.

Subagent brief (include verbatim in the spawn prompt, plus pointers to
`data/packs/` and the validator):

- Author **50 pack JSON files** under `data/packs/<category>/`, conforming to
  the LIB-02 schema, in these categories (create `categories.json` entries
  with this order): `basics` (the 4 existing starter packs live here — do not
  modify them; add ~4 more), `numbers-time` (~6), `people-family` (~5),
  `food-drink` (~6), `places-travel` (~6), `daily-life` (~6), `nature-weather`
  (~5), `body-health` (~4), `school-work` (~4), `verbs-in-action` (~4).
  Counts are guidance; total new packs must be exactly 50.
- Difficulty arc: roughly HSK 1–2 vocabulary early in each category,
  HSK 2–3 later; `sort_order` unique within a category and reflecting that
  arc, starting after any existing packs in the category.
- Each pack: 5–8 characters with accurate tone-marked pinyin (nǐ not ni3)
  and concise English meanings; 2–4 short sentences (2–6 glyphs) composed
  **only** of corpus glyphs, natural and thematically on-pack, with tone-marked
  pinyin and translations; `glyph` = the most iconic member character;
  `color` = a hex color harmonizing with the existing palette
  (`#c4633f`, `#3f8a86`, `#5b5fa8`, `#b5852e` — stay in that muted range,
  vary hue per category); one-line `description` in the product voice
  ("Say hello, introduce yourself, and thank people.").
- Simplified characters only. `starter` is `false` for all 50 (the starter
  set remains the original four). No duplicate slugs; avoid re-teaching the
  same character as a *member* across packs where reasonable (sentences may
  reuse any corpus glyph freely).
- Loop: write files → run `uv run python scripts/validate_pack_data.py` →
  fix → repeat until exit 0. Then run the LIB-02 seed integration test.

**AC:** validator exits 0; `just bootstrap` on a fresh DB seeds 54 packs /
10 categories and re-runs idempotently; spot-review confirms pinyin tone
marks and sentence naturalness on a random 10-pack sample; bench for a fresh
user still shows exactly the 4 starter packs.

## LIB-07 — [FE] Library route + home bench changes

Deps: LIB-04 (types regenerated). Frontend-only.

- New route `src/routes/packs.library.tsx` (`/packs/library` — TanStack
  Router prefers the static segment over `packs.$packId`, add a route test
  proving it): fetches `GET /api/v1/library` once (TanStack Query), renders
  category sections in order; each pack row shows glyph tile, title,
  description, counts, and an **Enable/Enabled toggle** (optimistic mutation
  on `PUT .../enabled`, invalidates `["packs"]` and `["library"]`). A
  client-side search input filters across pack title/description/character
  meanings (no server round-trip). Bottom CTA and empty-search state link to
  `/packs/generate`, shown only when `generation.enabled` (reuse the
  status-probe pattern from `packs.index.tsx`).
- `packs.index.tsx` (home bench): list unchanged (now naturally shorter —
  enabled + owned only); replace the `CreatePackCard` slot with a
  **"Browse the library"** card (glyph 书 or similar, links to
  `/packs/library`; not gated on generation). The AI card moves entirely
  into the library per product intent.
- `src/lib/api.ts`: `getLibrary`, `setPackEnabled`; `src/mocks/handlers.ts`:
  handlers for both.

**AC:** unit tests (`packs.library.test.tsx`): renders categories in order;
toggle fires the PUT and optimistically flips; search narrows rows; AI CTA
hidden when generation disabled. `packs.index.test.tsx` updated: library
card always present, AI card gone. `just gate-fe` green.

## LIB-08 — [FE] Enable/disable from pack detail

Deps: LIB-04. Frontend-only.

- `packs.$packId.tsx`: for global packs, show an Enable button when
  `!enabled` (prominent — this is the library's deep-link landing) and a
  low-emphasis "Remove from my packs" (disable) when enabled, with copy
  clarifying progress is kept. Owned packs keep the existing Delete flow;
  no toggle.
- Disabled global packs remain fully viewable (per LIB-03 `get_visible`),
  so library users can preview before enabling.

**AC:** unit tests: enable button on a disabled global pack fires PUT and
updates state; disable confirms and returns to `/packs`; owned pack shows
Delete, never the toggle.

## LIB-09 — [E2E + docs] End-to-end flows, docs, ADR

Deps: LIB-05, LIB-06, LIB-07, LIB-08.

- e2e `tests/e2e/library.spec.ts` (reuse `pack-helpers.ts`): fresh user sees
  only starter packs on the bench; opens library, enables a pack from a
  non-basics category, sees it on the bench and traceable; disables a
  starter pack, bench shrinks, progress badge state survives re-enable.
  Update `home-pack.spec.ts`/`path.spec.ts` if bench assumptions changed.
- Docs: `docs/architecture.md` (enablement overlay + data pipeline),
  `docs/api.md` (library + enabled endpoints), `CLAUDE.md` project-structure
  note for `data/packs/`; new `docs/adrs/0012-pack-library-enablement.md`
  recording the lazy-overlay decision (absence = starter default) and
  build-time-vs-runtime AI content split.

**AC:** `just gate-expensive` green; ADR merged; api.md matches exported
OpenAPI.

---

## Rollout & risk notes

- **Single-release safety:** LIB-01..LIB-03 must deploy together (the
  migration alone leaves `starter=false` everywhere; only the seed +
  enablement-aware queries make the bench correct). Since bootstrap runs
  migrate → import → seed in one pass, a normal deploy satisfies this.
- **No behavior change at cutover** for existing users: all four current
  packs become starter, and lazy semantics enable them by default — the
  bench renders identically before LIB-06 lands.
- **Scale ceiling:** at ~50–300 packs a single un-paginated library payload
  (slim DTO) is fine; revisit pagination/search-server-side only past that.
- **Content removal policy:** the seed pipeline never deletes packs; retiring
  a library pack is a manual migration decision (users may have progress).
