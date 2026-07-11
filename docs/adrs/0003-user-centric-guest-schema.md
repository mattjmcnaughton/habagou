# ADR 0003: Use A User-Centric Guest Schema

## Status

Superseded in part by [ADR 0007](0007-session-cookie-oidc-auth.md).

## Context

v1 ships without login, but progress should not need a schema migration when
real accounts arrive.

## Decision

Model users from day one and resolve all v1 requests to a fixed seeded guest
user through `get_current_user`.

ADR 0007 replaces the resolver half of this decision with signed session-cookie
authentication. The user-centric schema decision remains in force.

## Consequences

- Progress, completions, request logs, and workflow events are already
  user-scoped.
- Adding authentication later can replace the resolver without changing the
  progress tables or public API shapes.
- The shared guest user makes production mutation tests unsafe; staging and
  local e2e can mutate, while production smoke stays read-only.
