# ADR 0011: Conversational Practice Agent

## Status

Accepted.

## Context

[ADR 0010](0010-agent-pack-generation.md) shipped the first LLM feature: an
agent chat that drafts packs, built on pydantic-ai over OpenRouter, with a
client-held conversation history and no server-side conversation store. The
product now wants a second, parallel LLM surface: a **conversational practice
tutor** ([prd-practice.md](../product/prd-practice.md)) — text-only chat on a
learner-chosen topic, replying in beginner-level Chinese with pinyin, English
translation one tap away, and an English "break glass" aside on request.

Unlike pack generation, nothing in a practice conversation is traced, so the
hard constraint that shaped ADR 0010 — corpus grounding — **does not apply**.
There is no reason the tutor may only use hanzi from the stroke corpus; it just
converses. What the feature does need is a reply shape rich enough to drive
the UI (hanzi/pinyin/hidden-English per sentence, plus an optional English
aside) without a second model call, and the same cost/availability guardrails
the generation feature already established.

Product decisions locked during planning: Practice is a fourth top-level tab;
conversations are ephemeral; difficulty is fixed at beginner (no level picker,
no grounding in the learner's packs or review states yet).

## Decision

Ship a practice-chat agent as a new bounded context that reuses the ADR 0010
architecture minus corpus grounding, with structured turns as the central
design.

**Agent.** A pydantic-ai agent with structured output, module-singleton, model
injected at run time — the same construction as
`services/pack_generation.py`, in a new `services/practice_chat.py`. Provider
is the same OpenRouter seam and the same `OPENROUTER_API_KEY`; the model id is
a separate setting, `PRACTICE_MODEL` (defaulting to the generation default),
so chat can move to a cheaper/faster model than drafting without a code
change. When the key is unset the feature is disabled and the endpoints
return 503, exactly like generation.

**Structured turns — the central design.** Each agent turn's `output_type` is:

- `PracticeTurn`
  - `segments: list[PracticeSegment]` — one per sentence, each with `hanzi`,
    `pinyin`, `english`.
  - `english_aside: str | None` — filled only when the learner asked for
    help in English.

This makes the three UX requirements properties of the schema rather than of
prompt-parsing: tap-for-translation is free and instant (the English is
generated with the turn and merely hidden client-side), reveal granularity is
per-sentence, and break-glass is a field, not a conversational mode the
server or client must track. The system prompt pins the tutor persona: reply
in simplified Chinese at HSK 1–2, 1–3 short segments per turn, always fill
pinyin and english, end with a question, accept English/Chinese/mixed input,
use `english_aside` only on request. **No `find_characters` tool and no
corpus output validator** — grounding is not a requirement here.

**Endpoints** (`/api/v1/practice`, session-authenticated):

- `GET /status` — readiness probe (`enabled`), the same pattern the frontend
  already uses to gate the create-pack card.
- `POST /turn` — topic plus learner message plus opaque client-held `history`
  in → `PracticeTurn` plus updated `history` out. The first turn of a
  conversation carries the topic and empty history and returns the agent's
  opener.

**No persistence at all.** Conversation state is the same opaque, client-held
pydantic-ai message history as generation (`dump_message_history` /
`load_message_history`, extracted to a shared module so both services use one
implementation). There is no conversation table, no migration, and no rows
written anywhere in this feature — practice deliberately does not create
`activity_completions` or touch review state.

**Rate limiting.** A second `FixedWindowRateLimiter` instance on `app.state`
with its own env cap, `PRACTICE_RATE_LIMIT_PER_HOUR` (default 60 — turns are
frequent and cheap relative to pack drafts), counted on attempt, 429 over the
cap. Same single-process caveat as ADR 0010.

**No streaming.** Turns are request/response like every other call in the
app. Replies are 1–3 short sentences, so time-to-full-response is close to
time-to-first-token, and SSE would be the single most expensive piece of new
infrastructure in the feature. Revisit when voice forces the latency
question.

**Frontend.** A fourth tab, Practice, in `tab-bar.tsx`; a topic-picker route
and a chat route under `/practice`; a pure reducer module
(`lib/practice-chat.ts`) modeled on `generation-chat.ts` for turn lifecycle,
failure kinds, and retry; a segment bubble component rendering hanzi
prominently with pinyin beneath and English behind a per-segment tap;
`english_aside` as a visually distinct helper bubble. The tab is always
rendered; the screen itself shows an unavailable state when `/status` reports
disabled (hiding a tab on an async fetch would shift the app shell).

**Testing posture: zero real LLM calls in CI**, identical to ADR 0010: the
shared conftest's `ALLOW_MODEL_REQUESTS = False`, every tier drives the agent
with `TestModel`/`FunctionModel` via `Agent.override`, and one
`@pytest.mark.external` contract test exercises the real provider and asserts
the `PracticeTurn` schema holds. The flow emits WF-16 workflow events
(`practice_turn_completed`, with `outcome=error` on rate-limit/unconfigured/
provider failures), and Logfire's pydantic-ai instrumentation covers the
conversations with no extra work.

## Consequences

- **Model-supplied pinyin and translations are unverified** — the same
  trade-off ADR 0010 accepted for pack glosses, with the same containment:
  the content is ephemeral and shown only to the learner who prompted it.
  A wrong gloss misinforms one reply, not stored content. ("Ephemeral" means
  no application storage; like generation, full conversations are exported to
  Logfire spans for operator review when `LOGFIRE_TOKEN` is configured.)
- **Ephemeral means lossy.** Leaving the chat screen (or refreshing) discards
  the conversation. Accepted deliberately; `sessionStorage` retention of the
  serialized history is a cheap client-only mitigation if it stings, and a
  future `practice_sessions` table is purely additive — nothing in this
  design blocks it.
- **English is generated on every turn even if never revealed.** A few dozen
  extra output tokens per turn buys instant tap-reveal with no second
  request; accepted as the right trade at chat-model prices.
- **The rate limiter remains single-process** (in-memory windows), now for
  two features. The shared-store caveat from ADR 0010 applies unchanged and
  becomes marginally more relevant with a second LLM surface.
- **Fixed difficulty will misfit some learners.** HSK 1–2 in the prompt fits
  the base PRD's primary user; a level picker is a recorded fast-follow, and
  grounding vocabulary in `ReviewState`/`PackRepository` data is a natural
  later step the user-scoped data layer already supports.
- **Practice is invisible to progress.** No completions, streaks, or stats —
  the deliberate parallel-flow framing. If practice should ever count toward
  the daily goal, that is a product decision requiring a new
  `activity_completions` source, not a small tweak.
- Voice and streaming are deferred together: adding voice will force
  latency/streaming decisions this ADR intentionally avoids, and the
  request/response `POST /turn` contract would gain a streaming sibling
  rather than change shape.
