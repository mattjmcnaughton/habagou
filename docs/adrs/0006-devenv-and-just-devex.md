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

- Humans get a Docker-free primary workflow after installing Nix/devenv.
- Agents can use Docker without installing Nix on the host.
- The app only depends on environment variables such as `DATABASE_URL`, so the
  same commands work against devenv, Compose, CI, staging, or production.
