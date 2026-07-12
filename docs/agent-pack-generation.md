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

Each ticket is one logical change with its own AC; where two must land in the same commit to keep `just gate` green, that's stated in Deps. Numbers are contiguous within an epic but PRs merge per-epic.

### Epic 6 — Pack ownership cleanup (PR 1)

**Admin removal** (first — admin is the only runtime writer of non-`PUBLISHED` status, so it must go before status can be dropped).

#### HAB-060 — [BE] Remove admin HTTP API
Deps: none.
Delete `routers/v1/admin.py` and unregister the router in `app.py`. Delete `tests/integration/test_admin_api.py` in the same commit (its endpoints are gone).
**AC:** no `/api/v1/admin/*` routes in the OpenAPI schema; app boots; suite green.

#### HAB-061 — [BE] Remove admin service, DTOs, and config
Deps: HAB-060.
Delete `services/admin.py`, `dtos/admin.py`; remove `admin_token` from `config.py` and `.env.example`.
**AC:** `grep -rin admin_token src scripts` clean; `grep -rin AdminService src` clean; suite green.

#### HAB-062 — [BE] Retire the WF-09 admin workflow event
Deps: HAB-061.
Remove the `WF-09` admin_action expectation from `test_workflow_event_coverage.py` and any lingering event references.
**AC:** workflow-event coverage test passes without WF-09; no `WF-09`/`admin_action` references remain.

**Ownership column & write path.**

#### HAB-063 — [BE] Add `Pack.owner_id` column + migration
Deps: none.
Add nullable `owner_id` FK → `users.id` on `packs` (`NULL` = global). Alembic migration, clean downgrade, existing rows backfilled `NULL`. Add the ORM relationship. No behavior change yet.
**AC:** upgrade + downgrade clean; existing four packs are `owner_id IS NULL`; model round-trips a global and an owned pack.

#### HAB-064 — [BE] `PackRepository.create(owner_id=...)` write path
Deps: HAB-063.
Add a create method that persists a pack + its `PackCharacter`/`PackSentence` rows with an `owner_id` (mirrors the seed write path). Not yet wired to any endpoint.
**AC:** integration test creates an owned pack with characters + sentences and reads it back.

**Status removal** (gates must move to ownership *before* the column is dropped).

#### HAB-065 — [BE] Rewrite visibility gates from status → ownership
Deps: HAB-063.
In `packs.py` and `progress.py`, replace `status == PUBLISHED` checks with "global (`owner_id IS NULL`) or owned by caller". Status column stays for now.
**AC:** a user can view/trace global packs and their own; a foreign owned pack → 404; progress on a foreign pack rejected.

#### HAB-066 — [BE] `list_published` → `list_visible(user)`
Deps: HAB-065.
Rename/replace the catalog query to return global ∪ caller-owned packs. Update `PackService` + callers.
**AC:** catalog returns global + own, excludes other users' packs; existing catalog integration tests updated and green.

#### HAB-067 — [BE] Drop `status` column + `pack_status` enum + `PackStatus`
Deps: HAB-065, HAB-066, HAB-062 (last status writer gone).
Migration drops the column and the `pack_status` Postgres enum type (clean downgrade). Delete `PackStatus` from `models.py`; drop it from `__all__`; update `seed.py` to stop setting status.
**AC:** `grep -rn PackStatus src` clean; migration up/down clean; seed idempotent; suite green.

**UUID addressing & slug demotion.**

#### HAB-068 — [BE] Repository: address packs by id
Deps: HAB-063.
`get_by_slug` → `get_by_id(pack_id)`; add owner-scoped `get_visible(pack_id, user)`. Update `set_sort_order` and other slug-keyed methods that survive.
**AC:** repo fetches by id; `get_visible` returns global/own, `None` for foreign; unit/integration green.

#### HAB-069 — [BE] Route params slug → `{pack_id}`
Deps: HAB-068.
Change `/api/v1/packs/{pack_id}` and `/api/v1/progress/packs/{pack_id}` route params and handlers to UUID. Regenerate OpenAPI; update the drift check.
**AC:** endpoints resolve by id; foreign/unknown id → 404; OpenAPI drift check green.

#### HAB-070 — [BE] Demote `slug` to nullable seed key
Deps: HAB-069.
Migration: `slug` nullable + partial unique index `WHERE slug IS NOT NULL`. Confirm `seed.py` still upserts by slug and stays idempotent. Slug no longer appears in any route.
**AC:** migration up/down clean; seed re-run idempotent; a user pack with `slug IS NULL` persists; no slug in the API surface.

**Frontend & ADR.**

#### HAB-071 — [FE] Address packs by id
Deps: HAB-069.
Regenerate `api-types.ts`; switch pack navigation/links/progress calls from slug to `pack_id`. Confirm no hand-written admin-API references remain (only generated types referenced admin).
**AC:** catalog + trace + progress flows work by id; e2e green; no slug in pack routes.

#### HAB-072 — ADR: pack ownership & status removal
Deps: HAB-060–071.
Write `docs/adrs/00NN-pack-ownership.md`: two-tier ownership, UUID addressing, `PackStatus` removal, admin removal — one coherent decision. Note it supersedes the `packs.status` forward-compat obligation in `tickets.md`.
**AC:** ADR merged; `tickets.md` scope note updated.

### Epic 7 — Agent pack generation (PR 2)

**Foundations.**

#### HAB-073 — [BE] Add `pydantic-ai` dependency
Deps: HAB-066 (ownership visibility landed).
Add `pydantic-ai` to `pyproject.toml`; `uv lock`. No app code yet.
**AC:** `uv sync --frozen` resolves; import smoke test passes; `just gate` green.

#### HAB-074 — [BE] Provider/model/key config
Deps: HAB-073.
Add provider, model, and API-key settings to `config.py` (env-driven, no key in repo). A helper reports whether generation is configured.
**AC:** app boots with keys unset; the "configured?" helper returns false when unset, true when set; no secret committed.

#### HAB-075 — [BE] `PackDraft` output schema
Deps: HAB-073.
Define the `PackDraft` `output_type` DTO (title, characters[hanzi/pinyin/meaning], optional sentences, coverage note).
**AC:** schema validates a well-formed draft and rejects malformed input; unit test covers both.

**Grounding.**

#### HAB-076 — [BE] `find_characters` grounding tool
Deps: HAB-075, HAB-013 (`CharacterRepository.bulk_exists`).
Implement the agent tool over `bulk_exists`: given candidate hanzi, return real matches (with pinyin/meaning) plus the dropped set.
**AC (unit):** tool returns only corpus rows and surfaces the dropped candidates; no network.

#### HAB-077 — [BE] Output validator rejects non-corpus hanzi
Deps: HAB-075, HAB-076.
Add an `output_validator` on the agent that fails validation for any hanzi absent from `Character`, triggering a model retry.
**AC (unit, `FunctionModel`):** a draft containing a non-corpus hanzi is rejected and retried; a valid draft passes; no network.

**Service & endpoints.**

#### HAB-078 — [BE] Generation service + injected agent dependency
Deps: HAB-074, HAB-077.
`services/pack_generation.py` holding `Agent[GenerationDeps, PackDraft]` with the grounding tool + validator; exposed via FastAPI dependency `get_generation_agent`.
**AC:** service returns a valid `PackDraft` under `TestModel`; the dependency is overridable via `app.dependency_overrides`.

#### HAB-079 — [BE] Multi-turn message history
Deps: HAB-078.
Accept prior message history in the service so refinement turns ("make it harder") carry context; thread it through pydantic-ai.
**AC (unit):** a second turn with history produces a refined draft; history is passed to the model (asserted via `FunctionModel`).

#### HAB-080 — [BE] Generate/chat endpoint
Deps: HAB-079.
`routers/v1/generation.py` generate endpoint: `(topic, history) → PackDraft`. Current-user gated; returns the "disabled" error when generation is unconfigured (HAB-074).
**AC (integration, stubbed model):** returns a corpus-valid draft; unauthenticated → 401; unconfigured → clear disabled error.

#### HAB-081 — [BE] Save endpoint
Deps: HAB-080, HAB-064.
Save endpoint: `PackDraft → PackRepository.create(owner_id=current_user.id)`. Current-user gated.
**AC (integration):** save persists pack + characters + sentences owned by the caller; the pack then appears in that user's `list_visible` and is traceable; a second user cannot see it.

#### HAB-082 — [BE] Rate limit + generation workflow event
Deps: HAB-080, HAB-081.
Per-user rate limit on generate/save; emit a workflow event for both actions (new WF id).
**AC:** exceeding the limit → 429; workflow-event coverage test asserts the new event.

**Test infra & FE.**

#### HAB-083 — [BE] `ALLOW_MODEL_REQUESTS=False` guard
Deps: HAB-078.
Set `models.ALLOW_MODEL_REQUESTS = False` in the shared conftest.
**AC:** any un-stubbed model request anywhere in the normal suite raises; `just gate` + integration + e2e make zero real calls.

#### HAB-084 — [BE] External contract test
Deps: HAB-081, HAB-083.
One `@pytest.mark.external` test running the real provider against the real prompt + `output_type`, gated behind `just test-external` (not on PRs).
**AC:** `just test-external` exercises a real call and validates the schema; the test is excluded from `just gate`/integration/e2e.

#### HAB-085 — [FE] Chat scaffold + draft preview
Deps: HAB-080, HAB-071.
Chat surface: topic input, send, rendered draft preview (characters + coverage note).
**AC (e2e, agent stubbed):** entering a topic renders a draft; deterministic, no network.

#### HAB-086 — [FE] Refinement turns + Save
Deps: HAB-085, HAB-081.
History-carrying refinement turns and a Save action that lands the pack in the user's catalog.
**AC (e2e, agent stubbed):** generate → refine → save → the pack appears in the catalog and is traceable.

#### HAB-087 — ADR: revise 0004 (AI generation shipped)
Deps: HAB-073–086.
Supersede/amend ADR 0004: generation is no longer deferred; record corpus-grounding + private-by-ownership as the realized shape.
**AC:** ADR merged; 0004 marked superseded with a pointer.

---

### Open questions

- **Rate limiting / cost caps** — per-user generation quota? Out of scope to design here; HAB-073 assumes a simple per-user rate limit. Confirm the policy.
- **Provider choice** — which hosted model/provider for `config.py` (HAB-070)? Affects the external test and cost model.
- **Corpus coverage floor** — is a "found N of M" threshold below which we refuse to save a too-thin pack worth having? Currently we generate-and-report rather than refuse.
