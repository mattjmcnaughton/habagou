# ADR 0005: Store Progress As Append-Only Completion Events

## Status

Accepted.

## Context

The app needs to know whether a user completed trace, match, and sentence
activities, plus simple aggregates such as completion count and best duration.

## Decision

Record each completed activity in `activity_completions` and aggregate progress
at read time.

## Consequences

- Writes are simple and preserve history.
- Per-pack progress can derive completed status, counts, and best duration
  without mutable state rows.
- Read-time aggregation is acceptable at v1 scale; if later volumes require it,
  cached summaries can be added without losing the event log.
