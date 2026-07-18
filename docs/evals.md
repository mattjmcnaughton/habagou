# Agent Evaluation

> **Status: planned.** The harness described here is not built yet, but the
> shape is decided: pydantic-evals, a DB-free `evals/` harness beside `tests/`,
> a `just evals` entry point locally, and an opt-in GitHub Actions workflow
> driven by an `OPENROUTER_API_KEY` repository secret. Implementation is
> phased below; each phase is one reviewable PR.

## Why

Habagou has two pydantic-ai agents: pack generation
(`src/habagou/agents/generation.py`, [ADR 0010](adrs/0010-agent-pack-generation.md))
and the conversational practice tutor (`src/habagou/agents/practice.py`,
[ADR 0011](adrs/0011-conversational-practice-agent.md)). Today their quality is
covered by two very different mechanisms, with a gap in between:

- **Runtime enforcement** (production): the three corpus-grounding layers —
  the `find_characters` tool, the output validator's `ModelRetry` loop, and
  `PackRepository.create` re-validating at save. These *enforce* hard
  constraints per request but measure nothing.
- **Contract tests** (`tests/external/`): one live round trip per agent via
  `just test-external`, guarding against prompt/schema/provider drift. A smoke
  signal, not a quality measure.

Neither answers the questions that come up every time a prompt or the model
allowlist changes: does this prompt revision still hold the corpus constraint
without burning retries? Is a new OpenRouter model good enough to add to the
admin picker? Did a prompt change regress pinyin formatting, pack sizing, or
the tutor's HSK level? An evaluation harness answers those *before* shipping,
by running the agents against a curated dataset and scoring the outputs.

This is a development-time tool. It never runs on the request path, never
ships in the production image, and lives in its own dependency group.

## What the `agents/` extraction enables

Agent definitions live in `src/habagou/agents/`, assembled **without a bound
model** and depending only on their deps protocols (e.g. `CorpusReader`) —
never on `services/`, `routers/`, `config`, or the database. An eval harness
therefore imports `build_generation_agent()` / `build_practice_agent()` and
supplies:

- **a model** — any pydantic-ai model, e.g. one per allowlisted OpenRouter id
  for model sweeps, via `agent.run(..., model=...)`;
- **deps** — for generation, a frozen in-memory corpus fixture satisfying
  `CorpusReader` (the `_StubCorpus` pattern in
  `tests/external/test_generation_contract.py`), so no Postgres is needed.

That deps seam is what makes the whole plan below cheap to operate: the
harness needs a Python toolchain and an OpenRouter key, and nothing else — no
database, no Keycloak, no frontend build. Locally that means `uv run`; in CI
it means a single lightweight job.

## Tooling: pydantic-evals

[pydantic-evals](https://ai.pydantic.dev/evals/) is the choice, for reasons of
fit rather than novelty:

- Same family as pydantic-ai; code-first (`Dataset` / `Case` / `Evaluator`),
  datasets serializable to YAML/JSON with a generated schema.
- Emits OpenTelemetry spans and reports into Logfire, which is already in the
  stack (`telemetry.py`, `send_to_logfire="if-token-present"`), so eval runs
  and production traces land in one place. Terminal report tables work with no
  token.
- Supports deterministic evaluators (plain Python), `LLMJudge` for subjective
  rubrics, and span-based evaluators that inspect *how* a run behaved (e.g.
  how often `find_characters` was called), not just the final output.

Known trade-offs: the library is young and its API has moved between releases
(**pin an exact version** and bump deliberately); `LLMJudge` scores cost money
and vary run to run, so results read as trends and distributions, not
pass/fail gates.

It goes in its own `evals` dependency group (not `dev`), so `just gate` and
the CI gate job never pay for it: `uv sync --group evals` pulls it in only
where evals actually run.

## Harness design

```
evals/                       # peer of tests/, dev-only, never packaged
  __main__.py                # CLI entry point: `uv run python -m evals`
  corpus_fixture.py          # loads the frozen corpus snapshot -> CorpusReader stub
  corpus_snapshot.json       # committed {hanzi: stroke_count} map (see below)
  models.py                  # model id -> pydantic-ai OpenRouter model resolution
  generation/
    dataset.yaml             # topics, corpus-gap cases, refinement turns
    evaluators.py            # see below
  practice/
    dataset.yaml             # openers, "explain that" turns, learner mistakes
    evaluators.py
```

### Corpus fixture

`CorpusReader` needs membership and stroke counts only — never `stroke_data` —
so the fixture is a committed JSON map of `hanzi -> stroke_count` derived from
the same pinned `hanzi-writer-data` archive that `scripts/import_stroke_data.py`
imports (same `CORPUS_VERSION` / `CORPUS_SHA256`). A small regeneration script
reuses the import script's download/verify helpers; the snapshot only changes
when the pinned corpus version does. Using the *full* real corpus (not the
36-character slice the contract test uses) matters here: eval cases probe
realistic topics, and corpus-gap behaviour (`coverage_note`) is only honest
against the real membership set.

### Runner CLI

A tiny argparse CLI, no framework:

```
uv run python -m evals --agent generation            # default model
uv run python -m evals --agent practice --models anthropic/claude-sonnet-5
uv run python -m evals --sweep                       # all allowlisted models, both agents
uv run python -m evals --agent generation --report .artifacts/evals/gen.json
```

- `--models` takes OpenRouter ids; `--sweep` expands to
  `settings.generation_model_ids` / `settings.practice_model_ids`, which turns
  a run into the evidence behind the admin model allowlist.
- `--report` writes the pydantic-evals report as JSON (for CI artifacts and
  later baseline comparison) in addition to the terminal table.
- Concurrency is bounded (pydantic-evals `max_concurrency`) so a sweep cannot
  stampede the provider.
- **Keyless behaviour:** if `OPENROUTER_API_KEY` is unset, exit non-zero
  immediately with a one-line message. Unlike `tests/external/` there is no
  reason to skip quietly — an eval run with no key is always a mistake.
- The suite-wide `ALLOW_MODEL_REQUESTS = False` guard is a pytest conftest
  concern and does not apply here; this is a separate entry point, not pytest.

### Judge model

`LLMJudge`'s default judge is an OpenAI-direct model, which would demand a
second API key. Instead the harness pins one explicit judge model routed
through the same OpenRouter key (a cheap-but-strong id, fixed in
`evals/models.py`). One secret configures everything, and judge drift is a
deliberate, diffable change.

### Evaluators

Generation (all deterministic):

- every drafted glyph (members + sentence glyphs) is in the corpus fixture;
- pinyin carries tone marks, never digits (`nǐ`, not `ni3`);
- sentences are punctuation-free;
- pack size within 5–12 unless the case requests otherwise;
- `coverage_note` mentions the deliberately-absent characters a case's
  metadata lists;
- `usage.requests` as a numeric score — the same round-trip signal the
  service logs as `model_requests`.

Practice (deterministic where possible, `LLMJudge` for the rest):

- 1–3 segments, each carrying hanzi/pinyin/english (deterministic);
- `english_aside` set only when the case asked for help (deterministic);
- HSK 1–2 vocabulary level, turn ends with an inviting question, mistakes
  corrected without lecturing (judge).

### Scores vs. hard floors

Almost everything above is a **tracked score**: the report shows a
distribution, and a regression is a trend to investigate, not a red X. Exactly
one evaluator is a **hard floor** that fails the run: corpus membership after
retries must be 100%. The output validator already enforces it per request, so
a violation surviving to the eval report means the retry budget was exhausted
— which is precisely the "this prompt/model combination doesn't work" signal
that should be unmissable. `usage.requests` stays a score (it measures how
*efficiently* the constraint held), but membership itself is binary.

## Running locally

```
just evals            # both agents, default models, terminal report
just evals-sweep      # both agents, every allowlisted model id
```

- Same env story as the rest of the repo: `OPENROUTER_API_KEY` comes from the
  environment or `.env` (pydantic-settings already reads it).
- With a `LOGFIRE_TOKEN` present the run also lands in Logfire next to
  production traces; without one, the terminal table is the whole story.
  Nothing to configure either way (`send_to_logfire="if-token-present"`).
- Never collected by `just gate`, `just gate-expensive`, or any pytest target.
  `just gate-external` also stays eval-free: contract tests answer "does the
  wiring still work" cheaply, evals answer "how good is it" expensively, and
  keeping them separate keeps both invocable with intent.

## Running in GitHub Actions

A **separate workflow** (`.github/workflows/evals.yml`), never a required
check and never part of `ci.yml`. It needs one repository secret:
`OPENROUTER_API_KEY`. Optionally a second, `LOGFIRE_TOKEN`, to persist run
history in Logfire — worthwhile once runs are scheduled, since artifacts alone
make trend-reading manual.

### Triggers

1. **`workflow_dispatch`** (the primary mode): inputs for `agent`
   (generation/practice/both), `models` (comma-separated ids, empty = feature
   defaults), and `sweep` (boolean). Run it by hand before merging a prompt
   change or when vetting a model for the allowlist.
2. **`schedule`**: weekly sweep over the allowlisted models. This is the trend
   line that makes score drift visible — provider-side model updates regress
   quality without any commit changing.
3. **Not (yet) on `pull_request`.** Spending real money on every PR push is
   the wrong default for a two-agent app. If a PR trigger earns its keep
   later, it should be label-gated (e.g. `run-evals`) and path-filtered to
   `src/habagou/agents/**` and `evals/**`. Note the standard caveat: secrets
   are unavailable to `pull_request` runs from forks, and working around that
   with `pull_request_target` is a known footgun — for a personal repo,
   same-repo branches make this moot, but it belongs in the workflow as an
   explicit `if:` guard anyway.

### Job shape

The job is deliberately the smallest thing in CI — no Postgres service, no
Keycloak, no pnpm/Node, no Playwright:

```yaml
jobs:
  evals:
    runs-on: ubuntu-latest
    concurrency:
      group: evals-${{ github.ref }}
      cancel-in-progress: true
    steps:
      - checkout
      - setup uv, python 3.12
      - uv sync --frozen --group evals
      - run: uv run python -m evals ... --report .artifacts/evals/report.json
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          LOGFIRE_TOKEN: ${{ secrets.LOGFIRE_TOKEN }}
      - write markdown summary to $GITHUB_STEP_SUMMARY
      - upload .artifacts/evals/ as an artifact
```

- **Exit-code policy mirrors the gating philosophy:** the job fails on harness
  errors and on the corpus-membership hard floor, and *only* those. Low judge
  scores never fail the job — they show up in the step summary and the trend.
- **Step summary** is the human-facing report: per-case scores, per-model
  aggregates for sweeps, and the `usage.requests` distribution, rendered as
  markdown tables from the JSON report.
- **Artifacts** keep the raw JSON per run (named with model id + SHA), so any
  two runs can be diffed after the fact even without Logfire.

### Cost control

- Datasets stay small by design (sizes below); a full sweep is
  `(models × cases)` runs plus judge calls, and both factors are bounded.
- `max_concurrency` in the runner caps burst spend and rate-limit pressure.
- The `concurrency` group cancels superseded dispatch runs on the same ref.
- The scheduled run uses the allowlist as-is; vetting *candidate* models is
  always an explicit dispatch with `models=` input.
- The judge model is pinned cheap. If weekly sweep cost ever matters, drop the
  schedule to the default models only — the allowlist sweep stays on demand.

## Dataset curation

Starting sizes — enough to read a trend, small enough to run on a whim:

- **Generation: 10–15 cases.** Mix of: plain topics ("ordering food",
  "weather"), topics chosen to force corpus gaps (case metadata lists the
  absent characters `coverage_note` must mention), explicit size requests
  ("just 5 characters"), and at least two refinement turns.
- **Practice: 5–10 cases.** Openers on a topic, "what does that mean?" turns
  (must set `english_aside`), turns that must *not* set it, and learner
  messages with small mistakes (judge checks correction-without-lecturing).

Refinement-turn cases need a first-turn `message_history`. Recording real
histories goes stale as the prompt evolves, so refinement cases instead build
a **synthetic history**: the case supplies the first-turn request plus a
hand-written valid `PackDraft`, and the harness fabricates the history
(user prompt + model response) around them. That keeps refinement cases
prompt-version-independent — the system prompt is injected fresh at run time,
only the conversational shape is fixed.

## Alternatives considered (briefly)

- **Extend `tests/external/` with more pytest cases.** Zero new dependencies,
  but pytest wants pass/fail, and eval results are scores and distributions;
  no dataset/report/model-sweep structure, and it would grow into a bespoke
  harness anyway.
- **Hosted eval platforms** (Braintrust, LangSmith, promptfoo, ...). More
  UI and collaboration features, but another vendor, another data path for
  learner-adjacent content, and overlapping with what Logfire already
  provides. Not warranted at two agents.

## Implementation phases

Each phase is one PR, independently useful, in dependency order:

1. **Skeleton + generation, deterministic only.** `evals` dependency group
   (pydantic-evals pinned), corpus snapshot + regeneration script, runner CLI,
   `generation/dataset.yaml` with the deterministic evaluators, `just evals`.
   Proves the harness end to end with zero judge spend.
2. **Practice + judge.** `practice/dataset.yaml`, deterministic evaluators,
   `LLMJudge` rubrics through the pinned OpenRouter judge model.
3. **Sweep + reports.** `--sweep` over the allowlist, `--report` JSON output,
   `just evals-sweep`.
4. **GitHub Actions.** `evals.yml` with `workflow_dispatch` + weekly
   `schedule`, step-summary rendering, artifact upload. Requires the
   `OPENROUTER_API_KEY` secret to be uploaded first.
5. **Later, if earned:** baseline files + regression deltas in the step
   summary, a label-gated PR trigger, span-based evaluators for
   `find_characters` call patterns.

## Decisions and open questions

Resolved by this plan:

- **Tool:** pydantic-evals, exact-pinned, in an `evals` dependency group.
- **Hard floor vs. score:** corpus membership is the one hard failure;
  everything else is a tracked score.
- **Judge:** one pinned model via OpenRouter — a single secret covers agents
  and judge both.
- **Cadence:** on-demand (`just evals`, `workflow_dispatch`) plus a weekly
  scheduled sweep; no per-PR runs for now.
- **CI posture:** separate non-required workflow; fails only on harness
  errors and the hard floor.
- **Refinement histories:** synthesized per-case from a hand-written first
  draft, not recorded transcripts.

Still open (fine to settle during implementation):

- Which OpenRouter id to pin as the judge, and the exact rubric wording for
  the three practice judge criteria.
- Whether the step summary should eventually compare against a committed
  baseline (phase 5) or Logfire trend-reading suffices.
- Whether `usage.requests` should grow a soft alerting threshold in the
  summary (e.g. flag cases averaging > 2 requests) once real distributions
  exist.
