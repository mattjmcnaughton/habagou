# Habagou — PRD Addendum: Conversational Practice

| | |
|---|---|
| Status | **Final v1.0** — approved for implementation |
| Depends on | [PRD](prd.md) v1.0 — packs, activities, users/progress remain as specified there; [prd-path.md](prd-path.md) — the Path remains the default surface |
| Related | [ADR 0011](../adrs/0011-conversational-practice-agent.md) — technical decision record |
| Last updated | 2026-07-18 |

## 1. Summary

Habagou teaches learners to *write* characters; nothing in the app exercises
*using* them in conversation. This addendum adds a **conversational practice
agent**: a text-only chat with an AI tutor on a learner-chosen topic, replying
in simplified Chinese with pinyin, with an English translation one tap away
and an English "break glass" escape hatch when the learner asks for help.

Practice is a **parallel flow**, not a change to the core loop: it gets its
own top-level tab alongside Path, Packs, and Progress, and it does not touch
the scheduler, packs, or progress tracking. Conversations are ephemeral —
nothing is stored server-side.

## 2. Problem & motivation

The Path and pack activities build recognition and handwriting, but a learner
who can trace 你好 still freezes when asked 你想喝什么. There is no low-stakes
place to *produce* language — to read a question, compose a reply, and get an
immediate, comprehensible response. Real conversation partners are
intimidating and not always available; generic chatbots reply above a
beginner's level and give no pinyin or translation support. A tutor agent
pinned to beginner level, with pinyin always visible and English one tap
away, fills that gap in the same 5–15 minute sessions the rest of the app is
built around.

## 3. Goals

1. Let the learner practice reading and producing Chinese in a free-form
   text conversation on a topic they choose.
2. Keep every agent reply comprehensible to a beginner: short sentences,
   HSK 1–2 vocabulary, pinyin always shown, English translation on demand.
3. Never leave the learner stuck: they can write in English, Chinese, or a
   mix, and can ask the agent to explain in English at any point.
4. Ship it as a parallel surface with zero impact on the Path, packs, and
   progress features specified in the base PRD and the Path addendum.

## 4. Non-goals

- **Voice** — no speech input or audio output. Text only. Voice is the
  natural v2 of this feature and this design must not preclude it, but it is
  explicitly out of scope now.
- **Persisted conversations.** Conversations are ephemeral, client-held
  state; there is no server-side conversation store, no history screen, and
  no resuming a conversation after the client discards it.
- **Adaptive difficulty.** The tutor level is fixed at beginner (HSK 1–2) in
  the system prompt. A user-facing level picker is a recorded fast-follow,
  not part of this release.
- **Grounding in the learner's vocabulary.** The agent does not read the
  learner's packs or review states to pick words. (Future work — the data
  layer already supports it.)
- **Progress integration.** Practice conversations do not create
  `activity_completions`, do not count toward the daily goal or streak, and
  do not appear on the Progress tab.
- **Streaming responses.** Turns are request/response, matching the pack
  generation chat. Revisit alongside voice.
- **Verified glosses.** Pinyin and translations are model-supplied and
  unverified, the same trade-off [ADR 0010](../adrs/0010-agent-pack-generation.md)
  accepted for generated packs.
- Everything the base PRD already excludes (§ 4) still applies.

## 5. Users

Same beginner learner as the base PRD (§ 5): knows some pinyin and HSK 1–2
vocabulary. For this feature they are additionally assumed to be able to
*read* short sentences with pinyin support, which the Trace/Match activities
build toward.

## 6. Functional requirements

### 6.1 Entry & topic selection

- FR-35: The tab bar gains a fourth top-level tab, **Practice**, alongside
  Path, Packs, and Progress. The tab is always rendered; when the feature is
  not configured server-side (see FR-44), the Practice screen shows a
  friendly unavailable state instead of the topic picker.
- FR-36: The Practice screen opens on a topic picker: a free-text topic
  input plus a small set of starter-topic chips (e.g. "Ordering food",
  "Meeting someone new", "Asking for directions"), mirroring the starter
  chips of the pack-generation chat. Picking or typing a topic starts the
  conversation.
- FR-37: The agent opens the conversation: after the learner submits a
  topic, the first turn is an agent greeting/question on that topic — the
  learner never faces a blank chat with the first move.

### 6.2 Conversation

- FR-38: Each agent turn is structured as one or more **segments**, one per
  sentence. A segment carries hanzi, pinyin, and an English translation. The
  bubble renders hanzi prominently with pinyin beneath; the English is
  hidden by default.
- FR-39: Tapping a segment toggles its English translation. Reveal is
  per-segment, not per-message, and revealing is purely client-side (the
  translation was generated with the turn — no extra request).
- FR-40: The learner's composer is plain free text and accepts English,
  Chinese, or mixed input; the agent understands all three and keeps
  replying in Chinese segments regardless of input language.
- FR-41: **Break glass:** when the learner asks for help in understanding
  ("what does X mean?", "explain that", "say it in English"), the agent turn
  carries an English aside rendered as a visually distinct helper bubble,
  and the conversation continues in Chinese segments in the same turn.
- FR-42: Agent replies stay beginner-sized: 1–3 short segments per turn,
  HSK 1–2 vocabulary, ending with a question or prompt that invites the next
  learner turn.
- FR-43: Conversations are ephemeral. Conversation state lives only in the
  client for the life of the chat screen; a **New conversation** action
  returns to the topic picker and discards the old state. No conversation
  data is persisted server-side.

### 6.3 Availability, limits & failures

- FR-44: The feature is enabled only when the server has an LLM provider
  configured (same mechanism as pack generation). A status endpoint reports
  enablement; when disabled, turn requests fail with 503 and the UI shows
  the unavailable state of FR-35.
- FR-45: Turn requests are rate-limited per user (fixed window, counted on
  attempt, env-configured cap; default 60/hour — chat turns are more
  frequent and cheaper than pack drafts). Over the cap, the API returns 429
  and the chat shows a friendly "take a break" message. No retry countdown
  is shown (the API does not expose the window — mirroring the
  pack-generation chat, which refuses to fake one); the conversation is
  kept and the composer stays usable.
- FR-46: A failed turn appears in the conversation as an error entry,
  mirroring the pack-generation chat's failure handling; the conversation
  is never lost. Provider and network failures offer a "Try again"
  affordance that resubmits the last message without duplicating its
  bubble; rate-limit entries omit it (the re-enabled composer is the retry
  path).

## 7. Design requirements

Same visual language as the rest of the app (base PRD § 7: dark theme,
Hanken Grotesk + Noto Sans SC, mobile-first). The chat reuses the
pack-generation chat's conversational layout (bubbles, pending indicator,
composer). Hanzi render in the hanzi font at reading size with pinyin as a
secondary line; unrevealed translation is visually discoverable (affordance
that the bubble is tappable) without cluttering the reading experience. The
English aside (FR-41) is visually distinct from Chinese segments.

## 8. Success metrics

In addition to the base PRD's metrics (§ 8):

- Comprehensibility: a learner can complete a multi-turn conversation using
  tap-reveal and break-glass rather than abandoning it.
- Engagement: practice sessions of several turns occur alongside — not
  instead of — Path usage.

## 9. Delivery

Three slices, each independently landable:

1. **Backend** — practice agent service, `status` + `turn` endpoints, rate
   limiting, tests (no migrations; the feature has no persistence).
2. **Frontend** — Practice tab, topic picker, chat screen with tap-reveal
   segments and break-glass aside, reducer + component tests.
3. **Polish** — starter chips, unavailable/limit states, e2e coverage, docs
   (`docs/api.md`, workflow catalog WF-16).

## 10. Open questions

None outstanding. Decisions locked during planning: fourth tab (vs. an entry
card), ephemeral conversations (vs. persisted), fixed beginner level (vs. a
level picker) — see [ADR 0011](../adrs/0011-conversational-practice-agent.md).
