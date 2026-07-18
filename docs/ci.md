# Continuous Integration

GitHub Actions workflows in `.github/workflows/`. Two run automatically on
every push/PR to `main`; one is opt-in because it spends money.

| Workflow | File | Trigger | Purpose |
| -------- | ---- | ------- | ------- |
| CI | `ci.yml` | push/PR to `main` | Correctness gates (below) |
| Evals | `evals.yml` | `workflow_dispatch` only | Agent quality measurement ([docs/evals.md](evals.md)) |
| Release | `release.yml` | see file | Release automation |

## CI (`ci.yml`)

Five independent jobs, all required to be green:

- **gate** — `just gate`: formatting (ruff/prettier), linting, typecheck
  (ty/tsc), backend + frontend unit tests. No services needed.
- **integration** — `just test-integration` against a Postgres service
  container, plus the data-invariant check and a migration
  downgrade-to-base verification.
- **e2e** — backend e2e anchors and the Playwright browser suite against a
  real Postgres + Keycloak.
- **openapi-drift** — regenerates the OpenAPI artifact and frontend API types
  and fails on any diff.
- **compose-smoke** — builds the production image and smoke-tests the full
  Compose stack over HTTP.

None of these call LLM providers: the unit suite hard-disables model requests
(`tests/conftest.py` sets `ALLOW_MODEL_REQUESTS = False` and scrubs
`OPENROUTER_API_KEY`), and the live-provider contract tests
(`tests/external/`) are only reachable via `just test-external`, which CI
never invokes.

## Evals (`evals.yml`)

Runs the agent eval harness (`evals/`, [docs/evals.md](evals.md)) against the
live OpenRouter provider. **Opt-in by design**: eval runs cost real money, so
the workflow has no `push`/`pull_request`/`schedule` trigger and is never a
required check.

### Triggering a run

Actions tab → **Evals** → *Run workflow*, or:

```
gh workflow run evals.yml [--ref my-branch] [-f models=anthropic/claude-sonnet-5,minimax/minimax-m3]
```

- **`models` input**: comma-separated OpenRouter model ids. Empty runs the
  configured default generation model. This is how a candidate model is
  vetted before being added to the admin allowlist
  (`ADMIN_CHAT_MODELS`).
- **`--ref`**: any branch — evaluate a prompt change *before* merging it.
  (GitHub only lists a workflow for dispatch once its file exists on the
  default branch; after that, any ref works.)

### Setup (one-time)

Upload the **`OPENROUTER_API_KEY`** repository secret (Settings → Secrets and
variables → Actions). Until it exists, dispatched runs fail immediately with
the harness's "OPENROUTER_API_KEY is not set" message (exit 2) — nothing
hangs, nothing silently skips.

### Reading results

The same report lands in three places:

1. **Job log** — the full pydantic-evals table (per-case assertions with
   reasons, `model_requests` metric, averages). This is the machine-readable
   surface: agents can fetch it via job logs.
2. **Job summary** — the identical table rendered on the run's Summary page.
3. **`eval-report` artifact** — `report.json` with per-case assertion
   values/reasons, metrics, and durations, keyed by model id. Diffable across
   runs.

### Pass/fail semantics

The job fails **only** on harness errors or the hard floor (a case that
errored or drafted non-corpus glyphs after the agent's retry budget —
`CorpusMembership`). Soft checks (pinyin format, punctuation, pack size) and
the `model_requests` metric never fail the job; they are trends to read, not
gates. A red Evals run therefore always means "this prompt/model combination
is broken", never "a score dipped".

### Environment

The job installs the minimal env for the harness — `uv sync --frozen
--no-dev --group evals` — and nothing else: no Node, no Postgres, no
Keycloak. The corpus fixture is the committed snapshot
(`evals/corpus_snapshot.json`), so no database or corpus download happens in
CI. A `concurrency` group cancels superseded runs on the same ref.
