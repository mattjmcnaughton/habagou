# ADR 0008: Review State As A Rebuildable Projection

## Status

Accepted. Documents an exception to [ADR 0005](0005-append-only-progress-events.md).

## Context

The Learning Path schedules spaced-repetition reviews per reviewable unit
`(user, pack, unit_type, unit_ref, activity)`. Choosing the next path item needs
each unit's current `reps`, `last_seen_at`, and `due_at`. [ADR 0005](0005-append-only-progress-events.md)
established that progress is stored as append-only completion events and
aggregated at read time. Recomputing every unit's ladder position by replaying
the whole `activity_completions` log on each `GET /path` does not fit the
read-time-aggregation pattern cheaply: the scheduler runs on the hot path and
needs indexed lookups by `due_at`, not a full-history scan per request.

## Decision

Keep the append-only completion event log as the single source of truth, and
maintain `review_states` as a **derived cache** — a projection over those events:

- On each path-item completion, within the same transaction that appends the
  `source='path'` completion event, apply the Leitner ladder to every reviewable
  unit in the item and upsert its `review_states` row (`reps += 1`,
  `due_at = completed_at + LADDER[...]`, `last_seen_at = completed_at`).
- `review_states` holds no information that is not derivable from the event log.
  It can be dropped and rebuilt in full by replaying `activity_completions` in
  `completed_at` order through the same pure ladder function. A unit test proves
  `replay(events) == table contents`.

This is the documented exception to ADR 0005's "aggregate at read time": review
state is materialized eagerly rather than aggregated on read.

## Consequences

- The scheduler reads current review state with indexed `due_at` lookups instead
  of replaying history on every request.
- Correctness still rests on the event log. If the projection is ever suspect, it
  is discarded and rebuilt from events; no ground-truth data lives only in the
  cache.
- Writes cost more: a completion now updates the projection transactionally in
  addition to appending the event. The two must move together — a partial write
  that appends the event without updating the projection is a bug, not a
  tolerated skew, and is recoverable by replay.
- The ladder logic lives in a pure module shared by the on-completion update and
  the rebuild path, so both produce identical state by construction.
