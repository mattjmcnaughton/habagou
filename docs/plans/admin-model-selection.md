# Plan — Admin user class + AI model selection

**Status: executed** (see execution notes below). Self-contained
implementation plan for an implementing agent. Ordered tickets with
dependencies and acceptance criteria (AC), following the conventions of
[tickets.md](../tickets.md).

> **Execution notes.** Between planning and execution, main gained a second AI
> chat (conversational practice, ADR 0011) and a shared cached OpenRouter
> builder (`services/openrouter.py`). The implementation therefore covers
> **both** chats with one shared allowlist — `ADMIN_CHAT_MODELS` (not the
> planned `ADMIN_GENERATION_MODELS`) plus per-feature
> `generation_model_ids`/`practice_model_ids` (each feature's default model
> prepended) — and mirrors the status/`model`-override API shape onto
> `/api/v1/practice/status` and `/api/v1/practice/turn`. ADM-02's cache
> refactor was already done upstream; only labels and the override parameter
> were added. Everything else landed as planned.

Branch: `claude/admin-class-model-selection-ixgqf0`. Suggested commit split:
one commit for ADM-01 (admin class), one for ADM-02..ADM-05 (model selection),
docs folded into each.

## Product intent

1. Introduce an **admin** user class: any authenticated (non-guest) user whose
   email is on the `mattjmcnaughton.com` domain.
2. First admin-only capability: **choosing the AI model** used by the
   pack-generation chat (`/packs/generate`), instead of the single server-wide
   `GENERATION_MODEL`. Initial selectable models (OpenRouter IDs):
   - `anthropic/claude-sonnet-5` (Claude Sonnet 5)
   - `minimax/minimax-m3` (MiniMax M3)

   ⚠️ **Verify both slugs against OpenRouter before shipping** (e.g.
   `curl -s https://openrouter.ai/api/v1/models | jq -r '.data[].id' | grep -iE 'sonnet-5|minimax'`).
   If a slug differs, use OpenRouter's actual ID and keep the display label.
   Non-admins keep today's behavior exactly (server default model, no picker).

## Required reading for the implementing agent

- `CLAUDE.md` (gates, layering: routers → services → repositories; DTOs are
  Pydantic, separate from DB models)
- `docs/architecture.md`, `docs/auth.md`, `docs/api.md` (generation section)
- Code: `src/habagou/config.py`, `src/habagou/dependencies.py`,
  `src/habagou/routers/auth.py`, `src/habagou/routers/v1/generation.py`,
  `src/habagou/services/pack_generation.py`, `src/habagou/dtos/auth.py`,
  `src/habagou/dtos/generation.py`, frontend
  `src/habagou/web/frontend/src/routes/packs.generate.tsx`,
  `src/lib/api.ts`, `src/lib/generation-chat.ts`, `src/mocks/handlers.ts`

## Design decisions (already made — do not relitigate)

- **Admin is derived, not stored.** No DB column, no Alembic migration. A user
  is admin iff `not user.is_guest`, `user.email` is set, and the part after the
  final `@` case-insensitively equals a configured admin domain. `User.email`
  is refreshed from the IdP on every sign-in (`AuthService.sign_in`), so admin
  status self-heals. Exact domain match only — `notmattjmcnaughton.com` and
  subdomains must NOT match. (If per-user grants are ever needed, that is the
  moment to add a column; out of scope here.)
- **Model choice is per draft turn**, sent by the client in the `/draft` body.
  There is no server-side conversation store, so this mirrors the existing
  client-held-history design. Switching models mid-conversation is allowed —
  pydantic-ai binds the model per `agent.run` and history replay is
  model-agnostic (the only cost is losing provider prompt-cache hits).
- **Server-side enforcement.** The picker being hidden in the UI is cosmetic;
  the `/draft` endpoint must reject a `model` from a non-admin (403) and a
  model outside the allowlist (422 with an error message naming the allowed ids).
- **Admin-ness reaches the frontend two ways**: `is_admin` on the session DTO
  (general-purpose), and the generation status response carrying the model
  list only for admins (what the picker actually keys off).

---

## ADM-01 — [BE] Admin user classification

Deps: none.

- `src/habagou/config.py` — add to `Settings`:

  ```python
  # Comma-separated email domains whose (non-guest) users are admins.
  admin_email_domains: str = "mattjmcnaughton.com"
  ```

  Add a property `admin_email_domain_set: frozenset[str]` that splits on
  commas, strips whitespace, lowercases, and drops empties.
- New module `src/habagou/authz.py`:

  ```python
  def is_admin(user: User) -> bool
  ```

  Rules: `False` for guests (`user.is_guest`), `False` when `email` is `None`
  or contains no `@`; otherwise compare `email.rsplit("@", 1)[1].lower()`
  against `settings.admin_email_domain_set`. Import `settings` from
  `habagou.config` (module-level singleton, matching existing usage).
- `src/habagou/dtos/auth.py` — add `is_admin: bool = False` to `UserDTO`.
- `src/habagou/routers/auth.py` — populate `is_admin=is_admin(user)` in
  `get_auth_session`.
- `docs/auth.md` — add a short "Admin users" section: definition (email-domain
  derived, config `ADMIN_EMAIL_DOMAINS`, default `mattjmcnaughton.com`), the
  trust note (relies on the OIDC provider's `email` claim; both Keycloak and
  Auth0 are trusted for this), and that guests are never admins.
- `.env.example` — add `ADMIN_EMAIL_DOMAINS=mattjmcnaughton.com` beside the
  other auth vars.
- Tests (`tests/unit/test_authz.py`, plus extend
  `tests/integration/test_auth_api.py`):
  - unit: match (`x@mattjmcnaughton.com`), case-insensitive
    (`X@MATTJMCNAUGHTON.COM`), non-match (`x@example.com`), lookalike
    (`x@notmattjmcnaughton.com` → False), subdomain
    (`x@sub.mattjmcnaughton.com` → False), no email, email without `@`,
    guest with matching email → False, multi-domain config parsing.
  - integration: `GET /api/v1/auth/session` returns `is_admin: true` for a
    signed-in user with a matching email, `false` otherwise (see the existing
    session tests in `test_auth_api.py` for the sign-in fixture pattern).

**AC:** `just gate-be` green; session endpoint reports `is_admin`; no DB
migration added; `docs/auth.md` documents the rule.

## ADM-02 — [BE] Multi-model configuration & model construction

Deps: none (parallel with ADM-01).

- `src/habagou/config.py` — add:

  ```python
  # Comma-separated OpenRouter model ids admins may select for pack
  # generation, in display order. The server default (generation_model) is
  # always selectable and need not be listed.
  admin_generation_models: str = "anthropic/claude-sonnet-5,minimax/minimax-m3"
  ```

  Add property `generation_model_ids: tuple[str, ...]`: parsed
  `admin_generation_models` (split/strip/drop-empty, order-preserving,
  deduped) with `generation_model` prepended if not already present. This
  tuple IS the allowlist and the picker order (default first).
- `src/habagou/services/pack_generation.py`:
  - Change `_build_model()` → `_build_model(model_id: str | None = None)`.
    `None` falls back to `settings.generation_model`. Replace the single-slot
    cache with `dict[tuple[str, str], OpenAIChatModel]` keyed on
    `(resolved_model_id, settings.openrouter_api_key)` — each entry owns an
    httpx pool (see the existing cache comment), so cache per id. Keep the
    `GenerationNotConfiguredError` gate unchanged.
  - `generate_pack_draft(...)` gains keyword-only `model_id: str | None = None`,
    threads it to `_build_model`, and adds `model=resolved_model_id` to BOTH
    the `generation_run_completed` and `generation_run_failed` log events (so
    models can be compared in telemetry).
  - Add a display-label map near the allowlist consumer:

    ```python
    _MODEL_LABELS = {
        "anthropic/claude-sonnet-5": "Claude Sonnet 5",
        "minimax/minimax-m3": "MiniMax M3",
        "deepseek/deepseek-v4-flash": "DeepSeek v4 Flash",
    }
    def model_label(model_id: str) -> str  # falls back to the id itself
    ```
- Tests (extend `tests/unit/test_config.py` and
  `tests/unit/test_pack_generation.py`):
  - `generation_model_ids`: default prepended, dedupe when default is also
    listed, whitespace/empty-entry handling, ordering.
  - `_build_model`: distinct ids → distinct cached instances; same id twice →
    same instance; still raises `GenerationNotConfiguredError` when
    unconfigured. Follow the existing cache-reset pattern in
    `test_pack_generation.py` (tests there already poke the module-level
    cache; keep them isolated with a fixture that clears the dict).
  - `model_label` fallback.

**AC:** `just gate-be` green; no behavior change for callers that pass no
model id.

## ADM-03 — [BE] API surface: model on `/draft`, options on `/status`

Deps: ADM-01, ADM-02.

- `src/habagou/dtos/generation.py`:
  - `GenerationDraftRequestDTO` — add
    `model: Annotated[str, Field(min_length=1, max_length=200)] | None = None`
    with a docstring: admin-only, must be one of the server's selectable
    generation model ids, `None` = server default.
  - New `GenerationModelOptionDTO` with `id: str`, `label: str`.
  - `GenerationStatusDTO` — add
    `models: list[GenerationModelOptionDTO] | None = None` and
    `default_model: str | None = None`; document that both are populated only
    for admin callers (`None` for everyone else — the response gates the UI).
- `src/habagou/routers/v1/generation.py`:
  - `get_generation_status`: when `settings.generation_configured` and
    `is_admin(current_user)`, populate
    `models=[GenerationModelOptionDTO(id=i, label=model_label(i)) for i in settings.generation_model_ids]`
    and `default_model=settings.generation_model`.
  - `generate_draft`: inside the existing `workflow_event` block, after the
    rate-limiter acquire and alongside the history validation (matching the
    existing "caller error after quota" precedent):
    - `payload.model is not None and not is_admin(current_user)` → set
      `event.outcome = "error"`, raise 403 with detail
      `"model selection requires an admin account"`.
    - `payload.model not in settings.generation_model_ids` → 422 with detail
      naming the allowed ids.
    - Thread `model_id=payload.model` into `generate_pack_draft`.
    - Add `model=payload.model or settings.generation_model` to
      `event.fields` — then check
      `tests/integration/test_workflow_event_coverage.py`: if WF-15 asserts an
      exact field set for `pack_draft_generated`, add `model` there.
  - Document the new 403/422 in the route's `responses={...}` map.
- Regenerate the committed OpenAPI artifact (CI enforces drift via
  `just openapi-check`):

  ```
  just openapi-export   # rewrites docs/api/openapi-v1.json AND src/habagou/web/frontend/src/lib/api-types.ts
  ```

  Commit both regenerated files with this ticket.
- `docs/api.md` — generation section: add `model` to the `/draft` body docs
  (admin-only, allowlist, 403/422 behavior) and the `models`/`default_model`
  fields to the `/status` response docs.
- Integration tests (`tests/integration/test_generation_api.py`; reuse its
  existing agent-override/FunctionModel and sign-in fixtures; use an admin
  email fixture, e.g. `dev@mattjmcnaughton.com`, via the existing
  identity/sign-in helpers):
  - status: admin sees `models` (default first) + `default_model`; non-admin
    sees both `null`; unauthenticated stays 401.
  - draft: admin + allowlisted model → 200 (assert via a FunctionModel that
    the run executed; asserting the exact bound model id is optional — unit
    coverage in ADM-02 owns `_build_model` resolution); non-admin + model →
    403; admin + unknown model → 422; omitted model unchanged for both.
  - 403/422 model failures still consume rate-limit quota (matches history-422
    precedent) — assert or consciously document.

**AC:** `just gate-be` green; `just openapi-check` green (artifact + generated
types committed); `just test-integration` green including the new cases.

## ADM-04 — [FE] Model picker in the generation chat

Deps: ADM-03 (needs regenerated `api-types.ts`).

- `src/lib/api.ts` — `generateDraft(topic, history?, model?)`: include `model`
  in the typed request body (JSON.stringify drops `undefined`, matching the
  existing `history` comment). `GenerationStatus` picks up the new fields
  automatically from the regenerated `api-types.ts`.
- `src/routes/packs.generate.tsx`:
  - Add `useQuery({ queryKey: ["generation-status"], queryFn: getGenerationStatus })`
    (same key as `packs.index.tsx` so the cache is shared).
  - Local state: `const [model, setModel] = useState<string | undefined>()` —
    `undefined` means server default. `generation-chat.ts` needs **no changes**
    (model is per-request, not conversation state).
  - When `status.data?.models` is non-null with ≥ 2 entries, render a compact
    picker (chip row or `<select>`, styled like the existing composer chrome)
    adjacent to the composer, one option per `models` entry using `label`,
    default model preselected. Disable it while `busy` (mid-draft/save).
  - Thread the selection into BOTH `submitTopic` and `handleRetry` mutation
    calls (`generateDraft(topic, history, model)`). Never send `model` when the
    picker isn't rendered.
  - Non-admins and unconfigured servers see zero UI change.
- `src/mocks/handlers.ts` — default `/generation/status` handler keeps
  `models`/`default_model` null; add an admin-status variant handler
  (`models` with the three ids/labels) for tests.
- Frontend unit tests (`packs.generate.test.tsx`, `api.test.ts`, msw):
  - picker hidden when `models` is null; shown with admin status (labels
    rendered, default preselected).
  - selecting a model → POST `/generation/draft` body contains that `model`
    (capture via msw); no selection → body omits `model`; retry after a
    provider failure keeps the selected model.
  - `api.test.ts`: `generateDraft` includes/omits `model` correctly.
- e2e (`tests/e2e/generate-pack.spec.ts`): the dev Keycloak user is not on the
  admin domain, so assert the picker is absent in the existing flow (one
  locator assertion; do not build an admin e2e login unless one already
  exists).

**AC:** `just gate-fe` green; `just test-e2e-fe` green; non-admin UI is
pixel-identical to before.

## ADM-05 — Verification & handoff

Deps: ADM-01..ADM-04.

- Run the full gates, in order: `just gate`, `just openapi-check`,
  `just gate-expensive` (adds integration + browser e2e). All green.
- Optional (needs a real key + network): `just test-external` /
  `HABAGOU_ALLOW_EXTERNAL_MODEL_REQUESTS=1` smoke a real draft against each of
  the two new OpenRouter ids to confirm the slugs resolve — this is the check
  that catches a wrong model id, which no offline test can.
- Manual verification (see `docs/development.md` for env setup): with
  `OPENROUTER_API_KEY` set, sign in as a `@mattjmcnaughton.com` user → picker
  visible, drafts succeed per model; sign in as the dev user → no picker;
  `curl` the draft endpoint with `model` as a non-admin → 403.

**AC:** `just gate-expensive` green; both commits pushed to
`claude/admin-class-model-selection-ixgqf0`.

## Explicit non-goals

- No DB migration / stored roles, no admin management UI.
- No per-model rate limits or pricing display (the existing
  `generation_rate_limit_per_hour` applies unchanged).
- No model choice on `/generation/packs` (save) — saving is model-free.
- No changes to the pack-generation prompt, grounding, or corpus logic.
