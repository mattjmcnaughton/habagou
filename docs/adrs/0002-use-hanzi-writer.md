# ADR 0002: Use Hanzi Writer For Tracing

## Status

Accepted.

## Context

Stroke-order tracing needs quiz behavior, hints, per-stroke callbacks, and a
known-compatible stroke-data format. Building that canvas engine from scratch is
not necessary for v1.

## Decision

Use Hanzi Writer as the tracing engine and provide corpus data through a custom
`charDataLoader` that calls Habagou's API.

## Consequences

- The prototype's interaction model carries into production.
- Frontend tests can script completion through a controlled test event while the
  browser still renders the real writer component.
- The app remains coupled to Hanzi Writer's data shape, which is mitigated by the
  corpus import and API contract tests.
