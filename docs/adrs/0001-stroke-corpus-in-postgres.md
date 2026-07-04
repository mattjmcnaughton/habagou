# ADR 0001: Store Stroke Corpus In Postgres

## Status

Accepted.

## Context

Habagou needs Hanzi Writer stroke JSON for every pack character and every
sentence-only character. Loading that data from a CDN at runtime would make core
practice flows depend on a third-party service and would leave seed data
unvalidated.

## Decision

Import the pinned `hanzi-writer-data` corpus into the `characters` table during
`just bootstrap`, then serve stroke JSON through `/api/v1/characters/{hanzi}/strokes`.

## Consequences

- Seed/import can fail fast when curated packs reference missing characters.
- Production serves immutable stroke data from the same database as pack data.
- The app owns corpus availability; the tradeoff is a larger bootstrap step and
  a license propagation obligation for the derived data.
