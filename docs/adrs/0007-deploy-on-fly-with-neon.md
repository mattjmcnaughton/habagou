# ADR 0007: Deploy On Fly.io With Neon Postgres

## Status

Accepted.

## Context

Habagou previously targeted a Kubernetes + Helm + External Secrets + Tailscale
stack. For a low-traffic hobby app that operational burden was high relative to
value. The app is a single stateless container with env-driven config and
standard health probes; the stroke corpus and seed data live in Postgres, so no
persistent volume is required.

## Decision

- Host the app on Fly.io (public HTTP, scale-to-zero, Fly-managed TLS).
- Use Neon Free for Postgres under Neon project **`habagou`** (pooled endpoint
  over the public internet with SSL).
- Store secrets in `fly secrets` (no AWS Secrets Manager / External Secrets).
- Run migrations, corpus import, and seed once per deploy via Fly
  `release_command` (entrypoint gated on `RELEASE_COMMAND=1`); app machines set
  `HABAGOU_RUN_BOOTSTRAP=0`.
- Deploy continuously from the existing Release workflow: semantic-release →
  parallel GHCR publish + `flyctl deploy --remote-only` (Fly builds from the
  release tag; GHCR is retained as a published artifact, not the deploy source).
- Leave `OTEL_EXPORTER_OTLP_ENDPOINT` empty for now.

Update (2026-07-17): Logfire is now the production trace exporter when a
`LOGFIRE_TOKEN` secret is present. The generic OTLP endpoint remains an optional
fallback, but is no longer set to an empty value in `fly.toml`.

## Consequences

- Cutover and ongoing ops are documented in [deploy.md](../deploy.md).
- The Helm chart and its CI job are removed.
- Docker Compose remains for local prod-like verification.
- Cold starts from scale-to-zero and Neon idle wakeups are acceptable.
