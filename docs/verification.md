# Habagou — Verification & Validation (VERIFICATION)

| | |
|---|---|
| Status | **Final v1.0** — approved for implementation |
| Depends on | [PRD](product/prd.md), [TDD](technical/tdd.md), [DEVEX](devex.md) |
| Goal | (1) name the workflows, (2) keep test coverage tied to those workflows, (3) instrument each so prod shows it working |

## 1. Approach

The unit of verification is the **workflow** — a named, user- or operator-visible journey with preconditions and postconditions. Everything hangs off the workflow ID:

- Tests are **tagged** with the workflow(s) they prove (`@pytest.mark.workflow("WF-03")`, Playwright `@wf-03` tag).
- Production instrumentation emits **the same IDs** (`workflow="WF-03"` field on structured events).

This gives one vocabulary from PRD → test → prod dashboard without a separate
traceability enforcement layer.

## 2. Workflow catalog

The machine-readable catalog lives at `src/habagou/workflows.yml` and is
packaged with the application. It is the single source of truth for workflow
IDs and titles.

Each workflow gets a short spec section in this doc as it's implemented (steps, invariants, edge cases). The catalog is the contract; PRD FRs map into it (e.g. FR-4..7 ⊂ WF-03).

## 3. Test layers and what each is allowed to prove

| Layer | Proves | Explicitly does NOT prove | Speed / where |
|---|---|---|---|
| **Unit (BE)** | Pure logic: progress aggregation, grapheme splitting, seed validation, DTO mapping | Anything about Postgres or HTTP | ms; every `just gate` |
| **Unit (FE)** | Activity state machines (trace idx/stroke/complete; match select/wrong/lock; sentence advance), component wiring against **MSW handlers derived from the OpenAPI schema** | Real network, real writer rendering | ms; every `just gate` |
| **Integration (BE)** | Repositories + migrations against real Postgres; API contracts at the ASGI level with real DB; import/seed scripts incl. failure paths | Browser behavior | s; `just gate-expensive`, CI |
| **E2E (Playwright)** | Full workflows through the real stack (real backend, real DB, real hanzi-writer in a real browser), desktop + mobile viewports | — | 10s–min; CI on PRs to main |
| **E2E (staging)** | The **full** Playwright suite, mutating workflows included (WF-03/04/05/08), against the staging deployment: `just e2e BASE_URL=…` | — (staging authenticated test data is disposable; suite may reset progress freely) | every staging deploy |
| **Smoke (prod)** | Read-only subset of e2e against **production** (`just smoke BASE_URL=…`): healthz/readyz, login screen, anonymous session probe, unauthenticated API gate | Mutating workflows and provider login | post-deploy, cron |
| **Invariant checks** | Data-level truths in any live DB: every published pack's chars **and sentence chars** exist in corpus; no completion rows reference missing users/packs | Behavior | `scripts/check_invariants.py`; post-deploy, cron |

Cross-cutting rules:

- **Contract single-source**: the backend OpenAPI schema is exported as a checked-in artifact; a CI step fails if it drifts from code, and FE MSW handlers/types are validated against it. FE unit tests therefore cannot pass against a fictional API.
- **Determinism**: e2e uses fixture-friendly content — 一 (one stroke) for trace-input tests, seeded RNG for match shuffle (test hook), scripted pointer events along stroke medians (Hanzi Writer's quiz accepts median-following paths; a writer stub is the fallback if flake appears).
- **Test data isolation** (uses DEVEX §2 infrastructure): integration/e2e fixtures create a **per-test database** inside the instance's cluster via `CREATE DATABASE test_<id> TEMPLATE habagou_test_base`, where the template DB is migrated+seeded once per session with the fixture corpus subset. Tests run fully parallel with zero shared state; teardown is `DROP DATABASE`.
- **The e2e harness provisions instances exactly like a developer does** (same bootstrap path), so "works on my machine" and "works in CI" are the same claim.

## 4. Workflow Coverage

Kept intentionally lightweight:

1. `src/habagou/workflows.yml` lists workflow IDs and titles.
2. Tests declare workflows via marks/tags.
3. Code review checks that workflow changes add or update meaningful tests.

There is deliberately no CI script that proves every workflow has a required
layer matrix. The test suite should cover the workflows, but the workflow labels
are a shared vocabulary, not an enforcement framework.

### WF-11 — Review dashboard

Steps:

1. Learner opens `/progress`.
2. The frontend requests `GET /api/v1/progress/summary` with the browser's
   `tz_offset_minutes`.
3. The API resolves the current user, aggregates that user's
   `activity_completions` by local day, and returns the current streak, best
   streak, daily goal, 45-day heatmap window, and next milestone.
4. The progress screen renders the goal ring, streak chip, collapsible
   heatmap, milestone card, pack progress, and "Practice now" link.

Invariants:

- Streaks count consecutive local days with at least three completions.
- An unfinished today does not break an existing streak; current streak anchors
  at yesterday unless today has met the goal.
- Summary data is derived only from the append-only `activity_completions` log.
- All aggregation is scoped by `get_current_user`, so other users' rows never
  affect the dashboard.

Edge cases:

- Empty history returns a zero-state summary with 45 zero-filled activity days.
- `tz_offset_minutes` shifts UTC instants into the learner's local day before
  grouping.
- A sub-target day contributes to heatmap intensity but not to streak length.

### WF-12 — View path

Steps:

1. Learner opens the app (or scrolls the Path stream) and the frontend
   requests `GET /api/v1/path` with an optional `cursor`.
2. If fewer than the pending window (default 10) of not-yet-done items exist
   for the current user, the API generates more items at the tail of the
   queue using current review state before responding.
3. The API returns the queue page (`items`, `next_cursor`, `daily`, `streak`,
   `due`), scoped by `get_current_user`.
4. The Path screen renders done/current/locked nodes, the goal-ring hero,
   streak, and due counts, and offers the current item as the next lesson.

Invariants:

- The Path never returns an empty queue — if nothing is due and nothing new
  remains, generation falls back to early review of the soonest-due/weakest
  units (see `docs/product/prd-path.md` FR-20).
- `items` ordering is: today's done items, then current, then pending, by
  `position`.
- All reads are scoped by `get_current_user`; other users' items and review
  state never affect the queue.

Edge cases:

- A brand-new learner with no review state yet receives an all-`new`-kind
  queue in curriculum order.
- Paging past `next_cursor` extends the queue rather than returning an empty
  page.

### WF-13 — Complete path item

Steps:

1. Learner finishes the current path item's activity in the item-scoped
   lesson runner (`/lesson/$itemId`).
2. The frontend posts `POST /api/v1/path/items/{item_id}/complete` with
   `duration_ms`.
3. The API appends a `source='path'` row to `activity_completions` (with
   `path_item_id` set) and applies the Leitner-ladder update to every
   reviewable unit in the item, updating `review_states` transactionally in
   the same operation.
4. The API recomputes daily goal/streak (now including this completion) and
   returns `{ daily, streak, item_id, next_item_id }`.
5. The frontend returns to the Path, marks the node done, advances the
   current node, and updates the goal ring.

Invariants:

- A `source='path'` completion row always has `path_item_id` set (see
  `docs/adrs/0008-review-state-as-rebuildable-projection.md`).
- Completing a path item never writes to or changes whole-pack activity
  completion state; `per_pack_aggregate` (filtered to `source='pack'`) is
  unaffected.
- Every reviewable unit in the completed item gets `reps += 1` and a new
  `due_at` per the ladder (`LADDER = (1, 3, 7, 14, 30)` days).

Edge cases:

- Completing an already-completed item returns 409 and does not double-apply
  the ladder update.
- Completing an unknown `item_id` (wrong user or nonexistent) returns 404.
- A completion that pushes the learner past the daily goal still reports the
  true `daily.completed` count (uncapped), matching `daily.target`.

### WF-14 — Review resurfacing

Steps:

1. A reviewable unit's `due_at` (set by a prior WF-13 completion) elapses.
2. On a subsequent `GET /api/v1/path` (WF-12), queue generation selects that
   unit's due reviewable unit ahead of new material (oldest `due_at` first,
   per the generation batch rule) and materializes a `kind='review'` path
   item covering it.
3. The learner sees the review item in the stream like any other path item
   and completes it via WF-13, which re-advances the unit on the ladder.

Invariants:

- A reviewable unit only resurfaces as a review item once its `due_at` has
  passed relative to generation time.
- Review generation strictly precedes new-material generation within a batch
  (due reviews first).
- `review_states` used for resurfacing decisions is always derivable by
  replaying `activity_completions` (the rebuild-from-events property from
  ADR-0008).

Edge cases:

- A unit backdated far past due still resurfaces exactly once per due cycle,
  not repeatedly, until it is completed again.
- A unit that has never been completed (no `review_states` row) is never
  treated as due — it can only appear as `kind='new'`.

### WF-15 — Generate practice pack

Steps:

1. A signed-in learner posts a topic to `POST /api/v1/generation/draft`.
2. The API meters the request against the caller's hourly quota, then runs the
   generation agent, which grounds every candidate glyph against the stroke
   corpus (tool + output validator) before returning a corpus-valid draft plus
   the conversation history for client-side refinement turns.
3. The learner optionally refines across turns, then posts the finalized draft
   to `POST /api/v1/generation/packs`, which persists it as a pack they own
   (re-validating every glyph against the corpus at the repository layer).

Invariants:

- Every glyph in a drafted or saved pack — members and each sentence glyph —
  exists in the stroke corpus; the corpus is the only source of truth.
- Draft generation is capped per user in a fixed one-hour window (default 10;
  see `services.rate_limit`). The counter increments on every authenticated
  attempt, before the billed model call, so repeated failures still consume
  quota. The cap is in-memory and per-process (single-machine deployment).
- Saving is gated only by authentication and corpus validity, not the draft cap.

Edge cases:

- An over-quota draft returns 429 `rate_limited` and emits
  `pack_draft_generated` with `outcome=error`.
- Generation with no provider configured returns 503; a provider failure
  returns 502; a malformed client-held history returns 422. Each emits
  `pack_draft_generated` with `outcome=error`.
- Saving a draft that references a non-corpus glyph returns 422 and emits
  `generated_pack_saved` with `outcome=error`.

### WF-16 — Conversation practice

Steps:

1. A signed-in learner posts a message (their chosen topic on the first turn,
   chat input after that) plus the client-held history to
   `POST /api/v1/practice/turn`.
2. The API meters the request against the caller's hourly practice quota, then
   runs the practice agent, which returns a structured tutor turn: 1–8
   per-sentence segments (hanzi/pinyin/English) and an optional English aside.
3. The client renders the segments (English hidden behind a per-segment tap),
   holds the updated history, and replays it on the next turn.

Invariants:

- Conversations are ephemeral and client-held: no server-side conversation
  store, no rows written anywhere in a turn (ADR 0011).
- Practice turns are capped per user in a fixed one-hour window (default 60),
  independent of the generation cap, counted on every authenticated attempt
  before the billed model call. In-memory and per-process, like generation.
- Every segment carries all three renderings, so tap-for-translation never
  needs a second model call.

Edge cases:

- An over-quota turn returns 429 `rate_limited`; practice with no provider
  configured returns 503; a provider failure returns 502; a malformed
  client-held history returns 422. Each emits `practice_turn_completed` with
  `outcome=error`.

## 5. Production instrumentation

Same vocabulary, three signal types. All flow through one tiny helper (`src/habagou/events.py`) so field names cannot drift.

### 5.1 Structured events (structlog, JSON — the floor)

One canonical event per workflow outcome, always with: `workflow`, `outcome` (`ok|error`), `duration_ms`, plus context:

| Event | Workflow | Extra fields |
|---|---|---|
| `bootstrap_completed` | WF-01 | `chars_imported`, `packs_seeded`, `migrations_applied` |
| `pack_list_served` / `pack_served` | WF-02 | `pack_slug`, `pack_count` |
| `pack_deleted` | WF-02 | `pack_id`, `user_id` (`outcome=error` with `reason` on not-found/curated) |
| `activity_completed` | WF-03/04/05 | `activity`, `pack_slug`, `user_id`, `duration_ms` (client-reported) |
| `strokes_served` | WF-06 | `hanzi`, `cache_hit` (if server-side cache added), `found` |
| `strokes_missing` | WF-06 | `hanzi` — **leading indicator of corpus/seed drift; alertable at rate > 0** |
| `progress_viewed` | WF-07 | `pack_slug`, `user_id` |
| `progress_reset` | WF-08 | `pack_slug`, `deleted_count` |
| `deploy_ready` | WF-10 | `database` |
| `progress_summary_viewed` | WF-11 | `user_id`, `current_streak` |
| `path_viewed` | WF-12 | `user_id`, `item_count`, `due_new`, `due_review` |
| `path_item_completed` | WF-13/14 | `activity`, `pack_slug`, `kind`, `user_id`, `duration_ms` (client-reported) |
| `pack_draft_generated` | WF-15 | `user_id`, `character_count` (`outcome=error` on rate-limit/unconfigured/provider failures) |
| `generated_pack_saved` | WF-15 | `user_id`, `pack_id` |
| `practice_turn_completed` | WF-16 | `user_id`, `segment_count` (`outcome=error` on rate-limit/unconfigured/provider failures) |
| `auth_signed_in` | WF-AUTH-SIGN-IN | `user_id`, `provider` |
| `auth_signed_out` | WF-AUTH-SIGN-OUT | `user_id`, `provider` |
| `auth_gate_rejected` | WF-AUTH-GATE | `path` |
| `invariant_check` | — | `check`, `outcome`, `violations` |

Note `activity_completed` is *derived from the same write* that creates the `activity_completions` row — the business table is itself instrumentation; the log event just makes it streamable. Likewise, `path_item_completed` is derived from the same write that appends the `source='path'` completion row and updates `review_states`; WF-14 (review resurfacing) has no dedicated event of its own — it is proven by a later `path_viewed`/`path_item_completed` pair on a `kind='review'` item, the same way WF-03/04/05 share `activity_completed`.

### 5.2 Traces (OpenTelemetry + optional Logfire)

FastAPI requests, SQLAlchemy queries, and Pydantic AI calls are instrumented with
Logfire and share its OpenTelemetry provider with the optional generic OTLP
exporter. Logfire export only occurs when `LOGFIRE_TOKEN` is present; tokenless
local/test startup is a supported no-export path. System metrics instrumentation
is intentionally not enabled. Pydantic AI spans include the full generation
conversation so user messages, replayed history, tool activity, and model
responses can be reviewed in Logfire. Workflow outcomes are emitted as structured events from
`events.py`.

### 5.3 Environment tiers & live validation loops

| Environment | Verification | Mutations allowed |
|---|---|---|
| Local / CI | Full suite against ephemeral per-test databases | Yes (ephemeral) |
| **Staging** | **Full e2e suite** (`just e2e BASE_URL=…`) after every staging deploy — same tagged workflows, real deployed stack | Yes — staging authenticated test data is disposable; the suite resets it |
| Production | `just smoke BASE_URL=…` (read-only: health, login, anonymous auth/session gate) + `uv run python scripts/check_invariants.py --dsn "$DATABASE_URL"` | No |

- **Staging deploy gate**: a staging deploy is done when the full e2e suite passes against it; a prod deploy is done when smoke + invariants pass against it. Both runnable on cron thereafter.
- **Dashboards** (whatever the sink — Grafana/Loki or hosted): one row per workflow, fed by structured workflow events. "Is WF-03 working in prod?" = nonzero ok-rate, ~zero error-rate, sane p95, zero `strokes_missing`.
- **Mutating verification lives in staging** (above), not prod: driving WF-03
  against prod would require a dedicated synthetic account and provider
  credentials. Revisit prod synthetics when that account exists.

## 6. Verification gate summary

| Gate | Contents | When |
|---|---|---|
| `just gate` | fmt, lint, typecheck, unit (BE+FE), OpenAPI drift check | every commit / pre-push |
| `just gate-expensive` | gate + integration + e2e (parallel, per-test DBs) | pre-merge / CI PR |
| `just e2e BASE_URL=…` | full mutating e2e vs staging | every staging deploy |
| `just smoke BASE_URL=…` + `uv run python scripts/check_invariants.py --dsn "$DATABASE_URL"` | read-only prod validation | post-deploy, cron |
