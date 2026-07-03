# Habagou — Verification & Validation (VERIFICATION)

| | |
|---|---|
| Status | **Final v1.0** — approved for implementation |
| Depends on | [PRD](product/prd.md), [TDD](technical/tdd.md), [DEVEX](devex.md) |
| Goal | (1) name the workflows, (2) provably show each works pre-merge, (3) instrument each so prod shows it working |

## 1. Approach

The unit of verification is the **workflow** — a named, user- or operator-visible journey with preconditions and postconditions. Everything hangs off the workflow ID:

- Tests are **tagged** with the workflow(s) they prove (`@pytest.mark.workflow("WF-03")`, Playwright `@wf-03` tag).
- Production instrumentation emits **the same IDs** (`workflow="WF-03"` field on structured events).
- CI produces a **traceability report**: for every workflow in the catalog, which unit/integration/e2e tests ran and passed. A workflow with no e2e coverage fails the report.

This gives one vocabulary from PRD → test → prod dashboard: "is tracing working?" is answerable at every stage by the same key.

## 2. Workflow catalog

| ID | Workflow | Actor | Postcondition (the thing we can assert) |
|----|----------|-------|------------------------------------------|
| WF-01 | Bootstrap | Operator | Empty DB → migrated schema, ≥9 000 corpus chars, guest user, 4 published packs; idempotent on re-run |
| WF-02 | Browse library | Learner | Home shows all published packs with correct counts and the user's completion badges |
| WF-03 | Trace a pack | Learner | All chars traced stroke-by-stroke → done screen → `activity_completions` row (trace) → badge visible |
| WF-04 | Match a pack | Learner | All pairs matched → elapsed time shown → completion row (match) → badge visible |
| WF-05 | Sentence a pack | Learner | All sentences traced, **including non-pack chars** (很) → completion row (sentence) → badge visible |
| WF-06 | Serve strokes | System | Any corpus char returns valid Hanzi Writer JSON < 150 ms p95, immutable-cached; unknown char → 404 |
| WF-07 | Review progress | Learner | Pack screen shows per-activity completed/best-duration truthfully from the event log |
| WF-08 | Reset progress | Learner | Confirmed reset → completions for (user, pack) deleted → badges cleared |
| WF-09 | Admin curate | Admin | Retire/publish/reorder takes effect in WF-02 output; unauthorized → 401 |
| WF-10 | Deploy & serve | Operator | Clean `docker compose up` → WF-01 runs → app healthy → WF-03 passes end-to-end |

Each workflow gets a short spec section in this doc as it's implemented (steps, invariants, edge cases). The catalog is the contract; PRD FRs map into it (e.g. FR-4..7 ⊂ WF-03).

## 3. Test layers and what each is allowed to prove

| Layer | Proves | Explicitly does NOT prove | Speed / where |
|---|---|---|---|
| **Unit (BE)** | Pure logic: progress aggregation, grapheme splitting, seed validation, DTO mapping | Anything about Postgres or HTTP | ms; every `just gate` |
| **Unit (FE)** | Activity state machines (trace idx/stroke/complete; match select/wrong/lock; sentence advance), component wiring against **MSW handlers derived from the OpenAPI schema** | Real network, real writer rendering | ms; every `just gate` |
| **Integration (BE)** | Repositories + migrations against real Postgres; API contracts at the ASGI level with real DB; import/seed scripts incl. failure paths | Browser behavior | s; `just gate-expensive`, CI |
| **E2E (Playwright)** | Full workflows through the real stack (real backend, real DB, real hanzi-writer in a real browser), desktop + mobile viewports | — | 10s–min; CI on PRs to main |
| **E2E (staging)** | The **full** Playwright suite, mutating workflows included (WF-03/04/05/08), against the staging deployment: `just e2e BASE_URL=…` | — (staging guest data is disposable; suite may reset progress freely) | every staging deploy |
| **Smoke (prod)** | Read-only subset of e2e against **production** (`just smoke BASE_URL=…`): healthz/readyz, WF-02, WF-06 | Mutating workflows (prod guest progress is real data) | post-deploy, cron |
| **Invariant checks** | Data-level truths in any live DB: every published pack's chars **and sentence chars** exist in corpus; guest user exists; no completion rows reference retired users/packs | Behavior | `scripts/check_invariants.py`; post-deploy, cron |

Cross-cutting rules:

- **Contract single-source**: the backend OpenAPI schema is exported as a checked-in artifact; a CI step fails if it drifts from code, and FE MSW handlers/types are validated against it. FE unit tests therefore cannot pass against a fictional API.
- **Determinism**: e2e uses fixture-friendly content — 一 (one stroke) for trace-input tests, seeded RNG for match shuffle (test hook), scripted pointer events along stroke medians (Hanzi Writer's quiz accepts median-following paths; a writer stub is the fallback if flake appears).
- **Test data isolation** (uses DEVEX §2 infrastructure): integration/e2e fixtures create a **per-test database** inside the instance's cluster via `CREATE DATABASE test_<id> TEMPLATE habagou_test_base`, where the template DB is migrated+seeded once per session with the fixture corpus subset. Tests run fully parallel with zero shared state; teardown is `DROP DATABASE`.
- **The e2e harness provisions instances exactly like a developer does** (same bootstrap path), so "works on my machine" and "works in CI" are the same claim.

## 4. Traceability

Enforced mechanically, kept lightweight:

1. `docs/workflows.yml` — machine-readable catalog (ID, title, minimum required layers, e.g. WF-03 requires unit+integration+e2e; WF-10 requires the compose smoke).
2. Tests declare workflows via marks/tags.
3. CI job `verify-traceability`: parses test reports (pytest junit + Playwright JSON), joins against the catalog, fails if any workflow misses its minimum layer or any tagged test failed; emits a matrix artifact (workflow × layer → pass/fail/missing) on every PR.

This is ~100 lines of script, not a framework — but it makes "provably show the workflows work" a CI gate rather than a code-review vibe.

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
| `progress_reset` | WF-08 | `pack_slug`, `deleted_count` |
| `admin_action` | WF-09 | `action`, `pack_slug`, `authorized` |
| `invariant_check` | — | `check`, `outcome`, `violations` |

Note `activity_completed` is *derived from the same write* that creates the `activity_completions` row — the business table is itself instrumentation; the log event just makes it streamable.

### 5.2 Traces & metrics (OpenTelemetry — scaffolded in, exports when configured)

Scaffold with the template's `enable_otel=true`: FastAPI + SQLAlchemy auto-instrumentation, OTLP exporter active only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (no-op locally). `events.py` additionally increments counters `habagou_workflow_total{workflow,outcome}` and records `habagou_workflow_duration_ms{workflow}` — giving rate/error/duration per workflow, the prod mirror of the CI traceability matrix.

### 5.3 Environment tiers & live validation loops

| Environment | Verification | Mutations allowed |
|---|---|---|
| Local / CI | Full suite against ephemeral per-test databases | Yes (ephemeral) |
| **Staging** | **Full e2e suite** (`just e2e BASE_URL=…`) after every staging deploy — same tagged workflows, same traceability matrix, real deployed stack | Yes — staging guest progress is disposable; the suite resets it |
| Production | `just smoke BASE_URL=…` (read-only: health, WF-02, WF-06) + `scripts/check_invariants.py` | No |

- **Staging deploy gate**: a staging deploy is done when the full e2e matrix passes against it; a prod deploy is done when smoke + invariants pass against it. Both runnable on cron thereafter.
- **Dashboards** (whatever the sink — Grafana/Loki or hosted): one row per workflow, fed by `habagou_workflow_total`/`duration` — deliberately the same shape as the CI matrix. "Is WF-03 working in prod?" = nonzero ok-rate, ~zero error-rate, sane p95, zero `strokes_missing`.
- **Mutating verification lives in staging** (above), not prod: driving WF-03 against prod would pollute the shared guest user's real progress. Revisit prod synthetics when v2 accounts allow a dedicated synthetic user.

## 6. Verification gate summary

| Gate | Contents | When |
|---|---|---|
| `just gate` | fmt, lint, typecheck, unit (BE+FE), OpenAPI drift check | every commit / pre-push |
| `just gate-expensive` | gate + integration + e2e (parallel, per-test DBs) | pre-merge / CI PR |
| `verify-traceability` | workflow × layer matrix, fails on gaps | CI PR |
| `just e2e BASE_URL=…` | full mutating e2e vs staging | every staging deploy |
| `just smoke BASE_URL=…` + invariants | read-only prod validation | post-deploy, cron |
