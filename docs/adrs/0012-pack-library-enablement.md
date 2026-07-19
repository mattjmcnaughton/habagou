# ADR 0012: Pack Library With Lazy Per-User Enablement

## Status

Accepted.

## Context

The catalog grew from four curated packs to a library of dozens (eventually
hundreds). Under the pre-library model, "global pack" conflated three things:
curated content, presence on every user's home bench, and membership in every
user's Learning Path curriculum. Seeding 50+ global packs would have flooded
both surfaces for every learner.

Two sub-decisions were needed: how a user's chosen subset of the library is
stored, and where library content comes from.

## Decision

**Enablement is a lazy per-user overlay.** A new `user_pack_settings` table
(`user_id`, `pack_id`, `enabled`, PK on the pair) stores only *explicit
overrides*. Absence of a row means "use the pack's default", which is the new
`packs.starter` flag. Effective enablement for a global pack is
`COALESCE(setting.enabled, packs.starter)`; owned packs are always enabled and
never have rows. The bench (`GET /api/v1/packs`) and the per-user Learning
Path curriculum filter on this expression.

**Starter packs are auto-enabled for everyone** — existing users, new users,
and guests — precisely because the overlay is lazy: no signup hook, no
backfill migration, no per-user writes. Disabling a starter pack writes
`enabled=false`; enabling a library pack writes `enabled=true`.

**Disable is the user action on curated packs; delete stays forbidden.**
Disabling prunes the user's never-completed path items for that pack (the
one documented exception to the append-only path queue — completed items and
their completion events are untouched) and leaves `activity_completions` and
`review_states` intact, so re-enabling resumes progress.

**Library content is build-time data, not runtime AI.** Curated packs live in
`data/packs/<category>/<slug>.json` plus `data/packs/categories.json`,
validated in the gate by `scripts/validate_pack_data.py` against the committed
corpus index (`data/corpus_index.txt`) and upserted idempotently by slug in
`scripts/seed.py`. The initial 50-pack library was authored offline by a
Claude subagent iterating against the validator, then human-reviewed as an
ordinary content diff. The runtime OpenRouter generation agent (ADR 0010)
remains only for user-initiated custom packs, which are owned, not global.

## Consequences

- No behavior change at cutover: the four original packs are the starter set,
  and lazy semantics enable them by default, so pre-library benches render
  identically.
- The seed pipeline never deletes packs; retiring library content users may
  have progress on is a deliberate manual operation.
- `user_pack_settings` rows cascade away with their user or pack.
- The library endpoint returns the whole catalog in one un-paginated response
  with slim rows (no progress aggregates). Revisit pagination or server-side
  search only if the catalog grows past several hundred packs.
- The stroke corpus can now be fetched from either of two sha-pinned mirrors
  (GitHub tag archive or the immutable npm registry tarball), keeping
  bootstrap working in sandboxes whose egress policy blocks GitHub downloads.
