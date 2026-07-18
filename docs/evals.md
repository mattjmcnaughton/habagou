# Agent Evaluation

> **Status: WIP.** This document captures the current thinking on how to
> evaluate Habagou's agents. No harness exists yet; nothing here is decided
> beyond the `agents/` extraction that enables it. Treat the tool choice below
> as a proposal to be validated, not a commitment.

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
ships in the production image, and belongs in the `dev` dependency group.

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

## Leading option: pydantic-evals

[pydantic-evals](https://ai.pydantic.dev/evals/) is the current front-runner,
for reasons of fit rather than novelty:

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
(pin it); `LLMJudge` scores cost money and vary run to run, so results read as
trends and distributions, not pass/fail gates.

### Sketch (not built yet)

```
evals/                       # peer of tests/, dev-only, never packaged
  corpus_fixture.py          # frozen all_hanzi snapshot -> CorpusReader stub
  generation/
    dataset.yaml             # topics, corpus-gap cases, refinement turns
    evaluators.py            # see below
  practice/
    dataset.yaml             # openers, "explain that" turns, learner mistakes
    evaluators.py
```

Candidate evaluators — generation (all deterministic):

- every drafted glyph (members + sentence glyphs) is in the corpus fixture;
- pinyin carries tone marks, never digits (`nǐ`, not `ni3`);
- sentences are punctuation-free;
- pack size within 5–12 unless the case requests otherwise;
- `coverage_note` mentions the deliberately-absent characters a case's
  metadata lists;
- `usage.requests` as a numeric score — the same round-trip signal the
  service logs as `model_requests`.

Candidate evaluators — practice (deterministic where possible, `LLMJudge`
for the rest):

- 1–3 segments, each carrying hanzi/pinyin/english (deterministic);
- `english_aside` set only when the case asked for help (deterministic);
- HSK 1–2 vocabulary level, turn ends with an inviting question, mistakes
  corrected without lecturing (judge).

### Operational posture

Mirrors `tests/external/`: opt-in, real `OPENROUTER_API_KEY`, real provider
calls, never collected by `just gate` or CI. A `just evals` target would run
the harness; parameterizing over `settings.generation_model_ids` /
`settings.practice_model_ids` turns it into the evidence behind the admin
model allowlist. The suite-wide `ALLOW_MODEL_REQUESTS = False` guard is a
pytest conftest concern and does not apply to a separate eval entry point.

## Alternatives considered (briefly)

- **Extend `tests/external/` with more pytest cases.** Zero new dependencies,
  but pytest wants pass/fail, and eval results are scores and distributions;
  no dataset/report/model-sweep structure, and it would grow into a bespoke
  harness anyway.
- **Hosted eval platforms** (Braintrust, LangSmith, promptfoo, ...). More
  UI and collaboration features, but another vendor, another data path for
  learner-adjacent content, and overlapping with what Logfire already
  provides. Not warranted at two agents.

## Open questions

- Dataset curation: how many cases per agent are enough to trust a trend?
  (Starting guess: 10–15 generation topics, 5–10 practice conversations.)
- Judge model choice and rubric wording for the practice evaluators.
- Whether any deterministic evaluator should be a hard assertion (e.g.
  corpus membership must be 100% after retries) vs. a tracked score.
- Run cadence: on demand only, or a scheduled run per allowlisted model?
- Whether refinement-turn cases need recorded first-turn histories, and how
  those recordings stay fresh as the prompt evolves.
