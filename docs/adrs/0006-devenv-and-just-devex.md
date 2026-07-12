# ADR 0006: Use Devenv For Toolchain And Database, Just For App Processes

## Status

Accepted.

## Context

Habagou development needs repeatable Python, Node, Postgres, and command tooling
while also supporting multiple local worktrees and agent development without
host-level Nix installs.

## Decision

Use devenv to pin the toolchain and run a per-checkout Postgres service. Use the
justfile as the interface for bootstrap, app processes, tests, Compose, smoke,
and verification commands. Agents use `Dockerfile.dev`, which installs Nix and
devenv inside the container.

## Consequences

- **Do not install Nix on the host solely for Habagou.** Prefer already-installed
  `uv` / `pnpm` / `just` plus Compose or other existing Postgres/Keycloak.
- devenv remains available for hermetic, multi-worktree local clusters when
  Nix/devenv is already present (including cloud-agent / `Dockerfile.dev`
  environments that ship it).
- The app only depends on environment variables such as `DATABASE_URL`, so the
  same commands work against devenv, Compose, CI, staging, or production.
