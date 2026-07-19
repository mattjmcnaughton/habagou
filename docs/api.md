# API Reference

## Health

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/healthz` | Liveness probe — returns 200 if the process is alive |
| GET | `/readyz` | Readiness probe — returns 200 if the service is ready to accept traffic |

## Endpoints

All `/api/v1` data endpoints require a valid signed session cookie. Missing or
invalid sessions return the standard error envelope with HTTP 401:

```json
{
  "error": {
    "code": "unauthenticated",
    "message": "authentication required",
    "request_id": "..."
  }
}
```

### Auth

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/auth/login` | Start the configured provider login flow |
| GET | `/auth/callback` | Complete provider callback, provision/load user, and set the session cookie |
| POST | `/auth/logout` | Clear the local session cookie |
| GET | `/api/v1/auth/session` | Probe the current session; always returns 200 with `authenticated`, `provider`, and optional `user` |

The authenticated `user` object includes `feature_flags`: the user's resolved
feature-flag map (every code-registered flag key with its effective on/off
state). See [Feature Flags](#feature-flags).

### Feature Flags

Feature flags are defined in code (`services/feature_flags.py`) with a default
per flag; the `FEATURE_FLAG_DEFAULTS` setting can flip a default globally
without a deploy of code (comma-separated `key:on` / `key:off` entries), and
the endpoints below manage per-user database overrides, which win over both —
note this means a settings flip changes the default but does not force the
flag for users holding an override. All three endpoints are admin-only (403
for regular users).

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/v1/admin/feature-flags` | List every registered flag with its effective default and per-user override count |
| PUT | `/api/v1/admin/feature-flags/{flag_key}/users/{user_id}` | Set (upsert) one user's override; body `{"enabled": bool}` |
| DELETE | `/api/v1/admin/feature-flags/{flag_key}/users/{user_id}` | Clear one user's override (idempotent 204) |

`PUT` and `DELETE` return 404 for a `flag_key` not registered in code; `PUT`
also returns 404 when the target user does not exist.

### Packs

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/v1/packs` | List the user's bench: owned packs plus enabled global packs, in curriculum order |
| GET | `/api/v1/packs/{pack_id}` | Fetch one visible pack with its characters and sentences |
| PUT | `/api/v1/packs/{pack_id}/enabled` | Enable or disable a global (library) pack for the current user |
| DELETE | `/api/v1/packs/{pack_id}` | Delete one of the current user's own packs |

A pack is **visible** to a user when it is global (a curated, seeded pack) or
privately owned by that user; a pack owned by someone else is invisible (see
[ADR 0009](adrs/0009-pack-ownership.md)). Visible global packs are further
split by **enablement** (see
[ADR 0012](adrs/0012-pack-library-enablement.md)): `GET /api/v1/packs` lists
only enabled ones, while a disabled global pack stays fetchable by id so the
library can preview it.

Both `PackSummaryDTO` (list rows) and `PackDetailDTO` (detail) carry an `owned`
boolean (`true` when the current user owns the pack), a `starter` boolean (the
pack is enabled by default for every user), and an `enabled` boolean (the
current user's effective enablement; always `true` for owned packs).

`PUT /api/v1/packs/{pack_id}/enabled` takes `{"enabled": true|false}` and is
idempotent. Disabling prunes the user's never-completed path items for the
pack; progress, review state, and completed lessons are kept, so re-enabling
resumes where the learner left off.

- 204 — the choice was recorded.
- 404 — the pack is not visible (unknown id, or another user's private pack).
- 409 — the pack is owned by the caller; owned packs are always enabled.

`GET /api/v1/packs/{pack_id}` returns 404 when the pack is not visible — an
unknown id and another user's private pack are indistinguishable, so pack
existence never leaks.

`DELETE /api/v1/packs/{pack_id}` -> 204 No Content on success; it hard-deletes
the pack and, by database cascade, its characters, sentences, and every user's
completions, path items, and review state for it.

- 204 — the pack was owned by the caller and has been deleted.
- 403 — the pack is visible but global/curated; curated packs are seed-managed
  and cannot be deleted through the API (disable it instead).
- 404 — the pack is not visible (unknown id, or another user's private pack).

### Library

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/v1/library` | The full curated pack library, grouped by category |

Returns `{"categories": [...]}` in display order; each category carries its
`slug`, `title`, and `packs` (id, title, glyph, color, description, counts,
`starter`, and the caller's `enabled` flag). Library rows are intentionally
slim — no per-pack progress aggregates — because the library lists the whole
catalog; progress belongs to the bench (`GET /api/v1/packs`). Owned packs
never appear in the library.

### Progress

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/v1/progress/summary` | Current user's daily goal, streaks, 45-day activity heatmap, and next milestone |
| GET | `/api/v1/progress/packs/{pack_id}` | Current user's per-activity progress for a pack |
| POST | `/api/v1/progress/completions` | Record an activity completion for the current user |
| DELETE | `/api/v1/progress/packs/{pack_id}` | Reset current user's progress for a pack |

`GET /api/v1/progress/summary` accepts optional
`tz_offset_minutes` (`-900` to `900`), matching JavaScript
`new Date().getTimezoneOffset()`, so streaks and heatmap buckets use the
learner's local day.

Since the Learning Path shipped, `GET /api/v1/progress/summary` additionally
returns:

```json
{
  "characters_traced": 15,
  "packs_completed": 1,
  "packs_total": 4
}
```

- `characters_traced` — distinct pack characters the current user has traced
  at least once, via path Trace items or a completed whole-pack Trace
  activity.
- `packs_completed` — packs where all three whole-pack activities are
  complete for the current user.
- `packs_total` — total global packs. The Learning Path and these stats stay
  global-only this epic (see
  [ADR 0009](adrs/0009-pack-ownership.md)); private, owned packs are excluded.

### Path

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/v1/path` | Current user's endless, scheduler-ordered path item queue |
| POST | `/api/v1/path/items/{item_id}/complete` | Record completion of a path item for the current user |

The Path is the default, scheduler-ordered stream of short lesson items
(**path items**) described in `CONTEXT.md`. Path completions feed the same
daily-goal/streak counters as whole-pack activity completions but never
affect whole-pack activity badges (`per_pack_aggregate` filters to
`source='pack'`).

`GET /api/v1/path?cursor=<int>&limit=<int<=50>` -> 200

```json
{
  "items": [ /* PathItemDTO, see below */ ],
  "next_cursor": 17,
  "daily": { "completed": 2, "target": 3 },
  "streak": 12,
  "due": { "new": 1, "review": 2 }
}
```

- `items` — today's done items, then the current item, then pending items up
  to `limit`.
- `next_cursor` — pass as `cursor` to page further by `position`.
- `daily` / `streak` — the same daily-goal/streak counters as
  `GET /api/v1/progress/summary`, counting both pack and path completions.
- `due` — counts of new vs. review items available in the queue.

If fewer than the server's pending window (default 10) of not-yet-done items
remain, the server materializes more path items at the tail of the queue
using current review state before responding.

`PathItemDTO`:

```json
{
  "id": "uuid",
  "position": 4,
  "activity": "trace" | "match" | "sentence",
  "kind": "new" | "review",
  "state": "done" | "current" | "locked",
  "unit_label": "UNIT 1 · WARMING UP" | null,
  "pack": { "title": "Numbers", "glyph": "三", "color": "#3f8a86" },
  "content": {
    "trace":    { "chars": [{ "hanzi": "一", "pinyin": "yī", "meaning": "one" }] },
    "match":    { "pairs": [{ "hanzi": "一", "pinyin": "yī", "meaning": "one" }] },
    "sentence": { "hanzi": "一二三", "pinyin": "yī èr sān", "translation": "one two three" }
  }
}
```

`content` carries exactly one key, matching `activity`. `unit_label` is a
derived, cosmetic grouping label (see `CONTEXT.md`) and is `null` when an
item does not start a new unit. Item content is pinned at generation time and
does not change even if the underlying pack content changes later.

`POST /api/v1/path/items/{item_id}/complete` body:

```json
{ "duration_ms": 41200 }
```

-> 201

```json
{
  "daily": { "completed": 3, "target": 3 },
  "streak": 12,
  "item_id": "uuid",
  "next_item_id": "uuid"
}
```

- 201 — completion recorded; every reviewable unit in the item advances on
  the Leitner ladder (see `docs/product/prd-path.md` FR-26).
- 409 — the item was already completed.
- 404 — `item_id` does not exist for the current user.

### Generation

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/v1/generation/status` | Report whether generation is configured (entry-point gating) |
| POST | `/api/v1/generation/draft` | Draft (or refine) a corpus-grounded pack from a topic |
| POST | `/api/v1/generation/packs` | Persist a finalized draft as a pack owned by the current user |

Agent pack generation drafts a themed practice pack from a topic, grounded so it
only ever references hanzi that exist in the stroke corpus (see
[ADR 0010](adrs/0010-agent-pack-generation.md)). Generation is env-configured
(`OPENROUTER_API_KEY`, `GENERATION_MODEL`); when unconfigured,
`POST /api/v1/generation/draft` returns 503. The frontend calls the
`GET /api/v1/generation/status` probe (`{"enabled": bool}`) to hide the
"Create a pack" entry point while generation is unconfigured, so a user is
never routed into a flow the `/draft` endpoint can only 503.

For admin callers (see [Admin users](auth.md#admin-users)) the status response
additionally carries the admin model picker's data — `models` (the selectable
OpenRouter models as `{id, label}`, server default first, from
`ADMIN_CHAT_MODELS` plus the default) and `default_model`. Both are `null` for
non-admin callers and when generation is unconfigured; the response itself
gates the picker UI.

`POST /api/v1/generation/draft` body:

```json
{
  "topic": "ordering food at a restaurant",
  "history": null
}
```

- `topic` — required, 1–2000 chars.
- `history` — the opaque message-history array returned by a prior draft turn,
  or `null` on the first turn. The client holds it between turns and passes it
  back to refine the draft; there is no server-side conversation store.

-> 200

```json
{
  "draft": {
    "title": "At the Restaurant",
    "characters": [
      { "hanzi": "菜", "pinyin": "cài", "meaning": "dish; vegetable" }
    ],
    "sentences": [
      { "hanzi": "我要茶", "pinyin": "wǒ yào chá", "translation": "I want tea" }
    ],
    "coverage_note": "found 6 of 8 requested characters; 望 and 憧 aren't in the corpus yet"
  },
  "history": [ /* opaque, pass back on the next refinement turn */ ]
}
```

- `draft.characters` — 1–30 members, each with a model-supplied pinyin and
  meaning (the corpus stores no glosses).
- `draft.sentences` — up to 12 optional practice sentences; every glyph is also
  corpus-validated.
- `coverage_note` — a non-null honest note when some requested characters are
  absent from the corpus, rather than silently shrinking the pack.
- `model` — optional, admin-only OpenRouter model override for this turn; must
  be one of the ids the status response listed. `null`/omitted runs the server
  default. Switching models mid-conversation is allowed (the history replay is
  model-agnostic).
- 403 — `model` was sent by a non-admin caller.
- 429 — the caller exceeded `GENERATION_RATE_LIMIT_PER_HOUR` (default 10, counted
  per attempt).
- 502 — the generation run failed (provider/model error).
- 503 — generation is not configured (`OPENROUTER_API_KEY` unset).
- 422 — `history` is present but is not a valid generation message history, or
  `model` is not one of the selectable ids (the error names them).

`POST /api/v1/generation/packs` body:

```json
{ "draft": { /* a PackDraft returned by /generation/draft */ } }
```

-> 201 — a `PackDetailDTO` for the newly created pack, owned by and visible only
to the caller. Glyph, color, and sort order are defaulted at save time; owned
packs list after curated ones.

- 422 — the draft references a character absent from the stroke corpus
  (re-validated at save).

### Practice

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/v1/practice/status` | Report whether practice is configured (screen gating) |
| POST | `/api/v1/practice/turn` | Run one conversational practice turn |

Conversational practice is a text chat with an AI tutor on a learner-chosen
topic (see [ADR 0011](adrs/0011-conversational-practice-agent.md)). It shares
the OpenRouter key with generation but has its own model (`PRACTICE_MODEL`)
and its own hourly cap. Conversations are ephemeral and client-held: there is
no server-side conversation store and nothing is persisted. The frontend calls
the `GET /api/v1/practice/status` probe (`{"enabled": bool}`) to show an
unavailable state (the Practice tab itself always renders) while practice is
unconfigured.

For admin callers the status response also carries `models`/`default_model`
(the admin model picker's data, mirroring the generation status probe), and
`POST /api/v1/practice/turn` accepts the same optional admin-only `model`
override with the same 403/422 behavior as `/generation/draft`.

`POST /api/v1/practice/turn` body:

```json
{
  "message": "ordering food at a restaurant",
  "history": null
}
```

- `message` — required, 1–2000 chars. On the first turn it is the learner's
  chosen topic (the tutor opens the conversation from it); on later turns it
  is the learner's chat input — English, Chinese, or mixed.
- `history` — the opaque message-history array returned by a prior turn, or
  `null` on the first turn. The client holds it between turns and passes it
  back; discarding it is how a conversation ends.

-> 200

```json
{
  "turn": {
    "segments": [
      { "hanzi": "你好", "pinyin": "nǐ hǎo", "english": "Hello!" },
      { "hanzi": "你想吃什么", "pinyin": "nǐ xiǎng chī shénme", "english": "What do you want to eat?" }
    ],
    "english_aside": null
  },
  "history": [ /* opaque, pass back on the next turn */ ]
}
```

- `turn.segments` — 1–8 per-sentence segments, each carrying the sentence
  three ways. All glosses are model-supplied and unverified (contained to one
  ephemeral reply). The UI shows hanzi + pinyin and reveals `english` per
  segment on tap.
- `turn.english_aside` — non-null only when the learner asked for help in
  English ("break glass"); rendered apart from the Chinese segments.
- 429 — the caller exceeded `PRACTICE_RATE_LIMIT_PER_HOUR` (default 60,
  counted per attempt).
- 502 — the practice turn failed (provider/model error).
- 503 — practice is not configured (`OPENROUTER_API_KEY` unset).
- 422 — `history` is present but is not a valid practice message history.
