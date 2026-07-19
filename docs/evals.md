# Agent Evaluation

> **Status: first slice built.** The harness in `evals/` runs the pack
> generation agent against a small curated dataset with deterministic
> evaluators, locally (`just evals`) and via the opt-in `Evals` GitHub Actions
> workflow (`.github/workflows/evals.yml`, see [docs/ci.md](ci.md)). Everything
> else — practice-agent evals, LLM judges, model sweeps, scheduled runs — is a
> future extension, listed at the bottom.

## Why

Habagou has two pydantic-ai agents: pack generation
(`src/habagou/agents/generation.py`, [ADR 0010](adrs/0010-agent-pack-generation.md))
and the conversational practice tutor (`src/habagou/agents/practice.py`,
[ADR 0011](adrs/0011-conversational-practice-agent.md)). Before this harness,
their quality was covered by two very different mechanisms with a gap in
between:

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
admin picker? An eval run answers those *before* shipping, by running the
agent against a curated dataset and scoring the outputs.

This is a development-time tool. It never runs on the request path, never
ships in the production image (hatch packages only `src/habagou`), and its
dependencies live in the `evals` dependency group (included into `dev` so
local tooling sees it; installed standalone by the evals CI job via
`uv sync --no-dev --group evals`).

## What is built

```
evals/                        # peer of tests/, dev-only, never packaged
  __main__.py                 # CLI: uv run python -m evals  (= just evals)
  corpus.py                   # SnapshotCorpus: CorpusReader over the snapshot
  corpus_snapshot.json        # committed {hanzi: stroke_count}, full corpus
  generation.py               # evaluators + dataset loader + task builder
  generation_dataset.yaml     # the cases (topics + per-case size metadata)
scripts/
  gen_eval_corpus_snapshot.py # regenerate the snapshot from the pinned archive
.github/workflows/evals.yml   # opt-in workflow_dispatch run (docs/ci.md)
```

The harness is built on [pydantic-evals](https://ai.pydantic.dev/evals/)
(same family as pydantic-ai; code-first `Dataset`/`Case`/`Evaluator`; exact
version pinned by `uv.lock`). It imports `build_generation_agent()` — the
agent factory that binds no model and touches no config or database — and
supplies the two things a run needs:

- **a model**: any pydantic-ai model via `agent.run(..., model=...)`; the CLI
  resolves OpenRouter ids through the same
  `habagou.services.openrouter.build_openrouter_model` the app uses.
- **deps**: `SnapshotCorpus`, an in-memory `CorpusReader` over
  `corpus_snapshot.json`. The snapshot is the **full** pinned
  hanzi-writer-data corpus (~9.5k characters, same `CORPUS_VERSION`/SHA as
  `scripts/import_stroke_data.py`), so grounding behaves exactly as in
  production — no Postgres, no Keycloak, no frontend build anywhere in the
  loop. Regenerate it only when the pinned corpus version bumps.

### The evaluators (all deterministic, no judge spend)

Every case in `generation_dataset.yaml` is scored by four plain-Python
evaluators plus one metric:

| Check | What it verifies | Gates? |
| ----- | ---------------- | ------ |
| `CorpusMembership` | Every drafted glyph — pack members and each glyph inside every sentence — exists in the corpus snapshot | **Yes — hard floor** |
| `PinyinToneMarks` | Pinyin uses tone marks, never digits (`nǐ`, not `ni3`), across characters and sentences | No |
| `PunctuationFreeSentences` | Sentence hanzi contain no punctuation (the corpus has none to trace) | No |
| `PackSize` | 5–12 characters, or the case's `min_size`/`max_size` metadata override | No |
| `MaxDuration` | Wall-clock response time under a 30s budget (pydantic-evals built-in) | No |
| `model_requests` (metric) | pydantic-ai's round-trip count per run — the same signal the service logs | No (tracked) |

Response time shows up twice: the raw per-case duration is always in the
report's Duration column (and `task_duration` in the JSON artifact), and
`MaxDuration` turns it into a pass/fail flag against the 30-second budget so
slow prompt/model combinations stand out in the assertions column. It stays a
soft check: latency measured from a shared CI runner against a live provider
is noisy, so read it as a trend and as a within-run comparison between models
— never a gate. It also correlates with `model_requests`: a run that burned
retries is usually a run that blew the time budget too, and the pair
distinguishes "slow model" from "model that needed three round trips".

**Gating philosophy.** Only `CorpusMembership` fails a run (CLI exit 1, red
CI job). The output validator already enforces membership per request, so a
violation surviving to the report means the retry budget was exhausted —
exactly the "this prompt/model combination doesn't work" signal that should
be unmissable. Everything else is a tracked score: a regression is a trend to
investigate, not a red X. `model_requests` is quietly the most interesting
column — with the corpus riding in the system prompt, an efficient run
finishes in **1 request**; higher means the model burned `find_characters`
calls or `ModelRetry` round trips to hold the constraint, which is the
latency/cost signal that disqualifies a model from the allowlist.

### The dataset

Six cases today: five plain beginner topics (restaurant, weather, family,
shopping, travel) and one explicit-size request (`small-pack`, with a
metadata-narrowed 4–6 band). Small by design — a full run is six generation
calls per model. Add cases by editing `generation_dataset.yaml`; per-case
`metadata` currently supports `min_size`/`max_size`.

## Running locally

```
just evals                                   # configured default model
just evals --models anthropic/claude-sonnet-5,minimax/minimax-m3
just evals --smoke                           # offline plumbing check, no key
just evals --report .artifacts/evals/report.json
```

- `OPENROUTER_API_KEY` comes from the environment or `.env` (pydantic-settings
  reads it), same as the app. Without a key the CLI exits 2 with a one-line
  message — an eval run with no key is always a mistake, so there is no silent
  skip.
- `--smoke` runs the whole pipeline against a stub `TestModel` (real agent,
  real prompt, real tool + validator, fixed output) with no key and no
  network. `tests/unit/test_evals_harness.py` runs the same path in the gate,
  so harness breakage is caught by `just gate`, while real eval runs stay
  opt-in.
- Exit codes: `0` ran and the hard floor held everywhere; `1` a case errored
  or drafted non-corpus glyphs after retries; `2` misconfiguration.
- Never collected by `just gate` / `gate-expensive` / `gate-external` or any
  pytest target — evals measure quality and cost money; the gates check
  correctness and stay free.

## Running in GitHub Actions

`.github/workflows/evals.yml` — full operational detail in
[docs/ci.md](ci.md). The short version:

- **Trigger:** `workflow_dispatch` only (Actions tab → Evals → Run workflow),
  with a `models` input (comma-separated OpenRouter ids; empty = configured
  default). Runs on any branch ref, so a prompt change can be evaluated
  before merge. Never a required check, never triggered by pushes or PRs.
- **Secret:** `OPENROUTER_API_KEY` (repository secret). Until it is uploaded,
  a dispatched run fails immediately with the harness's exit-2 message.
- **Results:** the report table lands in three places — the job log, the job
  summary (`$GITHUB_STEP_SUMMARY`), and an `eval-report` artifact containing
  the JSON. The job fails only on harness errors or the hard floor.
- **Cost control:** dispatch-only, six cases per model, bounded concurrency,
  and a `concurrency` group that cancels superseded runs on the same ref.

## Alternatives considered (briefly)

- **Extend `tests/external/` with more pytest cases.** Zero new dependencies,
  but pytest wants pass/fail, and eval results are scores and distributions;
  no dataset/report/model-sweep structure, and it would grow into a bespoke
  harness anyway.
- **Hosted eval platforms** (Braintrust, LangSmith, promptfoo, ...). More UI
  and collaboration features, but another vendor, another data path for
  learner-adjacent content. Not warranted at two agents.

## Future extensions

Roughly in the order they would earn their keep:

1. **Practice-agent evals.** `practice_dataset.yaml` + deterministic checks
   (1–3 segments each carrying hanzi/pinyin/english; `english_aside` set
   *only* when the case asked for help — both directions) and `LLMJudge`
   rubrics (HSK 1–2 vocabulary, turn ends with an inviting question, mistakes
   corrected without lecturing). The judge model must be pinned to an
   OpenRouter id — `LLMJudge`'s default judge is OpenAI-direct and would
   demand a second API key.
2. **Model sweep.** A `--sweep` flag expanding to
   `settings.generation_model_ids` / `practice_model_ids`, turning a run into
   the evidence behind the admin model allowlist; a matching workflow input.
3. **Corpus-gap cases.** Prompts naming characters deliberately absent from
   the corpus, with metadata listing them; an evaluator checks
   `coverage_note` mentions each (the "be honest about gaps" behavior).
4. **Refinement-turn cases.** Synthetic first-turn histories (case supplies
   the request plus a hand-written valid `PackDraft`; the harness fabricates
   the `message_history`), plus an overlap evaluator that catches
   starting-over-from-scratch. Synthetic beats recorded transcripts because
   it stays valid as the system prompt evolves.
5. **Scheduled runs.** A weekly `schedule` trigger over the allowlist, once
   the secret is uploaded and dispatch runs have proven the cost envelope —
   the trend line that catches provider-side model drift with no commit.
6. **Logfire reporting.** `logfire.configure(send_to_logfire="if-token-present")`
   in the runner so runs land beside production traces; add `LOGFIRE_TOKEN`
   as an optional workflow secret.
7. **Baselines.** Compare `--report` JSON against a committed baseline and
   render deltas in the step summary (pydantic-evals `print(baseline=...)`
   supports this natively).
8. **Span-based evaluators** inspecting *how* a run behaved (e.g.
   `find_characters` call patterns), not just the final output.
