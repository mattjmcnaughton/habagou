# Agent Pack Generation — PRD, Design, Tickets

**Status: Draft for review.** Owner: @mattjmcnaughton. Branch: `claude/agent-pack-suggestions-keaix0`.

A single dossier for the "chatbot creates practice packs" feature. It contains three parts:

1. [PRD](#part-1--prd) — what we're building and why.
2. [Design](#part-2--design) — how it's built, including the pack-ownership cleanup it depends on.
3. [Tickets](#part-3--tickets) — ordered work breakdown (Epics 6–7, continuing from HAB-053).

Reference docs: [PRD](product/prd.md), [TDD](technical/tdd.md), [Architecture](architecture.md), [ADR 0001 — corpus in Postgres](adrs/0001-stroke-corpus-in-postgres.md), [ADR 0004 — defer AI generation](adrs/0004-defer-ai-generation.md) (this feature reverses it).

> **Reverses prior decisions.** ADR 0004 deferred AI generation and preserved `packs.status` as a forward-compat hook for it. This feature (a) implements AI generation and (b) finds that pack *ownership*, not *status*, is the mechanism it actually needs — so `packs.status` is removed rather than used. Both changes require new ADRs (see [§2.7](#27-adr-obligations)).

---

## Part 1 — PRD

### 1.1 Problem

Habagou teaches Hanzi by tracing characters stroke-by-stroke, but the practice set is a fixed catalog of four curated packs (`greetings`, `numbers`, `family`, `food-drink`). A learner with a concrete goal — "I'm going to a restaurant next week", "I want the characters on my medication label" — has no way to get a practice set for *their* need. Adding one today means a code change, a seed edit, and a deploy.

### 1.2 Goal

Let a logged-in user describe a topic in natural language and get a private, traceable practice pack generated for them on the spot, drawn from characters the app can actually render.

### 1.3 Non-goals

- **Not** a general Chinese tutor / conversation partner. The chat exists to produce a pack, then stops.
- **Not** community/shared content. Generated packs are private to their creator; there is no publish-to-everyone flow in this feature.
- **Not** teaching characters outside the stroke corpus. If a character has no stroke data, it cannot appear in a pack (see [§2.2](#22-the-hard-constraint-corpus-grounding)).
- **Not** offline/on-device generation. Generation calls a hosted LLM provider at runtime.

### 1.4 Users & stories

- *As a goal-driven learner*, I type "characters for ordering at a restaurant" and receive a pack of relevant, traceable characters with pinyin and meaning, so I can practice immediately.
- *As a learner mid-conversation*, I say "make it a bit harder" or "add some food words", and the pack is refined without starting over.
- *As any learner*, my generated packs appear in my catalog next to the curated ones and track progress identically.
- *As a learner*, when my topic only partially maps to the corpus, I'm told honestly ("I found 8 of ~12 characters; the rest aren't in the tracing set yet") rather than handed a silently stunted pack.

### 1.5 UX shape

Multi-turn chat (wanted from day one, not a later add):

```
User:  I'm going to a restaurant in Beijing, what should I practice?
Agent: Here's a "Restaurant" pack — 9 characters incl. 菜 (cài, dish),
       喝 (hē, drink), 水 (shuǐ, water)… want me to add ordering phrases?
User:  yes, and make it a little harder
Agent: Updated — added 3 sentence drills and swapped in 餐/廳…
       [Save pack]  [Keep chatting]
```

- The draft pack is visible/previewable during the conversation; **Save** persists it to the user's catalog.
- Refinement turns carry conversation history so "make it harder" has context.

### 1.6 Success metrics

- A user can go from a one-line topic to a saved, traceable pack in one round-trip.
- Generated packs are corpus-valid 100% of the time (no dead entries) — enforced, not hoped.
- A bad generation is contained to the requesting user; it can never appear in another user's catalog.

### 1.7 Risks

| Risk | Mitigation |
| --- | --- |
| Model suggests characters not in the corpus | Output validator rejects them; agent retries. Grounding tool returns only real rows. ([§2.2](#22-the-hard-constraint-corpus-grounding)) |
| Thin corpus coverage for niche topics | Agent reports coverage honestly; shortfall is a signal for corpus expansion. |
| Provider cost / latency / outage | Generation is user-initiated and rate-limited; failure degrades to an error message, not a broken catalog. |
| Low-quality generations pollute shared content | Impossible by construction — packs are private by ownership ([§2.1](#21-two-tier-pack-ownership)). |

---

## Part 2 — Design

The feature is two sequenced pieces: a **cleanup** that reshapes packs around ownership, then the **agent** layered on top. The cleanup is a prerequisite because it establishes the privacy/visibility model the agent relies on.

### 2.1 Two-tier pack ownership

Add one nullable column to `Pack`:

- **`owner_id: FK(users.id) NULL`**
  - `NULL` → **global pack** — curated, seeded via `scripts/seed.py`, visible to everyone. (Today's four packs.)
  - non-null → **user pack** — generated by the agent, visible only to that user.

This single column replaces the two mechanisms it makes redundant:

- **Visibility gate.** Today `packs.py` and `progress.py` gate on `status == PUBLISHED`. That becomes: a user may see/trace a pack iff `owner_id IS NULL OR owner_id == user.id`.
- **Catalog composition.** `list_published()` → `list_visible(user)` = global ∪ owned.

Because privacy is now ownership, there is **no draft/publish state** for user packs — they are private the moment they exist and shown immediately. See [§2.3](#23-removing-packstatus).

### 2.2 The hard constraint: corpus grounding

A `PackCharacter` FKs to `Character`, and `Character` rows exist only for hanzi imported from the pinned stroke corpus (ADR 0001). **A pack can only contain a character the app can render stroke-by-stroke.** This is the central design constraint, and the agent must be built around it, not against it.

Grounding is enforced in two layers so a hallucinated character can never reach the database:

1. **A corpus-search tool** on the agent — `find_characters(candidates) -> [CharacterMatch]` — backed by `CharacterRepository.bulk_exists` (already returns the missing set in one query, HAB-013). The agent proposes candidate hanzi; the tool returns only those that exist, with pinyin/meaning. The model reasons over the *real* corpus, not its training memory.
2. **An output validator** on the agent's `output_type` — rejects any hanzi not present in `Character`. On rejection, pydantic-ai feeds the error back and the model retries. The schema is the contract.

Coverage honesty ([§1.4]) falls out of layer 1: the tool knows exactly which candidates were dropped, so the agent can report the shortfall.

### 2.3 Removing `PackStatus`

`PackStatus {DRAFT, PUBLISHED, RETIRED}` currently does two jobs — catalog filtering and the visibility gate — both now owned by `owner_id` ([§2.1](#21-two-tier-pack-ownership)). It is also already effectively constant: `seed.py` writes every pack `PUBLISHED`, and the only runtime writer of other states was the admin subsystem, which is being removed ([§2.4](#24-removing-the-admin-subsystem)).

Decision: **drop the column and the `pack_status` enum type entirely.** Delete `PackStatus`, rewrite both gates as ownership checks, rename `list_published` → `list_visible`.

Capability consciously dropped: `RETIRED` was a soft-delete that hid a global pack while preserving `ActivityCompletion` history FK'd to it. Without status, removing a shipped global pack is a real delete that touches that history. Acceptable because global content is seed-managed and retire is unused — flagged here for whenever a shipped pack is first removed.

### 2.4 Removing the admin subsystem

Admin today is a shared-secret (`ADMIN_TOKEN`) HTTP API with three actions — publish / retire / patch sort_order — all on existing global packs. There is no admin *user role* (`User` has only `is_guest`), no admin UI, and no create-pack path anywhere (packs come only from `seed.py`).

In the new model every write is accounted for without it: global packs are code/seed-managed, user packs are agent-created and owner-scoped. The token API is vestigial. **Remove it end-to-end**: `dtos/admin.py`, `services/admin.py`, `routers/v1/admin.py`, the `admin_token` setting + its auth path, the `app.py` wiring, `tests/integration/test_admin_api.py`, and retire the `WF-09` workflow event from coverage.

Capability dropped: runtime status changes to global packs. Replacement: edit seed data and deploy ("content as code"), consistent with schema-in-migrations and config-in-pyproject. If live moderation is ever needed it will be a different, authenticated, per-user concept.

### 2.5 UUID-only addressing

All pack routes address by `pack.id` (UUID), never slug: `/api/v1/packs/{pack_id}`, `/api/v1/progress/packs/{pack_id}`. `get_by_slug` → `get_by_id`; add owner-scoped `get_visible(pack_id, user)` for authorization.

`slug` is demoted, not deleted: its only remaining consumer is `seed.py`, which upserts by slug (`select(Pack).where(Pack.slug == ...)`) to stay idempotent. So `slug` becomes **nullable** (user packs have none) with a **partial unique index** `WHERE slug IS NOT NULL`, and never appears in a URL again.

### 2.6 The agent

Built with pydantic-ai, wired to fit the existing router → service → repository layering.

- **`services/pack_generation.py`** holds an injected `Agent[GenerationDeps, PackDraft]`. `output_type=PackDraft` (title, characters[hanzi+pinyin+meaning], optional sentences). Deps carry the DB session and current user for the grounding tool.
- **Injected as a FastAPI dependency** (`get_generation_agent`) — never constructed inline — so every test tier can override it (see [§2.8](#28-testing--ci-strategy)).
- **Multi-turn**: the endpoint accepts prior message history; pydantic-ai threads it so refinement turns ("make it harder") have context. History is client-held per chat session; no server-side conversation store in this feature.
- **Persistence**: on **Save**, `PackService`/`PackRepository.create(owner_id=current_user.id, ...)` writes the pack + `PackCharacter`/`PackSentence` rows, reusing the same write path seed uses.
- **New router** `routers/v1/generation.py` (chat/generate + save endpoints), current-user gated by the existing session-cookie resolver — no new auth concept.

### 2.7 ADR obligations

Two ADRs accompany this work:

- **Supersede ADR 0004** — AI generation is no longer deferred; record the corpus-grounding + private-by-ownership model as the shape it took.
- **New ADR — pack ownership & status removal** — record two-tier ownership, UUID addressing, `PackStatus` removal, and admin removal as one coherent decision, superseding the `packs.status` forward-compat note in `tickets.md`.

### 2.8 Testing & CI strategy

Non-negotiable: **PR CI makes no real LLM API call.** pydantic-ai is built for this.

- **Global safety net** — `models.ALLOW_MODEL_REQUESTS = False` in shared conftest; any accidental real request raises instead of hitting the wire.
- **Unit (`just gate`, every PR)** — `TestModel`/`FunctionModel` via `Agent.override`; test prompt construction, grounding-tool wiring, output-validator logic, coverage-shortfall reporting. No DB, no network.
- **Integration (`just test-integration`, Postgres job)** — real app via `create_app()` + `ASGITransport`, model stubbed through `app.dependency_overrides[get_generation_agent]`. Exercises the full slice incl. the grounding tool hitting **real Postgres** and the pack-create write path — model stubbed, everything else real.
- **E2E (`just test-e2e`, Playwright)** — real chat UI, agent stubbed via dependency override. Deterministic; validates the user-facing generate → save → trace flow.
- **External (`@pytest.mark.external`, `gate-external` only — NOT on PRs)** — one test runs the *real* provider against the real prompt + `output_type` to catch schema/model drift. Runs locally or on a scheduled/manual job with the key in secrets.

`TestModel`/`FunctionModel` first; reach for VCR cassettes only if a bug class needs real response shapes (higher fidelity, higher maintenance + secret-scrubbing cost).

### 2.9 Sequencing

Two PRs. Cleanup lands and stabilizes the ownership model first; the agent is then a clean addition.

```
PR 1 (Epic 6, cleanup)         PR 2 (Epic 7, agent)
owner_id + UUID addressing  →  pydantic-ai agent + grounding
drop status + admin            chat/generate/save endpoints
list_visible, ADR              offline test tiers, external test, ADR
```

---

## Part 3 — Tickets

Ordered for an implementing agent. Every ticket passes `just gate` before merge; feature tests carry workflow tags. **[FE]**/**[BE]** touch one side. Continues numbering from HAB-053.

### Epic 6 — Pack ownership cleanup (PR 1)

#### HAB-060 — [BE] `Pack.owner_id` + migration
Deps: none (builds on shipped schema).
Add nullable `owner_id` FK → `users.id` on `packs` (`NULL` = global). Alembic migration with clean downgrade. Backfill existing rows to `NULL`.
**AC:** upgrade + downgrade clean; existing four packs are `owner_id IS NULL`; integration test round-trips a global pack and an owned pack.

#### HAB-061 — [BE] Drop `PackStatus`
Deps: HAB-060, HAB-063 (admin removal — the other status writer).
Remove `status` column + `pack_status` enum type (migration). Delete `PackStatus` from `models.py`. Update `seed.py` to stop setting status.
**AC:** migration drops column + enum type with clean downgrade; `grep PackStatus src/` returns nothing; seed still idempotent; suite green.

#### HAB-062 — [BE] Ownership-based visibility & UUID addressing
Deps: HAB-060, HAB-061.
`list_published` → `list_visible(user)` = `owner_id IS NULL OR owner_id == user.id`. `get_by_slug` → `get_by_id`; add `get_visible(pack_id, user)`. Rewrite the `packs.py` / `progress.py` gates from status to ownership. Route params slug → `{pack_id}` on `/api/v1/packs/*` and `/api/v1/progress/packs/*`. Demote `slug` to nullable + partial unique index `WHERE slug IS NOT NULL`.
**AC:** a user sees global + own packs, not others'; requesting another user's pack by id → 404; progress on an unowned/foreign pack rejected; OpenAPI drift check updated.

#### HAB-063 — [BE] Remove admin subsystem
Deps: none (can land early in the PR).
Delete `dtos/admin.py`, `services/admin.py`, `routers/v1/admin.py`, `test_admin_api.py`; remove `admin_token` from `config.py` + `.env.example`; unwire from `app.py`; drop `WF-09` from `test_workflow_event_coverage.py`.
**AC:** `grep -ri admin_token src tests scripts` clean (except generated types, regenerated); no `/api/v1/admin/*` routes in OpenAPI; suite green.

#### HAB-064 — [FE] UUID pack addressing
Deps: HAB-062.
Regenerate `api-types.ts`; switch pack navigation/links/progress calls from slug to `pack_id`. Remove any admin-API surface if referenced.
**AC:** catalog + trace + progress flows work addressing by id; e2e green; no slug in pack routes.

#### HAB-065 — ADR: pack ownership & status removal
Deps: HAB-060–064.
Write `docs/adrs/00NN-pack-ownership.md`: two-tier ownership, UUID addressing, `PackStatus` removal, admin removal. Note it supersedes the `packs.status` forward-compat obligation in `tickets.md`.
**AC:** ADR merged; `tickets.md` scope note updated.

### Epic 7 — Agent pack generation (PR 2)

#### HAB-070 — [BE] pydantic-ai + provider config
Deps: HAB-062. Also revises ADR 0004 (HAB-076).
Add `pydantic-ai` dependency; provider/model + API-key settings in `config.py` (env-driven, no key in repo). No generation logic yet.
**AC:** `uv sync` resolves; app boots without a key configured (generation endpoint returns a clear "disabled" error, mirroring how admin returned 503 when unconfigured).

#### HAB-071 — [BE] Corpus-grounding tool + `PackDraft` schema
Deps: HAB-070, HAB-013 (`CharacterRepository.bulk_exists`).
Define `PackDraft` `output_type`. Implement the `find_characters` agent tool over `bulk_exists`, returning matches + the dropped set. Output validator rejects non-corpus hanzi.
**AC (unit, `TestModel`/`FunctionModel`, no network):** validator strips/errrors on a non-corpus hanzi and the model retries; tool returns only real rows; coverage shortfall surfaced in the draft.

#### HAB-072 — [BE] Generation service + injected agent
Deps: HAB-071.
`services/pack_generation.py` holding `Agent[GenerationDeps, PackDraft]`, exposed via FastAPI dependency `get_generation_agent`. Multi-turn: accept prior message history.
**AC:** service returns a valid `PackDraft` under a stubbed model; dependency is overridable in tests.

#### HAB-073 — [BE] Generation + save endpoints
Deps: HAB-072.
`routers/v1/generation.py`: a generate/chat endpoint (topic + history → draft) and a save endpoint (draft → persisted owned pack via `PackRepository.create(owner_id=current_user.id)`). Current-user gated; rate-limited. New workflow event for the generate/save actions.
**AC (integration, Postgres, stubbed model via `dependency_overrides`):** generate returns a corpus-valid draft; save persists pack + characters + sentences owned by the caller; saved pack then appears in that user's `list_visible` and is traceable; a second user cannot see it.

#### HAB-074 — [BE] `ALLOW_MODEL_REQUESTS=False` guard + external contract test
Deps: HAB-073.
Set `models.ALLOW_MODEL_REQUESTS = False` in shared conftest. Add one `@pytest.mark.external` test running the real provider against the real prompt + `output_type`.
**AC:** any un-stubbed model request in the normal suite raises; `just test-external` exercises the real call; PR CI (`just gate` + integration + e2e) makes zero real calls.

#### HAB-075 — [FE] Generation chat UI
Deps: HAB-073, HAB-064.
Chat surface: topic input, streamed/rendered draft preview, "make it harder"-style refinement turns carrying history, Save. Saved pack lands in the user's catalog.
**AC:** e2e (agent stubbed via dependency override) drives generate → refine → save → trace; deterministic, no network.

#### HAB-076 — ADR: revise 0004 (AI generation shipped)
Deps: HAB-070–075.
Supersede/amend ADR 0004: generation is no longer deferred; record corpus-grounding + private-by-ownership as the realized shape.
**AC:** ADR merged; 0004 marked superseded with a pointer.

---

### Open questions

- **Rate limiting / cost caps** — per-user generation quota? Out of scope to design here; HAB-073 assumes a simple per-user rate limit. Confirm the policy.
- **Provider choice** — which hosted model/provider for `config.py` (HAB-070)? Affects the external test and cost model.
- **Corpus coverage floor** — is a "found N of M" threshold below which we refuse to save a too-thin pack worth having? Currently we generate-and-report rather than refuse.
