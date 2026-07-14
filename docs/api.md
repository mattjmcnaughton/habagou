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
| POST | `/api/v1/generation/draft` | Draft (or refine) a corpus-grounded pack from a topic |
| POST | `/api/v1/generation/packs` | Persist a finalized draft as a pack owned by the current user |

Agent pack generation drafts a themed practice pack from a topic, grounded so it
only ever references hanzi that exist in the stroke corpus (see
[ADR 0010](adrs/0010-agent-pack-generation.md)). Both endpoints require a valid
session. Generation is env-configured (`OPENROUTER_API_KEY`, `GENERATION_MODEL`);
when unconfigured, `POST /generation/draft` returns 503.

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
- 429 — the caller exceeded `GENERATION_RATE_LIMIT_PER_HOUR` (default 10, counted
  per attempt).
- 502 — the generation run failed (provider/model error).
- 503 — generation is not configured (`OPENROUTER_API_KEY` unset).
- 422 — `history` is present but is not a valid generation message history.

`POST /api/v1/generation/packs` body:

```json
{ "draft": { /* a PackDraft returned by /generation/draft */ } }
```

-> 201 — a `PackDetailDTO` for the newly created pack, owned by and visible only
to the caller. Glyph, color, and sort order are defaulted at save time; owned
packs list after curated ones.

- 422 — the draft references a character absent from the stroke corpus
  (re-validated at save).
