# ADR 0009: Pack Ownership Replaces Pack Status

## Status

Accepted. Supersedes the `packs.status` forward-compat hook recorded in
[ADR 0004](0004-defer-ai-generation.md).

## Context

Epic 6 needed a mechanism for the upcoming Epic 7 agent to create packs on a
learner's behalf without exposing them to every other learner. `packs.status`
(`DRAFT` / `PUBLISHED` / `RETIRED`) was doing two unrelated jobs: filtering the
catalog to publishable content, and gating visibility for the not-yet-built
authoring path ADR 0004 anticipated. Neither job needs a status enum once
per-pack ownership exists — ownership alone determines both the catalog
listing and who may see a pack, and it additionally gives Epic 7 a concrete
place to attach agent-created packs (`owner_id`) instead of a `DRAFT` row
everyone can already query.

Keeping `status` alongside ownership would leave two overlapping gates to keep
in sync for no added expressiveness, so this ADR removes it rather than
layering ownership on top.

## Decision

Replace `PackStatus` with a nullable `Pack.owner_id` FK to `users.id`:

- **`owner_id IS NULL`** — a global, curated pack. Seed-managed, visible to
  every user, listed in the catalog and the Learning Path.
- **`owner_id = <user.id>`** — a private pack, visible only to its owner.
  Created via `PackRepository.create(owner_id=...)`, the write path the
  upcoming Epic 7 agent uses; not yet reachable from any current endpoint.

Visibility is exactly ownership: a pack is visible to a caller iff
`owner_id IS NULL OR owner_id = caller`. The catalog endpoint is
`PackRepository.list_visible` (global packs union the caller's own); a single
pack fetch is `get_visible`, same predicate. This collapses catalog filtering
and visibility gating into one SQL predicate instead of two independent
checks.

The Learning Path scheduler and the pack-based progress stats
(`packs_completed`, `packs_total` on `GET /api/v1/progress/summary`) stay
**global-only this epic**: both read `list_global_with_content`
(`owner_id IS NULL`), unchanged by the presence of owned packs. Whether owned
packs join the Path is an Epic 7 decision, made once there is a concrete
authoring flow to design against.

`PackStatus` and the `pack_status` Postgres enum are dropped along with the
`status` column; nothing reads or writes them.

Because ownership subsumes what a token-gated authoring surface would have
needed, the admin subsystem is removed end-to-end: the `admin_token`-protected
HTTP API, `AdminService`, admin DTOs, the `admin_token` config field, and the
WF-09 `admin_action` workflow event. Every remaining pack write is accounted
for without it: global packs are content-as-code, changed by editing the seed
and deploying; user packs are created by the owner-scoped agent write path.
No runtime actor needs a standing admin credential.

Pack addressing switches to UUID-only: all pack routes and request/response
bodies use `pack.id`. `slug` is demoted to a nullable seed key — a stable
label used only by the corpus seed pipeline to match curated content across
runs — via a partial unique index (`WHERE slug IS NOT NULL`), and it no longer
appears anywhere in the API surface (routes, DTOs, or the Path's
`PathPackDTO`). Ordering ties (`sort_order` collisions) now break on `id`
instead of `slug`.

## Consequences

- One ownership predicate replaces two independent gates (`status` filtering,
  a not-yet-built authoring visibility check); there is no way for the two to
  drift out of sync because there is only one.
- **Capability dropped: RETIRED soft-delete.** Removing a shipped global pack
  is now a real `DELETE`, cascading through completion history and path
  items, with no reversible intermediate state. Accepted because global
  content is seed-managed and versioned in the repo, and `RETIRED` was never
  exercised at runtime — re-seeding is the recovery path, not undo.
- Reverses ADR 0004's decision to preserve `packs.status` as the forward-compat
  hook for future AI generation: ownership, not status, turned out to be the
  mechanism that generation-adjacent work (Epic 7) actually needs. The corpus-
  in-Postgres half of ADR 0004 is unaffected.
- The admin token API, service, DTOs, config, and WF-09 event are gone; no
  standing credential exists for pack mutation. Any future need to curate
  global packs out-of-band goes through the seed pipeline and deploy, not a
  runtime endpoint.
- Callers must address packs by `pack.id` everywhere; `slug` is invisible
  outside the seed pipeline. Clients that stored or displayed a pack's slug
  (e.g. the Path's pack reference) now use `id`/`title` instead.
- Epic 7 still has to decide, and design against a real authoring flow before
  deciding, whether owned packs participate in the Learning Path — this ADR
  deliberately leaves the scheduler and progress stats global-only rather than
  guessing at that answer now.
