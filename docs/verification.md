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

## 5. Production instrumentation

Same vocabulary, three signal types. All flow through one tiny helper (`src/habagou/events.py`) so field names cannot drift.

### 5.1 Structured events (structlog, JSON — the floor)

One canonical event per workflow outcome, always with: `workflow`, `outcome` (`ok|error`), `duration_ms`, plus context:

| Event | Workflow | Extra fields |
|---|---|---|
| `bootstrap_completed` | WF-01 | `chars_imported`, `packs_seeded`, `migrations_applied` |
| `pack_list_served` / `pack_served` | WF-02 | `pack_slug`, `pack_count` |
| `activity_completed` | WF-03/04/05 | `activity`, `pack_slug`, `user_id`, `duration_ms` (client-reported) |
| `strokes_served` | WF-06 | `hanzi`, `cache_hit` (if server-side cache added), `found` |
| `strokes_missing` | WF-06 | `hanzi` — **leading indicator of corpus/seed drift; alertable at rate > 0** |
| `progress_viewed` | WF-07 | `pack_slug`, `user_id` |
| `progress_reset` | WF-08 | `pack_slug`, `deleted_count` |
| `admin_action` | WF-09 | `action`, `pack_slug`, `authorized` |
| `deploy_ready` | WF-10 | `database` |
| `progress_summary_viewed` | WF-11 | `user_id`, `current_streak` |
| `auth_signed_in` | WF-AUTH-SIGN-IN | `user_id`, `provider` |
| `auth_signed_out` | WF-AUTH-SIGN-OUT | `user_id`, `provider` |
| `auth_gate_rejected` | WF-AUTH-GATE | `path` |
| `invariant_check` | — | `check`, `outcome`, `violations` |

Note `activity_completed` is *derived from the same write* that creates the `activity_completions` row — the business table is itself instrumentation; the log event just makes it streamable.

### 5.2 Traces (OpenTelemetry — scaffolded in, exports when configured)

Scaffold with the template's `enable_otel=true`: FastAPI + SQLAlchemy auto-instrumentation, OTLP exporter active only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (no-op locally). Workflow outcomes are emitted as structured events from `events.py`.

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
