# ADR 0010: Agent Pack Generation

## Status

Accepted. Supersedes [ADR 0004](0004-defer-ai-generation.md), which deferred
AI pack generation to a later version.

## Context

[ADR 0004](0004-defer-ai-generation.md) kept v1 focused by deferring
AI-assisted pack generation, while preserving optionality through the
corpus-in-Postgres decision. Epic 7 reverses that deferral and ships it.

The ground it builds on is already in place. [ADR 0009](0009-pack-ownership.md)
replaced pack lifecycle status with a nullable `packs.owner_id`, precisely so an
agent could create packs on a learner's behalf without exposing them to everyone
— visibility is exactly ownership. It also **deliberately left one question for
this epic**: whether owned packs participate in the Learning Path and progress
stats, declining to guess before a real authoring flow existed. Both that
question and the generation design are resolved here.

The hard constraint is corpus grounding. A pack may only trace hanzi that exist
in the `characters` table, and that table stores `hanzi`/`stroke_data`/
`stroke_count` and *no* glosses. A language model will happily invent characters
it "knows" and pinyin/meanings that read plausibly, so the design has to keep it
honest about corpus membership while accepting that the glosses can only come
from the model.

## Decision

Ship agent pack generation with the model grounded against the stroke corpus in
three layers, private-by-ownership, behind two authenticated endpoints.

**Agent.** A pydantic-ai `Agent[GenerationDeps, PackDraft]`
(`pydantic-ai-slim[openai]`) whose structured output is a validated `PackDraft`.
The provider is **OpenAI-compatible models via OpenRouter** (`OpenAIChatModel` +
`OpenRouterProvider`), env-configured: `GENERATION_MODEL` (default
`deepseek/deepseek-v4-flash`) and `OPENROUTER_API_KEY`. OpenRouter gives us a single
billing/routing seam and easy model swaps without a code change. When the key is
unset, generation is disabled and both endpoints return 503.

**Three-layer corpus grounding** — the central design:

1. **`find_characters` tool** over `CharacterRepository`: the model calls it to
   learn which candidate hanzi exist in the corpus and each one's stroke count
   (a difficulty signal). It returns membership only — the corpus has no
   glosses, so the model supplies every pinyin/meaning itself.
2. **Output validator**: raises `ModelRetry` for any non-corpus glyph — pack
   members *and* every glyph inside every sentence (sentences are traced glyph
   by glyph) — so pydantic-ai feeds the error back and the model retries, within
   a bounded retry budget.
3. **`PackRepository.create` re-validates at save**, now including sentence
   glyphs. This epic aligned layer 3 with the seed script's `required_hanzi`, so
   the save path enforces exactly what the seed pipeline does.

**Endpoints** (`/api/v1/generation`, session-authenticated):

- `POST /draft` — topic plus an opaque, client-held message history in →
  `PackDraft` plus updated history out. Multi-turn refinement is supported with
  **no server-side conversation store**; the client replays the history it holds.
- `POST /packs` — a finalized draft → an owned pack via
  `PackRepository.create(owner_id=caller)`, `201` with `PackDetailDTO`.
  Save-time defaults the draft omits: `glyph` = the first character, `color` = a
  deterministic pick from the curated palette, `sort_order` = 1000 (owned packs
  list after curated ones).

**Path participation stays global-only this epic.** Resolving the question
[ADR 0009](0009-pack-ownership.md) deferred: generated packs live in the Packs
library (`list_visible`) and are fully traceable there, but the Learning Path
scheduler and progress stats remain global-only. Scheduler participation for
owned packs is future work, once real generated packs exist to design against.

**Rate limiting.** A per-user fixed-window in-memory cap on draft generation
(`GENERATION_RATE_LIMIT_PER_HOUR`, default 10), counting *on attempt* for cost
safety (a failed or unconfigured run still consumes quota), returning 429 over
the cap. Explicitly single-process by design.

**Testing posture: zero real LLM calls in CI.** The shared conftest sets
`ALLOW_MODEL_REQUESTS = False`; every tier drives the agent with pydantic-ai's
`TestModel`/`FunctionModel` via `Agent.override`. Integration tests stub only
the model — real agent, tool, validator, and Postgres. A single
`@pytest.mark.external` contract test (`tests/external/`) exercises the real
provider via `just test-external` and is never collected by the gate/CI suites.
Generation-facing DTOs carry input bounds for cost/DoS containment, and the flow
emits WF-15 workflow events (`pack_draft_generated`, `generated_pack_saved`).

## Consequences

- Reverses [ADR 0004](0004-defer-ai-generation.md): agent generation now exists
  and is secured. The corpus-in-Postgres decision that ADR anticipated is what
  makes layer-1/2/3 grounding possible.
- **Model-supplied glosses are unverified.** Pinyin and meanings come from the
  model, not the corpus. This is accepted because they are pack-local data
  contained to a single owner's private pack — a wrong gloss misinforms only its
  author, never global content or another learner.
- **Corpus coverage gaps are reported, not refused.** When requested characters
  are absent, the model says so honestly in `coverage_note` (e.g. "found 6 of 8
  requested") rather than silently shrinking the pack or failing the request.
- **The rate limiter is single-process.** In-memory windows cap spend only
  within one uvicorn process; a multi-process or multi-host deployment would
  need a shared store (e.g. Redis). Acceptable on Habagou's single-machine Fly
  deployment; called out so it is a conscious constraint, not a latent surprise.
- Generated packs are private by ownership and traceable in the Packs library,
  but stay out of the Learning Path and progress stats this epic — the
  deliberate resolution of the question [ADR 0009](0009-pack-ownership.md) left
  open, deferring scheduler participation to future work.
- CI and the gate make no real provider calls, so the suite is deterministic and
  free to run; the one live contract test guards against prompt/schema/provider
  drift on demand.
