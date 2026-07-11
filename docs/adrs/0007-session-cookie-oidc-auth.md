# ADR 0007: Session-Cookie OIDC Auth Replaces The Guest Resolver

## Status

Accepted.

## Context

ADR 0003 made progress data user-scoped before real authentication existed. The
remaining runtime behavior still resolved every request to a fixed seeded guest
user, which created a dev/prod fork in the most security-sensitive boundary.

## Decision

Use Authlib's Starlette integration with a configurable OIDC provider. Keycloak
is the local provider; Auth0 and other standards-compliant OIDC providers use
their discovery metadata. After the callback, Habagou provisions or loads a
`users` row by `(auth_issuer, auth_subject)` and stores the user id in
Starlette's signed session cookie.

All `/api/v1` data endpoints require that session. Health, readiness, auth
routes, and SPA static files remain open. Admin endpoints continue to use
`ADMIN_TOKEN`.

Guest access is removed from runtime code. Existing guest rows and progress are
left untouched; a later migration can clean up `users.is_guest` if needed.

## Consequences

- `get_current_user` remains the single resolver boundary, now backed by the
  signed session cookie.
- Integration tests mint real Starlette-compatible session cookies rather than
  bypassing auth.
- Local logout only clears Habagou's session. RP-initiated provider logout is
  deferred.
- A config-gated dev-login endpoint is the sanctioned fallback if browser e2e
  against Keycloak proves too slow or flaky, but it is deliberately not built now.
